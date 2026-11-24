import asyncio
import hashlib
import json
import os
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

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
    async def test_inspect_selected_project_without_modifying_it(self):
        with TemporaryDirectory() as directory:
            project = Path(directory) / "Sample.L5X"
            project.write_bytes(PROJECT)
            server = StdioServerParameters(
                command=sys.executable,
                args=["-m", "logix_project_mcp.server", "--project", str(project)],
            )

            async with stdio_client(server) as (reader, writer), ClientSession(reader, writer) as client:
                await client.initialize()
                tools = (await client.list_tools()).tools
                self.assertEqual({tool.name for tool in tools}, {"get_project", "list_tags", "read_routine"})
                for tool in tools:
                    self.assertIn("source_sha256", tool.outputSchema["required"])
                schemas = {tool.name: tool.outputSchema["properties"] for tool in tools}
                self.assertEqual(schemas["list_tags"]["result"]["type"], "array")
                self.assertEqual(schemas["read_routine"]["result"]["type"], "string")

                summary, tags, controller_tags, routine = await asyncio.gather(
                    client.call_tool("get_project"),
                    client.call_tool("list_tags", {"program": "MainProgram"}),
                    client.call_tool("list_tags"),
                    client.call_tool("read_routine", {"program": "MainProgram", "routine": "MainRoutine"}),
                )
                for read in (summary, tags, controller_tags, routine):
                    self.assertFalse(read.isError, read.content)
                    self.assertEqual(read.structuredContent["source_sha256"], hashlib.sha256(PROJECT).hexdigest())
                self.assertEqual(summary.structuredContent["controller"], "Sample")
                self.assertEqual(summary.structuredContent["programs"][0]["name"], "MainProgram")
                self.assertEqual(tags.structuredContent["result"][0]["name"], "ProgramTag")
                self.assertEqual(controller_tags.structuredContent["result"][0]["name"], "ControllerTag")
                self.assertEqual(json.loads(tags.content[0].text), tags.structuredContent["result"][0])
                self.assertIn("Sample rung", routine.structuredContent["result"])
                self.assertEqual(routine.content[0].text, routine.structuredContent["result"])
                self.assertEqual(project.read_bytes(), PROJECT)

                missing = await client.call_tool("list_tags", {"program": "Missing"})
                self.assertTrue(missing.isError)

                project.unlink()
                other = project.with_name("Other.L5X")
                other.write_bytes(PROJECT.replace(b'Name="Sample"', b'Name="Other"'))
                unavailable = await client.call_tool("get_project")
                self.assertTrue(unavailable.isError)
                self.assertIn("Could not read Sample.L5X", unavailable.content[0].text)

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
                for _ in range(2):
                    summary = await client.call_tool("get_project")
                    self.assertFalse(summary.isError, summary.content)
                    self.assertTrue(summary.structuredContent["controller"])
                    self.assertTrue(summary.structuredContent["software_revision"])
                    self.assertEqual(summary.structuredContent["source_sha256"], original.hex())
        finally:
            with project.open("rb") as source:
                self.assertEqual(hashlib.file_digest(source, "sha256").digest(), original)
