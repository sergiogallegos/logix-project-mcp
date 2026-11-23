"""Load a saved project into the XML representation used by the MCP tools."""

import asyncio
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree.ElementTree import Element, ParseError

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

PROJECT_EXTENSIONS = {".acd", ".l5k", ".l5x"}
SDK_TIMEOUT_SECONDS = 90


class ProjectReadError(Exception):
    """An expected project read failure with a message for the MCP client."""


async def read_project(path: Path) -> tuple[Element, Element]:
    """Return the L5X root and controller from the latest saved project."""
    try:
        if path.suffix.lower() == ".l5x":
            root = parse_l5x(path)
        else:
            root = await export_saved_project(path)
    except (OSError, ParseError, DefusedXmlException) as exc:
        raise ProjectReadError(f"Could not read {path.name}: {exc}") from exc

    controller = root.find("Controller")
    if root.tag != "RSLogix5000Content" or controller is None:
        raise ProjectReadError("Expected a Logix Designer project with a controller.")
    if root.get("TargetType", "Controller") != "Controller":
        raise ProjectReadError("Select a full project export to inspect its controller.")
    return root, controller


def parse_l5x(path: Path) -> Element:
    return ElementTree.parse(path, forbid_dtd=True).getroot()


async def export_saved_project(path: Path) -> Element:
    if sys.platform != "win32":
        raise ProjectReadError("ACD and L5K inspection requires the Rockwell SDK on Windows.")

    with TemporaryDirectory(prefix="logix-project-mcp-") as directory:
        snapshot = Path(directory) / f"source{path.suffix}"
        output = Path(directory) / "snapshot.L5X"
        shutil.copyfile(path, snapshot)

        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "logix_project_mcp._sdk_worker", str(snapshot), str(output),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, diagnostic = await asyncio.wait_for(process.communicate(), SDK_TIMEOUT_SECONDS)
        except TimeoutError as exc:
            raise ProjectReadError(
                f"Logix Designer SDK did not finish exporting {path.name} "
                f"within {SDK_TIMEOUT_SECONDS} seconds."
            ) from exc
        finally:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()

        if process.returncode:
            detail = diagnostic.decode("utf-8", errors="replace").strip()
            raise ProjectReadError(f"Logix Designer SDK could not export {path.name}: {detail}")

        return parse_l5x(output)
