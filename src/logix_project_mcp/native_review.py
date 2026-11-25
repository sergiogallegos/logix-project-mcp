"""Apply one locally approved routine description to a staged ACD and routine export."""

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Callable
from hashlib import file_digest
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree.ElementTree import Element, tostring

from pydantic import TypeAdapter

from .build_check import check_build
from .documentation import description_spans
from .export import RoutineComponent, component_xpath, validate_artifact
from .inventory import PROTECTION_ELEMENTS, xml_boolean
from .project import (ProjectReadError, ProjectSnapshot, controller_from_l5x, export_snapshot,
                      parse_l5x, parse_l5x_bytes, run_sdk_worker, snapshot_source)
from .proposals import Proposal, check_documentation_boundary, resolve_target, validate_proposal
from .selection import ProjectSelection, read_selection, validate_project_path


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
        paths = {p.suffix[1:].lower(): str(destination / p.name) for p in (acd, component)}
        receipt = {"proposal": proposal, "outputs": paths}
        if not confirm(receipt):
            return None
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
        # Windows rename publishes the complete pair and fails if the destination now exists.
        if sha256_file(bundle / component.name) != component_hash or sha256_file(bundle / acd.name) != acd_hash:
            raise ProjectReadError("artifact_changed", "A verified output changed before publication.")
        try:
            os.rename(bundle, destination)
        except OSError as exc:
            if os.path.lexists(destination):
                raise ProjectReadError("destination_exists", "The output directory is already occupied.") from exc
            raise
        return {**receipt, "sha256": hashes, "build": build}


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
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument("--approval-id", required=True)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    if not sys.stdin.isatty():
        parser.error("Review requires a local interactive terminal.")
    try:
        if args.project:
            fixed = ProjectSelection(validate_project_path(args.project))
            current = lambda: fixed
        else:
            current = lambda: read_selection(args.selection_file)
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
