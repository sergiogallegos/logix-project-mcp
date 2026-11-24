"""Serve one user-selected, saved project over MCP stdio."""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Annotated, TypedDict
from xml.etree.ElementTree import Element, tostring

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from .project import PROJECT_EXTENSIONS, ProjectReadError, ProjectSnapshot, read_project

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)


class RoutineSummary(TypedDict):
    name: str | None
    type: str | None


class ProgramSummary(TypedDict):
    name: str | None
    routines: list[RoutineSummary]


class SnapshotResult(TypedDict):
    source_sha256: str


class ProjectSummary(SnapshotResult):
    file: str
    controller: str | None
    processor_type: str | None
    software_revision: str | None
    programs: list[ProgramSummary]


class TagsResult(SnapshotResult):
    result: list[dict]


class RoutineResult(SnapshotResult):
    result: str


def create_server(path: Path) -> FastMCP:
    server = FastMCP(
        "logix-project-mcp",
        instructions="Inspect the saved Studio 5000 project selected at server startup.",
    )
    project_read_lock = asyncio.Lock()

    async def load() -> ProjectSnapshot:
        try:
            async with project_read_lock:
                return await read_project(path)
        except ProjectReadError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(annotations=READ_ONLY)
    async def get_project() -> ProjectSummary:
        """Get controller metadata and the programs and routines in the saved project."""
        root, controller, fingerprint = await load()
        return {
            "file": path.name,
            "source_sha256": fingerprint,
            "controller": controller.get("Name"),
            "processor_type": controller.get("ProcessorType"),
            "software_revision": root.get("SoftwareRevision"),
            "programs": [
                {
                    "name": program.get("Name"),
                    "routines": [
                        {"name": routine.get("Name"), "type": routine.get("Type")}
                        for routine in program.findall("Routines/Routine")
                    ],
                }
                for program in controller.findall("Programs/Program")
            ],
        }

    @server.tool(annotations=READ_ONLY)
    async def list_tags(program: str | None = None) -> Annotated[CallToolResult, TagsResult]:
        """List controller tags, or tags in the named program when provided."""
        _, controller, fingerprint = await load()
        scope = controller if program is None else find_named(controller, "Programs/Program", program)
        tags = [
            {
                "name": tag.get("Name"),
                "data_type": tag.get("DataType"),
                "description": tag.findtext("Description"),
            }
            for tag in scope.findall("Tags/Tag")
        ]
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(tag, ensure_ascii=False, indent=2)) for tag in tags],
            structuredContent={"result": tags, "source_sha256": fingerprint},
        )

    @server.tool(annotations=READ_ONLY)
    async def read_routine(program: str, routine: str) -> Annotated[CallToolResult, RoutineResult]:
        """Read the L5X for a routine in the named program, including logic and comments."""
        _, controller, fingerprint = await load()
        selected_program = find_named(controller, "Programs/Program", program)
        selected_routine = find_named(selected_program, "Routines/Routine", routine)
        xml = tostring(selected_routine, encoding="unicode").strip()
        return CallToolResult(
            content=[TextContent(type="text", text=xml)],
            structuredContent={"result": xml, "source_sha256": fingerprint},
        )

    return server


def find_named(parent: Element, selector: str, name: str) -> Element:
    for item in parent.findall(selector):
        if item.get("Name", "").casefold() == name.casefold():
            return item
    raise ToolError(f"{selector.rsplit('/', 1)[-1]} {name!r} was not found.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a saved Studio 5000 project over MCP.")
    parser.add_argument("--project", required=True, type=Path, help="Path to an ACD, L5K, or full L5X project")
    args = parser.parse_args()
    path = args.project.resolve()

    if path.suffix.lower() not in PROJECT_EXTENSIONS or not path.is_file():
        parser.error("--project must point to an existing .ACD, .L5K, or .L5X file")

    create_server(path).run(transport="stdio")


if __name__ == "__main__":
    main()
