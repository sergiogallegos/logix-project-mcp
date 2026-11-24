import hashlib
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EXPORT = b"""<RSLogix5000Content SoftwareRevision="38.02" TargetType="Controller">
  <Controller Name="Sample" ProcessorType="1756-L85E" MajorRev="38" MinorRev="11">
    <Description>Inventory sample</Description>
    <DataTypes>
      <DataType Name="Part" Class="User" Family="NoFamily"><Members>
        <Member Name="Backing" DataType="SINT" Dimension="0" Hidden="true" />
        <Member Name="Valid" DataType="BIT" Target="Backing" BitNumber="2" Hidden="false" />
      </Members></DataType>
      <DataType Name="ModuleInput" Class="IO" />
    </DataTypes>
    <Modules><Module Name="Local" CatalogNumber="1756-L85E" Major="38" Minor="11">
      <Ports><Port Id="1" Address="0" Type="ICP" Upstream="false" /></Ports>
    </Module><Module Name="InputModule" ParentModule="Local" ParentModPortId="1" Inhibited="true" /></Modules>
    <AddOnInstructionDefinitions>
      <AddOnInstructionDefinition Name="Filter" Revision="1.2" Vendor="Sample Vendor">
        <Parameters><Parameter Name="Input" DataType="REAL" Usage="Input" Required="true" Visible="true" /></Parameters>
      </AddOnInstructionDefinition>
      <EncodedData EncodedType="AddOnInstructionDefinition" Name="VendorBlock" Revision="2.0">
        <Description>Public instruction description</Description>
        ENCODED_INSTRUCTION_BYTES
      </EncodedData>
      <AddOnInstructionDefinition Name="LockedBlock" IsEncrypted="true">
        <EncryptedAOIContent>LOCKED_INSTRUCTION_BYTES</EncryptedAOIContent>
      </AddOnInstructionDefinition>
    </AddOnInstructionDefinitions>
    <Tags><Tag Name="Shared" DataType="Part" TagType="Base"><Data>SAVED_TAG_VALUE</Data></Tag></Tags>
    <Programs>
      <Program Name="Main" MainRoutineName="Run" Disabled="false">
        <Tags><Tag Name="Shared" TagType="Alias" AliasFor="Local:1:I.Data.0" /></Tags>
        <Routines>
          <Routine Name="Run" Type="RLL"><RLLContent><Rung><Text>VISIBLE_LOGIC_BODY</Text></Rung></RLLContent></Routine>
          <EncodedData EncodedType="Routine" Name="VendorLogic" Type="SFC">ENCODED_ROUTINE_BYTES</EncodedData>
          <Routine Name="Locked" Type="ST"><EncryptedContent>LOCKED_ROUTINE_BYTES</EncryptedContent></Routine>
        </Routines>
        <ChildPrograms><ChildProgram Name="Child" /></ChildPrograms>
      </Program>
      <Program Name="Diagnostics"><Tags><Tag Name="Shared" DataType="BOOL" /></Tags>
        <Routines><Routine Name="Run" Type="ST" /></Routines>
      </Program>
      <Program Name="Child" />
    </Programs>
    <Tasks>
      <Task Name="Fast" Type="PERIODIC" Rate="2.500" Priority="4" Watchdog="100" InhibitTask="false">
        <ScheduledPrograms><ScheduledProgram Name="Diagnostics" /><ScheduledProgram Name="Main" /></ScheduledPrograms>
      </Task>
      <Task Name="Triggered" Type="EVENT"><EventInfo EventTrigger="Consumed Tag" EventTag="Shared" EnableTimeout="true" /></Task>
    </Tasks>
  </Controller>
</RSLogix5000Content>"""


class InventoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_inventory_over_stdio(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "Sample.L5X"
            path.write_bytes(EXPORT)
            server = StdioServerParameters(
                command=sys.executable,
                args=["-m", "logix_project_mcp.server", "--project", str(path)],
            )
            async with stdio_client(server) as (reader, writer), ClientSession(reader, writer) as client:
                await client.initialize()
                tools = {tool.name: tool for tool in (await client.list_tools()).tools}
                tool = tools["get_inventory"]
                self.assertEqual(tool.inputSchema["properties"], {})
                self.assertIn("programs", tool.outputSchema["required"])
                invalid = await client.call_tool("get_inventory", {"program": "Main"})
                self.assertTrue(invalid.isError)
                self.assertEqual(invalid.meta["logix-project-mcp/error"]["code"], "invalid_arguments")

                response = await client.call_tool("get_inventory")
                self.assertFalse(response.isError, response.content)
                inventory = response.structuredContent
                self.assertEqual(json.loads(response.content[0].text), inventory)
                self.assertEqual(inventory["file"], "Sample.L5X")
                self.assertEqual(inventory["format"], "l5x")
                self.assertEqual(inventory["software_revision"], "38.02")
                self.assertEqual(inventory["source_sha256"], hashlib.sha256(EXPORT).hexdigest())
                self.assertEqual(inventory["controller"], {
                    "name": "Sample", "description": "Inventory sample", "processor_type": "1756-L85E",
                    "major_revision": "38", "minor_revision": "11",
                })
                periodic, event = inventory["tasks"]
                self.assertEqual(periodic["scheduled_programs"], ["Diagnostics", "Main"])
                self.assertEqual((periodic["rate"], periodic["priority"], periodic["watchdog"]), ("2.500", "4", "100"))
                self.assertIs(periodic["inhibited"], False)
                self.assertIsNone(periodic["event"])
                self.assertEqual(event["event"], {"trigger": "Consumed Tag", "tag": "Shared", "timeout_enabled": True})
                self.assertEqual(event["scheduled_programs"], [])
                self.assertIsNone(event["rate"])

                main, diagnostics, child = inventory["programs"]
                tag = inventory["controller_tags"][0]
                self.assertEqual((tag["scope"], tag["qualified_name"], tag["data_type"]), ("controller", "Shared", "Part"))
                self.assertEqual(main["tags"][0]["scope"], "program")
                self.assertEqual(main["tags"][0]["qualified_name"], "Program:Main.Shared")
                self.assertEqual(main["tags"][0]["alias_for"], "Local:1:I.Data.0")
                self.assertEqual(diagnostics["tags"][0]["qualified_name"], "Program:Diagnostics.Shared")
                self.assertEqual(main["child_programs"], ["Child"])
                self.assertEqual(child["tags"], [])
                self.assertEqual(child["routines"], [])
                self.assertIsNone(child["main_routine"])
                self.assertEqual(main["main_routine"], "Run")
                self.assertEqual(diagnostics["routines"][0]["qualified_name"], "Program:Diagnostics.Run")
                self.assertEqual([(item["qualified_name"], item["protected"]) for item in main["routines"]], [
                    ("Program:Main.Run", False), ("Program:Main.VendorLogic", True), ("Program:Main.Locked", True),
                ])

                local, child_module = inventory["modules"]
                self.assertEqual(local["catalog_number"], "1756-L85E")
                self.assertEqual(local["ports"], [{"id": "1", "address": "0", "type": "ICP", "upstream": False}])
                self.assertEqual((child_module["parent_module"], child_module["parent_port_id"]), ("Local", "1"))
                self.assertIs(child_module["inhibited"], True)
                data_type, = inventory["user_defined_types"]
                self.assertEqual(data_type["name"], "Part")
                backing, bit = data_type["members"]
                self.assertIs(backing["hidden"], True)
                self.assertEqual((bit["data_type"], bit["target"], bit["bit_number"]), ("BIT", "Backing", "2"))
                clear, encoded, locked = inventory["add_on_instructions"]
                self.assertEqual((clear["name"], clear["revision"], clear["protected"]), ("Filter", "1.2", False))
                self.assertIs(clear["parameters"][0]["required"], True)
                self.assertEqual((encoded["name"], encoded["revision"], encoded["protected"]), ("VendorBlock", "2.0", True))
                self.assertEqual(encoded["description"], "Public instruction description")
                self.assertEqual(encoded["parameters"], [])
                self.assertIs(locked["protected"], True)
                for payload in (
                    "SAVED_TAG_VALUE", "VISIBLE_LOGIC_BODY", "ENCODED_INSTRUCTION_BYTES",
                    "LOCKED_INSTRUCTION_BYTES", "ENCODED_ROUTINE_BYTES", "LOCKED_ROUTINE_BYTES",
                ):
                    self.assertNotIn(payload, response.content[0].text)
                self.assertEqual(path.read_bytes(), EXPORT)

                minimal = b'<RSLogix5000Content><Controller Name="Empty" /></RSLogix5000Content>'
                path.write_bytes(minimal)
                response = await client.call_tool("get_inventory")
                self.assertFalse(response.isError, response.content)
                inventory = response.structuredContent
                self.assertIsNone(inventory["software_revision"])
                self.assertIsNone(inventory["controller"]["processor_type"])
                for section in ("tasks", "programs", "controller_tags", "modules", "user_defined_types", "add_on_instructions"):
                    self.assertEqual(inventory[section], [])
                self.assertEqual(inventory["source_sha256"], hashlib.sha256(minimal).hexdigest())
