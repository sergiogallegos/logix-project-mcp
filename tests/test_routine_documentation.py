import copy
import hashlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonschema import validate
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from logix_project_mcp.project import parse_l5x_bytes
from logix_project_mcp.routines import inspect_routine


PROJECT = b'''<?xml version="1.0" encoding="UTF-8"?>
<RSLogix5000Content TargetType="Controller" SoftwareRevision="38.02">
  <Controller Name="Sample">
    <Programs>
      <Program Name="First">
        <Routines>
          <Routine Name="Main" Type="RLL"><Description>Old ladder note</Description><RLLContent><Rung Number="0" Type="N"><Comment><![CDATA[Existing rung note]]></Comment><Text><![CDATA[]]></Text></Rung></RLLContent></Routine>
          <Routine Name="Protected" Type="ST" IsEncrypted="true" />
          <EncodedData Name="Encoded" EncodedType="Routine" />
          <Routine Name="Diagram" Type="FBD"><FBDContent /></Routine>
          <Routine Name="Incomplete" Type="ST" />
          <Routine Name="Duplicate" Type="ST"><STContent /></Routine>
          <Routine Name="DUPLICATE" Type="ST"><STContent /></Routine>
        </Routines>
      </Program>
      <Program Name="Second">
        <Routines>
          <Routine Name="Main" Type="ST"><STContent><Line Number="0"><![CDATA[// Existing line note]]></Line></STContent><STContent OnlineEditType="Pending"><Line Number="0"><![CDATA[// Pending line note]]></Line></STContent></Routine>
          <Routine Name="Remove" Type="RLL"><Description>Remove this note</Description><RLLContent /></Routine>
        </Routines>
      </Program>
    </Programs>
  </Controller>
</RSLogix5000Content>'''


def operation(program, name, description):
    return {
        "operation": "set_description",
        "target": {"kind": "routine", "program": program, "name": name},
        "description": description,
    }


class RoutineDocumentationTests(unittest.IsolatedAsyncioTestCase):
    async def test_scoped_routine_documentation_preserves_all_sections(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory).resolve()
            source = folder / "Sample.L5X"
            source.write_bytes(PROJECT)
            exports = folder / "Exports"
            exports.mkdir()
            server = StdioServerParameters(command=sys.executable, args=[
                "-m", "logix_project_mcp.server", "--project", str(source), "--export-dir", str(exports),
            ])
            async with stdio_client(server) as (reader, writer), ClientSession(reader, writer) as client:
                await client.initialize()
                tools = {tool.name: tool for tool in (await client.list_tools()).tools}

                async def call(name, arguments, error=None):
                    result = await client.call_tool(name, arguments)
                    if error:
                        self.assertTrue(result.isError, result)
                        details = result.meta["logix-project-mcp/error"]
                        validate(details, tools[name].meta["logix-project-mcp/error-schema"])
                        self.assertEqual(details["code"], error)
                        return
                    self.assertFalse(result.isError, result.content)
                    validate(result.structuredContent, tools[name].outputSchema)
                    return result.structuredContent

                operations = [
                    operation("first", "main", "Reviewed ladder description"),
                    operation("second", "MAIN", "Reviewed ST description"),
                    operation("Second", "Remove", None),
                ]
                args = {"operations": operations, "expected_source_sha256": hashlib.sha256(PROJECT).hexdigest()}
                validate(args, tools["preview_change_proposal"].inputSchema)
                proposal = await call("preview_change_proposal", args)
                self.assertEqual([entry["target"] for entry in proposal["preview"]], [
                    {"kind": "routine", "program": "First", "name": "Main"},
                    {"kind": "routine", "program": "Second", "name": "Main"},
                    {"kind": "routine", "program": "Second", "name": "Remove"},
                ])
                self.assertEqual([entry["before"] for entry in proposal["preview"]], ["Old ladder note", None, "Remove this note"])
                approval = {"proposal": proposal, "expected_approval_id": proposal["approval_id"]}
                self.assertTrue((await call("validate_change_proposal", approval))["valid"])
                artifact = await call("create_documentation_copy", {**approval, "filename": "Reviewed.L5X"})
                expected = (PROJECT.replace(b"Old ladder note", b"Reviewed ladder description")
                            .replace(b'<Routine Name="Main" Type="ST">', b'<Routine Name="Main" Type="ST"><Description>Reviewed ST description</Description>')
                            .replace(b"<Description>Remove this note</Description>", b""))
                output = Path(artifact["path"])
                self.assertEqual(output.read_bytes(), expected)
                self.assertEqual(artifact["artifact_sha256"], hashlib.sha256(expected).hexdigest())
                before, after = parse_l5x_bytes(PROJECT), parse_l5x_bytes(expected)
                for program in ("First", "Second"):
                    path = f"Controller/Programs/Program[@Name='{program}']/Routines/Routine[@Name='Main']"
                    self.assertEqual(inspect_routine(program, before.find(path))["sections"],
                                     inspect_routine(program, after.find(path))["sections"])
                for name, error in (
                    ("Protected", "invalid_proposal"), ("Encoded", "invalid_proposal"),
                    ("Diagram", "invalid_proposal"), ("Incomplete", "invalid_proposal"),
                    ("Duplicate", "ambiguous_target"), ("Missing", "not_found"),
                ):
                    await call("preview_change_proposal", {**args, "operations": [operation("First", name, "Note")]}, error)
                await call("preview_change_proposal", {**args, "operations": [operations[0], operation("First", "Main", "Another note")]}, "ambiguous_target")
                changed = copy.deepcopy(proposal)
                changed["preview"][0]["target"]["program"] = "Second"
                await call("create_documentation_copy", {**approval, "proposal": changed, "filename": "Altered.L5X"}, "invalid_proposal")
                invalid_operation = {**operations[0], "logic": "unsupported"}
                await call("preview_change_proposal", {**args, "operations": [invalid_operation]}, "invalid_arguments")
                self.assertEqual(source.read_bytes(), PROJECT)
                self.assertEqual(list(exports.iterdir()), [output])
