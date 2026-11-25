"""Measure offline inspection through installed MCP stdio servers."""

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from xml.etree.ElementTree import Element, SubElement, tostring

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def fixture(programs: int, tags: int, lines: int) -> bytes:
    root = Element("RSLogix5000Content", TargetType="Controller", SoftwareRevision="38.02")
    controller = SubElement(root, "Controller", Name="Benchmark")
    collection = SubElement(controller, "Programs")
    for p in range(programs):
        program = SubElement(collection, "Program", Name=f"Program{p}")
        declarations = SubElement(program, "Tags")
        for t in range(tags):
            tag = SubElement(declarations, "Tag", Name=f"Point{t}", DataType="DINT")
            description = "BaselineMarker" if (p, t) == (programs - 1, tags - 1) else f"Inspection point {t} in program {p}"
            SubElement(tag, "Description").text = description
        routines = SubElement(program, "Routines")
        for r in range(4):
            routine = SubElement(routines, "Routine", Name=f"Notes{r}", Type="ST")
            body = SubElement(routine, "STContent")
            for i in range(lines):
                SubElement(body, "Line", Number=str(i)).text = f"// Inspection note {i} for program {p}"
    return tostring(root, encoding="utf-8")


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def peak_mib(pid: int) -> float | None:
    if sys.platform == "win32":
        count = subprocess.check_output([
            "powershell.exe", "-NoProfile", "-NonInteractive", "-Command", f"(Get-Process -Id {pid}).PeakWorkingSet64",
        ], text=True)
        return round(int(count) / (1024 ** 2), 1)
    if sys.platform.startswith("linux"):
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmHWM:"):
                return round(int(line.split()[1]) / 1024, 1)
    return None


@asynccontextmanager
async def connect(source: Path, pid_file: Path, comparison: Path | None = None):
    # Capture the server PID without modifying its CLI or writing to its stdout.
    launcher = ("import os, sys; from pathlib import Path; "
                "Path(sys.argv.pop(1)).write_text(str(os.getpid())); "
                "from logix_project_mcp.server import main; main()")
    args = ["-c", launcher, str(pid_file), "--project", str(source)]
    if comparison:
        args += ["--compare-project", str(comparison)]
    params = StdioServerParameters(command=sys.executable, args=args, env=dict(os.environ))
    start = perf_counter()
    async with stdio_client(params) as streams, ClientSession(*streams, read_timeout_seconds=timedelta(minutes=3)) as client:
        await client.initialize()
        startup = round(perf_counter() - start, 4)
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert "get_project" in tools and (comparison is None or "compare_projects" in tools)
        yield client, int(pid_file.read_text()), startup


async def timed(client, name, args=None):
    start = perf_counter()
    result = await client.call_tool(name, args or {})
    seconds = round(perf_counter() - start, 4)
    if result.isError:
        raise RuntimeError(f"{name}: {result.content}")
    return result.structuredContent, seconds


async def l5x(folder: Path, programs: int, tags: int, lines: int):
    source, candidate = folder / "Selected.L5X", folder / "Candidate.L5X"
    data = fixture(programs, tags, lines)
    source.write_bytes(data)
    candidate.write_bytes(data.replace(b"BaselineMarker", b"ReviewedMarker"))
    before, after = digest(source), digest(candidate)
    match_name = f"Program:Program{programs - 1}.Point{tags - 1}"
    query = {"kind": "comment", "query": "BaselineMarker"}

    def check_search(result):
        assert result["source_sha256"] == before and len(result["matches"]) == 1
        assert result["matches"][0]["location"]["program"] == f"Program{programs - 1}"
        assert result["matches"][0]["location"]["declaration"] == f"Point{tags - 1}"

    async with connect(source, folder / "first.pid", candidate) as (first, pid, startup):
        report = {"bytes": len(data), "startup_s": startup}
        for tool in ("get_project", "search_project", "compare_projects"):
            samples = []
            for _ in range(3):
                result, elapsed = await timed(first, tool, query if tool == "search_project" else None)
                samples.append(elapsed)
                if tool == "get_project":
                    assert result["source_sha256"] == before and len(result["programs"]) == programs
                elif tool == "search_project":
                    check_search(result)
                else:
                    assert result["before"]["source_sha256"] == before and result["after"]["source_sha256"] == after
                    assert [c["component"]["qualified_name"] for c in result["changes"]] == [match_name]
            report[tool + "_s"] = samples
        async with connect(source, folder / "second.pid") as (second, other_pid, _):
            start = perf_counter()
            pair = await asyncio.gather(timed(first, "search_project", query), timed(second, "search_project", query))
            report["paired_wall_s"] = round(perf_counter() - start, 4)
            report["paired_client_s"] = [elapsed for _, elapsed in pair]
            for result, _ in pair:
                check_search(result)
            report["server_peak_mib"] = [peak_mib(pid), peak_mib(other_pid)]
        assert digest(source) == before and digest(candidate) == after
        return report


async def native(folder: Path, originals: list[Path]):
    suffix = originals[0].suffix.lower()
    if suffix not in (".acd", ".l5k") or originals[1].suffix.lower() != suffix:
        raise ValueError("Supply two saved ACD files or two saved L5K files.")
    fingerprints = [digest(path) for path in originals]
    if fingerprints[0] == fingerprints[1]:
        raise ValueError("The samples must have different saved bytes.")
    selected = folder / ("Selected" + suffix)
    shutil.copyfile(originals[0], selected)
    results = []
    async with connect(selected, folder / "native.pid") as (client, pid, startup):
        projections = []
        for index, fingerprint in enumerate(fingerprints):
            if index:
                # Publish the second saved version at the same path in this session.
                staged = folder / ("NewSave" + suffix)
                shutil.copyfile(originals[index], staged)
                staged.replace(selected)
            samples = []
            for _ in range(3):
                result, elapsed = await timed(client, "get_project")
                assert result["source_sha256"] == fingerprint
                projection = {key: value for key, value in result.items() if key != "source_sha256"}
                if samples:
                    assert projections[-1] == projection
                else:
                    projections.append(projection)
                samples.append(elapsed)
            results.append({"bytes": selected.stat().st_size, "revision": result["software_revision"],
                            "programs": len(result["programs"]), "get_project_s": samples,
                            "server_peak_mib": peak_mib(pid)})
        if projections[0] == projections[1]:
            raise ValueError("Choose samples with a visible difference in the controller, revision, programs or routines.")
        async with connect(selected, folder / "independent.pid") as (independent, _, _):
            fresh, _ = await timed(independent, "get_project")
            assert fresh == result, "The post-save summary differs from an independent cold read."
        assert [digest(path) for path in originals] == fingerprints
    return {"startup_s": startup, "saved_versions": results}


def native_fixtures(folder: Path, template: Path) -> list[Path]:
    """Scale the empty synthetic revision 38 L5K from docs/compatibility.md."""
    content = template.read_text(encoding="utf-8-sig")
    empty_tags = "\n\tTAG\n\tEND_TAG"
    controller = "CONTROLLER McpSnapshotSample ("
    if content.count(empty_tags) != 1 or content.count(controller) != 1:
        raise ValueError("Use the empty Synthetic38.L5K from the compatibility walkthrough.")
    paths = []
    for count in (16, 8192):
        declarations = "".join(f"\t\tPoint{i} : DINT (RADIX := Decimal) := 0;\n" for i in range(count))
        data = content.replace(empty_tags, "\n\tTAG\n" + declarations + "\tEND_TAG")
        path = folder / f"Sample{count}.L5K"
        path.write_text(data.replace(controller, f"CONTROLLER Sample{count} ("), encoding="utf-8")
        paths.append(path)
    return paths


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--native-pair", nargs=2, type=Path, metavar=("FIRST", "SECOND"),
                        help="Benchmark two native samples with different project summaries on Windows")
    inputs.add_argument("--synthetic-l5k", type=Path, metavar="TEMPLATE",
                        help="Generate and benchmark small and large L5K files from the empty Synthetic38.L5K")
    args = parser.parse_args()
    with TemporaryDirectory(prefix="logix-benchmark-") as temporary:
        folder = Path(temporary)
        if args.synthetic_l5k:
            results = await native(folder, native_fixtures(folder, args.synthetic_l5k))
        elif args.native_pair:
            results = await native(folder, args.native_pair)
        else:
            results = {"small": await l5x(folder, 1, 16, 8), "large": await l5x(folder, 32, 256, 128)}
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
