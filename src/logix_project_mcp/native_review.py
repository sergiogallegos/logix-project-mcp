"""Apply one locally approved routine description to a staged ACD and routine export."""

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import file_digest, sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from xml.etree.ElementTree import Element, tostring

from pydantic import TypeAdapter

from .build_check import BuildReport, check_build
from .documentation import description_spans, snapshot_artifact
from .export import RoutineComponent, component_xpath, validate_artifact
from .inventory import PROTECTION_ELEMENTS, xml_boolean
from .project import (ProjectReadError, ProjectSnapshot, controller_from_l5x, export_snapshot, file_version,
                      parse_l5x, parse_l5x_bytes, run_sdk_worker, snapshot_source)
from .proposals import (Digest, Proposal, StrictRecord, canonical_json, check_documentation_boundary,
                        resolve_target, validate_proposal)
from .review import approval_path_for
from .selection import ProjectSelection, read_selection, validate_project_path


class OutputPair[T](StrictRecord):
    acd: T
    l5x: T


class NativeApproval(StrictRecord):
    schema_version: Literal[1]
    decision: Literal["approved_native_copy"]
    approved_at: str
    proposal: Proposal
    outputs: OutputPair[str]
    approval_path: str
    sha256: OutputPair[Digest]
    build: BuildReport


def output_paths(directory: Path) -> OutputPair[str]:
    return {"acd": str(directory / "Reviewed.ACD"), "l5x": str(directory / "Routine.L5X")}


async def check_native_approval(current: Callable[[], ProjectSelection], destination: Path, review_id: str) -> dict:
    selection = current()
    destination = destination.resolve(strict=True)
    paths = output_paths(destination)
    approval = approval_path_for(Path(paths["acd"]))
    if not os.path.lexists(approval):
        raise ProjectReadError("artifact_unavailable", "This bundle has no native approval record to check.")
    acd, component = Path(paths["acd"]), Path(paths["l5x"])
    files = (selection.path, acd, component, approval)
    with TemporaryDirectory(prefix="logix-check-native-") as temporary:
        folder = Path(temporary)
        versions = [file_version(path.lstat()) for path in files]
        saved = folder / "approval.json"
        if await snapshot_artifact(approval, saved) != review_id:
            raise ProjectReadError("artifact_changed", "The approval record differs from the retained review ID.")
        record = TypeAdapter(NativeApproval).validate_json(saved.read_bytes(), strict=True)
        if record["outputs"] != paths or record["approval_path"] != str(approval):
            raise ProjectReadError("invalid_proposal", "The approval belongs to a different output directory.")
        source = record["proposal"]["source"]
        build = record["build"]
        if (build["status"] == "failed" or build["artifact_sha256"] != record["sha256"]["acd"]
                or build["software_revision"] != source["software_revision"]):
            raise ProjectReadError("invalid_proposal", "The build record does not match the approved ACD.")
        if str(selection.path) != source["path"] or selection.selection_id != source["selection_id"]:
            raise ProjectReadError("selection_changed", "The approval belongs to a different saved project selection.")
        if await snapshot_source(selection.path, folder / "source.ACD") != source["source_sha256"]:
            raise ProjectReadError("project_changed", "The approved source has changed. Create a fresh preview.")
        for kind, path in (("acd", acd), ("l5x", component)):
            if await snapshot_artifact(path, folder / path.name) != record["sha256"][kind]:
                raise ProjectReadError("artifact_changed", f"{path.name} differs from the approved output.")
        if versions != [file_version(path.lstat()) for path in files]:
            raise ProjectReadError("artifact_changed", "A file changed while checking the approval.")
        if current() != selection:
            raise ProjectReadError("selection_changed", "The selection changed while checking the approval.")
    return {**record, "review_id": review_id}


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def patch_component(path: Path, target: RoutineComponent, proposal: Proposal) -> None:
    validate_artifact(path, target)
    data = path.read_bytes()
    root = parse_l5x_bytes(data)
    if root.get("SoftwareRevision") != proposal["source"]["software_revision"]:
        raise ProjectReadError("export_failed", "The routine export has a different software revision.")
    _, routine = resolve_target(root.find("Controller"), target)
    change = proposal["preview"][0]
    descriptions = routine.findall("Description")
    if (routine.get("Use") != "Target" or len(descriptions) > 1
            or routine.findtext("Description") != change["before"]):
        raise ProjectReadError("export_failed", "The exported routine differs from the reviewed target.")
    spans = description_spans(data, root)
    start = end = spans[routine].opening_end
    if descriptions:
        span = spans[descriptions[0]]
        start, end = span.start, span.end
    text = change["after"]
    replacement = b""
    if text is not None:
        # Studio writes descriptions as CDATA. Preserve a literal closing delimiter across sections.
        escaped = text.replace("]]>", "]]]]><![CDATA[>").replace("\r", "]]>&#13;<![CDATA[")
        replacement = f"<Description><![CDATA[{escaped}]]></Description>".encode("utf-8")
    path.write_bytes(data[:start] + replacement + data[end:])
    _, updated = resolve_target(parse_l5x(path).find("Controller"), target)
    if updated.findtext("Description") != text:
        raise ProjectReadError("export_failed", "The routine component could not represent the reviewed text.")


def verify_readback(baseline: Element, reopened: Element, target: RoutineComponent, proposal: Proposal) -> None:
    check_documentation_boundary(reopened)
    revision = baseline.get("SoftwareRevision")
    if not revision or reopened.get("SoftwareRevision") != revision:
        raise ProjectReadError("export_failed", "The staged project has a different software revision.")
    before, after = controller_from_l5x(baseline), controller_from_l5x(reopened)
    _, original = resolve_target(before, target)
    _, updated = resolve_target(after, target)
    expected = proposal["preview"][0]["after"]
    actual = updated.findtext("Description")
    if actual != expected and (expected is None or actual != f"\n{expected}\n"):
        raise ProjectReadError("export_failed", "The reopened ACD differs from the approved description.")
    # Remove the reviewed field from both exports before comparing the complete controller trees.
    for controller, routine in ((before, original), (after, updated)):
        controller.attrib.pop("LastModifiedDate", None)
        description = routine.find("Description")
        if description is not None:
            routine.remove(description)
        pending = [controller]
        while pending:
            node = pending.pop()
            if node.tail is not None and not node.tail.strip():
                node.tail = None
            if node.tag in PROTECTION_ELEMENTS or xml_boolean(node, "IsEncrypted") is True:
                continue
            if len(node) and node.text is not None and not node.text.strip():
                node.text = None
            pending.extend(node)
    if tostring(before) != tostring(after):
        raise ProjectReadError("export_failed", "The reopened ACD has changes outside the reviewed description.")


async def publish_native(current: Callable[[], ProjectSelection], proposal: Proposal, approval_id: str,
                         destination: Path, confirm: Callable[[dict], bool]) -> dict | None:
    if sys.platform != "win32":
        raise ProjectReadError("unsupported_platform", "Native review requires the Windows Logix Designer SDK.")
    selection = current()
    proposal = deepcopy(proposal)
    destination = destination.parent.resolve(strict=True) / destination.name
    changes = proposal["operations"]
    if (selection.path.suffix.lower() != ".acd" or len(changes) != 1
            or changes[0]["target"]["kind"] != "routine"):
        raise ProjectReadError("invalid_proposal", "Select an ACD with one reviewed routine description.")
    target = TypeAdapter(RoutineComponent).validate_python(changes[0]["target"], strict=True)
    if os.path.lexists(destination):
        raise ProjectReadError("destination_exists", "Choose a new output directory.")
    with TemporaryDirectory(dir=destination.parent, prefix=".logix-native-") as temporary:
        folder = Path(temporary)
        bundle = folder / "bundle"
        acd, component = folder / "Reviewed.ACD", folder / "Routine.L5X"
        fingerprint = await snapshot_source(selection.path, acd)
        if fingerprint != proposal["source"]["source_sha256"]:
            raise ProjectReadError("project_changed", "The source changed after preview. Create a new proposal.")
        baseline = folder / "baseline.L5X"
        await export_snapshot(acd, baseline, selection.path.name)
        root = parse_l5x(baseline)
        validate_proposal(selection, ProjectSnapshot(root, controller_from_l5x(root), fingerprint), proposal, approval_id)
        paths = output_paths(destination)
        approval = approval_path_for(Path(paths["acd"]))
        receipt = {"proposal": proposal, "outputs": paths, "approval_path": str(approval)}
        if not confirm(deepcopy(receipt)):
            return None
        approved_at = datetime.now(timezone.utc).isoformat()
        if current() != selection:
            raise ProjectReadError("selection_changed", "The project selection changed during native review.")
        if await snapshot_source(selection.path, folder / "approved.ACD") != fingerprint:
            raise ProjectReadError("project_changed", "The source changed during native review.")
        xpath = component_xpath(target)
        await export_snapshot(acd, component, selection.path.name, xpath)
        patch_component(component, target, proposal)
        component_hash = sha256_file(component)
        await run_sdk_worker(acd.name, "import", "--import-routine", str(acd), str(component), xpath.rsplit("/", 1)[0])
        bundle.mkdir()
        acd_hash = await snapshot_source(acd, bundle / acd.name)
        readback = folder / "reopened.L5X"
        await export_snapshot(acd, readback, acd.name)
        verify_readback(root, parse_l5x(readback), target, proposal)
        if await snapshot_source(component, bundle / component.name) != component_hash or sha256_file(acd) != acd_hash:
            raise ProjectReadError("artifact_changed", "A staged output changed during verification.")
        hashes = {"acd": acd_hash, "l5x": component_hash}
        build = await check_build(bundle / acd.name, acd_hash, known_revision=root.get("SoftwareRevision"))
        if build["status"] == "failed":
            raise ProjectReadError("export_failed", "Logix Designer rejected the staged project. " +
                                   "\n".join(build["diagnostics"]))
        if await snapshot_source(selection.path, folder / "latest.ACD") != fingerprint:
            raise ProjectReadError("project_changed", "The source changed during native review.")
        if current() != selection:
            raise ProjectReadError("selection_changed", "The project selection changed during native review.")
        record: NativeApproval = {
            "schema_version": 1, "decision": "approved_native_copy", "approved_at": approved_at,
            "proposal": proposal, "outputs": paths, "approval_path": str(approval), "sha256": hashes, "build": build,
        }
        encoded = canonical_json(record) + b"\n"
        review_id = sha256(encoded).hexdigest()
        staged_record = bundle / approval.name
        with staged_record.open("xb") as stream:
            stream.write(encoded)
        if (sha256_file(bundle / component.name) != component_hash or sha256_file(bundle / acd.name) != acd_hash
                or sha256_file(staged_record) != review_id):
            raise ProjectReadError("artifact_changed", "A verified output changed before publication.")
        # Windows rename publishes both artifacts and the approval together without replacing an existing directory.
        try:
            os.rename(bundle, destination)
        except OSError as exc:
            if os.path.lexists(destination):
                raise ProjectReadError("destination_exists", "The output directory is already occupied.") from exc
            raise
        return {**record, "review_id": review_id}


def confirm_native(receipt: dict) -> bool:
    print(json.dumps(receipt, indent=2, ensure_ascii=True), file=sys.stderr)
    print("Type APPROVE to apply this description to the staged ACD and publish both files: ",
          end="", flush=True, file=sys.stderr)
    return sys.stdin.readline().strip() == "APPROVE"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--project", type=Path)
    source.add_argument("--selection-file", type=Path)
    parser.add_argument("--check", metavar="REVIEW_ID", help="Check the published bundle against the retained review ID")
    parser.add_argument("--proposal", type=Path)
    parser.add_argument("--approval-id")
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    if args.check is not None and (args.proposal is not None or args.approval_id is not None):
        parser.error("Use --check with the output directory and the original source selection.")
    if args.check is None and (args.proposal is None or args.approval_id is None):
        parser.error("Approval requires --proposal and --approval-id.")
    if args.check is None and not sys.stdin.isatty():
        parser.error("Review requires a local interactive terminal.")
    try:
        if args.project:
            fixed = ProjectSelection(validate_project_path(args.project))
            current = lambda: fixed
        else:
            current = lambda: read_selection(args.selection_file)
        if args.check is not None:
            checked = asyncio.run(check_native_approval(current, args.output_directory.absolute(), args.check))
            print(json.dumps(checked))
            return
        proposal = TypeAdapter(Proposal).validate_json(args.proposal.read_bytes(), strict=True)
        result = asyncio.run(publish_native(current, proposal, args.approval_id, args.output_directory.absolute(),
                                            confirm_native))
        if result is None:
            raise SystemExit(2)
        print(json.dumps(result))
    except (ProjectReadError, OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
