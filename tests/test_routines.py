import hashlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree.ElementTree import fromstring

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EXPORT = b"""<RSLogix5000Content SoftwareRevision="38.02" TargetType="Controller">
  <Controller Name="Sample"><Programs>
    <Program Name="Main"><Routines>
      <Routine Name="Ladder" Type="RLL"><Description>Ladder example</Description><RLLContent>
        <Rung Number="07" Type="N"><Comment><![CDATA[  Keep <this> comment
and its spacing  ]]></Comment><Text><![CDATA[  XIC(Ready)OTE(Done);  ]]></Text></Rung>
        <Rung Number="08" Type="N" />
      </RLLContent></Routine>
      <Routine Name="TextRoutine" Type="ST">
        <STContent OnlineEditType="Original">
          <Line Number="0"><![CDATA[  (* exact comment *)  ]]></Line>
          <Line Number="1"><![CDATA[\tIF Sample < 2 THEN  ]]></Line><Line Number="2" />
        </STContent>
        <STContent OnlineEditType="PendingEdits"><Line Number="1">pending</Line></STContent>
        <STContent OnlineEditType="TestEdits"><Line Number="1">tested</Line></STContent>
      </Routine>
      <Routine Name="Blocks" Type="FBD"><FBDContent SheetOrientation="Landscape">
        <Sheet Number="3"><Description>Sheet comment</Description>
          <Block ID="1" X="16" Y="25" Type="ADD" />
          <Wire FromID="1" FromParam="Dest" ToID="2" />
          <TextBox ID="3" X="100" Y="200"><Text><![CDATA[  diagram note  ]]></Text></TextBox>
        </Sheet>
      </FBDContent></Routine>
      <Routine Name="Chart" Type="SFC"><SFCContent>
        <Step ID="0" X="100" Y="150"><Action ID="1"><Body><STContent>
          <Line Number="0"><![CDATA[  Value := 1;  ]]></Line>
        </STContent></Body></Action></Step>
        <Transition ID="2" X="100" Y="225"><Condition><STContent><Line Number="0">Ready</Line></STContent></Condition></Transition>
        <DirectedLink FromID="0" ToID="2" />
      </SFCContent></Routine>
      <EncodedData EncodedType="Routine" Name="Vendor" Type="FBD">
        <Description>Visible description</Description>ENCODED_PAYLOAD
      </EncodedData>
      <Routine Name="Locked" Type="ST"><STContent><Line>PROTECTED_TEXT</Line></STContent>
        <EncryptedContent>LOCKED_PAYLOAD</EncryptedContent>
      </Routine>
      <Routine Name="Unknown" Type="Custom"><CustomContent>Raw fallback</CustomContent></Routine>
      <Routine Name="MissingContent" Type="ST" />
      <Routine Name="Empty" Type="ST"><STContent /></Routine>
    </Routines></Program>
    <Program Name="Other"><Routines>
      <Routine Name="Ladder" Type="RLL"><RLLContent><Rung Number="0"><Text>Other program</Text></Rung></RLLContent></Routine>
    </Routines></Program>
  </Programs></Controller>
</RSLogix5000Content>"""


class RoutineInspectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_inspection_over_stdio(self):
        with TemporaryDirectory() as directory:
            project = Path(directory) / "Routines.L5X"
            project.write_bytes(EXPORT)
            fingerprint = hashlib.sha256(EXPORT).hexdigest()
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "logix_project_mcp.server", "--project", str(project)],
            )
            async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as client:
                await client.initialize()
                tools = {tool.name: tool for tool in (await client.list_tools()).tools}
                tool = tools["read_routine"]
                self.assertEqual(set(tool.inputSchema["required"]), {"program", "routine"})
                self.assertIn("inspection", tool.outputSchema["required"])
                summary = await client.call_tool("get_project")
                self.assertFalse(summary.isError, summary.content)
                self.assertIn({"name": "Vendor", "type": "FBD"}, summary.structuredContent["programs"][0]["routines"])

                async def read(routine, program="Main", status="readable"):
                    result = await client.call_tool("read_routine", {"program": program, "routine": routine})
                    self.assertFalse(result.isError, result.content)
                    self.assertEqual(result.structuredContent["source_sha256"], fingerprint)
                    inspection = result.structuredContent["inspection"]
                    self.assertEqual(inspection["status"], status)
                    self.assertEqual(inspection["routine"].casefold(), routine.casefold())
                    self.assertEqual(inspection["program"].casefold(), program.casefold())
                    self.assertEqual(result.content[0].text, result.structuredContent["result"] or inspection["message"])
                    return result.structuredContent

                ladder = await read("ladder", "main")
                inspection = ladder["inspection"]
                self.assertEqual(inspection["qualified_name"], "Program:Main.Ladder")
                self.assertEqual((inspection["language"], inspection["description"]), ("RLL", "Ladder example"))
                rungs = inspection["sections"][0]["rungs"]
                self.assertEqual(rungs[0], {
                    "number": "07", "type": "N", "text": "  XIC(Ready)OTE(Done);  ",
                    "comment": "  Keep <this> comment\nand its spacing  ",
                })
                self.assertEqual(fromstring(ladder["result"]).findtext("RLLContent/Rung/Text"), rungs[0]["text"])
                self.assertIsNone(rungs[1]["text"])
                self.assertIsNone(rungs[1]["comment"])
                other = (await read("Ladder", "Other"))["inspection"]
                self.assertEqual(other["qualified_name"], "Program:Other.Ladder")
                self.assertEqual(other["sections"][0]["rungs"][0]["text"], "Other program")

                st = (await read("TextRoutine"))["inspection"]
                self.assertEqual(st["language"], "ST")
                original, pending, tested = st["sections"]
                self.assertEqual(original["lines"], [
                    {"number": "0", "text": "  (* exact comment *)  "},
                    {"number": "1", "text": "\tIF Sample < 2 THEN  "},
                    {"number": "2", "text": ""},
                ])
                self.assertEqual(
                    [section["attributes"]["OnlineEditType"] for section in st["sections"]],
                    ["Original", "PendingEdits", "TestEdits"],
                )
                self.assertEqual(pending["lines"][0]["text"], "pending")
                self.assertEqual(tested["lines"][0]["text"], "tested")

                fbd = (await read("Blocks"))["inspection"]
                self.assertEqual(fbd["language"], "FBD")
                sheet, = fbd["sections"][0]["elements"]
                self.assertEqual((sheet["kind"], sheet["attributes"]["Number"]), ("Sheet", "3"))
                description, block, wire, text_box = sheet["children"]
                self.assertEqual(description["text"], "Sheet comment")
                self.assertEqual((block["attributes"]["X"], block["attributes"]["Y"]), ("16", "25"))
                self.assertEqual(wire["attributes"], {"FromID": "1", "FromParam": "Dest", "ToID": "2"})
                self.assertEqual(text_box["children"][0]["text"], "  diagram note  ")

                sfc = (await read("Chart"))["inspection"]
                self.assertEqual(sfc["language"], "SFC")
                step, transition, link = sfc["sections"][0]["elements"]
                self.assertEqual((step["kind"], transition["attributes"]["Y"]), ("Step", "225"))
                action = step["children"][0]
                body, = action["children"]
                content, = body["children"]
                self.assertEqual(content["children"][0]["text"], "  Value := 1;  ")
                self.assertEqual(link["attributes"], {"FromID": "0", "ToID": "2"})

                for name, description in (("Vendor", "Visible description"), ("Locked", None)):
                    protected = await read(name, status="protected")
                    self.assertEqual(protected["inspection"]["sections"], [])
                    self.assertEqual(protected["inspection"]["description"], description)
                    self.assertEqual(protected["result"], "")
                    self.assertIsNotNone(protected["inspection"]["message"])

                unsupported = await read("Unknown", status="unsupported")
                self.assertIn("Raw fallback", unsupported["result"])
                self.assertEqual(unsupported["inspection"]["sections"], [])
                absent = (await read("MissingContent", status="unsupported"))["inspection"]
                self.assertIn("STContent", absent["message"])
                empty = (await read("Empty"))["inspection"]
                self.assertEqual(empty["sections"], [{"attributes": {}, "lines": []}])
            self.assertEqual(project.read_bytes(), EXPORT)
