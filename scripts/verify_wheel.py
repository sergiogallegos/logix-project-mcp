"""Exercise installation, upgrade and removal in a disposable Python environment."""

import argparse
import json
import os
import subprocess
import venv
from hashlib import file_digest
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree


TESTS = Path(__file__).resolve().parents[1] / "tests"
COMMANDS = ("logix-project-mcp", "logix-project-mcp-doctor", "logix-project-mcp-menu",
            "logix-project-mcp-review", "logix-project-mcp-review-tag", "logix-project-mcp-share")


def verify(folder: Path, wheel: Path, previous: Path | None, sdk: Path | None) -> None:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    if not sdk:
        env.pop("LOGIX_PROJECT_MCP_TEST_PROJECT", None)
        env.pop("LOGIX_PROJECT_MCP_TEST_DOCUMENTATION_L5X", None)
    install = folder / "Python Environment"
    venv.EnvBuilder(with_pip=True).create(install)
    windows = os.name == "nt"
    scripts = install / ("Scripts" if windows else "bin")

    def command(name):
        return scripts / (name + ".exe" if windows else name)

    def run(*args, capture=False, cwd=folder):
        return subprocess.run(args, cwd=cwd, env=env, check=True, text=True,
                              stdout=subprocess.PIPE if capture else None).stdout

    def pip(*args):
        run(command("python"), "-m", "pip", "--disable-pip-version-check", *args)

    pip("install", previous or wheel, *([sdk] if sdk else []))
    source = folder / "Sample project.L5X"
    source.write_bytes(b'<RSLogix5000Content TargetType="Controller" SoftwareRevision="38.02">'
                       b'<Controller Name="PackagingSample"/></RSLogix5000Content>')
    selection = folder / "Engineer selection.json"
    run(command("logix-project-mcp-share"), "--selection-file", selection, source)
    state = selection.read_bytes()
    assert json.loads(state)["path"] == str(source)

    if windows:
        config = folder / "CustomToolsMenu.xml"
        config.write_bytes(b'<CustomToolsContent SchemaRevision="1.0"><CustomTool>'
                           b'<Command>compare.exe</Command><ToolName>Compare</ToolName>'
                           b'</CustomTool></CustomToolsContent>')
        menu = (command("logix-project-mcp-menu"), "--config", config)
        menu_install = (*menu, "install", "--selection-file", selection)
        initial = json.loads(run(*menu_install, capture=True))
        assert initial["changed"]
        configured = config.read_bytes()

    # Before the first versioned release, successive development wheels can share a version.
    pip("install", "--upgrade", "--force-reinstall", wheel)
    pip("check")
    run(command("python"), "-c",
        "from importlib.util import find_spec; import sys; "
        "assert (find_spec('logix_designer_sdk') is not None) == (sys.argv[1] == 'native')",
        "native" if sdk else "sdk-free")
    for name in COMMANDS:
        run(command(name), "--help", capture=True)
    assert selection.read_bytes() == state
    if windows:
        assert config.read_bytes() == configured
        repeated = json.loads(run(*menu_install, capture=True))
        assert not repeated["changed"]
    run(command("logix-project-mcp-doctor"), "--project", source)
    # The suite imports the repository's examples. Production code uses the src layout.
    run(command("python"), "-m", "unittest", "discover", "-s", TESTS, "-v", cwd=TESTS.parent)

    if windows:
        removed = json.loads(run(*menu, "remove", capture=True))
        repeated = json.loads(run(*menu, "remove", capture=True))
        assert removed["changed"] and not repeated["changed"]
        entries = ElementTree.parse(config).getroot().findall("CustomTool")
        assert [(e.findtext("ToolName"), e.findtext("Command")) for e in entries] == [("Compare", "compare.exe")]
        remaining = config.read_bytes()
    pip("uninstall", "-y", "logix-project-mcp")
    run(command("python"), "-c", "from importlib.util import find_spec; assert find_spec('logix_project_mcp') is None")
    assert all(not command(name).exists() for name in COMMANDS)
    assert selection.read_bytes() == state
    if windows:
        assert config.read_bytes() == remaining


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--previous-wheel", type=Path, help="Install a prior helper-enabled wheel before upgrading")
    parser.add_argument("--sdk-wheel", type=Path, help="Install the local Rockwell wheel for a Windows native run")
    args = parser.parse_args()
    wheel = args.wheel.resolve(strict=True)
    with wheel.open("rb") as artifact:
        print(f"Verifying {wheel.name} SHA-256 {file_digest(artifact, 'sha256').hexdigest()}", flush=True)
    with TemporaryDirectory(prefix="logix-wheel-") as folder:
        verify(Path(folder).resolve(), wheel,
               args.previous_wheel.resolve(strict=True) if args.previous_wheel else None,
               args.sdk_wheel.resolve(strict=True) if args.sdk_wheel else None)
    print("Wheel installation, upgrade, tests and removal passed.")


if __name__ == "__main__":
    main()
