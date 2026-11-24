import asyncio
import hashlib
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonschema import validate
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from test_stdio import PROJECT


class SelectionTests(unittest.IsolatedAsyncioTestCase):
    async def share(self, file, *arguments, success=True):
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "logix_project_mcp.share", "--selection-file", str(file), *map(str, arguments),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if success:
            self.assertEqual(process.returncode, 0, stderr.decode(errors="replace"))
            return json.loads(stdout)
        self.assertNotEqual(process.returncode, 0)

    async def test_local_helper_switches_and_refreshes_one_running_session(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory).resolve()
            first = folder / "Window A" / "Same project.L5X"
            second = folder / "Window B" / "Same project.L5X"
            for source in (first, second):
                source.parent.mkdir()
                source.write_bytes(PROJECT)
            selection_file = folder / "Shared state.json"
            exports = folder / "Exports"
            exports.mkdir()
            server = StdioServerParameters(command=sys.executable, args=[
                "-m", "logix_project_mcp.server", "--selection-file", str(selection_file),
                "--compare-project", str(first), "--export-dir", str(exports),
            ])
            async with stdio_client(server) as (reader, writer), ClientSession(reader, writer) as client:
                await client.initialize()
                tools = {tool.name: tool for tool in (await client.list_tools()).tools}

                async def call(name, arguments=None, error=None):
                    result = await client.call_tool(name, arguments or {})
                    if error:
                        self.assertTrue(result.isError, result)
                        self.assertEqual(result.meta["logix-project-mcp/error"]["code"], error)
                        validate(result.meta["logix-project-mcp/error"], tools[name].meta["logix-project-mcp/error-schema"])
                        return
                    self.assertFalse(result.isError, result.content)
                    validate(result.structuredContent, tools[name].outputSchema)
                    return result.structuredContent

                self.assertNotIn("select_project", tools)
                self.assertIsNone((await call("get_capabilities"))["project"])
                await call("get_project", error="selection_required")
                shared = await self.share(selection_file, first)
                selected = (await call("get_project"))["selection"]
                self.assertEqual(selected["path"], str(first))
                self.assertEqual(selected["software_revision"], "38.00")
                self.assertEqual(selected["selection_id"], shared["selection_id"])
                self.assertEqual((await call("list_tags"))["selection"], selected)
                self.assertEqual((await call("read_routine", {"program": "MainProgram", "routine": "MainRoutine"}))["selection"], selected)
                await call("get_project", {"path": str(second)}, error="invalid_arguments")
                page = await call("search_project", {"query": "ControllerTag"})

                await self.share(selection_file, second)
                current = await call("get_project")
                self.assertEqual(current["selection"]["path"], str(second))
                self.assertEqual(current["source_sha256"], page["source_sha256"])
                await call("search_project", {"query": "ControllerTag", "offset": 1,
                           "expected_source_sha256": page["source_sha256"],
                           "expected_selection_id": selected["selection_id"]}, error="selection_changed")
                state = selection_file.read_bytes()
                await self.share(selection_file, folder / "Missing.ACD", success=False)
                invalid = folder / "Invalid.L5X"
                invalid.write_bytes(b"<invalid/>")
                await self.share(selection_file, invalid, success=False)
                self.assertEqual(selection_file.read_bytes(), state)

                changed = PROJECT.replace(b'Name="Sample"', b'Name="Updated"').replace(b'38.00', b'38.02')
                second.write_bytes(changed)
                updated = await call("get_inventory")
                self.assertEqual(updated["selection"]["controller"], "Updated")
                self.assertEqual(updated["selection"]["software_revision"], "38.02")
                self.assertEqual(updated["source_sha256"], hashlib.sha256(changed).hexdigest())
                refreshed = await self.share(selection_file, "--refresh")
                self.assertNotEqual(refreshed["selection_id"], current["selection"]["selection_id"])
                compared = await call("compare_projects")
                self.assertEqual(compared["selection"]["path"], str(second))
                artifact = await call("export_project", {"filename": "Shared.L5X"})
                self.assertEqual(artifact["selection"]["path"], str(second))
                self.assertEqual((exports / "Shared.L5X").read_bytes(), changed)

                moved = second.with_name("Moved.L5X")
                second.rename(moved)
                await call("get_project", error="project_unavailable")
                self.assertEqual((await call("get_capabilities"))["selection"]["path"], str(second))
                state = selection_file.read_bytes()
                await self.share(selection_file, "--refresh", success=False)
                self.assertEqual(selection_file.read_bytes(), state)
                await self.share(selection_file, moved)
                self.assertEqual((await call("get_project"))["selection"]["path"], str(moved))
                moved.unlink()
                await call("get_project", error="project_unavailable")
                await self.share(selection_file, first)
                self.assertEqual((await call("get_project"))["selection"]["path"], str(first))
                state = selection_file.read_bytes()
                selection_file.write_bytes(b"invalid JSON")
                await call("get_project", error="invalid_selection")
                selection_file.write_bytes(state)
                self.assertEqual((await call("get_project"))["selection"]["path"], str(first))
                self.assertEqual(first.read_bytes(), PROJECT)

    async def test_unrelated_selection_file_is_preserved(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "Project.L5X"
            source.write_bytes(PROJECT)
            selection = folder / "Other.json"
            selection.write_bytes(b'{"other":true}')
            await self.share(selection, source, success=False)
            self.assertEqual(selection.read_bytes(), b'{"other":true}')
