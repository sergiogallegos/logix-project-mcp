import asyncio
import hashlib
import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from logix_project_mcp.documentation import stage_documentation_copy
from logix_project_mcp.project import ProjectReadError, ProjectSnapshot, controller_from_l5x, parse_l5x_bytes
from logix_project_mcp.proposals import canonical_json, create_proposal
from logix_project_mcp.review import approval_path_for, main, review_artifact
from logix_project_mcp.selection import ProjectSelection
from test_documentation import EXPECTED, OPERATIONS, PROJECT


async def fixture(folder):
    source = folder / "Source.L5X"
    source.write_bytes(PROJECT)
    selection = ProjectSelection(source)
    root = parse_l5x_bytes(PROJECT)
    proposal = create_proposal(selection, ProjectSnapshot(root, controller_from_l5x(root), hashlib.sha256(PROJECT).hexdigest()), OPERATIONS)
    receipt = await stage_documentation_copy(selection, lambda: selection, folder, "Reviewed.L5X", proposal, proposal["approval_id"])
    return selection, proposal, receipt, Path(receipt["path"])


class ReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_decline_approval_and_replay(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory).resolve()
            selection, proposal, receipt, artifact = await fixture(folder)
            approval_path = approval_path_for(artifact)
            decisions = []

            def confirm(preview):
                self.assertEqual(preview["proposal"], proposal)
                self.assertEqual(preview["artifact"]["artifact_sha256"], receipt["artifact_sha256"])
                self.assertEqual(preview["artifact"]["path"], str(artifact))
                self.assertEqual(preview["artifact"]["vendor_verification"], "not_performed")
                self.assertEqual(preview["approval_path"], str(approval_path))
                content = {key: value for key, value in preview.items() if key != "review_id"}
                self.assertEqual(preview["review_id"], hashlib.sha256(canonical_json(content)).hexdigest())
                decisions.append(preview)
                return len(decisions) == 2

            self.assertIsNone(await review_artifact(selection, lambda: selection, artifact, proposal, receipt, confirm))
            self.assertFalse(approval_path.exists())
            record = await review_artifact(selection, lambda: selection, artifact, proposal, receipt, confirm)
            self.assertEqual(record["decision"], "approved_documentation_copy")
            self.assertEqual(record["review_id"], decisions[0]["review_id"])
            self.assertEqual(json.loads(approval_path.read_bytes()), record)
            original_record = approval_path.read_bytes()
            with self.assertRaises(ProjectReadError) as caught:
                await review_artifact(selection, lambda: selection, artifact, proposal, receipt, confirm)
            self.assertEqual(caught.exception.code, "destination_exists")
            self.assertEqual(len(decisions), 2)
            self.assertEqual(approval_path.read_bytes(), original_record)
            self.assertEqual(selection.path.read_bytes(), PROJECT)
            self.assertEqual(artifact.read_bytes(), EXPECTED)

    async def test_changes_after_review_and_competing_receipt(self):
        for event in ("source", "artifact", "selection", "collision"):
            with self.subTest(event=event), TemporaryDirectory() as directory:
                folder = Path(directory).resolve()
                selection, proposal, receipt, artifact = await fixture(folder)
                approval_path = approval_path_for(artifact)
                current = selection

                def confirm(preview):
                    nonlocal current
                    if event == "source":
                        selection.path.write_bytes(PROJECT + b"\n")
                    elif event == "artifact":
                        artifact.write_bytes(EXPECTED + b"\n")
                    elif event == "selection":
                        current = ProjectSelection(selection.path, "1" * 32)
                    else:
                        approval_path.write_bytes(b"existing receipt")
                    return True

                with self.assertRaises(ProjectReadError) as caught:
                    await review_artifact(selection, lambda: current, artifact, proposal, receipt, confirm)
                self.assertEqual(caught.exception.code, {
                    "source": "project_changed", "artifact": "artifact_changed",
                    "selection": "selection_changed", "collision": "destination_exists",
                }[event])
                if event == "collision":
                    self.assertEqual(approval_path.read_bytes(), b"existing receipt")
                else:
                    self.assertFalse(approval_path.exists())
                self.assertEqual(selection.path.read_bytes(), PROJECT + (b"\n" if event == "source" else b""))
                self.assertEqual(artifact.read_bytes(), EXPECTED + (b"\n" if event == "artifact" else b""))

    async def test_invalid_receipt_rejected_before_prompt(self):
        with TemporaryDirectory() as directory:
            selection, proposal, receipt, artifact = await fixture(Path(directory).resolve())

            def not_called(preview):
                self.fail("Invalid review must fail before prompting.")

            for invalid, error in (
                ({**receipt, "path": str(artifact.with_name("Another.L5X"))}, "invalid_proposal"),
                ({**receipt, "approval_id": "0" * 64}, "invalid_proposal"),
                ({**receipt, "artifact_sha256": "0" * 64}, "artifact_changed"),
            ):
                with self.assertRaises(ProjectReadError) as caught:
                    await review_artifact(selection, lambda: selection, artifact, proposal, invalid, not_called)
                self.assertEqual(caught.exception.code, error)
            self.assertFalse(approval_path_for(artifact).exists())


class ReviewCommandTests(unittest.TestCase):
    def test_cli_confirmation_and_noninteractive_rejection(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory).resolve()
            selection, proposal, receipt, artifact = asyncio.run(fixture(folder))
            proposal_file, receipt_file = folder / "proposal.json", folder / "creation.json"
            proposal_file.write_bytes(canonical_json(proposal))
            receipt_file.write_bytes(canonical_json(receipt))
            args = ["--project", str(selection.path), "--proposal", str(proposal_file),
                    "--receipt", str(receipt_file), str(artifact)]
            blocked = subprocess.run(
                [sys.executable, "-m", "logix_project_mcp.review", *args],
                input="APPROVE\n", text=True, capture_output=True, check=False,
            )
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn("interactive terminal", blocked.stderr)
            self.assertFalse(approval_path_for(artifact).exists())
            for response in ("DECLINE\n", "APPROVE\n"):
                with patch.object(sys, "argv", ["review", *args]), patch.object(sys, "stdin", io.StringIO(response)), redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()) as stderr:
                    with patch.object(sys.stdin, "isatty", return_value=True):
                        if response.startswith("DECLINE"):
                            with self.assertRaises(SystemExit) as declined:
                                main()
                            self.assertEqual(declined.exception.code, 2)
                            self.assertFalse(approval_path_for(artifact).exists())
                        else:
                            main()
                            self.assertEqual(json.loads(stdout.getvalue()), json.loads(approval_path_for(artifact).read_bytes()))
                    self.assertIn("Reviewed controller note", stderr.getvalue())
                    self.assertIn("Type APPROVE", stderr.getvalue())
            self.assertEqual(selection.path.read_bytes(), PROJECT)
            self.assertEqual(artifact.read_bytes(), EXPECTED)
