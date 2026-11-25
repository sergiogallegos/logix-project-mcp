import json
import unittest
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from logix_project_mcp import build_check
from logix_project_mcp.project import ProjectReadError


FULL = b'<RSLogix5000Content TargetType="Controller" SoftwareRevision="38.02"><Controller/></RSLogix5000Content>'


class BuildCheckTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        folder = Path(self.enterContext(TemporaryDirectory()))
        self.artifact = folder / "Reviewed.L5X"
        self.artifact.write_bytes(FULL)
        self.enterContext(patch.object(build_check, "sys", Mock(platform="win32")))
        self.enterContext(patch.object(build_check, "find_spec", return_value=object()))
        self.worker = self.enterContext(patch.object(build_check, "run_sdk_worker", side_effect=self.build))
        self.error = None
        self.log = "[date][WARN][Project] A sample warning\n"

    async def build(self, name, action, flag, source, result):
        self.assertEqual((action, flag), ("build", "--build"))
        self.assertEqual(Path(source).read_bytes(), self.artifact.read_bytes())
        self.assertNotEqual(Path(source), self.artifact)
        Path(source).write_bytes(b"compiled cache")
        Path(result).write_text(json.dumps({"error": self.error}), encoding="utf-8")
        Path(result).with_suffix(".log").write_text(self.log, encoding="utf-8")

    async def check(self):
        return await build_check.check_build(self.artifact, sha256(self.artifact.read_bytes()).hexdigest())

    async def test_compiler_result_and_diagnostics_are_bound_to_original_bytes(self):
        report = await self.check()
        self.assertEqual(report, {"status": "passed", "artifact_sha256": sha256(FULL).hexdigest(),
                                  "software_revision": "38.02", "diagnostics": ["A sample warning"]})
        self.assertEqual(self.artifact.read_bytes(), FULL)
        self.log *= 31
        self.log += "[date][ERROR][Project] Unexpected token\n"
        report = await self.check()
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["diagnostics"][0], "Unexpected token")
        self.log = "[date][INFO][Project] ImportLog <Exception Severity='Error' Line='10'>\n"
        self.assertEqual((await self.check())["status"], "failed")
        self.error = "build: RxSTX_E_UNEXPECTED_TOKEN"
        self.assertIn(self.error, (await self.check())["diagnostics"])

    async def test_manual_and_invalid_inputs_do_not_run_compiler(self):
        self.artifact.write_bytes(FULL.replace(b"38.02", b"35.00"))
        self.assertEqual((await self.check())["status"], "manual_required")
        self.artifact.write_bytes(FULL.replace(b'="Controller"', b'="Routine"'))
        with self.assertRaises(ProjectReadError):
            await self.check()
        self.artifact.write_bytes(FULL)
        with patch.object(build_check, "find_spec", return_value=None):
            self.assertEqual((await self.check())["status"], "manual_required")
        with self.assertRaisesRegex(ProjectReadError, "retained SHA-256"):
            await build_check.check_build(self.artifact, "0" * 64)
        self.worker.assert_not_awaited()

    async def test_save_during_compilation_invalidates_result(self):
        async def save(*args):
            await self.build(*args)
            self.artifact.write_bytes(FULL + b" ")
        self.worker.side_effect = save
        with self.assertRaisesRegex(ProjectReadError, "changed during"):
            await self.check()
