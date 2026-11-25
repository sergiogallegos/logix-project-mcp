"""Install the local sharing helper in Logix Designer's Custom Tools menu."""

import argparse
import ctypes
import json
import os
import sys
from pathlib import Path, PureWindowsPath
from tempfile import NamedTemporaryFile
from uuid import uuid4
from xml.dom import Node, minidom
from xml.parsers.expat import ExpatError

from defusedxml import minidom as safe_xml
from defusedxml.common import DefusedXmlException

MENU_NAME = "Send Current Project to Agent"
STATUS_TEXT = "Share the current saved Studio 5000 project with logix-project-mcp"
ARGUMENT_PREFIX = "-m logix_project_mcp.share --dialog --selection-file "
PROJECT_MACRO = '"%project_path%"'
MAX_TOOLS = 16


class MenuError(Exception):
    """An expected Custom Tools configuration failure."""


def locate_config() -> Path:
    candidates = set()
    for variable in ("ProgramFiles(x86)", "ProgramFiles"):
        if directory := os.environ.get(variable):
            for relative in (
                "Rockwell Software/RSLogix 5000/Common/CustomToolsMenu.xml",
                "Rockwell Software/Logix Designer/Common/CustomToolsMenu.xml",
            ):
                candidate = Path(directory) / relative
                if candidate.is_file():
                    candidates.add(candidate.resolve())
    if len(candidates) != 1:
        raise MenuError("Locate the installed CustomToolsMenu.xml and supply its path with --config.")
    return candidates.pop()


def fields(node: minidom.Element, name: str) -> list[minidom.Element]:
    return [child for child in node.childNodes if child.nodeType == Node.ELEMENT_NODE and child.tagName == name]


def text_field(node: minidom.Element, name: str) -> str:
    matches = fields(node, name)
    if len(matches) > 1:
        raise MenuError(f"A Custom Tool contains multiple {name} elements. Review the configuration before editing it.")
    if not matches:
        return ""
    return "".join(
        child.data for child in matches[0].childNodes
        if child.nodeType in (Node.TEXT_NODE, Node.CDATA_SECTION_NODE)
    ).strip()


def change_field(document: minidom.Document, node: minidom.Element, name: str, value: str) -> None:
    matches = fields(node, name)
    if matches:
        field = matches[0]
        while field.firstChild is not None:
            field.removeChild(field.firstChild)
    else:
        field = document.createElement(name)
        node.appendChild(document.createTextNode("\n    "))
        node.appendChild(field)
    if value:
        field.appendChild(document.createTextNode(value))


def managed_tool(tool: minidom.Element) -> bool:
    arguments = text_field(tool, "Arguments")
    return (
        text_field(tool, "StatusBarText") == STATUS_TEXT
        and PureWindowsPath(text_field(tool, "Command")).name.casefold() == "pythonw.exe"
        and arguments.startswith(ARGUMENT_PREFIX)
        and arguments.endswith(" " + PROJECT_MACRO)
    )


def install_values(pythonw: Path, selection_file: Path) -> dict[str, str]:
    if pythonw.name.casefold() != "pythonw.exe" or not pythonw.is_file():
        raise MenuError("Use a Windows Python environment with pythonw.exe and logix-project-mcp installed.")
    if selection_file.suffix.lower() != ".json":
        raise MenuError("Select the .json path configured for the MCP server.")
    if any(character in str(selection_file) or character in str(pythonw) for character in ('%', '"', '\r', '\n')):
        raise MenuError("Choose Python and selection paths that can be used literally in the Custom Tools argument string.")
    return {
        "Command": str(pythonw),
        "WorkingDirectory": str(pythonw.parent),
        "Arguments": f'{ARGUMENT_PREFIX}"{selection_file}" {PROJECT_MACRO}',
        "ToolName": MENU_NAME,
        "StatusBarText": STATUS_TEXT,
        "ToolbarIcon": "",
    }


def update_xml(original: bytes, values: dict[str, str] | None) -> bytes | None:
    try:
        document = safe_xml.parseString(original, forbid_dtd=True)
    except (ExpatError, DefusedXmlException) as exc:
        raise MenuError(f"Invalid Custom Tools XML: {exc}") from exc
    root = document.documentElement
    if root.tagName != "CustomToolsContent" or root.getAttribute("SchemaRevision") != "1.0":
        raise MenuError("Expected a CustomToolsContent XML configuration with schema revision 1.0.")
    tools = fields(root, "CustomTool")
    matches = [
        tool for tool in tools
        if text_field(tool, "ToolName").replace("&", "").casefold() == MENU_NAME.casefold()
    ]
    if len(matches) > 1 or (matches and not managed_tool(matches[0])):
        raise MenuError(f"A conflicting '{MENU_NAME}' entry already exists. Review it in Custom Tools.")
    existing = matches[0] if matches else None
    if values is None:
        if existing is None:
            return None
        preceding = existing.previousSibling
        root.removeChild(existing)
        if preceding is not None and preceding.nodeType == Node.TEXT_NODE and not preceding.data.strip():
            root.removeChild(preceding)
    elif existing is not None:
        changes = {
            name: value for name, value in values.items()
            if name != "ToolbarIcon" and text_field(existing, name) != value
        }
        if not changes:
            return None
        for name, value in changes.items():
            change_field(document, existing, name, value)
    else:
        if sum(bool(text_field(tool, "Command")) for tool in tools) >= MAX_TOOLS:
            raise MenuError("Logix Designer supports up to 16 Custom Tools. Free a menu entry before installing.")
        entry = document.createElement("CustomTool")
        for name, value in values.items():
            change_field(document, entry, name, value)
        entry.appendChild(document.createTextNode("\n  "))
        tail = root.lastChild
        if tail is not None and tail.nodeType == Node.TEXT_NODE and not tail.data.strip():
            root.insertBefore(document.createTextNode("\n  "), tail)
            root.insertBefore(entry, tail)
        else:
            root.appendChild(document.createTextNode("\n  "))
            root.appendChild(entry)
            root.appendChild(document.createTextNode("\n"))
    return document.toxml(encoding="UTF-8")


def replace_config(config: Path, staged: Path, backup: Path) -> None:
    if sys.platform == "win32":
        # ReplaceFileW retains the original file's ACL and creates its backup.
        replace = ctypes.WinDLL("kernel32", use_last_error=True).ReplaceFileW
        replace.argtypes = [
            ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
            ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p,
        ]
        replace.restype = ctypes.c_int
        if not replace(str(config), str(staged), str(backup), 0, None, None):
            error = ctypes.WinError(ctypes.get_last_error())
            if not config.exists() and backup.exists():
                os.rename(backup, config)
            raise error
    else:
        with backup.open("xb") as destination:
            destination.write(config.read_bytes())
        staged.chmod(config.stat().st_mode & 0o777)
        os.replace(staged, config)


def configure_menu(config: Path, values: dict[str, str] | None) -> Path | None:
    config = config.resolve(strict=True)
    original = config.read_bytes()
    updated = update_xml(original, values)
    if updated is None:
        return None
    backup = config.with_name(f"{config.name}.logix-project-mcp-{uuid4().hex}.bak")
    staged = None
    try:
        with NamedTemporaryFile(dir=config.parent, prefix=".logix-menu-", delete=False) as temporary:
            staged = Path(temporary.name)
            temporary.write(updated)
        if config.read_bytes() != original:
            raise MenuError("Custom Tools changed during the update. Retry after closing the configuration dialog.")
        replace_config(config, staged, backup)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
    return backup


def main() -> None:
    parser = argparse.ArgumentParser(description="Install or remove the Logix Designer project sharing menu entry.")
    parser.add_argument("--config", type=Path, help="Existing CustomToolsMenu.xml (defaults to the installed configuration)")
    commands = parser.add_subparsers(dest="action", required=True)
    install = commands.add_parser("install", help="Add or update the sharing entry")
    install.add_argument("--selection-file", required=True, type=Path, help="JSON path configured for the MCP server")
    commands.add_parser("remove", help="Remove the sharing entry")
    args = parser.parse_args()
    try:
        config = args.config.resolve() if args.config else locate_config()
        values = None
        if args.action == "install":
            pythonw = Path(sys.executable).absolute().with_name("pythonw.exe")
            values = install_values(pythonw, args.selection_file.resolve())
        backup = configure_menu(config, values)
        print(json.dumps({"config": str(config), "changed": backup is not None, "backup": str(backup) if backup else None}))
    except (MenuError, OSError, RuntimeError, ValueError) as exc:
        print(f"Custom Tools update failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
