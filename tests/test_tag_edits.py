import os
import shutil
import subprocess
import sys
import unittest
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonschema import validate
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from logix_project_mcp.project import ProjectReadError, export_snapshot, parse_l5x, read_project
from logix_project_mcp.selection import ProjectSelection
from logix_project_mcp.tag_edits import preview_tag, read_state, review_copy


SAMPLE = b'''<RSLogix5000Content SoftwareRevision="38.02" TargetType="Controller"><Controller Name="Sample">
<Tags/><Programs><Program Name="Main"><Tags><Tag Name="Existing" DataType="BOOL"/></Tags></Program></Programs>
</Controller></RSLogix5000Content>'''


class TagEditTests(unittest.IsolatedAsyncioTestCase):
    async def test_lifecycle_through_stdio_and_local_review(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp).resolve()
            path = folder / "Input.L5X"
            path.write_bytes(SAMPLE)
            for i, change in enumerate((
                {"operation": "create", "name": "MyScratch", "value": -2147483648},
                {"operation": "set_value", "name": "myscratch", "value": 2147483647},
                {"operation": "rename", "name": "MyScratch", "new_name": "RenamedScratch"},
                {"operation": "remove", "name": "RenamedScratch"},
            )):
                change["program"] = "Main"
                source = path.read_bytes()
                current = ProjectSelection(path)
                args = StdioServerParameters(command=sys.executable, args=["-m", "logix_project_mcp.server", "--project", str(path)])
                async with stdio_client(args) as streams, ClientSession(*streams) as client:
                    await client.initialize()
                    tool = next(t for t in (await client.list_tools()).tools if t.name == "preview_tag_edit")
                    self.assertTrue(tool.annotations.readOnlyHint)
                    request = {"change": change, "expected_source_sha256": sha256(source).hexdigest()}
                    validate(request, tool.inputSchema)
                    result = await client.call_tool(tool.name, request)
                    self.assertFalse(result.isError, result.content)
                    preview = result.structuredContent
                    validate(preview, tool.outputSchema)
                    if i == 0:
                        for invalid, code in (
                            ({**request, "expected_source_sha256": "0" * 64}, "project_changed"),
                            ({**request, "change": {**change, "name": "exISTING"}}, "invalid_proposal"),
                            ({**request, "change": {**change, "value": 2147483648}}, "invalid_arguments"),
                            ({**request, "change": {**change, "name": "9abc"}}, "invalid_arguments"),
                        ):
                            rejection = await client.call_tool(tool.name, invalid)
                            self.assertTrue(rejection.isError)
                            self.assertEqual(rejection.meta["logix-project-mcp/error"]["code"], code)
                output = folder / f"Step{i}.L5X"
                receipt = await review_copy(lambda: current, preview, preview["approval_id"], output, lambda _: True)
                self.assertEqual(receipt["artifact_sha256"], sha256(output.read_bytes()).hexdigest())
                self.assertEqual(path.read_bytes(), source)
                self.assertIn(b"<Tags/><Programs>", output.read_bytes())
                if i == 1:
                    self.assertEqual(output.read_bytes(), source.replace(b"-2147483648", b"2147483647"))
                if i == 2:
                    self.assertEqual(output.read_bytes(), source.replace(b'MyScratch', b'RenamedScratch'))
                path = output
            self.assertEqual(path.read_bytes(), SAMPLE)

    async def test_reference_checks_and_publication_boundaries(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / "Sample.L5X"
            selection = ProjectSelection(path)
            new = {"operation": "create", "name": "ScratchTag", "value": 0}
            for extra in (b'<Tag AliasFor="ScratchTag.0"/>', b'<Text>SomeCall(SCRATCHTAG);</Text>',
                          b'<Routine IsEncrypted="true"/>', b'<SafetySignature/>'):
                path.write_bytes(SAMPLE.replace(b"<Tags/>", b"<Tags/>" + extra))
                with self.assertRaises(ProjectReadError):
                    preview_tag(selection, await read_project(path), new)
            path.write_bytes(SAMPLE)
            proposal = preview_tag(selection, await read_project(path), new)
            output = path.with_name("New.L5X")

            async def stage(confirm, reviewed=proposal):
                return await review_copy(lambda: selection, reviewed, proposal["approval_id"], output, confirm)

            self.assertIsNone(await stage(lambda _: False))
            self.assertFalse(output.exists())
            with self.assertRaises(ProjectReadError):
                await stage(lambda _: self.fail("Changed preview reached approval"), {**proposal, "before": proposal["after"]})
            def save_during_review(_):
                path.write_bytes(SAMPLE + b"\n")
                return True
            with self.assertRaises(ProjectReadError):
                await stage(save_during_review)
            self.assertFalse(output.exists())
            path.write_bytes(SAMPLE)
            def occupy_destination(_):
                output.write_bytes(b"occupied")
                return True
            with self.assertRaises(FileExistsError):
                await stage(occupy_destination)
            self.assertEqual(output.read_bytes(), b"occupied")

    async def test_saved_values_references_and_documentation(self):
        tag = (b'<Tag Name="ScratchTag" TagType="Base" DataType="DINT" Radix="Decimal" ExternalAccess="None">'
               b'<Description><![CDATA[Preserve A & B]]></Description>'
               b'<Data Format="L5K">\r\n<![CDATA[-23]]>\r\n</Data>'
               b'<Data Format="Decorated"><DataValue DataType="DINT" Radix="Decimal" Value=\'-23\'/></Data></Tag>')
        with TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / "Source.L5X"
            selection = ProjectSelection(path, "1" * 32)
            source = SAMPLE.replace(b"<Tags/>", b"<Tags>" + tag + b"</Tags>")
            path.write_bytes(source)
            change = {"operation": "set_value", "name": "ScratchTag", "value": 11}
            preview = preview_tag(selection, await read_project(path), change)
            out = path.with_name("Updated.L5X")
            def refresh(_):
                nonlocal selection
                selection = ProjectSelection(path, "2" * 32)
                return True
            with self.assertRaises(ProjectReadError):
                await review_copy(lambda: selection, preview, preview["approval_id"], out, refresh)
            self.assertFalse(out.exists())
            preview = preview_tag(selection, await read_project(path), change)
            self.assertEqual(preview["before"]["description"], "Preserve A & B")
            await review_copy(lambda: selection, preview, preview["approval_id"], out, lambda _: True)
            self.assertEqual(out.read_bytes(), source.replace(b"-23", b"11"))
            for bad in (source.replace(b"Value='-23'", b"Value='42'"),
                        source.replace(b'ExternalAccess="None"', b'ExternalAccess="Read/Write"'),
                        source.replace(b'Name="Existing"', b'Name="ScratchTag"'),
                        source.replace(b"</Program>", b"<Routine><STContent><Line>ScratchTag := 0;</Line></STContent></Routine></Program>")):
                path.write_bytes(bad)
                for op in ({"operation": "rename", "new_name": "NewTag"}, {"operation": "remove"}):
                    with self.assertRaises(ProjectReadError):
                        preview_tag(selection, await read_project(path), {"name": "ScratchTag", **op})

            result = subprocess.run([sys.executable, "-m", "logix_project_mcp.tag_edits", "--project", str(path),
                                     "--proposal", "unused.json", "--approval-id", preview["approval_id"], str(out)],
                                    input="APPROVE\n", text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("interactive terminal", result.stderr)

    @unittest.skipUnless(sys.platform == "win32" and os.getenv("LOGIX_PROJECT_MCP_TEST_DOCUMENTATION_L5X"),
                         "Synthetic Windows SDK L5X sample required")
    async def test_sdk_reopens_private_dint(self):
        source = Path(os.environ["LOGIX_PROJECT_MCP_TEST_DOCUMENTATION_L5X"]).resolve()
        original = sha256(source.read_bytes()).digest()
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            selection = ProjectSelection(source)
            change = {"operation": "create", "name": "McpPrivateScratch", "value": -17}
            preview = preview_tag(selection, await read_project(source), change)
            output = folder / "Tag.L5X"
            await review_copy(lambda: selection, preview, preview["approval_id"], output, lambda _: True)
            scratch = folder / "Import.L5X"
            shutil.copyfile(output, scratch)
            exported = folder / "Reopened.L5X"
            await export_snapshot(scratch, exported, "synthetic private DINT")
            tag = parse_l5x(exported).find("./Controller/Tags/Tag[@Name='McpPrivateScratch']")
            self.assertIsNotNone(tag)
            self.assertEqual(read_state(tag), preview["after"])
        self.assertEqual(sha256(source.read_bytes()).digest(), original)
