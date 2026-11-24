import hashlib
import sys
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EXPORT = b"""<RSLogix5000Content SoftwareRevision="38.02" TargetType="Controller">
<Controller Name="Sample">
  <Description>Controller Marker</Description>
  <DataTypes><DataType Name="State" Class="User" /></DataTypes>
  <AddOnInstructionDefinitions><AddOnInstructionDefinition Name="Filter" /></AddOnInstructionDefinitions>
  <Tags>
    <Tag Name="Shared" DataType="DINT"><Description>Global Marker</Description></Tag>
    <Tag Name="SharedReset" DataType="DINT" />
    <Tag Name="GlobalAlias" TagType="Alias" AliasFor="Shared" />
    <Tag Name="MiddleAlias" TagType="Alias" AliasFor="GlobalAlias" />
    <Tag Name="CycleA" TagType="Alias" AliasFor="CycleB" />
    <Tag Name="CycleB" TagType="Alias" AliasFor="CycleA" />
    <Tag Name="Values" DataType="State" />
  </Tags>
  <Programs>
    <Program Name="Main">
      <Tags>
        <Tag Name="Shared" DataType="DINT" />
        <Tag Name="LocalAlias" AliasFor="Shared" />
        <Tag Name="Callee" DataType="DINT" />
      </Tags>
      <Routines>
        <Routine Name="Run" Type="RLL"><RLLContent>
          <Rung Number="7"><Comment>Rung Marker</Comment><Text><![CDATA[XIC(Shared)XIC(SharedReset)XIC(LocalAlias)XIC(MiddleAlias)XIC(Program:Main.Shared)XIC(Values[Shared].Shared)JSR(Callee,0)Filter(Values)XIC(CycleA);]]></Text></Rung>
        </RLLContent></Routine>
        <Routine Name="Callee" Type="ST"><STContent OnlineEditType="PendingEdits">
          <Line Number="0"><![CDATA[// Marker Shared]]></Line>
          <Line Number="1"><![CDATA[(* multiline comment]]></Line>
          <Line Number="2"><![CDATA[Shared *) LocalAlias := 1;]]></Line>
          <Line Number="3"><![CDATA['Shared $' escaped Shared'; Shared := 2;]]></Line>
          <Line Number="4"><![CDATA[// MarkerReset only]]></Line>
          <Line Number="5"><![CDATA[/* Shared */ LocalAlias := 3;]]></Line>
        </STContent></Routine>
        <Routine Name="Blocks" Type="FBD"><FBDContent><Sheet Number="2">
          <IRef ID="5" Operand="Shared" />
          <TextBox ID="6"><Text>Diagram Marker</Text></TextBox>
        </Sheet></FBDContent></Routine>
        <Routine Name="Chart" Type="SFC"><SFCContent><Step ID="2"><Action ID="3"><Body><STContent>
          <Line Number="4"><![CDATA[LocalAlias := 4;]]></Line>
        </STContent></Body></Action></Step></SFCContent></Routine>
        <EncodedData Name="Vendor" EncodedType="Routine" Type="ST">Shared Marker</EncodedData>
        <Routine Name="Locked" Type="ST"><STContent><Line>// Marker Shared</Line><Line>Shared := 99;</Line></STContent>
          <EncryptedContent>Shared Marker</EncryptedContent>
        </Routine>
      </Routines>
    </Program>
    <Program Name="Other"><Routines>
      <Routine Name="Run" Type="ST"><STContent><Line Number="8"><![CDATA[Shared := Program:Main.Shared; Program:Missing.Shared := 0;]]></Line></STContent></Routine>
    </Routines></Program>
  </Programs>
</Controller></RSLogix5000Content>"""


@asynccontextmanager
async def session(project):
    launch = StdioServerParameters(
        command=sys.executable,
        args=["-m", "logix_project_mcp.server", "--project", str(project)],
    )
    async with stdio_client(launch) as (reader, writer), ClientSession(reader, writer) as client:
        await client.initialize()
        yield client


class SearchTests(unittest.IsolatedAsyncioTestCase):
    async def call(self, client, tool, **arguments):
        reply = await client.call_tool(tool, arguments)
        self.assertFalse(reply.isError, reply.content)
        return reply.structuredContent

    async def test_scopes_aliases_and_exact_matches_through_stdio(self):
        with TemporaryDirectory() as directory:
            project = Path(directory) / "Search.L5X"
            project.write_bytes(EXPORT)
            async with session(project) as client:
                tools = {tool.name: tool for tool in (await client.list_tools()).tools}
                self.assertEqual(tools["search_project"].inputSchema["required"], ["query"])
                self.assertEqual(tools["find_references"].inputSchema["required"], ["name"])

                tags = await self.call(client, "search_project", query="shared", kind="tag")
                self.assertEqual(tags["source_sha256"], hashlib.sha256(EXPORT).hexdigest())
                self.assertEqual(tags["software_revision"], "38.02")
                self.assertEqual(
                    [item["symbol"]["qualified_name"] for item in tags["matches"]], ["Shared", "Program:Main.Shared"],
                )
                filtered = await self.call(client, "search_project", query="SHARED", kind="tag", program="main")
                self.assertEqual([item["location"]["scope"] for item in filtered["matches"]], ["program"])
                prefix = await self.call(client, "search_project", query="Share")
                self.assertEqual(prefix["matches"], [])
                routines = await self.call(client, "search_project", query="Run", kind="routine")
                self.assertEqual([item["location"]["program"] for item in routines["matches"]], ["Main", "Other"])
                symbols = await self.call(client, "search_project", query="State", kind="symbol")
                self.assertEqual(symbols["matches"][0]["symbol"]["kind"], "data_type")

                local = (await self.call(client, "find_references", name="Shared", program="MAIN"))["matches"]
                self.assertEqual(len(local), 11)
                alias = next(item for item in local if item["reference_kind"] == "alias_target")
                self.assertEqual(alias["location"]["declaration"], "LocalAlias")
                ladder = [item for item in local if item["location"]["rung"] == "7"]
                self.assertEqual(len(ladder), 4)
                self.assertTrue(all(item["location"]["column"] for item in ladder))
                self.assertEqual([item["symbol"]["name"] for item in ladder], ["Shared", "LocalAlias", "Shared", "Shared"])
                self.assertEqual(ladder[1]["alias_targets"][0]["qualified_name"], "Program:Main.Shared")
                st = [item for item in local if item["location"]["routine"] == "Callee"]
                self.assertEqual([item["location"]["line"] for item in st], ["2", "3", "5"])
                self.assertTrue(all(item["location"]["online_edit_type"] == "PendingEdits" for item in st))
                blocks = next(item for item in local if item["location"]["routine"] == "Blocks")
                self.assertEqual((blocks["location"]["sheet"], blocks["location"]["element_id"]), ("2", "5"))
                chart = next(item for item in local if item["location"]["routine"] == "Chart")
                self.assertEqual((chart["location"]["line"], chart["location"]["element_id"]), ("4", "3"))
                explicit = next(item for item in local if item["location"]["program"] == "Other")
                self.assertEqual(explicit["symbol"]["qualified_name"], "Program:Main.Shared")

                global_refs = (await self.call(client, "find_references", name="Shared"))["matches"]
                self.assertEqual(len(global_refs), 4)
                chain = next(item for item in global_refs if item["symbol"]["name"] == "MiddleAlias")
                self.assertEqual([item["name"] for item in chain["alias_targets"]], ["GlobalAlias", "Shared"])
                cycle = (await self.call(client, "find_references", name="CycleA"))["matches"]
                operand = next(item for item in cycle if item["reference_kind"] == "operand")
                self.assertEqual([item["name"] for item in operand["alias_targets"]], ["CycleB"])
                self.assertEqual((await self.call(client, "find_references", name="Callee", program="Main"))["matches"], [])
                for name, kind, reference_kind, program in (
                    ("Callee", "routine", "routine_call", "Main"),
                    ("Filter", "add_on_instruction", "instruction_call", None),
                    ("State", "data_type", "data_type", None),
                ):
                    with self.subTest(symbol=name):
                        result = await self.call(client, "find_references", name=name, kind=kind, program=program)
                        self.assertEqual([item["reference_kind"] for item in result["matches"]], [reference_kind])
                comments = (await self.call(client, "search_project", query="Marker", kind="comment"))["matches"]
                self.assertEqual([item["excerpt"] for item in comments], [
                    "Controller Marker", "Global Marker", "Rung Marker", "// Marker Shared", "Diagram Marker",
                ])
                self.assertTrue(all(item["location"]["routine"] not in {"Vendor", "Locked"} for item in local + comments))
            self.assertEqual(project.read_bytes(), EXPORT)

    async def test_pagination_is_bounded_and_checks_snapshot_fingerprint(self):
        rungs = "".join(f'<Rung Number="{n}"><Text>XIC(BulkTag);</Text></Rung>' for n in range(230))
        contents = (
            '<RSLogix5000Content><Controller Name="Sample"><Tags><Tag Name="BulkTag" /></Tags>'
            '<Programs><Program Name="Main"><Routines><Routine Name="Bulk" Type="RLL"><RLLContent>'
            f'{rungs}</RLLContent></Routine></Routines></Program></Programs></Controller></RSLogix5000Content>'
        ).encode()
        with TemporaryDirectory() as directory:
            project = Path(directory) / "Bulk.L5X"
            project.write_bytes(contents)
            async with session(project) as client:
                first = await self.call(client, "find_references", name="BulkTag", limit=200)
                self.assertEqual(len(first["matches"]), 200)
                self.assertEqual(first["next_offset"], 200)
                second = await self.call(
                    client, "find_references", name="BulkTag", limit=200, offset=first["next_offset"],
                    expected_source_sha256=first["source_sha256"],
                )
                self.assertEqual(len(second["matches"]), 30)
                self.assertIsNone(second["next_offset"])
                self.assertEqual([item["location"]["rung"] for item in first["matches"] + second["matches"]],
                                 [str(n) for n in range(230)])
                for tool, args, code in (
                    ("find_references", {"name": "BulkTag", "limit": 201}, "invalid_arguments"),
                    ("find_references", {"name": "Missing"}, "not_found"),
                    ("search_project", {"query": " \t "}, "invalid_arguments"),
                ):
                    reply = await client.call_tool(tool, args)
                    self.assertTrue(reply.isError)
                    self.assertEqual(reply.meta["logix-project-mcp/error"]["code"], code)
                project.write_bytes(contents.replace(b'Name="Sample"', b'Name="Updated"'))
                stale = await client.call_tool("find_references", {
                    "name": "BulkTag", "offset": 200, "expected_source_sha256": first["source_sha256"],
                })
                self.assertTrue(stale.isError)
                self.assertEqual(stale.meta["logix-project-mcp/error"]["code"], "project_changed")
