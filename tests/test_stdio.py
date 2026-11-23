import hashlib
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

                summary = await client.call_tool("get_project")
                self.assertFalse(summary.isError, summary.content)
                self.assertEqual(summary.structuredContent["controller"], "Sample")
                self.assertEqual(summary.structuredContent["programs"][0]["name"], "MainProgram")

                tags = await client.call_tool("list_tags", {"program": "MainProgram"})
                self.assertFalse(tags.isError, tags.content)
                self.assertEqual(tags.structuredContent["result"][0]["name"], "ProgramTag")

                routine = await client.call_tool(
                    "read_routine", {"program": "MainProgram", "routine": "MainRoutine"}
                )
                self.assertFalse(routine.isError, routine.content)
                self.assertIn("Sample rung", routine.structuredContent["result"])

                missing = await client.call_tool("list_tags", {"program": "Missing"})
                self.assertTrue(missing.isError)

            self.assertEqual(project.read_bytes(), PROJECT)

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
                summary = await client.call_tool("get_project")
                self.assertFalse(summary.isError, summary.content)
                self.assertTrue(summary.structuredContent["controller"])
                self.assertTrue(summary.structuredContent["software_revision"])
        finally:
            with project.open("rb") as source:
                self.assertEqual(hashlib.file_digest(source, "sha256").digest(), original)
