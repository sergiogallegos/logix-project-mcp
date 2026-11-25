"""Exercise the offline documentation workflow with an installed wheel and a sample project."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import sysconfig
from contextlib import asynccontextmanager
from datetime import timedelta
from hashlib import file_digest
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def launcher(name):
    return str(Path(sysconfig.get_path("scripts")) / (name + ".exe" if os.name == "nt" else name))


def digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


@asynccontextmanager
async def connect(*args):
    params = StdioServerParameters(command=launcher("logix-project-mcp"), args=list(map(str, args)), env=dict(os.environ))
    async with stdio_client(params) as streams, ClientSession(*streams, read_timeout_seconds=timedelta(minutes=3)) as client:
        await client.initialize()
        yield client


async def call(client, name, **args):
    result = await client.call_tool(name, args)
    if result.isError:
        raise RuntimeError(f"{name} failed: {result.content}")
    return result.structuredContent


def cli(name, *args):
    # stderr and stdin stay attached so only the local review command prompts.
    result = subprocess.run([launcher(name), *args], stdout=subprocess.PIPE, encoding="utf-8",
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    result.check_returncode()
    return json.loads(result.stdout)


async def check_import(folder, imported):
    evidence = json.loads((folder / "acceptance.json").read_text(encoding="utf-8"))
    source = Path(evidence["source"])
    require(imported.suffix.lower() == ".acd" and not imported.samefile(source),
            "Choose the separate ACD created by the desktop import.")
    candidate = folder / "Reviewed.L5X"
    checked = cli("logix-project-mcp-review", "--selection-file", folder / "selection.json",
                  "--check", evidence["review_id"], candidate)
    require(checked["artifact"]["artifact_sha256"] == evidence["artifact_sha256"], "Reviewed L5X hash differs.")
    operation, = checked["proposal"]["operations"]
    target = {"program": operation["target"]["program"], "routine": operation["target"]["name"]}
    imported_hash = digest(imported)
    async with connect("--project", candidate) as client:
        expected = await call(client, "read_routine", **target)
    async with connect("--project", imported) as client:
        summary = await call(client, "get_project")
        actual = await call(client, "read_routine", **target)
    note = operation["description"]
    # Logix Designer can surround description CDATA with XML formatting newlines.
    require(actual["inspection"]["description"] in (note, f"\n{note}\n"),
            "The imported ACD does not contain the reviewed routine description.")
    require(actual["inspection"]["language"] == expected["inspection"]["language"]
            and actual["inspection"]["sections"] == expected["inspection"]["sections"],
            "The imported routine sections differ from the reviewed copy.")
    require(summary["software_revision"] == evidence["revision"]
            and summary["controller"] == checked["proposal"]["source"]["controller"],
            "The imported controller or project revision differs.")
    require(actual["source_sha256"] == summary["source_sha256"] == imported_hash == digest(imported)
            and expected["source_sha256"] == digest(candidate) == evidence["artifact_sha256"]
            and digest(source) == evidence["source_sha256"], "A saved file changed during import or readback.")
    return {"imported_acd": str(imported), "imported_sha256": imported_hash, "review_id": evidence["review_id"],
            "revision": summary["software_revision"], "routine": evidence["routine"], "description": note}


async def accept(source, folder, program, routine, description):
    source_hash = digest(source)
    folder.mkdir(parents=True, exist_ok=False)
    selection = folder / "selection.json"
    baseline, candidate = folder / "Baseline.L5X", folder / "Reviewed.L5X"
    target = {"program": program, "routine": routine}
    qualified = f"Program:{program}.{routine}"
    share_args = ("logix-project-mcp-share", "--selection-file", selection)
    try:
        print(f"Sharing the saved sample {source.name}.", file=sys.stderr, flush=True)
        shared = cli(*share_args, source)
        async with connect("--selection-file", selection, "--export-dir", folder) as client:
            summary = await call(client, "get_project")
            require(summary["source_sha256"] == shared["source_sha256"] == source_hash
                    and summary["selection"]["selection_id"] == shared["selection_id"], "Shared source changed.")
            found = await call(client, "search_project", query=routine, program=program, kind="routine")
            require([m["symbol"]["qualified_name"] for m in found["matches"]] == [qualified], "Scoped routine not found.")
            original = await call(client, "read_routine", **target)
            require(original["inspection"]["status"] == "readable" and original["inspection"]["language"] in ("RLL", "ST"),
                    "Choose a readable Ladder or ST routine.")
            print(f"Exporting the full project after inspecting {qualified}.", file=sys.stderr, flush=True)
            exported = await call(client, "export_project", filename=baseline.name)
            require(exported["source_sha256"] == original["source_sha256"] == found["source_sha256"] == source_hash,
                    "Inspection and export refer to different saves.")
            selected = cli(*share_args, baseline)
            baseline_hash = digest(baseline)
            require(selected["source_sha256"] == baseline_hash, "Export changed during sharing.")
            operation = {"operation": "set_description", "target": {"kind": "routine", "program": program, "name": routine},
                         "description": description}

            async def preview(selection_id):
                return await call(client, "preview_change_proposal", operations=[operation],
                                  expected_source_sha256=baseline_hash, expected_selection_id=selection_id)

            stale = await preview(selected["selection_id"])
            refreshed = cli(*share_args, "--refresh")
            rejected = await client.call_tool("create_documentation_copy", {
                "proposal": stale, "expected_approval_id": stale["approval_id"], "filename": candidate.name,
            })
            require(rejected.isError and rejected.meta["logix-project-mcp/error"]["code"] == "selection_changed"
                    and not candidate.exists(), "The stale selection did not fail cleanly.")

            proposal = await preview(refreshed["selection_id"])
            request = {"proposal": proposal, "expected_approval_id": proposal["approval_id"]}
            await call(client, "validate_change_proposal", **request)
            receipt = await call(client, "create_documentation_copy", filename=candidate.name, **request)
            verification = await call(client, "verify_documentation_copy", filename=candidate.name, **request,
                                      expected_artifact_sha256=receipt["artifact_sha256"])
        async with connect("--project", baseline, "--compare-project", candidate) as client:
            comparison = await call(client, "compare_projects")
            changes = comparison["changes"]
            require(comparison["before"]["source_sha256"] == baseline_hash
                    and comparison["after"]["source_sha256"] == receipt["artifact_sha256"]
                    and len(changes) == 1 and changes[0]["component"]["qualified_name"] == qualified
                    and changes[0]["change"] == "modified" and changes[0]["source_diff"] is None,
                    "Expected only the selected routine's documentation to differ.")
        proposal_file, receipt_file = folder / "proposal.json", folder / "creation.json"
        proposal_file.write_text(json.dumps(proposal), encoding="utf-8")
        receipt_file.write_text(json.dumps(receipt), encoding="utf-8")
        print(f"Stale proposal rejected. The new comparison shows one documentation change to {qualified}.",
              file=sys.stderr, flush=True)
        review = ("logix-project-mcp-review", "--selection-file", selection)
        record = await asyncio.to_thread(cli, *review, "--proposal", proposal_file, "--receipt", receipt_file, candidate)
        checked = cli(*review, "--check", record["review_id"], candidate)
        require(checked["artifact"] == verification, "Local handoff differs from the MCP verification.")
        async with connect("--project", checked["artifact"]["path"]) as client:
            reopened = await call(client, "read_routine", **target)
            require(reopened["source_sha256"] == receipt["artifact_sha256"]
                    and reopened["inspection"]["description"] == description
                    and reopened["inspection"]["sections"] == original["inspection"]["sections"],
                    "Reopened routine differs from the reviewed description or selected saved logic.")
        require(digest(baseline) == baseline_hash and digest(candidate) == receipt["artifact_sha256"],
                "Baseline or candidate changed before handoff.")
    finally:
        require(digest(source) == source_hash, "The original saved sample changed during acceptance.")

    evidence = {
        "source": str(source), "source_sha256": source_hash, "revision": summary["software_revision"],
        "baseline": str(baseline), "baseline_sha256": baseline_hash, "routine": qualified,
        "stale_proposal_error": "selection_changed", "review_id": record["review_id"],
        "verified_copy": checked["artifact"]["path"], "artifact_sha256": reopened["source_sha256"],
        "reopened_with": "MCP read_routine",
    }
    (folder / "acceptance.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Share, inspect and review a saved sample")
    run.add_argument("sample", type=Path)
    run.add_argument("--work-dir", required=True, type=Path, help="New directory for this run")
    run.add_argument("--program", required=True)
    run.add_argument("--routine", required=True)
    run.add_argument("--description", required=True, help="New documentation text for the sample routine")
    reopen = commands.add_parser("check-import", help="Read back the separate ACD created by Studio")
    reopen.add_argument("imported", type=Path)
    reopen.add_argument("--work-dir", required=True, type=Path, help="Completed run directory")
    args = parser.parse_args()
    if args.command == "run" and not sys.stdin.isatty():
        parser.error("Run acceptance in an interactive terminal for local review.")
    try:
        if args.command == "check-import":
            result = asyncio.run(check_import(args.work_dir.resolve(strict=True), args.imported.resolve(strict=True)))
        else:
            result = asyncio.run(accept(args.sample.resolve(strict=True), args.work_dir.resolve(),
                                        args.program, args.routine, args.description))
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc
    except (OSError, ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
