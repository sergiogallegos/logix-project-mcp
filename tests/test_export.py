import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from logix_project_mcp.export import export_saved_project
from logix_project_mcp.project import ProjectReadError, parse_l5x


class ExportTests(unittest.IsolatedAsyncioTestCase):
    async def test_destination_created_during_export_wins(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "Sample.L5X"
            export = folder / "Export.L5X"
            source_data = b"<RSLogix5000Content><Controller /></RSLogix5000Content>"
            source.write_bytes(source_data)

            def create_competing_file(staged: Path):
                export.write_bytes(b"created during the export")
                return parse_l5x(staged)

            with patch("logix_project_mcp.export.parse_l5x", side_effect=create_competing_file):
                with self.assertRaises(ProjectReadError) as caught:
                    await export_saved_project(source, folder, export.name, None)
            self.assertEqual(caught.exception.code, "destination_exists")
            self.assertEqual(export.read_bytes(), b"created during the export")
            self.assertEqual(source.read_bytes(), source_data)
            self.assertEqual(set(folder.iterdir()), {source, export})
