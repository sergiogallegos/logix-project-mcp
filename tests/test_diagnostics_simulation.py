import hashlib
import unittest

from examples.diagnostics_simulation import SAVED_PROJECT, simulate


class DiagnosticsSimulationTests(unittest.TestCase):
    def test_simulated_provenance_and_scope(self):
        report = simulate()
        self.assertEqual(report, simulate())
        self.assertEqual(report["mode"], "offline_simulation")
        self.assertEqual(report["saved_source"]["source_sha256"], hashlib.sha256(SAVED_PROJECT).hexdigest())
        rows = {(row["saved"]["program"], row["saved"]["name"]): row for row in report["rows"]}
        expected = {
            (None, "DemoCounter"): ("simulated_fresh", 42),
            ("Example", "DemoCounter"): ("stale", 17),
            (None, "Unavailable"): ("unavailable", None),
            (None, "NoObservation"): ("not_observed", None),
            (None, "DifferentSnapshot"): ("snapshot_mismatch", None),
        }
        self.assertEqual(set(rows), set(expected))
        for identity, (status, value) in expected.items():
            with self.subTest(identity=identity):
                row = rows[identity]
                self.assertEqual(row["saved"]["provenance"], "saved_project")
                self.assertNotIn("value", row["saved"])
                self.assertEqual(row["observation"]["provenance"], "synthetic_fixture")
                self.assertEqual(row["observation"]["status"], status)
                self.assertEqual(row["observation"]["value"], value)
        self.assertIsNone(rows[(None, "NoObservation")]["observation"]["observed_at"])
