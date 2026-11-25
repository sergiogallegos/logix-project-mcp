"""Serve user-selected saved projects over MCP stdio."""

import argparse
import asyncio
import json
import sys
from collections.abc import Iterable
from importlib.util import find_spec
from pathlib import Path
from typing import Annotated, Literal, NotRequired, TypedDict, cast, get_args
from xml.etree.ElementTree import Element, tostring

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations
from pydantic import AfterValidator, ConfigDict, Field, TypeAdapter, ValidationError

from .comparison import ComparisonReport, compare
from .export import ExportComponent, ExportedFile, export_saved_project, validate_filename
from .inventory import (
    ProjectInventory,
    RoutineSummary,
    TagSummary,
    component_entries,
    project_inventory,
    routine_summary,
    tag_summary,
)
from .project import (
    NativeSnapshotCache,
    ProjectErrorCode,
    ProjectFormat,
    ProjectReadError,
    ProjectSnapshot,
    read_project,
)
from .routines import RoutineInspection, inspect_routine
from .search import ProjectSearch, SearchKind, SearchMatch, SymbolKind, page
from .selection import ProjectSelection, SelectionId, SelectionResult, read_selection, validate_project_path

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
EXPORT_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
ERROR_KEY = "logix-project-mcp/error"
ERROR_SCHEMA_KEY = "logix-project-mcp/error-schema"
ToolErrorCode = ProjectErrorCode | Literal["invalid_arguments", "unknown_tool"]
SourceHash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SearchQuery = Annotated[str, Field(min_length=1, max_length=200, pattern=r"\S")]


class ToolArguments(TypedDict):
    __pydantic_config__ = ConfigDict(extra="forbid")


class ListTagsArguments(ToolArguments, total=False):
    program: str | None


class ReadRoutineArguments(ToolArguments):
    program: str
    routine: str


class SearchPageArguments(ToolArguments, total=False):
    limit: Annotated[int, Field(ge=1, le=200)]
    offset: Annotated[int, Field(ge=0, le=2_147_483_647)]
    expected_source_sha256: SourceHash | None
    expected_selection_id: SelectionId | None


class SearchArguments(SearchPageArguments):
    query: SearchQuery
    kind: NotRequired[SearchKind]
    program: NotRequired[str | None]


class ReferenceArguments(SearchPageArguments):
    name: SearchQuery
    kind: NotRequired[SymbolKind]
    program: NotRequired[str | None]


class ControllerComparisonScope(ToolArguments):
    kind: Literal["controller"]


class ProgramComparisonScope(ToolArguments):
    kind: Literal["program"]
    program: Annotated[str, Field(min_length=1, pattern=r"\S")]


ComparisonScope = ControllerComparisonScope | ProgramComparisonScope


class CompareArguments(ToolArguments, total=False):
    scope: ComparisonScope | None


class ExportArguments(ToolArguments):
    filename: Annotated[
        str, Field(pattern=r'^[^<>:"/\\|?*\x00-\x1f]+[.][lL]5[xXkK]$', max_length=255),
        AfterValidator(validate_filename),
    ]
    component: NotRequired[ExportComponent | None]


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


class Capabilities(SelectionResult):
    schema_version: Literal[1]
    project: ProjectIdentity | None
    formats: list[FormatCapability]
    read_only: bool
    platform: str
    rockwell_sdk_module_found: bool
    comparison_project: NotRequired[ProjectIdentity]
    selection_mode: NotRequired[Literal["shared"]]


class ProgramSummary(TypedDict):
    name: str | None
    routines: list[RoutineSummary]


class SnapshotResult(SelectionResult):
    source_sha256: SourceHash


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
    inspection: RoutineInspection


class SearchResult(SnapshotResult, ProjectIdentity):
    software_revision: str | None
    matches: list[SearchMatch]
    next_offset: int | None


class ComparisonSource(SnapshotResult, ProjectIdentity):
    controller: str | None
    software_revision: str | None


class ComparisonResult(ComparisonReport, SelectionResult):
    before: ComparisonSource
    after: ComparisonSource


def create_server(
    path: Path | None, compare_path: Path | None = None, export_dir: Path | None = None,
    selection_file: Path | None = None,
) -> Server:
    server = Server(
        "logix-project-mcp",
        instructions="Inspect the saved Studio 5000 project selected by the local engineer.",
    )
    project_read_lock = asyncio.Lock()
    native_cache = NativeSnapshotCache()

    def selected() -> ProjectSelection:
        if selection_file is not None:
            return read_selection(selection_file)
        assert path is not None
        return ProjectSelection(path)

    async def load(expected_selection_id: str | None = None) -> tuple[ProjectSelection, ProjectSnapshot]:
        async with project_read_lock:
            selection = selected()
            if expected_selection_id is not None and selection.selection_id != expected_selection_id:
                raise ProjectReadError("selection_changed", "The shared project selection changed. Start a new search page sequence.")
            return selection, await read_project(selection.path, native_cache)

    async def get_capabilities() -> Capabilities:
        """Report the selected file, supported formats, and inspection requirements."""
        try:
            selection = selected()
        except ProjectReadError as exc:
            if exc.code != "selection_required":
                raise
            selection = None
        capabilities: Capabilities = {
            "schema_version": 1,
            "project": project_identity(selection.path) if selection is not None else None,
            "formats": [
                {
                    "format": format_name,
                    "requires_windows": format_name != "l5x",
                    "requires_rockwell_sdk": format_name != "l5x",
                }
                for format_name in get_args(ProjectFormat)
            ],
            "read_only": export_dir is None,
            "platform": sys.platform,
            "rockwell_sdk_module_found": find_spec("logix_designer_sdk") is not None,
        }
        if selection_file is not None:
            capabilities["selection_mode"] = "shared"
            if selection is not None:
                capabilities.update(selection.identity())
        if compare_path is not None:
            capabilities["comparison_project"] = {
                "file": compare_path.name, "format": cast(ProjectFormat, compare_path.suffix[1:].lower()),
            }
        return capabilities

    async def get_project() -> ProjectSummary:
        """Get controller metadata and the programs and routines in the saved project."""
        selection, snapshot = await load()
        root, controller, fingerprint = snapshot
        return {
            **project_identity(selection.path),
            **selection.identity(snapshot),
            "source_sha256": fingerprint,
            "controller": controller.get("Name"),
            "processor_type": controller.get("ProcessorType"),
            "software_revision": root.get("SoftwareRevision"),
            "programs": [
                {
                    "name": program.get("Name"),
                    "routines": [
                        routine_summary(routine) for routine in component_entries(program, "Routines", "Routine")
                    ],
                }
                for program in controller.findall("Programs/Program")
            ],
        }

    async def get_inventory() -> InventoryResult:
        """Inventory the controller, scheduled programs, tags, modules, UDTs, and Add-On Instructions."""
        selection, snapshot = await load()
        root, controller, fingerprint = snapshot
        return {
            **project_identity(selection.path),
            **selection.identity(snapshot),
            "source_sha256": fingerprint,
            "software_revision": root.get("SoftwareRevision"),
            **project_inventory(controller),
        }

    async def list_tags(program: str | None = None) -> tuple[list[TextContent], TagsResult]:
        """List controller tags, or tags in the named program when provided."""
        selection, snapshot = await load()
        _, controller, fingerprint = snapshot
        scope = controller if program is None else find_named(controller.findall("Programs/Program"), "Program", program)
        tags = [tag_summary(tag) for tag in scope.findall("Tags/Tag")]
        content = [TextContent(type="text", text=json.dumps(tag, ensure_ascii=False, indent=2)) for tag in tags]
        return content, {"result": tags, "source_sha256": fingerprint, **selection.identity(snapshot)}

    async def read_routine(program: str, routine: str) -> tuple[list[TextContent], RoutineResult]:
        """Inspect saved routine logic, comments, and source protection in the named program."""
        selection, snapshot = await load()
        _, controller, fingerprint = snapshot
        selected_program = find_named(controller.findall("Programs/Program"), "Program", program)
        selected_routine = find_named(component_entries(selected_program, "Routines", "Routine"), "Routine", routine)
        inspection = inspect_routine(selected_program.get("Name"), selected_routine)
        xml = "" if inspection["status"] == "protected" else tostring(selected_routine, encoding="unicode").strip()
        return [TextContent(type="text", text=xml or inspection["message"] or "")], {
            "result": xml,
            "source_sha256": fingerprint,
            "inspection": inspection,
            **selection.identity(snapshot),
        }

    async def search_snapshot(expected_source_sha256: str | None, expected_selection_id: str | None) -> tuple[ProjectSelection, ProjectSnapshot]:
        selection, snapshot = await load(expected_selection_id)
        if expected_source_sha256 is not None and expected_source_sha256 != snapshot.source_sha256:
            raise ProjectReadError("project_changed", "The saved project has changed. Start a new search page sequence.")
        return selection, snapshot

    def search_result(selection: ProjectSelection, snapshot: ProjectSnapshot, results: tuple[list[SearchMatch], int | None]) -> SearchResult:
        matches, next_offset = results
        return {
            **project_identity(selection.path),
            **selection.identity(snapshot),
            "software_revision": snapshot.root.get("SoftwareRevision"),
            "source_sha256": snapshot.source_sha256,
            "matches": matches,
            "next_offset": next_offset,
        }

    async def search_project(
        query: str, kind: SearchKind = "all", program: str | None = None,
        limit: int = 50, offset: int = 0, expected_source_sha256: str | None = None,
        expected_selection_id: str | None = None,
    ) -> SearchResult:
        """Search scoped declarations, exact symbols, and comments in a saved project."""
        selection, snapshot = await search_snapshot(expected_source_sha256, expected_selection_id)
        if program is not None:
            selected = find_named(snapshot.controller.findall("Programs/Program"), "Program", program)
            program = selected.get("Name", program)
        results = await asyncio.to_thread(
            lambda: page(ProjectSearch(snapshot.controller).search(query.strip(), kind, program), offset, limit)
        )
        return search_result(selection, snapshot, results)

    async def find_references(
        name: str, kind: SymbolKind = "tag", program: str | None = None,
        limit: int = 50, offset: int = 0, expected_source_sha256: str | None = None,
        expected_selection_id: str | None = None,
    ) -> SearchResult:
        """Find saved source locations that refer to one declared symbol, including through aliases."""
        selection, snapshot = await search_snapshot(expected_source_sha256, expected_selection_id)
        results = await asyncio.to_thread(
            lambda: page(ProjectSearch(snapshot.controller).references(name.strip(), kind, program), offset, limit)
        )
        return search_result(selection, snapshot, results)

    async def compare_projects(scope: ComparisonScope | None = None) -> ComparisonResult:
        """Compare the selected baseline with the configured candidate saved project."""
        assert compare_path is not None
        async with project_read_lock:
            selection = selected()
            baseline = await read_project(selection.path, native_cache)
            candidate = baseline if selection.path == compare_path else await read_project(compare_path, native_cache)
        kind = scope["kind"] if scope else "all"
        program = scope["program"] if scope and scope["kind"] == "program" else None
        report = await asyncio.to_thread(compare, baseline.controller, candidate.controller, kind, program)
        return {"before": comparison_source(selection.path, baseline), "after": comparison_source(compare_path, candidate), **report, **selection.identity(baseline)}

    async def export_project(filename: str, component: ExportComponent | None = None) -> ExportedFile | CallToolResult:
        """Export the selected saved project or a component to a new file in the configured export directory."""
        assert export_dir is not None
        if component is not None:
            if Path(filename).suffix.lower() != ".l5x":
                return tool_error("invalid_arguments", "Choose an .L5X filename for a component export.")
            if component["kind"] == "rungs" and component["last"] < component["first"]:
                return tool_error("invalid_arguments", "The first rung number must be at most the last rung number.")
        async with project_read_lock:
            selection = selected()
            result = await export_saved_project(selection.path, export_dir, filename, component)
            result.update(selection.identity())
            return result

    error_schema = TypeAdapter(ToolErrorDetails).json_schema()
    tools = {}
    registrations = (
        (get_project, ToolArguments, ProjectSummary),
        (get_inventory, ToolArguments, InventoryResult),
        (list_tags, ListTagsArguments, TagsResult),
        (read_routine, ReadRoutineArguments, RoutineResult),
        (search_project, SearchArguments, SearchResult),
        (find_references, ReferenceArguments, SearchResult),
        (get_capabilities, ToolArguments, Capabilities),
    )
    if compare_path is not None:
        registrations += ((compare_projects, CompareArguments, ComparisonResult),)
    if export_dir is not None:
        registrations += ((export_project, ExportArguments, ExportedFile),)
    for handler, request_type, result_type in registrations:
        arguments = TypeAdapter(request_type)
        tool = Tool(
            name=handler.__name__,
            description=handler.__doc__,
            inputSchema=arguments.json_schema(),
            outputSchema=TypeAdapter(result_type).json_schema(),
            annotations=EXPORT_WRITE if handler is export_project else READ_ONLY,
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


def find_named(items: Iterable[Element], kind: str, name: str) -> Element:
    for item in items:
        if item.get("Name", "").casefold() == name.casefold():
            return item
    raise ProjectReadError("not_found", f"{kind} {name!r} was not found.")


def project_identity(path: Path) -> ProjectIdentity:
    return {"file": path.name, "format": cast(ProjectFormat, path.suffix[1:].lower())}


def comparison_source(path: Path, snapshot: ProjectSnapshot) -> ComparisonSource:
    return {
        **project_identity(path),
        "source_sha256": snapshot.source_sha256,
        "controller": snapshot.controller.get("Name"),
        "software_revision": snapshot.root.get("SoftwareRevision"),
    }


async def run_stdio(path: Path | None, compare_path: Path | None = None, export_dir: Path | None = None, selection_file: Path | None = None) -> None:
    server = create_server(path, compare_path, export_dir, selection_file)
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())


def selected_project(parser: argparse.ArgumentParser, option: str, path: Path) -> Path:
    try:
        return validate_project_path(path)
    except ProjectReadError as exc:
        parser.error(f"{option}: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a saved Studio 5000 project over MCP.")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--project", type=Path, help="Path to an ACD, L5K, or full L5X project")
    selection.add_argument("--selection-file", type=Path, help="Local JSON selection file updated by the project sharing helper")
    parser.add_argument("--compare-project", type=Path, help="Candidate saved project for offline comparison")
    parser.add_argument("--export-dir", type=Path, help="Existing directory where the server may create offline exports")
    args = parser.parse_args()
    path = selected_project(parser, "--project", args.project) if args.project else None
    selection_file = args.selection_file.resolve() if args.selection_file else None
    if selection_file is not None and selection_file.suffix.lower() != ".json":
        parser.error("--selection-file must select a .json file")
    compare_path = selected_project(parser, "--compare-project", args.compare_project) if args.compare_project else None
    export_dir = args.export_dir.resolve() if args.export_dir is not None else None
    if export_dir is not None and not export_dir.is_dir():
        parser.error("--export-dir must point to an existing directory")
    asyncio.run(run_stdio(path, compare_path, export_dir, selection_file))


if __name__ == "__main__":
    main()
