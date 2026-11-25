import copy
import hashlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonschema import validate
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from logix_project_mcp.selection import publish_selection


PROJECT = b"""<RSLogix5000Content SoftwareRevision="38.02" TargetType="Controller">
  <Controller Name="Sample">
    <Description>Original controller note</Description>
    <Tags><Tag Name="Counter"><Description>Controller note</Description></Tag></Tags>
    <Programs><Program Name="Main">
      <Tags><Tag Name="Counter"><Description>Program note</Description></Tag>
      <Tag Name="Empty"><Description /></Tag>
      <Tag Name="Absent" /></Tags>
    </Program></Programs>
  </Controller>
</RSLogix5000Content>"""


def description(target, text):
    return {"operation": "set_description", "target": target, "description": text}


class ProposalTests(unittest.IsolatedAsyncioTestCase):
    async def test_preview_validation_and_rejections(self):
        with TemporaryDirectory() as directory:
            project = Path(directory).resolve() / "Review.L5X"
            project.write_bytes(PROJECT)
            server = StdioServerParameters(command=sys.executable, args=[
                "-m", "logix_project_mcp.server", "--project", str(project),
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
                        self.assertIsNone(result.structuredContent)
                        return
                    self.assertFalse(result.isError, result.content)
                    validate(result.structuredContent, tools[name].outputSchema)
                    return result.structuredContent

                operations = [
                    description({"kind": "controller_tag", "name": "counter"}, "Controller documentation"),
                    description({"kind": "program_tag", "program": "main", "name": "COUNTER"}, None),
                    description({"kind": "program_tag", "program": "Main", "name": "Empty"}, "New note"),
                    description({"kind": "program_tag", "program": "Main", "name": "Absent"}, ""),
                    description({"kind": "program", "program": "main"}, "Program-level documentation"),
                ]
                arguments = {"operations": operations, "expected_source_sha256": hashlib.sha256(PROJECT).hexdigest()}
                preview_tool = "preview_change_proposal"
                validate_tool = "validate_change_proposal"
                validate(arguments, tools[preview_tool].inputSchema)
                proposal = await call(preview_tool, arguments)
                self.assertEqual(proposal["source"]["software_revision"], "38.02")
                self.assertEqual(proposal["source"]["path"], str(project))
                self.assertEqual(proposal["preview"][0]["target"], {"kind": "controller_tag", "name": "Counter"})
                self.assertEqual(proposal["preview"][1]["target"], {"kind": "program_tag", "program": "Main", "name": "Counter"})
                self.assertEqual([entry["before"] for entry in proposal["preview"]], ["Controller note", "Program note", "", None, None])
                self.assertEqual([entry["after"] for entry in proposal["preview"]], ["Controller documentation", None, "New note", "", "Program-level documentation"])
                self.assertEqual(proposal["preview"][4]["target"], {"kind": "program", "program": "Main"})
                self.assertEqual(await call(preview_tool, arguments), proposal)
                approval = {"proposal": proposal, "expected_approval_id": proposal["approval_id"]}
                validate(approval, tools[validate_tool].inputSchema)
                self.assertTrue((await call(validate_tool, approval))["valid"])
                self.assertEqual(project.read_bytes(), PROJECT)
                self.assertEqual(list(project.parent.iterdir()), [project])

                for field, value in (("before", "Invented note"), ("after", "Different note")):
                    modified = copy.deepcopy(proposal)
                    modified["preview"][0][field] = value
                    await call(validate_tool, {**approval, "proposal": modified}, "invalid_proposal")
                modified = copy.deepcopy(proposal)
                modified["source"]["software_revision"] = "1.00"
                await call(validate_tool, {**approval, "proposal": modified}, "invalid_proposal")
                await call(validate_tool, {**approval, "expected_approval_id": "0" * 64}, "invalid_proposal")
                changed = await call(preview_tool, {**arguments, "operations": [
                    description({"kind": "controller_tag", "name": "Counter"}, "Different documentation")
                ]})
                self.assertNotEqual(changed["approval_id"], proposal["approval_id"])
                await call(validate_tool, {**approval, "proposal": changed}, "invalid_proposal")

                for operation, error in [
                    ({"operation": "replace_logic", "target": {"kind": "controller"}, "description": "Other"}, "invalid_arguments"),
                    (description({"kind": "controller_tag", "name": "Counter", "program": "Main"}, "Note"), "invalid_arguments"),
                    (description({"kind": "program_tag", "program": "Missing", "name": "Counter"}, "Note"), "not_found"),
                    (description({"kind": "controller"}, "Invalid\x00"), "invalid_arguments"),
                ]:
                    await call(preview_tool, {**arguments, "operations": [operation]}, error)
                await call(preview_tool, {**arguments, "operations": [operations[0], operations[0]]}, "ambiguous_target")
                await call(preview_tool, {**arguments, "operations": []}, "invalid_arguments")
                self.assertEqual(project.read_bytes(), PROJECT)

                duplicate = PROJECT.replace(b'</Tags>', b'<Tag Name="COUNTER" /></Tags>', 1)
                project.write_bytes(duplicate)
                await call(validate_tool, approval, "project_changed")
                await call(preview_tool, arguments, "project_changed")
                await call(preview_tool, {**arguments, "expected_source_sha256": hashlib.sha256(duplicate).hexdigest()}, "ambiguous_target")
                self.assertEqual(project.read_bytes(), duplicate)
                for invalid_source, error in (
                    (PROJECT.replace(b'<Tag Name="Counter">', b'<Tag Name="Counter" IsEncrypted="true">', 1), "invalid_proposal"),
                    (PROJECT.replace(b'Controller note</Description>', b'Controller note</Description><Description>Other</Description>', 1), "invalid_proposal"),
                    (PROJECT.replace(b'</Programs>', b'<Program Name="MAIN" /></Programs>'), "ambiguous_target"),
                ):
                    project.write_bytes(invalid_source)
                    await call(preview_tool, {**arguments, "expected_source_sha256": hashlib.sha256(invalid_source).hexdigest()}, error)
                    self.assertEqual(project.read_bytes(), invalid_source)

    async def test_selection_change_invalidates_identical_saved_bytes(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory).resolve()
            project = folder / "First.L5X"
            other = folder / "Second.L5X"
            for source in (project, other):
                source.write_bytes(PROJECT)
            state = folder / "selection.json"
            selected = publish_selection(state, project)
            server = StdioServerParameters(command=sys.executable, args=[
                "-m", "logix_project_mcp.server", "--selection-file", str(state),
            ])
            async with stdio_client(server) as (reader, writer), ClientSession(reader, writer) as client:
                await client.initialize()
                args = {
                    "operations": [description({"kind": "controller"}, "Reviewed note")],
                    "expected_source_sha256": hashlib.sha256(PROJECT).hexdigest(),
                    "expected_selection_id": selected.selection_id,
                }
                missing_id = await client.call_tool("preview_change_proposal", {k: v for k, v in args.items() if k != "expected_selection_id"})
                self.assertEqual(missing_id.meta["logix-project-mcp/error"]["code"], "selection_changed")
                result = await client.call_tool("preview_change_proposal", args)
                self.assertFalse(result.isError, result.content)
                proposal = result.structuredContent
                approval = {"proposal": proposal, "expected_approval_id": proposal["approval_id"]}
                publish_selection(state, project)
                refreshed = await client.call_tool("validate_change_proposal", approval)
                self.assertEqual(refreshed.meta["logix-project-mcp/error"]["code"], "selection_changed")
                publish_selection(state, other)
                switched = await client.call_tool("validate_change_proposal", approval)
                self.assertEqual(switched.meta["logix-project-mcp/error"]["code"], "selection_changed")
                rejected_preview = await client.call_tool("preview_change_proposal", args)
                self.assertEqual(rejected_preview.meta["logix-project-mcp/error"]["code"], "selection_changed")
                self.assertEqual(project.read_bytes(), PROJECT)
                self.assertEqual(other.read_bytes(), PROJECT)
