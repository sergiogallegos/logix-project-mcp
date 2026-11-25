"""Check a reviewed full project with the offline Logix Designer SDK compiler."""

import argparse
import asyncio
import json
import re
import sys
from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, TypedDict

from .project import ProjectReadError, controller_from_l5x, export_snapshot, parse_l5x, run_sdk_worker, snapshot_source


class BuildReport(TypedDict):
    status: Literal["passed", "failed", "manual_required"]
    artifact_sha256: str
    software_revision: str | None
    diagnostics: list[str]


def build_messages(log: Path) -> tuple[list[str], bool]:
    errors, warnings = [], []
    count = 0
    with log.open(encoding="utf-8-sig", errors="replace") as stream:
        for line in stream:
            # LogFileEventLogger prefixes entries with timestamp, severity and project path.
            match = re.match(r"^\[[^\]]+\]\[([^\]]+)\]\[.*?\] (.*)", line)
            if not match:
                continue
            level, message = match.groups()
            if message.startswith("ImportLog <Exception "):
                severity = re.search(r"""\bSeverity=['"](Error|Warning)['"]""", message, re.I)
                if severity:
                    level = severity[1].upper()
            if level == "ERROR" or re.match(r"Error\s*:", message, re.I):
                group = errors
            elif level in ("WARN", "WARNING") or re.match(r"Warning\s*:", message, re.I):
                group = warnings
            else:
                continue
            count += 1
            if len(group) < 30:
                group.append(message[:500])
    messages = (errors + warnings)[:30]
    if count > len(messages):
        messages.append(f"{count - len(messages)} additional diagnostics omitted.")
    return messages, bool(errors)


async def check_build(artifact: Path, expected_sha256: str, *, known_revision: str | None = None) -> BuildReport:
    suffix = artifact.suffix.lower()
    if suffix not in (".acd", ".l5x"):
        raise ProjectReadError("invalid_project", "Select a reviewed ACD or a full project L5X.")
    with TemporaryDirectory(prefix="logix-build-") as tmp:
        folder = Path(tmp)
        scratch = folder / ("Project" + suffix)
        digest = await snapshot_source(artifact, scratch)
        if digest != expected_sha256.lower():
            raise ProjectReadError("artifact_changed", "The artifact differs from the retained SHA-256.")
        revision = known_revision
        sdk_available = sys.platform == "win32" and find_spec("logix_designer_sdk") is not None
        if suffix == ".l5x" or (revision is None and sdk_available):
            xml = scratch
            if suffix == ".acd":
                xml = folder / "Baseline.L5X"
                await export_snapshot(scratch, xml, artifact.name)
            root = parse_l5x(xml)
            controller_from_l5x(root)
            revision = root.get("SoftwareRevision")
        report: BuildReport = {"status": "manual_required", "artifact_sha256": digest,
                               "software_revision": revision, "diagnostics": []}
        if not sdk_available:
            report["diagnostics"].append("Use Verify Controller in the matching Logix Designer or run this check with the Windows SDK.")
        elif not revision or not re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]+)?", revision):
            raise ProjectReadError("invalid_project", "Cannot determine the Logix Designer revision for the build.")
        elif int(revision.split(".")[0]) < 37:
            report["diagnostics"].append("This revision needs Verify Controller in the matching Logix Designer.")
        else:
            result = folder / "build.json"
            await run_sdk_worker(artifact.name, "build", "--build", str(scratch), str(result))
            error = json.loads(result.read_text(encoding="utf-8"))["error"]
            report["diagnostics"], logged_error = build_messages(result.with_suffix(".log"))
            report["status"] = "failed" if error is not None or logged_error else "passed"
            if error is not None:
                report["diagnostics"].insert(0, error)
        if await snapshot_source(artifact, folder / "latest") != digest:
            raise ProjectReadError("artifact_changed", "The artifact changed during the build check.")
        return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path, help="Reviewed ACD or full project L5X")
    parser.add_argument("--sha256", required=True, help="Artifact SHA-256 from the review receipt")
    args = parser.parse_args()
    try:
        report = asyncio.run(check_build(args.artifact.absolute(), args.sha256))
    except (OSError, ProjectReadError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
    print(json.dumps(report))
    raise SystemExit({"passed": 0, "failed": 1, "manual_required": 2}[report["status"]])


if __name__ == "__main__":
    main()
