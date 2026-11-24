"""Publish offline Logix exports from a verified copy of the selected project."""

import asyncio
import ntpath
import os
import stat
import sys
from pathlib import Path, PureWindowsPath
from tempfile import TemporaryDirectory
from typing import Annotated, Literal, TypedDict, cast
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException
from pydantic import ConfigDict, Field

from .project import (
    ProjectReadError,
    controller_from_l5x,
    export_snapshot,
    finish_file_operation,
    parse_l5x,
    snapshot_source,
)

LogixName = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=40)]
RungNumber = Annotated[int, Field(ge=0, le=2_147_483_647)]
ExportFormat = Literal["l5x", "l5k"]


class NamedComponent(TypedDict):
    __pydantic_config__ = ConfigDict(extra="forbid")

    kind: Literal["program", "data_type", "add_on_instruction"]
    name: LogixName


class RoutineComponent(TypedDict):
    __pydantic_config__ = ConfigDict(extra="forbid")

    kind: Literal["routine"]
    program: LogixName
    name: LogixName


class RungsComponent(TypedDict):
    __pydantic_config__ = ConfigDict(extra="forbid")

    kind: Literal["rungs"]
    program: LogixName
    routine: LogixName
    first: RungNumber
    last: RungNumber


ExportComponent = Annotated[NamedComponent | RoutineComponent | RungsComponent, Field(discriminator="kind")]


class ExportedFile(TypedDict):
    path: str
    format: ExportFormat
    component: ExportComponent | None
    source_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


NAMED_TARGETS = {
    "program": ("Programs", "Program"),
    "data_type": ("DataTypes", "DataType"),
    "add_on_instruction": ("AddOnInstructionDefinitions", "AddOnInstructionDefinition"),
}


def validate_filename(filename: str) -> str:
    is_reserved = getattr(ntpath, "isreserved", None)
    reserved = is_reserved(filename) if is_reserved else PureWindowsPath(filename).is_reserved()
    if reserved:
        raise ValueError("Choose a filename that Windows can create.")
    return filename


def component_xpath(component: ExportComponent) -> str:
    kind = component["kind"]
    if kind in ("routine", "rungs"):
        program = f"Controller/Programs/Program[@Name='{component['program']}']"
        if kind == "routine":
            return f"{program}/Routines/Routine[@Name='{component['name']}']"
        return (
            f"{program}/Routines/Routine[@Name='{component['routine']}']/RLLContent/"
            f"Rung[@Number>='{component['first']}'][@Number<='{component['last']}']"
        )
    collection, element = NAMED_TARGETS[kind]
    return f"Controller/{collection}/{element}[@Name='{component['name']}']"


def validate_artifact(output: Path, component: ExportComponent | None) -> None:
    info = output.lstat()
    if not stat.S_ISREG(info.st_mode) or not info.st_size:
        raise ProjectReadError("export_failed", "The SDK did not produce a regular, nonempty export file.")
    if output.suffix.lower() == ".l5k":
        return

    root = parse_l5x(output)
    if component is None:
        controller_from_l5x(root)
        return
    kind = component["kind"]
    if kind == "rungs":
        rungs = "./Controller/Programs/Program/Routines/Routine/RLLContent/Rung[@Use='Target']"
        target = root.get("TargetType") == "Rung" and root.find(rungs) is not None
    else:
        element = "Routine" if kind == "routine" else NAMED_TARGETS[kind][1]
        name = root.get("TargetName", "")
        target = root.get("TargetType") == element and name.casefold() == component["name"].casefold()
    if root.tag != "RSLogix5000Content" or root.find("Controller") is None or not target:
        raise ProjectReadError("export_failed", "The SDK output does not contain the requested Logix component.")


async def export_saved_project(
    source: Path, directory: Path, filename: str, component: ExportComponent | None,
) -> ExportedFile:
    destination = directory / filename
    extension = destination.suffix.lower()
    source_is_l5x = source.suffix.lower() == ".l5x"
    copy_l5x = source_is_l5x and extension == ".l5x" and component is None
    if os.path.lexists(destination):
        raise ProjectReadError("destination_exists", f"{filename} already exists in the selected export directory.")
    if not copy_l5x and sys.platform != "win32":
        raise ProjectReadError("unsupported_platform", "This export requires the Rockwell SDK on Windows.")

    try:
        with TemporaryDirectory(prefix=".logix-export-", dir=directory) as temporary:
            output = Path(temporary) / f"output{extension.upper()}"
            snapshot = output if copy_l5x else Path(temporary) / f"source{source.suffix}"
            fingerprint = await snapshot_source(source, snapshot)
            if source_is_l5x:
                try:
                    root = await finish_file_operation(asyncio.to_thread(parse_l5x, snapshot))
                    controller_from_l5x(root)
                except (ParseError, DefusedXmlException) as exc:
                    raise ProjectReadError("invalid_project", f"Could not read {source.name}: {exc}") from exc
            if not copy_l5x:
                selector = component_xpath(component) if component is not None else None
                await export_snapshot(snapshot, output, source.name, selector)
                try:
                    await finish_file_operation(asyncio.to_thread(validate_artifact, output, component))
                except (ParseError, DefusedXmlException, OSError) as exc:
                    raise ProjectReadError("export_failed", "The SDK output is missing or could not be read.") from exc
                except ProjectReadError as exc:
                    raise ProjectReadError("export_failed", str(exc)) from exc
            try:
                # Windows rename and POSIX link both fail atomically if the destination exists.
                if os.name == "nt":
                    os.rename(output, destination)
                else:
                    os.link(output, destination)
            except FileExistsError as exc:
                raise ProjectReadError(
                    "destination_exists", f"{filename} already exists in the selected export directory."
                ) from exc
    except OSError as exc:
        raise ProjectReadError("export_failed", f"Could not export {filename}: {exc}") from exc

    return {
        "path": str(destination),
        "format": cast(ExportFormat, extension[1:]),
        "component": component,
        "source_sha256": fingerprint,
    }
