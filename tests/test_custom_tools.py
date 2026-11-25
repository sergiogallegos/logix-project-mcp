import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from defusedxml.minidom import parseString

from logix_project_mcp.custom_tools import (
    MENU_NAME, MenuError, configure_menu, fields, install_values, text_field, update_xml,
)

ORIGINAL = b'''<?xml version="1.0" encoding="UTF-8"?>
<CustomToolsContent SchemaRevision="1.0">
  <!-- Existing engineer tools -->
  <CustomTool custom="preserve">
    <Command>C:\\Other Tools\\Compare.exe</Command>
    <Arguments>"%project_path%"</Arguments>
    <ToolName>Co&amp;mpare Tool</ToolName>
    <ToolbarIcon>compare.bmp</ToolbarIcon>
    <Extension>keep</Extension>
  </CustomTool>
  <CustomTool><Command/><ToolName/></CustomTool>
</CustomToolsContent>
'''


def entries(data):
    return fields(parseString(data).documentElement, "CustomTool")


class CustomToolsTests(unittest.TestCase):
    def test_install_update_remove_and_repeated_operations(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            pythonw = root / "Python Environment" / "pythonw.exe"
            pythonw.parent.mkdir()
            pythonw.touch()
            state = root / "Engineer Selection.json"
            config = root / "CustomToolsMenu.xml"
            config.write_bytes(ORIGINAL)
            existing = [node.toxml() for node in entries(ORIGINAL)]
            values = install_values(pythonw, state)
            backup = configure_menu(config, values)
            self.assertEqual(backup.read_bytes(), ORIGINAL)
            installed = config.read_bytes()
            tools = entries(installed)
            self.assertEqual([node.toxml() for node in tools[:-1]], existing)
            self.assertIn(b"<!-- Existing engineer tools -->", installed)
            self.assertEqual(text_field(tools[-1], "ToolName"), MENU_NAME)
            self.assertEqual(text_field(tools[-1], "Command"), str(pythonw))
            self.assertEqual(text_field(tools[-1], "Arguments"),
                             f'-m logix_project_mcp.share --dialog --selection-file "{state}" "%project_path%"')
            self.assertIsNone(configure_menu(config, values))
            self.assertEqual(config.read_bytes(), installed)

            new_values = install_values(pythonw, root / "Other selection.json")
            updated_backup = configure_menu(config, new_values)
            self.assertEqual(updated_backup.read_bytes(), installed)
            updated = config.read_bytes()
            self.assertEqual([node.toxml() for node in entries(updated)[:-1]], existing)
            self.assertEqual(text_field(entries(updated)[-1], "Arguments"), new_values["Arguments"])
            removed_backup = configure_menu(config, None)
            self.assertEqual(removed_backup.read_bytes(), updated)
            removed = config.read_bytes()
            self.assertEqual([node.toxml() for node in entries(removed)], existing)
            self.assertIn(b"<!-- Existing engineer tools -->", removed)
            self.assertIsNone(configure_menu(config, None))
            self.assertEqual(config.read_bytes(), removed)
            self.assertEqual(len(list(root.glob("*.bak"))), 3)

    def test_conflicting_and_invalid_configurations_are_preserved(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "CustomToolsMenu.xml"
            pythonw = root / "pythonw.exe"
            pythonw.touch()
            values = install_values(pythonw, root / "selection.json")
            conflict = ORIGINAL.replace(b"Co&amp;mpare Tool", MENU_NAME.encode())
            capacity = b'<CustomToolsContent SchemaRevision="1.0">' + (
                b"<CustomTool><Command>Other.exe</Command></CustomTool>" * 16
            ) + b"</CustomToolsContent>"
            for contents in (conflict, capacity, b"<invalid/>", b"<broken", b"<!DOCTYPE PrivateSample><a/>",
                             b'<?xml version="1.0" encoding="PrivateSample"?><a/>'):
                with self.subTest(contents=contents[:60]):
                    config.write_bytes(contents)
                    with self.assertRaises(MenuError) as failure:
                        configure_menu(config, values)
                    self.assertNotIn("PrivateSample", str(failure.exception))
                    self.assertEqual(config.read_bytes(), contents)
            config.write_bytes(conflict)
            with self.assertRaises(MenuError):
                configure_menu(config, None)
            self.assertEqual(config.read_bytes(), conflict)
            self.assertFalse(list(root.glob("*.bak")))

    def test_configuration_changed_before_publication(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "CustomToolsMenu.xml"
            config.write_bytes(ORIGINAL)
            pythonw = root / "pythonw.exe"
            pythonw.touch()
            values = install_values(pythonw, root / "selection.json")
            externally_changed = ORIGINAL.replace(b"compare.bmp", b"new.bmp")

            def change_during_update(data, new_values):
                config.write_bytes(externally_changed)
                return update_xml(data, new_values)

            with patch("logix_project_mcp.custom_tools.update_xml", side_effect=change_during_update):
                with self.assertRaises(MenuError):
                    configure_menu(config, values)
            self.assertEqual(config.read_bytes(), externally_changed)
            self.assertEqual(set(root.iterdir()), {config, pythonw})
