import asyncio
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from logix_project_mcp import native_review as native
from logix_project_mcp.project import ProjectReadError, ProjectSnapshot, parse_l5x, parse_l5x_bytes, read_project
from logix_project_mcp.proposals import create_proposal
from logix_project_mcp.selection import ProjectSelection


TARGET = {"kind": "routine", "program": "MainProgram", "name": "InspectText"}
NOTE = "Reviewed <text> & ]]> ✓"
OPERATIONS = [{"operation": "set_description", "target": TARGET, "description": NOTE}]
FULL = (b'<RSLogix5000Content TargetType="Controller" SoftwareRevision="38.02"><Controller Name="Sample">'
        b'<Programs><Program Name="MainProgram"><Routines><Routine Name="InspectText" Type="ST">'
        b'<STContent><Line Number="0">count := 0;</Line></STContent></Routine></Routines></Program>'
        b'</Programs></Controller></RSLogix5000Content>')
COMPONENT = FULL.replace(b'TargetType="Controller"', b'TargetType="Routine" TargetName="InspectText"').replace(
    b'<Routine Name=', b'<Routine Use="Target" Name=')


class NativeReviewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(TemporaryDirectory()))
        self.source = self.folder / "Source.ACD"
        self.source.write_bytes(FULL)
        self.destination = self.folder / "Export"
        self.selection = ProjectSelection(self.source)
        root = parse_l5x(self.source)
        snap = ProjectSnapshot(root, root.find("Controller"), native.sha256_file(self.source))
        self.proposal = create_proposal(self.selection, snap, OPERATIONS)
        self.enterContext(patch.object(native, "sys", Mock(platform="win32")))
        self.enterContext(patch.object(native, "export_snapshot", self.export))
        self.importer = self.enterContext(patch.object(native, "run_sdk_worker", side_effect=self.import_xml))
        self.build = self.enterContext(patch.object(native, "check_build", return_value={"status": "passed"}))

    async def export(self, acd, output, name, xpath=None):
        output.write_bytes(COMPONENT if xpath else acd.read_bytes())

    async def import_xml(self, name, action, mode, acd, component, xpath):
        self.assertEqual((action, mode, xpath), ("import", "--import-routine",
                                                "Controller/Programs/Program[@Name='MainProgram']/Routines"))
        self.assertNotEqual(Path(acd), self.source)
        data = Path(component).read_bytes()
        start, end = data.index(b"<Description>"), data.index(b"</Description>") + len(b"</Description>")
        Path(acd).write_bytes(FULL.replace(b"<STContent>", data[start:end] + b"<STContent>"))

    async def publish(self, confirm=lambda _: True, current=None):
        return await native.publish_native(current or (lambda: self.selection), self.proposal,
                                           self.proposal["approval_id"], self.destination, confirm)

    async def test_concurrent_reviews_publish_one_complete_pair(self):
        results = await asyncio.gather(self.publish(), self.publish(), return_exceptions=True)
        result, = [value for value in results if isinstance(value, dict)]
        self.assertEqual([e.code for e in results if isinstance(e, ProjectReadError)], ["destination_exists"])
        self.assertEqual({p.name for p in self.destination.iterdir()}, {"Reviewed.ACD", "Routine.L5X"})
        for fmt, name in result["outputs"].items():
            path = Path(name)
            self.assertEqual(native.sha256_file(path), result["sha256"][fmt])
            self.assertEqual(parse_l5x(path).findtext(".//Routine/Description"), NOTE)
        with self.assertRaisesRegex(ProjectReadError, "new output directory"):
            await self.publish()
        self.assertEqual(result["sha256"], {k: native.sha256_file(Path(v)) for k, v in result["outputs"].items()})
        self.assertEqual(self.source.read_bytes(), FULL)
        self.assertEqual(result["build"]["status"], "passed")

    async def test_build_error_prevents_native_publication(self):
        self.build.return_value = {"status": "failed", "diagnostics": ["Synthetic compiler diagnostic"]}
        with self.assertRaisesRegex(ProjectReadError, "Synthetic compiler diagnostic"):
            await self.publish()
        self.assertEqual(list(self.folder.iterdir()), [self.source])
        self.assertEqual(self.source.read_bytes(), FULL)

    async def test_component_changed_during_build_prevents_publication(self):
        async def alter_component(acd, digest, *, known_revision):
            acd.with_name("Routine.L5X").write_bytes(b"altered")
            return {"status": "passed"}
        self.build.side_effect = alter_component
        with self.assertRaisesRegex(ProjectReadError, "changed before publication"):
            await self.publish()
        self.assertEqual(list(self.folder.iterdir()), [self.source])

    def test_readback_preserves_unrelated_aoi_and_opaque_content(self):
        aoi = (b'<AddOnInstructionDefinitions><AddOnInstructionDefinition Name="Example" Revision="1.0"/>'
               b'<EncodedData EncodedType="AddOnInstructionDefinition"> <Blob>opaque data</Blob></EncodedData>'
               b'</AddOnInstructionDefinitions>')
        source = FULL.replace(b"<Programs>", aoi + b"<Programs>")
        reviewed = source.replace(b"<STContent>", b"<Description>Approved</Description><STContent>")
        proposal = {"preview": [{"after": "Approved"}]}
        native.verify_readback(parse_l5x_bytes(source), parse_l5x_bytes(reviewed), TARGET, proposal)
        for changed in (reviewed.replace(b'1.0"', b'2.0"'), reviewed.replace(b"opaque data", b"modified data"),
                        reviewed.replace(b" <Blob>", b"  <Blob>")):
            with self.assertRaisesRegex(ProjectReadError, "outside the reviewed description"):
                native.verify_readback(parse_l5x_bytes(source), parse_l5x_bytes(changed), TARGET, proposal)
        signed = reviewed.replace(b"</RSLogix5000Content>", b"<SafetySignature/></RSLogix5000Content>")
        with self.assertRaises(ProjectReadError) as rejected:
            native.verify_readback(parse_l5x_bytes(source), parse_l5x_bytes(signed), TARGET, proposal)
        self.assertEqual(rejected.exception.code, "unsupported_safety_content")

    async def test_failed_or_cancelled_import_never_publishes(self):
        self.assertIsNone(await self.publish(lambda _: False))
        self.importer.assert_not_awaited()
        for failure in (ProjectReadError("sdk_error", "import failed"), asyncio.CancelledError()):
            self.importer.side_effect = failure
            with self.assertRaises(type(failure)):
                await self.publish()
            self.assertEqual(list(self.folder.iterdir()), [self.source])
            self.assertEqual(self.source.read_bytes(), FULL)

    async def test_new_save_and_selection_switch_during_review(self):
        def save(_):
            self.source.write_bytes(FULL + b" ")
            return True

        with self.assertRaisesRegex(ProjectReadError, "changed during"):
            await self.publish(save)
        self.importer.assert_not_awaited()
        with self.assertRaisesRegex(ProjectReadError, "changed after preview"):
            await self.publish()
        self.assertEqual(self.source.read_bytes(), FULL + b" ")
        self.source.write_bytes(FULL)
        changed = ProjectSelection(self.source, "a" * 32)
        with self.assertRaisesRegex(ProjectReadError, "selection changed"):
            await self.publish(current=Mock(side_effect=[self.selection, changed]))
        self.assertEqual(list(self.folder.iterdir()), [self.source])

    async def test_source_saved_during_import_and_late_destination_collision(self):
        async def late_save(*args):
            await self.import_xml(*args)
            self.source.write_bytes(FULL + b" ")

        self.importer.side_effect = late_save
        with self.assertRaisesRegex(ProjectReadError, "source changed"):
            await self.publish()
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.source.read_bytes(), FULL + b" ")
        self.source.write_bytes(FULL)

        async def late_collision(*args):
            await self.import_xml(*args)
            self.destination.mkdir()
            (self.destination / "Reviewed.ACD").write_bytes(b"prior output")

        self.importer.side_effect = late_collision
        with self.assertRaisesRegex(ProjectReadError, "occupied"):
            await self.publish()
        self.assertEqual((self.destination / "Reviewed.ACD").read_bytes(), b"prior output")
        self.assertFalse((self.destination / "Routine.L5X").exists())

    async def test_verification_rejects_wrong_revision_logic_text_and_identity(self):
        async def wrong_import(*args):
            await self.import_xml(*args)
            path = Path(args[3])
            path.write_bytes(path.read_bytes().replace(original, replacement))

        self.importer.side_effect = wrong_import
        for original, replacement in ((b"38.02", b"38.01"), (b"count := 0", b"count := 1"), (b"Reviewed", b"Other")):
            with self.assertRaises(ProjectReadError):
                await self.publish()
            self.assertFalse(self.destination.exists())
        self.proposal["approval_id"] = "0" * 64
        with self.assertRaisesRegex(ProjectReadError, "approval identity"):
            await self.publish()
        self.assertEqual(self.source.read_bytes(), FULL)


@unittest.skipUnless(sys.platform == "win32" and os.getenv("LOGIX_PROJECT_MCP_TEST_NATIVE_OUTPUT_ACD"),
                     "Synthetic Windows SDK routine documentation sample required")
class NativeSdkTests(unittest.IsolatedAsyncioTestCase):
    async def test_reopened_native_and_component(self):
        source = Path(os.environ["LOGIX_PROJECT_MCP_TEST_NATIVE_OUTPUT_ACD"]).resolve()
        selection = ProjectSelection(source)
        fingerprint = native.sha256_file(source)
        snapshot = await read_project(source)
        proposal = create_proposal(selection, snapshot, [{**OPERATIONS[0], "description": "Native review sample"}])
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "Approved"
            receipt = await native.publish_native(lambda: selection, proposal, proposal["approval_id"], output,
                                                  lambda _: True)
            self.assertEqual(receipt["build"]["status"], "passed")
            self.assertEqual(receipt["build"]["artifact_sha256"], receipt["sha256"]["acd"])
            for kind, filename in receipt["outputs"].items():
                self.assertEqual(native.sha256_file(Path(filename)), receipt["sha256"][kind])
            self.assertEqual(parse_l5x(output / "Routine.L5X").findtext(".//Routine[@Use='Target']/Description"),
                             "Native review sample")
        self.assertEqual(native.sha256_file(source), fingerprint)
