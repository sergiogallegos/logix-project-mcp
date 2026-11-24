import hashlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree.ElementTree import Element, SubElement, fromstring, indent, tostring

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BASELINE = b"""<RSLogix5000Content TargetType="Controller" SoftwareRevision="38.02" Owner="First" ExportDate="Monday">
  <Controller Name="Fixture" ProcessorType="1756-L85E" MajorRev="38" TimeSlice="20" ProjectCreationDate="First save">
    <RedundancyInfo Enabled="false" />
    <Tags><Tag Name="Shared" DataType="DINT" />
      <Tag Name="OldTag" DataType="DINT" />
      <Tag Name="Value" DataType="DINT"><Data Format="L5K">7</Data>
        <Data Format="Decorated"><DataValue DataType="DINT" Value="7" /></Data>
      </Tag>
    </Tags>
    <Programs><Program Name="Main" MainRoutineName="Ladder">
      <Tags><Tag Name="Shared" DataType="BOOL" /></Tags>
      <Routines>
        <Routine Name="Ladder" Type="RLL"><RLLContent><Rung Number="0" Type="N">
          <Comment>Review this rung</Comment><Text>XIC(Shared)OTE(Ready);</Text>
        </Rung></RLLContent></Routine>
        <Routine Name="Code" Type="ST"><STContent><Line Number="0">  Value := 7;  </Line></STContent></Routine>
        <EncodedData Name="Locked" Type="ST" EncodedType="Routine">BASELINE_SECRET</EncodedData>
      </Routines>
    </Program><Program Name="Spare" /></Programs>
    <Tasks><Task Name="MainTask" Type="CONTINUOUS"><ScheduledPrograms>
      <ScheduledProgram Name="Main" /><ScheduledProgram Name="Spare" />
    </ScheduledPrograms></Task></Tasks>
  </Controller>
</RSLogix5000Content>"""


def fingerprint(data):
    return hashlib.sha256(data).hexdigest()


def round_trip() -> Element:
    root = fromstring(BASELINE)
    root.set("Owner", "Second")
    root.set("ExportDate", "Tuesday")
    controller = root.find("Controller")
    controller.set("ProjectCreationDate", "Second save")
    controller.set("LastModifiedDate", "Tuesday noon")
    controller.set("LastModifiedBy", "Second operator")
    controller.set("Use", "Target")
    tag = controller.find('Tags/Tag[@Name="Value"]')
    tag.remove(tag.find('Data[@Format="L5K"]'))
    tag.attrib = dict(reversed(list(tag.attrib.items())))
    controller.find('Programs/Program/Routines/EncodedData').text = "AFTER_SECRET"
    controller.find('Programs/Program/Routines/Routine').set("EditedDate", "Tuesday")
    indent(root, space="     ")
    return root


def changed() -> bytes:
    root = round_trip()
    controller = root.find("Controller")
    controller.set("TimeSlice", "30")
    controller.set("ProjectSN", "16#0000_0002")
    controller.find("RedundancyInfo").set("Enabled", "true")
    tags = controller.find("Tags")
    tags.remove(tags.find('Tag[@Name="OldTag"]'))
    tags.find('Tag[@Name="Value"]/Data/DataValue').set("Value", "8")
    main = controller.find('Programs/Program[@Name="Main"]')
    main.find('Tags/Tag[@Name="Shared"]').set("DataType", "DINT")
    SubElement(main.find("Tags"), "Tag", Name="NewTag", DataType="BOOL")
    main.find('Routines/Routine[@Name="Ladder"]/RLLContent/Rung/Text').text = "XIO(Shared)OTE(Ready);"
    main.find('Routines/Routine[@Name="Code"]/STContent/Line').text = "  Value := 8;  "
    schedule = controller.find("Tasks/Task/ScheduledPrograms")
    schedule[:] = reversed(list(schedule))
    SubElement(controller.find("Programs"), "Program", Name="NewProgram")
    return tostring(root)


class ComparisonTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_named_snapshots_and_scoped_review_over_stdio(self):
        with TemporaryDirectory() as directory:
            before = Path(directory) / "before" / "Fixture.L5X"
            after = Path(directory) / "after" / "Fixture.L5X"
            before.parent.mkdir()
            after.parent.mkdir()
            before.write_bytes(BASELINE)
            round_tripped = tostring(round_trip())
            after.write_bytes(round_tripped)
            launch = StdioServerParameters(
                command=sys.executable,
                args=["-m", "logix_project_mcp.server", "--project", str(before), "--compare-project", str(after)],
            )
            async with stdio_client(launch) as (reader, writer), ClientSession(reader, writer) as client:
                await client.initialize()
                tools = {tool.name: tool for tool in (await client.list_tools()).tools}
                self.assertIn("scope", tools["compare_projects"].inputSchema["properties"])
                capabilities = await client.call_tool("get_capabilities")
                self.assertEqual(capabilities.structuredContent["comparison_project"], {"file": "Fixture.L5X", "format": "l5x"})

                async def compare(**arguments):
                    result = await client.call_tool("compare_projects", arguments)
                    self.assertFalse(result.isError, result.content)
                    return result.structuredContent

                unchanged = await compare()
                self.assertEqual(unchanged["changes"], [])
                self.assertEqual(unchanged["before"]["file"], unchanged["after"]["file"])
                self.assertEqual(unchanged["before"]["controller"], unchanged["after"]["controller"])
                self.assertEqual(unchanged["before"]["source_sha256"], fingerprint(BASELINE))
                self.assertEqual(unchanged["after"]["source_sha256"], fingerprint(round_tripped))
                self.assertNotEqual(unchanged["before"]["source_sha256"], unchanged["after"]["source_sha256"])
                self.assertEqual([item["qualified_name"] for item in unchanged["protected_components"]], ["Program:Main.Locked"])

                candidate = changed()
                after.write_bytes(candidate)
                review = await compare()
                self.assertEqual(review["after"]["source_sha256"], fingerprint(candidate))
                changes = {item["component"]["qualified_name"]: item for item in review["changes"]}
                self.assertEqual(set(changes), {
                    "Fixture", "NewProgram", "MainTask", "OldTag", "Value", "Program:Main.Shared",
                    "Program:Main.NewTag", "Program:Main.Ladder", "Program:Main.Code",
                })
                self.assertEqual(changes["OldTag"]["change"], "removed")
                self.assertEqual(changes["Program:Main.NewTag"]["change"], "added")
                self.assertIn('TimeSlice="30"', changes["Fixture"]["xml_diff"])
                self.assertIn('ProjectSN="16#0000_0002"', changes["Fixture"]["xml_diff"])
                self.assertIn('Enabled="true"', changes["Fixture"]["xml_diff"])
                self.assertIn('Value="8"', changes["Value"]["xml_diff"])
                self.assertIn('Name="Spare"', changes["MainTask"]["xml_diff"])
                self.assertIn('-Rung 0  XIC(Shared)OTE(Ready);', changes["Program:Main.Ladder"]["source_diff"])
                self.assertIn('+Rung 0  XIO(Shared)OTE(Ready);', changes["Program:Main.Ladder"]["source_diff"])
                self.assertIn('+Line 0    Value := 8;  ', changes["Program:Main.Code"]["source_diff"])
                self.assertNotIn("BASELINE_SECRET", str(review))
                self.assertNotIn("AFTER_SECRET", str(review))

                program = await compare(scope={"kind": "program", "program": "mAiN"})
                self.assertTrue(all(item["component"]["program"] == "Main" for item in program["changes"]))
                controller = await compare(scope={"kind": "controller"})
                self.assertTrue(all(item["component"]["scope"] == "controller" for item in controller["changes"]))
                added = await compare(scope={"kind": "program", "program": "NewProgram"})
                self.assertEqual([(item["component"]["kind"], item["change"]) for item in added["changes"]], [("program", "added")])

                for arguments, code in (
                    ({"scope": {"kind": "program", "program": "Missing"}}, "not_found"),
                    ({"scope": {"kind": "controller", "program": "Main"}}, "invalid_arguments"),
                    ({"path": str(before)}, "invalid_arguments"),
                ):
                    invalid = await client.call_tool("compare_projects", arguments)
                    self.assertTrue(invalid.isError)
                    self.assertEqual(invalid.meta["logix-project-mcp/error"]["code"], code)

                self.assertEqual(before.read_bytes(), BASELINE)
                self.assertEqual(after.read_bytes(), candidate)
                duplicate = fromstring(candidate)
                SubElement(duplicate.find("Controller/Tags"), "Tag", Name="shared")
                after.write_bytes(tostring(duplicate))
                malformed = await client.call_tool("compare_projects")
                self.assertTrue(malformed.isError)
                self.assertEqual(malformed.meta["logix-project-mcp/error"]["code"], "invalid_project")
                after.unlink()
                absent = await client.call_tool("compare_projects")
                self.assertTrue(absent.isError)
                self.assertEqual(absent.meta["logix-project-mcp/error"]["code"], "project_unavailable")
                summary = await client.call_tool("get_project")
                self.assertFalse(summary.isError, summary.content)
                self.assertEqual(summary.structuredContent["source_sha256"], fingerprint(BASELINE))
