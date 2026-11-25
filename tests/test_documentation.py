import copy
import hashlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from jsonschema import validate
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from logix_project_mcp.documentation import build_documentation_copy, stage_documentation_copy
from logix_project_mcp.project import ProjectReadError, ProjectSnapshot, controller_from_l5x, parse_l5x_bytes
from logix_project_mcp.proposals import create_proposal
from logix_project_mcp.selection import ProjectSelection


PROJECT = b'''\xef\xbb\xbf<?xml version="1.0" encoding="UTF-8"?>\r
<RSLogix5000Content TargetType="Controller" SoftwareRevision="38.02">
  <!-- Keep this comment -->
  <Controller Name="Sample">
    <Description><![CDATA[Old controller description]]></Description>
    <Tags><Tag Name="Counter" DataType="DINT"><Description>Old tag text</Description><Data Format="Decorated"><DataValue Value="7"/></Data></Tag></Tags>
    <Programs><Program Name="Main">
      <Tags><Tag Name="Counter" DataType="DINT"><Description>Remove this</Description></Tag><Tag Name="Empty" DataType="BOOL" /></Tags>
      <Routines><Routine Name="MainRoutine" Type="ST"><STContent><Line Number="0"><![CDATA[// unchanged sample]]></Line></STContent></Routine></Routines>
    </Program></Programs>
  </Controller>
</RSLogix5000Content>'''

OPERATIONS = [
    {"operation": "set_description", "target": {"kind": "controller"}, "description": "Reviewed controller note"},
    {"operation": "set_description", "target": {"kind": "controller_tag", "name": "Counter"}, "description": "A & B < C > D\r\nUnicode: \u03b1"},
    {"operation": "set_description", "target": {"kind": "program_tag", "program": "main", "name": "counter"}, "description": None},
    {"operation": "set_description", "target": {"kind": "program_tag", "program": "Main", "name": "Empty"}, "description": ""},
    {"operation": "set_description", "target": {"kind": "program", "program": "Main"}, "description": "Program note"},
]

EXPECTED = (
    PROJECT.replace(b'<![CDATA[Old controller description]]>', b'Reviewed controller note')
    .replace(b'Old tag text', b'A &amp; B &lt; C &gt; D&#13;\nUnicode: \xce\xb1')
    .replace(b'<Description>Remove this</Description>', b'')
    .replace(b'<Tag Name="Empty" DataType="BOOL" />', b'<Tag Name="Empty" DataType="BOOL" ><Description></Description></Tag>')
    .replace(b'<Program Name="Main">', b'<Program Name="Main"><Description>Program note</Description>')
)


class DocumentationCopyTests(unittest.IsolatedAsyncioTestCase):
    async def test_reviewed_copy_over_stdio(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory).resolve()
            source = folder / "Sample.L5X"
            source.write_bytes(PROJECT)
            exports = folder / "Export"
            exports.mkdir()
            existing = exports / "Existing.L5X"
            existing.write_bytes(b"existing")
            server = StdioServerParameters(command=sys.executable, args=[
                "-m", "logix_project_mcp.server", "--project", str(source), "--export-dir", str(exports),
            ])
            async with stdio_client(server) as (reader, writer), ClientSession(reader, writer) as client:
                await client.initialize()
                tools = {tool.name: tool for tool in (await client.list_tools()).tools}
                tool = tools["create_documentation_copy"]
                self.assertFalse(tool.annotations.readOnlyHint)
                self.assertFalse(tool.annotations.destructiveHint)

                async def call(name, args, error=None):
                    result = await client.call_tool(name, args)
                    if error:
                        self.assertTrue(result.isError, result)
                        details = result.meta["logix-project-mcp/error"]
                        validate(details, tools[name].meta["logix-project-mcp/error-schema"])
                        self.assertEqual(details["code"], error)
                        return
                    self.assertFalse(result.isError, result.content)
                    validate(result.structuredContent, tools[name].outputSchema)
                    return result.structuredContent

                proposal = await call("preview_change_proposal", {
                    "operations": OPERATIONS, "expected_source_sha256": hashlib.sha256(PROJECT).hexdigest(),
                })
                request = {"proposal": proposal, "expected_approval_id": proposal["approval_id"], "filename": "Reviewed.L5X"}
                validate(request, tool.inputSchema)
                result = await call(tool.name, request)
                artifact = exports / request["filename"]
                self.assertEqual(result["path"], str(artifact))
                self.assertEqual(result["approval_id"], proposal["approval_id"])
                self.assertEqual(result["artifact_sha256"], hashlib.sha256(EXPECTED).hexdigest())
                self.assertEqual(artifact.read_bytes(), EXPECTED)
                self.assertEqual(source.read_bytes(), PROJECT)
                await call(tool.name, request, "destination_exists")
                await call(tool.name, {**request, "filename": existing.name}, "destination_exists")
                await call(tool.name, {**request, "filename": "../Outside.L5X"}, "invalid_arguments")
                await call(tool.name, {**request, "filename": "Another.ACD"}, "invalid_arguments")
                modified = copy.deepcopy(proposal)
                modified["preview"][0]["after"] = "Different text"
                await call(tool.name, {**request, "filename": "Tampered.L5X", "proposal": modified}, "invalid_proposal")
                source.write_bytes(PROJECT + b"\n")
                await call(tool.name, {**request, "filename": "Stale.L5X"}, "project_changed")
                self.assertEqual(source.read_bytes(), PROJECT + b"\n")
                self.assertEqual(existing.read_bytes(), b"existing")
                self.assertEqual(set(exports.iterdir()), {artifact, existing})

    async def test_changes_during_staging_and_destination_collision(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "Sample.L5X"
            source.write_bytes(PROJECT)
            selection = ProjectSelection(source)
            root = parse_l5x_bytes(PROJECT)
            proposal = create_proposal(selection, ProjectSnapshot(root, controller_from_l5x(root), hashlib.sha256(PROJECT).hexdigest()), OPERATIONS)
            for event in ("save", "selection", "destination"):
                source.write_bytes(PROJECT)
                destination = folder / f"{event}.L5X"
                current = selection

                def stage(*args):
                    nonlocal current
                    artifact = build_documentation_copy(*args)
                    if event == "save":
                        source.write_bytes(PROJECT + b"\n")
                    elif event == "selection":
                        current = ProjectSelection(source, "0" * 32)
                    else:
                        destination.write_bytes(b"competing file")
                    return artifact

                with patch("logix_project_mcp.documentation.build_documentation_copy", side_effect=stage):
                    with self.assertRaises(ProjectReadError) as caught:
                        await stage_documentation_copy(selection, lambda: current, folder, destination.name, proposal, proposal["approval_id"])
                self.assertEqual(caught.exception.code, {"save": "project_changed", "selection": "selection_changed", "destination": "destination_exists"}[event])
                if event == "destination":
                    self.assertEqual(destination.read_bytes(), b"competing file")
                else:
                    self.assertFalse(destination.exists())
                self.assertEqual(source.read_bytes(), PROJECT + (b"\n" if event == "save" else b""))
            self.assertEqual(set(folder.iterdir()), {source, folder / "destination.L5X"})

    def test_unsupported_encoding_is_not_modified(self):
        data = PROJECT.decode("utf-8-sig").replace('encoding="UTF-8"', 'encoding="UTF-16"').encode("utf-16")
        root = parse_l5x_bytes(data)
        selection = ProjectSelection(Path("Sample.L5X"))
        proposal = create_proposal(selection, ProjectSnapshot(root, controller_from_l5x(root), hashlib.sha256(data).hexdigest()), OPERATIONS)
        with self.assertRaises(ProjectReadError) as caught:
            build_documentation_copy(data, selection, proposal, proposal["approval_id"])
        self.assertEqual(caught.exception.code, "invalid_proposal")
