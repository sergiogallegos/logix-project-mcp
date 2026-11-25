"""Optional SDK reopen test for a synthetic full L5X documentation copy."""

import hashlib
import os
import shutil
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from logix_project_mcp.documentation import description_spans
from logix_project_mcp.inventory import project_inventory
from logix_project_mcp.project import controller_from_l5x, export_snapshot, parse_l5x


SYNTHETIC_SAMPLE = os.environ.get("LOGIX_PROJECT_MCP_TEST_DOCUMENTATION_L5X")


@unittest.skipUnless(sys.platform == "win32" and SYNTHETIC_SAMPLE, "Synthetic Windows SDK L5X sample required")
class VendorDocumentationTests(unittest.IsolatedAsyncioTestCase):
    async def test_sdk_reopens_synthetic_documentation_copy(self):
        source = Path(SYNTHETIC_SAMPLE).resolve(strict=True)
        self.assertEqual(source.suffix.lower(), ".l5x")
        fingerprint = hashlib.sha256(source.read_bytes()).hexdigest()
        note = "Synthetic documentation verification sample"
        try:
            with TemporaryDirectory() as directory:
                folder = Path(directory).resolve()
                server = StdioServerParameters(command=sys.executable, args=[
                    "-m", "logix_project_mcp.server", "--project", str(source), "--export-dir", str(folder),
                ])
                async with stdio_client(server) as (reader, writer), ClientSession(reader, writer) as client:
                    await client.initialize()

                    async def call(name, args):
                        result = await client.call_tool(name, args)
                        self.assertFalse(result.isError, result.content)
                        return result.structuredContent

                    proposal = await call("preview_change_proposal", {
                        "expected_source_sha256": fingerprint,
                        "operations": [{"operation": "set_description", "target": {"kind": "controller"}, "description": note}],
                    })
                    request = {"proposal": proposal, "expected_approval_id": proposal["approval_id"], "filename": "Reviewed.L5X"}
                    receipt = await call("create_documentation_copy", request)
                    verified = await call("verify_documentation_copy", {**request, "expected_artifact_sha256": receipt["artifact_sha256"]})
                    self.assertEqual(verified["vendor_verification"], "not_performed")
                artifact = Path(receipt["path"])
                artifact_digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
                self.assertEqual(artifact_digest, receipt["artifact_sha256"])
                try:
                    scratch = folder / "SdkReadCopy.L5X"
                    shutil.copyfile(artifact, scratch)
                    reopened = folder / "SdkReexport.L5X"
                    await export_snapshot(scratch, reopened, "synthetic documentation copy")
                    original_root = parse_l5x(source)
                    reopened_root = parse_l5x(reopened)
                    original_inventory = project_inventory(controller_from_l5x(original_root))
                    reopened_controller = controller_from_l5x(reopened_root)
                    reopened_inventory = project_inventory(reopened_controller)
                    self.assertEqual(original_root.get("SoftwareRevision"), reopened_root.get("SoftwareRevision"))
                    description = reopened_controller.find("Description")
                    self.assertIsNotNone(description)
                    data = reopened.read_bytes()
                    span = description_spans(data, reopened_root)[description]
                    raw = data[span.start:span.end]
                    self.assertIn(("<![CDATA[" + note + "]]>").encode("utf-8"), raw)
                    # Vendor export inserts formatting whitespace outside the CDATA.
                    reopened_inventory["controller"]["description"] = original_inventory["controller"]["description"]
                    self.assertEqual(reopened_inventory, original_inventory)
                finally:
                    self.assertEqual(hashlib.sha256(artifact.read_bytes()).hexdigest(), artifact_digest)
        finally:
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), fingerprint)
