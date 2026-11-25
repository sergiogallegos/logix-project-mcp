import copy
import os
import shutil
import sys
import unittest
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonschema import validate
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from logix_project_mcp import routine_edits, tag_edits
from logix_project_mcp.edit_review import publish_reviewed
from logix_project_mcp.project import ProjectReadError, export_snapshot, parse_l5x, read_project
from logix_project_mcp.selection import ProjectSelection


SAMPLE = b'''<RSLogix5000Content SoftwareRevision="38.02" TargetType="Controller"><Controller Name="Sample">
<Programs><Program Name="Main" MainRoutineName="Entry"><Tags>
<Tag Name="Scratch" TagType="Base" DataType="DINT" Radix="Decimal" ExternalAccess="None">
<Data Format="L5K"><![CDATA[0]]></Data></Tag></Tags><Routines>
<Routine Name="Entry" Type="ST"><STContent/></Routine></Routines></Program>
<Program Name="Other"><Tags/><Routines/></Program></Programs></Controller></RSLogix5000Content>'''


def request(language, op, value):
    return {"operation": op, "program": "Main", "routine": "Trial", "language": language,
            "statement": f"MOVE({value},Scratch);" if language == "RLL" else f"Scratch := {value};"}


class RoutineEditTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_and_update_over_stdio(self):
        for language in ("RLL", "ST"):
            with self.subTest(language=language), TemporaryDirectory() as tmp:
                path = Path(tmp).resolve() / "Source.L5X"
                path.write_bytes(SAMPLE)
                for op, value in (("create", -7), ("update", 2147483647)):
                    previous = path.read_bytes()
                    change = request(language, op, value)
                    server = StdioServerParameters(command=sys.executable, args=["-m", "logix_project_mcp.server",
                                                                               "--project", str(path)])
                    async with stdio_client(server) as streams, ClientSession(*streams) as client:
                        await client.initialize()
                        tool = next(t for t in (await client.list_tools()).tools if t.name == "preview_routine_edit")
                        self.assertTrue(tool.annotations.readOnlyHint)
                        args = {"change": change, "expected_source_sha256": sha256(previous).hexdigest()}
                        validate(args, tool.inputSchema)
                        result = await client.call_tool(tool.name, args)
                        self.assertFalse(result.isError, result.content)
                        preview = result.structuredContent
                        validate(preview, tool.outputSchema)
                        self.assertEqual(preview["destination_tag"], "Program:Main.Scratch")
                        self.assertEqual(preview["after"], change["statement"])
                        self.assertEqual(preview["before"], None if op == "create" else request(language, op, -7)["statement"])
                        bad = await client.call_tool(tool.name, {**args, "change": {**change, "statement": "Scratch := ;"}})
                        self.assertEqual(bad.meta["logix-project-mcp/error"]["code"], "invalid_proposal")
                        stale = await client.call_tool(tool.name, {**args, "expected_source_sha256": "0" * 64})
                        self.assertEqual(stale.meta["logix-project-mcp/error"]["code"], "project_changed")
                    target = path.with_name(f"{op}.L5X")
                    selection = ProjectSelection(path)
                    receipt = await publish_reviewed(lambda: selection, preview, preview["approval_id"], target,
                                                     lambda _: True, routine_edits.build_copy)
                    self.assertEqual(sha256(target.read_bytes()).hexdigest(), receipt["artifact_sha256"])
                    self.assertEqual(previous, path.read_bytes())
                    if op == "update":
                        self.assertEqual(target.read_bytes(), previous.replace(b"-7", b"2147483647"))
                    root = parse_l5x(target)
                    self.assertIsNone(root.find(".//Program[@Name='Other']/Routines/Routine"))
                    path = target

    async def test_preserves_comments_and_rejects_ambiguous_or_referenced_targets(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / "Source.L5X"
            sel = ProjectSelection(path)
            for lang, content in (
                ("RLL", b'<RLLContent><Rung Number="0" Type="N"><Comment><![CDATA[keep 12]]></Comment>'
                        b'<Text>\r\n<![CDATA[MOVE(12,Scratch);]]>\r\n</Text></Rung></RLLContent>'),
                ("ST", b'<STContent><Line Number="0">// note 12</Line><Line Number="1">\r\n'
                       b'<![CDATA[ Scratch := 12; // keep 12 & more]]>\r\n</Line></STContent>'),
            ):
                routine = b'<Routine Name="Trial" Type="' + lang.encode() + b'">' + content + b'</Routine>'
                source = SAMPLE.replace(b"</Routines>", routine + b"</Routines>", 1)
                path.write_bytes(source)
                change = request(lang, "update", -27)
                preview = routine_edits.preview_routine(sel, await read_project(path), change)
                actual = routine_edits.build_copy(source, sel, preview, preview["approval_id"])
                self.assertEqual(actual, source.replace(b"(12,", b"(-27,").replace(b":= 12;", b":= -27;"))
                edited = copy.deepcopy(preview)
                edited["after"] += " "
                with self.assertRaises(ProjectReadError):
                    routine_edits.build_copy(source, sel, edited, preview["approval_id"])
                for bad_source, bad_change in (
                    (source, {**change, "operation": "create"}),
                    (source, {**change, "program": "Other"}),
                    (source, {**change, "statement": change["statement"].replace("-27", "2147483648")}),
                    (source, {**change, "statement": change["statement"] + change["statement"]}),
                    (source.replace(b'MainRoutineName="Entry"', b'MainRoutineName="Trial"'), change),
                    (source.replace(b'<STContent/>', b'<STContent><Line Number="0">JSR(Trial);</Line></STContent>', 1), change),
                    (source.replace(b'Name="Main"', b'Name="Main" TestEdits="true"'), change),
                    (source.replace(b"<Tags>", b'<Tags><Tag Name="Alias" AliasFor="Scratch"/>'), change),
                    (source.replace(b'Name="Trial"', b'IsEncrypted="true" Name="Trial"'), change),
                    (source.replace(b'Name="Main"', b'Class="Safety" Name="Main"'), change),
                    (source.replace(b"<" + lang.encode() + b"Content>", b"<" + lang.encode() + b'Content OnlineEditType="Pending">'), change),
                    (source.replace(b'ExternalAccess="None"', b'ExternalAccess="Read/Write"'), change),
                ):
                    path.write_bytes(bad_source)
                    with self.assertRaises(ProjectReadError):
                        routine_edits.preview_routine(sel, await read_project(path), bad_change)

    async def test_legacy_ladder_mnemonic(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / "Legacy.L5X"
            path.write_bytes(SAMPLE.replace(b"38.02", b"35.00"))
            selection = ProjectSelection(path)
            snapshot = await read_project(path)
            change = request("RLL", "create", 5)
            with self.assertRaises(ProjectReadError):
                routine_edits.preview_routine(selection, snapshot, change)
            change["statement"] = "MOV(5,Scratch);"
            proposal = routine_edits.preview_routine(selection, snapshot, change)
            self.assertIn(b"<![CDATA[MOV(5,Scratch);]]>",
                          routine_edits.build_copy(path.read_bytes(), selection, proposal, proposal["approval_id"]))

    @unittest.skipUnless(sys.platform == "win32" and os.getenv("LOGIX_PROJECT_MCP_TEST_ROUTINE_L5X"),
                         "Synthetic Windows SDK routine-edit sample required")
    async def test_sdk_reopens_both_assignment_languages(self):
        source = Path(os.environ["LOGIX_PROJECT_MCP_TEST_ROUTINE_L5X"]).resolve()
        original = sha256(source.read_bytes()).digest()
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            current = source
            for language in ("RLL", "ST"):
                tag = "McpScratch" + language
                name = "McpTrial" + language
                program = "MainProgram"
                change = {"operation": "create", "name": tag, "program": program, "value": 0}
                selection = ProjectSelection(current)
                proposal = tag_edits.preview_tag(selection, await read_project(current), change)
                target = folder / f"{tag}.L5X"
                target.write_bytes(tag_edits.build_copy(current.read_bytes(), selection, proposal, proposal["approval_id"]))
                current = target
                for operation, value in (("create", 12), ("update", 37)):
                    change = request(language, operation, value)
                    change.update(program=program, routine=name, statement=change["statement"].replace("Scratch", tag))
                    selection = ProjectSelection(current)
                    proposal = routine_edits.preview_routine(selection, await read_project(current), change)
                    target = folder / f"{name}-{operation}.L5X"
                    target.write_bytes(routine_edits.build_copy(current.read_bytes(), selection, proposal, proposal["approval_id"]))
                    current = target
            scratch, exported = folder / "Import.L5X", folder / "Readback.L5X"
            shutil.copyfile(current, scratch)
            await export_snapshot(scratch, exported, "synthetic routine edits")
            root = parse_l5x(exported)
            for language, expected in (("RLL", "MOVE(37,McpScratchRLL);"), ("ST", "McpScratchST := 37;")):
                routine = root.find(f".//Program[@Name='MainProgram']/Routines/Routine[@Name='McpTrial{language}']")
                self.assertIsNotNone(routine)
                self.assertEqual(routine_edits.code_node(routine, language).text.strip(), expected)
        self.assertEqual(sha256(source.read_bytes()).digest(), original)
