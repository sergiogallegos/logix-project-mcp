"""Check the local MCP launch environment without displaying project contents."""

import argparse
import asyncio
import os
import platform
import re
import socket
import subprocess
import sys
import sysconfig
from datetime import timedelta
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from shutil import which
from typing import NamedTuple

NATIVE_EXTENSIONS = {".acd", ".l5k"}
RUNTIME_NAMES = ("Microsoft.NETCore.App", "Microsoft.WindowsDesktop.App", "Microsoft.AspNetCore.App")
SDK_SERVICE = "LdSdkService"
SDK_PORT = 53204
DOTNET_10 = re.compile(r"10\.0\.\d+")


class Check(NamedTuple):
    status: str
    name: str
    detail: str


def package_version(distribution: str) -> str | None:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return None


def run_check(command: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def runtime_versions(dotnet_root: Path | None) -> dict[str, set[str]]:
    if dotnet_root is None:
        return {}
    process = run_check([str(dotnet_root / "dotnet.exe"), "--list-runtimes"])
    if process is None or process.returncode:
        return {}

    runtimes: dict[str, set[str]] = {}
    for line in process.stdout.splitlines():
        fields = line.split(maxsplit=2)
        if len(fields) != 3:
            continue
        name, release, _ = fields
        if name in RUNTIME_NAMES and re.fullmatch(r"\d+\.\d+\.\d+(?:-[\w.-]+)?", release):
            runtimes.setdefault(name, set()).add(release)
    return runtimes


def dotnet_root() -> Path | None:
    if override := os.environ.get("DOTNET_ROOT"):
        return Path(override)
    if program_files := os.environ.get("ProgramFiles"):
        standard = Path(program_files) / "dotnet"
        if standard.is_dir():
            return standard
        if launcher := which("dotnet.exe"):
            return Path(launcher).resolve().parent
    return None


def studio_revisions() -> list[int]:
    revisions = set()
    for variable in ("ProgramFiles(x86)", "ProgramFiles", "ProgramW6432"):
        if base := os.environ.get(variable):
            root = Path(base) / "Rockwell Software" / "Studio 5000" / "Logix Designer"
            for executable in root.glob("*/v*/Bin/LogixDesigner.exe"):
                revision = executable.parents[1].name.removeprefix("v")
                if revision.isdecimal():
                    revisions.add(int(revision))
    return sorted(revisions)


def sdk_service_check() -> Check:
    result = run_check(["sc.exe", "query", SDK_SERVICE])
    if result is not None and result.returncode == 1060:
        return Check("FAIL", "SDK service", f"{SDK_SERVICE} is missing. Install the Rockwell SDK service.")
    if result is not None and result.returncode == 0:
        state = re.search(r"(?im)^\s*(?:STATE|ESTADO)\s*:\s*(\d+)\b", result.stdout)
        if state:
            if state[1] == "4":
                return Check("PASS", "SDK service", f"{SDK_SERVICE} is running.")
            return Check("FAIL", "SDK service", f"{SDK_SERVICE} is not running. Check Windows Services.")
    return Check(
        "WARN", "SDK service", f"Could not read the state of {SDK_SERVICE}. Check Windows Services."
    )


def windows_checks(wheel: str | None, root: Path | None) -> list[Check]:
    checks = [sdk_service_check()]
    try:
        with socket.create_connection(("127.0.0.1", SDK_PORT), timeout=2):
            checks.append(Check("PASS", "SDK endpoint", f"TCP loopback port {SDK_PORT} is reachable."))
    except OSError:
        checks.append(Check("WARN", "SDK endpoint", f"TCP loopback port {SDK_PORT} is unreachable here."))

    revisions = studio_revisions()
    if revisions:
        revisions_text = ", ".join(map(str, revisions))
        checks.append(Check("PASS", "Studio 5000", f"Detected Logix Designer revisions {revisions_text}."))
    else:
        checks.append(Check(
            "WARN", "Studio 5000", "No standard install found. Verify the project's revision is installed."
        ))

    versions = runtime_versions(root).get("Microsoft.NETCore.App", set())
    location = "DOTNET_ROOT" if os.environ.get("DOTNET_ROOT") else "the detected .NET installation"
    required_runtime = ".NET 10 Core Runtime" if wheel == "2.0.2" else ".NET Core Runtime"
    if wheel == "2.0.2":
        versions = {value for value in versions if DOTNET_10.fullmatch(value)}
    if versions:
        checks.append(Check(
            "PASS", ".NET runtime", f"{required_runtime} in {location} ({', '.join(sorted(versions))})."
        ))
    else:
        checks.append(Check(
            "FAIL", ".NET runtime",
            f"Could not find the {required_runtime}. Set DOTNET_ROOT to the install matching Python's architecture.",
        ))

    if wheel == "2.0.2" and (program_files_x86 := os.environ.get("ProgramFiles(x86)")):
        server_runtimes = runtime_versions(Path(program_files_x86) / "dotnet")
        common = set.intersection(*(server_runtimes.get(name, set()) for name in RUNTIME_NAMES))
        matching = sorted(value for value in common if DOTNET_10.fullmatch(value))
        if matching:
            checks.append(Check(
                "PASS", "SDK service runtimes", f"Matching x86 .NET 10 runtimes ({', '.join(matching)})."
            ))
        else:
            checks.append(Check(
                "WARN", "SDK service runtimes",
                "Could not verify matching x86 .NET 10, Desktop, and ASP.NET Core runtimes "
                "in the standard install.",
            ))
    return checks


def tool_error_hint(text: str) -> str:
    normalized = text.casefold()
    if any(term in normalized for term in ("timed out", "timeout", "did not finish", "deadline")):
        return (
            "The SDK timed out. Check the Windows service and forward ProgramFiles from "
            "the working Windows environment or configure your client to inherit it."
        )
    if "dotnet_root" in normalized or "coreclr" in normalized:
        return "The SDK could not load .NET. Check ProgramFiles, DOTNET_ROOT, and the runtime architecture."
    if "python wheel" in normalized:
        return "Install Rockwell's Python wheel into the environment used by the MCP client."
    if "licen" in normalized or "activat" in normalized:
        return "Check the Rockwell SDK activation and license in FactoryTalk Activation Manager."
    return "The server could not open the saved project. Check its format, revision, and local read access."


async def probe_mcp(project: Path, environment: dict[str, str] | None, name: str) -> Check:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    launch = StdioServerParameters(
        command=sys.executable,
        args=["-m", "logix_project_mcp.server", "--project", str(project)],
        env=environment,
    )
    try:
        with open(os.devnull, "w", encoding="utf-8") as diagnostics:
            async with (
                stdio_client(launch, errlog=diagnostics) as (reader, writer),
                ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=105)) as client,
            ):
                await client.initialize()
                result = await client.call_tool("get_project")
    except Exception:
        return Check(
            "FAIL", name,
            "MCP stdio did not complete. Check the local Python environment and launch configuration.",
        )

    if result.isError:
        message = " ".join(getattr(item, "text", "") for item in result.content)
        return Check("FAIL", name, tool_error_hint(message))
    revision = (result.structuredContent or {}).get("software_revision")
    if isinstance(revision, str) and re.fullmatch(r"\d+(?:\.\d+){0,3}", revision):
        return Check("PASS", name, f"MCP opened the saved project at Logix Designer revision {revision}.")
    return Check("PASS", name, "MCP opened the saved project.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, help="Verify an ACD, L5K, or full L5X through MCP stdio")
    parser.add_argument(
        "--compare-launch-env", action="store_true",
        help="Also test the MCP client's reduced environment for a native project",
    )
    args = parser.parse_args()
    project = args.project
    suffix = project.suffix.lower() if project else None
    native = suffix in NATIVE_EXTENSIONS or project is None
    if project and (suffix not in NATIVE_EXTENSIONS | {".l5x"} or not project.is_file()):
        parser.error("--project must point to an existing .ACD, .L5K, or .L5X file")
    if args.compare_launch_env and (project is None or not native):
        parser.error("--compare-launch-env requires an .ACD or .L5K project")

    checks = [Check("PASS", "Python", f"{platform.python_version()} ({sysconfig.get_platform()}).")]
    for package in ("logix-project-mcp", "mcp", "defusedxml"):
        installed = package_version(package)
        checks.append(Check(
            "PASS" if installed else "FAIL", package,
            installed or "Install the MCP package and its dependencies in this Python environment.",
        ))

    if native:
        if sys.platform == "win32":
            wheel = package_version("logix-designer-sdk")
            checks.append(Check(
                "PASS" if wheel else "FAIL", "Rockwell Python SDK",
                wheel or "Install the Rockwell Python wheel in this environment.",
            ))
            checks.extend(windows_checks(wheel, dotnet_root()))
        else:
            checks.append(Check(
                "FAIL", "Native projects",
                "ACD and L5K require the Rockwell SDK on Windows. Use a full L5X export on this host.",
            ))

    for check in checks:
        print(f"[{check.status}] {check.name} - {check.detail}", flush=True)
    failed = any(check.status == "FAIL" for check in checks)
    if project and not failed:
        environment = dict(os.environ) if native else None
        name = "MCP inherited launch" if native else "MCP SDK-free launch"
        probe = asyncio.run(probe_mcp(project.resolve(), environment, name))
        print(f"[{probe.status}] {probe.name} - {probe.detail}", flush=True)
        failed = probe.status == "FAIL"
        if args.compare_launch_env:
            reduced = {
                name: os.environ[name] for name in ("DOTNET_ROOT", "ProgramFiles")
                if name in os.environ
            }
            comparison = asyncio.run(probe_mcp(project.resolve(), reduced, "MCP reduced launch"))
            status = "WARN" if comparison.status == "FAIL" and not failed else comparison.status
            print(f"[{status}] {comparison.name} - {comparison.detail}", flush=True)
    elif project and failed:
        print("Fix the failed prerequisite checks to run the MCP project probe.")
    elif not failed:
        print("Use --project with a saved sample to verify an MCP project read.")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
