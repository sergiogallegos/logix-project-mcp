"""Serve one user-selected, saved project over MCP stdio."""

import argparse
import asyncio
import json
import sys
from importlib.util import find_spec
from pathlib import Path
from typing import Annotated, Literal, TypedDict, cast, get_args
from xml.etree.ElementTree import Element, tostring

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations
from pydantic import ConfigDict, Field, TypeAdapter, ValidationError

from .inventory import (
    ProjectInventory,
    RoutineSummary,
    TagSummary,
    project_inventory,
    routine_summary,
    tag_summary,
)
from .project import (
    PROJECT_EXTENSIONS,
    ProjectErrorCode,
    ProjectFormat,
    ProjectReadError,
    ProjectSnapshot,
    read_project,
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
ERROR_KEY = "logix-project-mcp/error"
ERROR_SCHEMA_KEY = "logix-project-mcp/error-schema"
ToolErrorCode = ProjectErrorCode | Literal["invalid_arguments", "unknown_tool"]


class ToolArguments(TypedDict):
    __pydantic_config__ = ConfigDict(extra="forbid")


class ListTagsArguments(ToolArguments, total=False):
    program: str | None


class ReadRoutineArguments(ToolArguments):
    program: str
    routine: str


class ToolErrorDetails(TypedDict):
    code: ToolErrorCode
    message: str


class ProjectIdentity(TypedDict):
    file: str
    format: ProjectFormat


class FormatCapability(TypedDict):
    format: ProjectFormat
    requires_windows: bool
    requires_rockwell_sdk: bool


class Capabilities(TypedDict):
    schema_version: Literal[1]
    project: ProjectIdentity
    formats: list[FormatCapability]
    read_only: Literal[True]
    platform: str
    rockwell_sdk_module_found: bool


class ProgramSummary(TypedDict):
    name: str | None
    routines: list[RoutineSummary]


class SnapshotResult(TypedDict):
    source_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class ProjectSummary(SnapshotResult, ProjectIdentity):
    controller: str | None
    processor_type: str | None
    software_revision: str | None
    programs: list[ProgramSummary]


class InventoryResult(SnapshotResult, ProjectIdentity, ProjectInventory):
    software_revision: str | None


class TagsResult(SnapshotResult):
    result: list[TagSummary]


class RoutineResult(SnapshotResult):
    result: str


def create_server(path: Path) -> Server:
    server = Server(
        "logix-project-mcp",
        instructions="Inspect the saved Studio 5000 project selected at server startup.",
    )
    project_read_lock = asyncio.Lock()
    project_format = cast(ProjectFormat, path.suffix[1:].lower())

    async def load() -> ProjectSnapshot:
        async with project_read_lock:
            return await read_project(path)

    async def get_capabilities() -> Capabilities:
        """Report the selected file, supported formats, and inspection requirements."""
        return {
            "schema_version": 1,
            "project": {"file": path.name, "format": project_format},
            "formats": [
                {
                    "format": format_name,
                    "requires_windows": format_name != "l5x",
                    "requires_rockwell_sdk": format_name != "l5x",
                }
                for format_name in get_args(ProjectFormat)
            ],
            "read_only": True,
            "platform": sys.platform,
            "rockwell_sdk_module_found": find_spec("logix_designer_sdk") is not None,
        }

    async def get_project() -> ProjectSummary:
        """Get controller metadata and the programs and routines in the saved project."""
        root, controller, fingerprint = await load()
        return {
            "file": path.name,
            "format": project_format,
            "source_sha256": fingerprint,
            "controller": controller.get("Name"),
            "processor_type": controller.get("ProcessorType"),
            "software_revision": root.get("SoftwareRevision"),
            "programs": [
                {
                    "name": program.get("Name"),
                    "routines": [routine_summary(routine) for routine in program.findall("Routines/Routine")],
                }
                for program in controller.findall("Programs/Program")
            ],
        }

    async def get_inventory() -> InventoryResult:
        """Inventory the controller, scheduled programs, tags, modules, UDTs, and Add-On Instructions."""
        root, controller, fingerprint = await load()
        return {
            "file": path.name,
            "format": project_format,
            "source_sha256": fingerprint,
            "software_revision": root.get("SoftwareRevision"),
            **project_inventory(controller),
        }

    async def list_tags(program: str | None = None) -> tuple[list[TextContent], TagsResult]:
        """List controller tags, or tags in the named program when provided."""
        _, controller, fingerprint = await load()
        scope = controller if program is None else find_named(controller, "Programs/Program", program)
        tags = [tag_summary(tag) for tag in scope.findall("Tags/Tag")]
        content = [TextContent(type="text", text=json.dumps(tag, ensure_ascii=False, indent=2)) for tag in tags]
        return content, {"result": tags, "source_sha256": fingerprint}

    async def read_routine(program: str, routine: str) -> tuple[list[TextContent], RoutineResult]:
        """Read the L5X for a routine in the named program, including logic and comments."""
        _, controller, fingerprint = await load()
        selected_program = find_named(controller, "Programs/Program", program)
        selected_routine = find_named(selected_program, "Routines/Routine", routine)
        xml = tostring(selected_routine, encoding="unicode").strip()
        return [TextContent(type="text", text=xml)], {"result": xml, "source_sha256": fingerprint}

    error_schema = TypeAdapter(ToolErrorDetails).json_schema()
    tools = {}
    for handler, request_type, result_type in (
        (get_project, ToolArguments, ProjectSummary),
        (get_inventory, ToolArguments, InventoryResult),
        (list_tags, ListTagsArguments, TagsResult),
        (read_routine, ReadRoutineArguments, RoutineResult),
        (get_capabilities, ToolArguments, Capabilities),
    ):
        arguments = TypeAdapter(request_type)
        tool = Tool(
            name=handler.__name__,
            description=handler.__doc__,
            inputSchema=arguments.json_schema(),
            outputSchema=TypeAdapter(result_type).json_schema(),
            annotations=READ_ONLY,
            _meta={ERROR_SCHEMA_KEY: error_schema},
        )
        tools[tool.name] = tool, arguments, handler

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [tool for tool, _, _ in tools.values()]

    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict):
        if name not in tools:
            return tool_error("unknown_tool", f"Unknown tool: {name}")
        _, request, handler = tools[name]
        try:
            parameters = request.validate_python(arguments, strict=True)
        except ValidationError as exc:
            fields = ", ".join(".".join(map(str, error["loc"])) for error in exc.errors(include_input=False))
            return tool_error("invalid_arguments", f"Check the input schema for {name} and correct {fields}.")
        try:
            return await handler(**parameters)
        except ProjectReadError as exc:
            return tool_error(exc.code, str(exc))

    return server


def tool_error(code: ToolErrorCode, message: str) -> CallToolResult:
    details: ToolErrorDetails = {"code": code, "message": message}
    return CallToolResult(
        isError=True,
        content=[TextContent(type="text", text=message)],
        _meta={ERROR_KEY: details},
    )


def find_named(parent: Element, selector: str, name: str) -> Element:
    for item in parent.findall(selector):
        if item.get("Name", "").casefold() == name.casefold():
            return item
    raise ProjectReadError("not_found", f"{selector.rsplit('/', 1)[-1]} {name!r} was not found.")


async def run_stdio(path: Path) -> None:
    server = create_server(path)
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a saved Studio 5000 project over MCP.")
    parser.add_argument("--project", required=True, type=Path, help="Path to an ACD, L5K, or full L5X project")
    args = parser.parse_args()
    path = args.project.resolve()

    if path.suffix.lower() not in PROJECT_EXTENSIONS or not path.is_file():
        parser.error("--project must point to an existing .ACD, .L5K, or .L5X file")

    asyncio.run(run_stdio(path))


if __name__ == "__main__":
    main()
