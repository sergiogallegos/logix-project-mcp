import asyncio
import hashlib
import json
import os
import sys
import unittest
from datetime import timedelta
from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonschema import validate
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT = b"""<RSLogix5000Content SoftwareRevision="38.00" TargetType="Controller">
  <Controller Name="Sample" ProcessorType="1756-L85E">
    <Tags><Tag Name="ControllerTag" DataType="DINT" /></Tags>
    <Programs><Program Name="MainProgram">
      <Tags><Tag Name="ProgramTag" DataType="BOOL" /></Tags>
      <Routines><Routine Name="MainRoutine" Type="RLL">
        <RLLContent><Rung Number="0"><Comment>Sample rung</Comment></Rung></RLLContent>
      </Routine></Routines>
    </Program></Programs>
  </Controller>
</RSLogix5000Content>"""
NATIVE_TEST_PROJECT = os.environ.get("LOGIX_PROJECT_MCP_TEST_PROJECT")


class StdioTests(unittest.IsolatedAsyncioTestCase):
    def assert_tool_error(self, result, code, error_schema):
        self.assertTrue(result.isError)
        self.assertIsNone(result.structuredContent)
        details = result.meta["logix-project-mcp/error"]
        validate(details, error_schema)
        self.assertEqual(set(details), {"code", "message"})
        self.assertEqual(details["code"], code)
        self.assertEqual(result.content[0].text, details["message"])

    async def test_export_creates_only_new_files_in_selected_directory(self):
        with TemporaryDirectory() as directory:
            home = Path(directory).resolve()
            project = home / "Sample.L5X"
            project.write_bytes(PROJECT)
            exports = home / "Reviewed exports"
            exports.mkdir()
            existing = exports / "Existing.L5X"
            existing.write_bytes(b"existing")
            unrelated = exports / "notes.txt"
            unrelated.write_bytes(b"notes")
            server = StdioServerParameters(
                command=sys.executable,
                args=["-m", "logix_project_mcp.server", "--project", str(project), "--export-dir", str(exports)],
            )

            async with stdio_client(server) as (reader, writer), ClientSession(reader, writer) as client:
                await client.initialize()
                tool = next(tool for tool in (await client.list_tools()).tools if tool.name == "export_project")
                self.assertFalse(tool.annotations.readOnlyHint)
                self.assertFalse(tool.annotations.destructiveHint)
                caps = await client.call_tool("get_capabilities")
                self.assertFalse(caps.structuredContent["read_only"])
                error_schema = tool.meta["logix-project-mcp/error-schema"]

                request = {"filename": "Project copy.L5X"}
                validate(request, tool.inputSchema)
                result = await client.call_tool(tool.name, request)
                self.assertFalse(result.isError, result.content)
                validate(result.structuredContent, tool.outputSchema)
                output = exports / request["filename"]
                self.assertEqual(result.structuredContent, {
                    "path": str(output), "format": "l5x", "component": None,
                    "source_sha256": hashlib.sha256(PROJECT).hexdigest(),
                })
                self.assertEqual(output.read_bytes(), PROJECT)

                for filename in ("../Elsewhere.L5X", r"C:\Elsewhere.L5X", "file:stream.L5X", "NUL.L5X", "project.ACD"):
                    with self.subTest(filename=filename):
                        error = await client.call_tool(tool.name, {"filename": filename})
                        self.assert_tool_error(error, "invalid_arguments", error_schema)
                routine = {"kind": "routine", "program": "MainProgram", "name": "MainRoutine"}
                error = await client.call_tool(tool.name, {"filename": "Wrong.L5K", "component": routine})
                self.assert_tool_error(error, "invalid_arguments", error_schema)
                error = await client.call_tool(tool.name, {
                    "filename": "Wrong.L5X",
                    "component": {"kind": "rungs", "program": "MainProgram", "routine": "MainRoutine", "first": 2, "last": 1},
                })
                self.assert_tool_error(error, "invalid_arguments", error_schema)
                for filename in (existing.name, output.name):
                    error = await client.call_tool(tool.name, {"filename": filename})
                    self.assert_tool_error(error, "destination_exists", error_schema)

                self.assertEqual(project.read_bytes(), PROJECT)
                invalid = b'<RSLogix5000Content TargetType="Routine"><Controller /></RSLogix5000Content>'
                project.write_bytes(invalid)
                error = await client.call_tool(tool.name, {"filename": "Invalid.L5X"})
                self.assert_tool_error(error, "invalid_project", error_schema)
                self.assertEqual(project.read_bytes(), invalid)
            self.assertEqual(existing.read_bytes(), b"existing")
            self.assertEqual(unrelated.read_bytes(), b"notes")
            self.assertEqual(output.read_bytes(), PROJECT)
            self.assertEqual(set(exports.iterdir()), {existing, unrelated, output})
            self.assertFalse((home / "Elsewhere.L5X").exists())

    async def test_inspect_selected_project_without_modifying_it(self):
        with TemporaryDirectory() as directory:
            project = Path(directory) / "Sample.L5X"
            project.write_bytes(PROJECT)
            server = StdioServerParameters(
                command=sys.executable,
                args=["-m", "logix_project_mcp.server", "--project", str(project)],
            )

            async with stdio_client(server) as (reader, writer), ClientSession(reader, writer) as client:
                self.assertIsNotNone((await client.initialize()).capabilities.tools)
                tools = {tool.name: tool for tool in (await client.list_tools()).tools}
                self.assertEqual(set(tools), {
                    "get_capabilities", "get_inventory", "get_project", "list_tags", "read_routine",
                    "search_project", "find_references",
                })
                error_schema = tools["get_project"].meta["logix-project-mcp/error-schema"]
                for tool in tools.values():
                    self.assertTrue(tool.annotations.readOnlyHint)
                    self.assertEqual(tool.meta["logix-project-mcp/error-schema"], error_schema)
                    self.assertFalse(tool.inputSchema["additionalProperties"])
                for name in ("get_inventory", "get_project", "list_tags", "read_routine", "search_project", "find_references"):
                    self.assertIn("source_sha256", tools[name].outputSchema["required"])
                self.assertEqual(tools["get_project"].inputSchema["properties"], {})
                self.assertEqual(tools["get_capabilities"].inputSchema["properties"], {})
                self.assertEqual(set(tools["list_tags"].inputSchema["properties"]), {"program"})
                self.assertFalse(tools["list_tags"].inputSchema.get("required"))
                self.assertEqual(set(tools["read_routine"].inputSchema["required"]), {"program", "routine"})
                schemas = {name: tool.outputSchema["properties"] for name, tool in tools.items()}
                self.assertEqual(schemas["list_tags"]["result"]["type"], "array")
                self.assertEqual(schemas["read_routine"]["result"]["type"], "string")

                capabilities = await client.call_tool("get_capabilities")
                self.assertFalse(capabilities.isError, capabilities.content)
                self.assertEqual(capabilities.structuredContent, {
                    "schema_version": 1,
                    "project": {"file": "Sample.L5X", "format": "l5x"},
                    "formats": [
                        {"format": name, "requires_windows": native, "requires_rockwell_sdk": native}
                        for name, native in [("acd", True), ("l5k", True), ("l5x", False)]
                    ],
                    "read_only": True,
                    "platform": sys.platform,
                    "rockwell_sdk_module_found": find_spec("logix_designer_sdk") is not None,
                })

                summary, tags, controller_tags, routine = await asyncio.gather(
                    client.call_tool("get_project"),
                    client.call_tool("list_tags", {"program": "mainprogram"}),
                    client.call_tool("list_tags", {"program": None}),
                    client.call_tool("read_routine", {"program": "MainProgram", "routine": "MainRoutine"}),
                )
                for read in (summary, tags, controller_tags, routine):
                    self.assertFalse(read.isError, read.content)
                    self.assertEqual(read.structuredContent["source_sha256"], hashlib.sha256(PROJECT).hexdigest())
                self.assertEqual(summary.structuredContent["controller"], "Sample")
                self.assertEqual(summary.structuredContent["file"], "Sample.L5X")
                self.assertEqual(summary.structuredContent["format"], "l5x")
                self.assertEqual(summary.structuredContent["software_revision"], "38.00")
                self.assertEqual(summary.structuredContent["programs"][0]["name"], "MainProgram")
                self.assertEqual(tags.structuredContent["result"][0]["name"], "ProgramTag")
                self.assertEqual(controller_tags.structuredContent["result"][0]["name"], "ControllerTag")
                self.assertEqual(json.loads(tags.content[0].text), tags.structuredContent["result"][0])
                self.assertIn("Sample rung", routine.structuredContent["result"])
                self.assertEqual(routine.content[0].text, routine.structuredContent["result"])
                self.assertEqual(project.read_bytes(), PROJECT)

                missing = await client.call_tool("list_tags", {"program": "Missing"})
                self.assert_tool_error(missing, "not_found", error_schema)
                missing_routine = await client.call_tool(
                    "read_routine", {"program": "MainProgram", "routine": "Missing"}
                )
                self.assert_tool_error(missing_routine, "not_found", error_schema)
                for name, arguments in (
                    ("read_routine", {"program": "MainProgram"}),
                    ("list_tags", {"program": 4}),
                    ("get_project", {"path": "Other.L5X"}),
                ):
                    with self.subTest(tool=name, arguments=arguments):
                        invalid = await client.call_tool(name, arguments)
                        self.assert_tool_error(invalid, "invalid_arguments", error_schema)
                unknown = await client.call_tool("missing_tool")
                self.assert_tool_error(unknown, "unknown_tool", error_schema)

                project.unlink()
                other = project.with_name("Other.L5X")
                other.write_bytes(PROJECT.replace(b'Name="Sample"', b'Name="Other"'))
                unavailable = await client.call_tool("get_project")
                self.assert_tool_error(unavailable, "project_unavailable", error_schema)
                self.assertIn("Could not read Sample.L5X", unavailable.content[0].text)
                capabilities_after_removal = await client.call_tool("get_capabilities")
                self.assertFalse(capabilities_after_removal.isError, capabilities_after_removal.content)
                self.assertEqual(capabilities_after_removal.structuredContent, capabilities.structuredContent)

                project.write_bytes(b"<RSLogix5000Content>")
                malformed = await client.call_tool("get_project")
                self.assert_tool_error(malformed, "invalid_project", error_schema)

                saved = PROJECT.replace(b'Name="Sample"', b'Name="Updated"')
                project.write_bytes(saved)
                refreshed = await client.call_tool("get_project")
                self.assertFalse(refreshed.isError, refreshed.content)
                self.assertEqual(refreshed.structuredContent["controller"], "Updated")
                self.assertEqual(refreshed.structuredContent["source_sha256"], hashlib.sha256(saved).hexdigest())
                self.assertEqual(project.read_bytes(), saved)

    @unittest.skipUnless(sys.platform == "win32" and NATIVE_TEST_PROJECT, "Windows SDK sample required")
    async def test_inspect_native_project_without_modifying_it(self):
        project = Path(NATIVE_TEST_PROJECT).resolve(strict=True)
        self.assertIn(project.suffix.lower(), {".acd", ".l5k"})
        with project.open("rb") as source:
            original = hashlib.file_digest(source, "sha256").digest()

        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "logix_project_mcp.server", "--project", str(project)],
            env=dict(os.environ),
        )

        try:
            async with (
                stdio_client(server) as (reader, writer),
                ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=100)) as client,
            ):
                await client.initialize()
                self.assertTrue((await client.list_tools()).tools)
                capabilities = await client.call_tool("get_capabilities")
                self.assertFalse(capabilities.isError, capabilities.content)
                self.assertEqual(capabilities.structuredContent["project"], {
                    "file": project.name, "format": project.suffix[1:].lower(),
                })
                self.assertTrue(capabilities.structuredContent["rockwell_sdk_module_found"])
                for _ in range(2):
                    summary = await client.call_tool("get_project")
                    self.assertFalse(summary.isError, summary.content)
                    self.assertTrue(summary.structuredContent["controller"])
                    self.assertTrue(summary.structuredContent["software_revision"])
                    self.assertEqual(summary.structuredContent["format"], project.suffix[1:].lower())
                    self.assertEqual(summary.structuredContent["source_sha256"], original.hex())
        finally:
            with project.open("rb") as source:
                self.assertEqual(hashlib.file_digest(source, "sha256").digest(), original)
