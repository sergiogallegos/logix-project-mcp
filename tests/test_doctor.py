import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class DoctorTests(unittest.TestCase):
    def test_sdk_free_check_opens_project_without_leaking_contents(self):
        contents = (
            b'<RSLogix5000Content SoftwareRevision="38.00" TargetType="Controller">'
            b'<Controller Name="PrivateControllerName" />'
            b"</RSLogix5000Content>"
        )
        with TemporaryDirectory() as directory:
            project = Path(directory) / "PrivateProjectName.L5X"
            project.write_bytes(contents)

            result = subprocess.run(
                [sys.executable, "-X", "utf8", "-m", "logix_project_mcp.doctor",
                 "--project", str(project)],
                capture_output=True,
                encoding="utf-8",
                env=dict(os.environ, LOGIX_DIAGNOSTIC_TEST_VALUE="PrivateEnvironmentValue"),
                timeout=25,
                check=False,
            )

            diagnostics = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, diagnostics)
            self.assertIn("[PASS] MCP SDK-free launch", diagnostics)
            self.assertIn("38.00", diagnostics)
            self.assertNotIn("SDK service", diagnostics)
            for value in ("PrivateProjectName", "PrivateControllerName", "PrivateEnvironmentValue"):
                self.assertNotIn(value, diagnostics)
            self.assertEqual(project.read_bytes(), contents)
