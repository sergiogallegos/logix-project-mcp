import hashlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonschema import validate
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


PROJECT = b"""<?xml version="1.0" encoding="UTF-8"?>
<RSLogix5000Content TargetType="Controller" SoftwareRevision="38.02">
  <Controller Name="Synthetic">
    <Description>Original controller note</Description>
    <AddOnInstructionDefinitions>
      <AddOnInstructionDefinition Name="Example" Revision="1.0">
        <Description>Original AOI description</Description>
        <Parameters><Parameter Name="ExampleParameter" DataType="DINT" Usage="Input"/></Parameters>
        <LocalTags><LocalTag Name="ExampleLocal" DataType="DINT"/></LocalTags>
        <Routines><Routine Name="ExampleRoutine" Type="ST"><STContent><Line Number="0"><![CDATA[// synthetic example]]></Line></STContent></Routine></Routines>
      </AddOnInstructionDefinition>
      <EncodedData Name="ProtectedExample" EncodedType="AddOnInstructionDefinition" Revision="1.0"><Description>Visible metadata</Description>FABRICATED_OPAQUE_AOI_BYTES</EncodedData>
    </AddOnInstructionDefinitions>
    <Tags><Tag Name="Demo" DataType="DINT"><Description>Original tag note</Description></Tag></Tags>
    <Programs><Program Name="ExampleProgram">
      <Tags><Tag Name="Demo" DataType="DINT"><Description>Program note</Description></Tag></Tags>
      <Routines>
        <EncodedData Name="ProtectedRoutine" EncodedType="Routine" Type="ST"><Description>Visible metadata</Description>FABRICATED_OPAQUE_ROUTINE_BYTES</EncodedData>
        <Routine Name="Readable" Type="ST"><STContent><Line Number="0"><![CDATA[// another example]]></Line></STContent></Routine>
      </Routines>
    </Program></Programs>
  </Controller>
</RSLogix5000Content>"""

OPERATIONS = [
    {"operation": "set_description", "target": {"kind": "controller_tag", "name": "Demo"}, "description": "Reviewed tag note"},
    {"operation": "set_description", "target": {"kind": "routine", "program": "ExampleProgram", "name": "Readable"}, "description": "Reviewed routine note"},
]


class DocumentationPreservationTests(unittest.IsolatedAsyncioTestCase):
    async def test_aoi_and_protected_payloads_preserved_exactly(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory).resolve()
            source = folder / "Source.L5X"
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
                    if error is not None:
                        self.assertTrue(result.isError, result)
                        details = result.meta["logix-project-mcp/error"]
                        validate(details, tools[name].meta["logix-project-mcp/error-schema"])
                        self.assertEqual(details["code"], error)
                        return
                    self.assertFalse(result.isError, result.content)
                    validate(result.structuredContent, tools[name].outputSchema)
                    return result.structuredContent

                args = {"operations": OPERATIONS, "expected_source_sha256": hashlib.sha256(PROJECT).hexdigest()}
                proposal = await call("preview_change_proposal", args)
                self.assertNotIn("FABRICATED_OPAQUE", str(proposal))
                approval = {"proposal": proposal, "expected_approval_id": proposal["approval_id"]}
                request = {**approval, "filename": "Reviewed.L5X"}
                receipt = await call("create_documentation_copy", request)
                artifact = Path(receipt["path"])
                expected = (PROJECT.replace(b"Original tag note", b"Reviewed tag note")
                            .replace(b'<Routine Name="Readable" Type="ST">', b'<Routine Name="Readable" Type="ST"><Description>Reviewed routine note</Description>'))
                self.assertEqual(artifact.read_bytes(), expected)
                verified = await call("verify_documentation_copy", {**request, "expected_artifact_sha256": receipt["artifact_sha256"]})
                self.assertEqual(verified["vendor_verification"], "not_performed")
                self.assertEqual(verified["artifact_sha256"], hashlib.sha256(expected).hexdigest())
                await call("preview_change_proposal", {**args, "operations": [{
                    "operation": "set_description", "target": {"kind": "routine", "program": "ExampleProgram", "name": "ProtectedRoutine"},
                    "description": "Not supported",
                }]}, "invalid_proposal")
                await call("preview_change_proposal", {**args, "operations": [{
                    "operation": "set_description", "target": {"kind": "add_on_instruction", "name": "Example"},
                    "description": "Not supported",
                }]}, "invalid_arguments")
                self.assertEqual(source.read_bytes(), PROJECT)
                self.assertEqual(list(exports.iterdir()), [artifact])

    async def test_safety_indicators_reject_proposals_but_allow_inspection(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory).resolve()
            source = folder / "Source.L5X"
            source.write_bytes(PROJECT)
            exports = folder / "Exports"
            exports.mkdir()
            server = StdioServerParameters(command=sys.executable, args=[
                "-m", "logix_project_mcp.server", "--project", str(source), "--export-dir", str(exports),
            ])
            async with stdio_client(server) as (reader, writer), ClientSession(reader, writer) as client:
                await client.initialize()
                tools = {tool.name: tool for tool in (await client.list_tools()).tools}
                variants = (
                    PROJECT.replace(b'</Controller>', b'<SafetySignaturesHmac Value="SYNTHETIC"/></Controller>'),
                    PROJECT.replace(b'<Tags><Tag Name="Demo"', b'<Tags SafetySignature="SYNTHETIC"><Tag Name="Demo"', 1),
                    PROJECT.replace(b'Name="ExampleProgram"', b'Name="ExampleProgram" Class="Safety"'),
                    PROJECT.replace(b'Name="Synthetic"', b'Name="Synthetic" SafetyLocked="true"'),
                    PROJECT.replace(b'Name="ProtectedExample"', b'Name="ProtectedExample" SafetySignatureID="SYNTHETIC"'),
                )
                for data in variants:
                    source.write_bytes(data)
                    read = await client.call_tool("get_project")
                    self.assertFalse(read.isError, read.content)
                    self.assertEqual(read.structuredContent["source_sha256"], hashlib.sha256(data).hexdigest())
                    preview = await client.call_tool("preview_change_proposal", {
                        "operations": OPERATIONS, "expected_source_sha256": read.structuredContent["source_sha256"],
                    })
                    self.assertTrue(preview.isError, preview)
                    details = preview.meta["logix-project-mcp/error"]
                    validate(details, tools["preview_change_proposal"].meta["logix-project-mcp/error-schema"])
                    self.assertEqual(details["code"], "unsupported_safety_content")
                    self.assertNotIn("SYNTHETIC", details["message"])
                    self.assertEqual(source.read_bytes(), data)
                    self.assertEqual(list(exports.iterdir()), [])
