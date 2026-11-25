import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from logix_project_mcp import review
from scripts import acceptance
from test_documentation import PROJECT


class AcceptanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_shared_sample_to_verified_readback(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp).resolve()
            source = folder / "Sample.L5X"
            source.write_bytes(PROJECT)
            run = folder / "Review"
            installed_cli = acceptance.cli
            prompts = []

            def confirm(preview):
                prompts.append(preview)
                return True

            def cli(name, *args):
                if name != "logix-project-mcp-review" or "--check" in args:
                    return installed_cli(name, *args)
                # Simulate the human decision only for this generated fixture.
                with (
                    patch.object(sys, "argv", [name, *map(str, args)]),
                    patch.object(sys, "stdin", io.StringIO()),
                    patch.object(sys.stdin, "isatty", return_value=True),
                    patch.object(review, "terminal_confirm", confirm),
                    redirect_stdout(io.StringIO()) as output,
                ):
                    review.main()
                return json.loads(output.getvalue())

            with patch.object(acceptance, "cli", cli):
                result = await acceptance.accept(source, run, "Main", "MainRoutine", "Fixture review note")
            self.assertEqual(result["stale_proposal_error"], "selection_changed")
            self.assertEqual(result["routine"], "Program:Main.MainRoutine")
            self.assertEqual(result["source_sha256"], result["baseline_sha256"])
            self.assertEqual(len(prompts), 1)
            self.assertEqual(prompts[0]["review_id"], result["review_id"])
            self.assertEqual(prompts[0]["proposal"]["preview"][0]["after"], "Fixture review note")
            self.assertEqual(acceptance.digest(Path(result["verified_copy"])), result["artifact_sha256"])
            self.assertEqual(json.loads((run / "acceptance.json").read_bytes()), result)
            self.assertEqual(source.read_bytes(), PROJECT)
