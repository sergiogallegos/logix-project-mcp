"""Read-only, content-bound previews of proposed documentation changes."""

import json
from collections.abc import Iterable
from hashlib import sha256
from typing import Annotated, Literal, TypedDict
from xml.etree.ElementTree import Element

from pydantic import AfterValidator, ConfigDict, Field

from .inventory import component_entries, has_protection
from .project import ProjectReadError, ProjectSnapshot
from .selection import ProjectSelection, SelectionId

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Name = Annotated[str, Field(min_length=1, max_length=255, pattern=r"\S")]


def xml_text(value: str) -> str:
    if any(not (c in "\t\n\r" or 0x20 <= ord(c) <= 0xD7FF
                or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF)
           for c in value):
        raise ValueError("Description contains a character not permitted in XML.")
    return value


Description = Annotated[str, Field(max_length=4096), AfterValidator(xml_text)]

# Presence of these markers does not establish signature validity. This workflow
# does not have vendor safety verification, so it cannot stage such projects.
SAFETY_SIGNATURE_MARKERS = {
    "safetysignature", "safetysignatureid", "safetysignaturetimestamp", "safetysignatureshmac",
    "parametersandlocaltagsrollupsignature",
}


def check_documentation_boundary(root: Element) -> None:
    def local_name(name: str) -> str:
        return name.rsplit("}", 1)[-1].casefold()

    for node in root.iter():
        attributes = {local_name(name): value for name, value in node.attrib.items()}
        if (local_name(node.tag) in SAFETY_SIGNATURE_MARKERS
                or SAFETY_SIGNATURE_MARKERS.intersection(attributes)
                or attributes.get("class", "").casefold() == "safety"
                or attributes.get("safetylocked", "").casefold() in ("true", "1")):
            raise ProjectReadError(
                "unsupported_safety_content",
                "Documentation proposals are not supported for exports with recognized safety-class or safety-signature indicators.",
            )


class StrictRecord(TypedDict):
    __pydantic_config__ = ConfigDict(extra="forbid")


class ControllerTarget(StrictRecord):
    kind: Literal["controller"]


class ProgramTarget(StrictRecord):
    kind: Literal["program"]
    program: Name


class ControllerTagTarget(StrictRecord):
    kind: Literal["controller_tag"]
    name: Name


class ProgramTagTarget(StrictRecord):
    kind: Literal["program_tag"]
    program: Name
    name: Name


class RoutineTarget(StrictRecord):
    kind: Literal["routine"]
    program: Name
    name: Name


Target = Annotated[
    ControllerTarget | ProgramTarget | ControllerTagTarget | ProgramTagTarget | RoutineTarget,
    Field(discriminator="kind"),
]


class DescriptionChange(StrictRecord):
    operation: Literal["set_description"]
    target: Target
    description: Description | None


Operations = Annotated[list[DescriptionChange], Field(min_length=1, max_length=50)]


class ProposalSource(StrictRecord):
    path: str
    selection_id: SelectionId | None
    source_sha256: Digest
    controller: str | None
    software_revision: str | None


class PreviewEntry(StrictRecord):
    operation: Literal["set_description"]
    target: Target
    before: str | None
    after: Description | None


class ProposalPayload(StrictRecord):
    schema_version: Literal[1]
    source: ProposalSource
    operations: Operations
    preview: Annotated[list[PreviewEntry], Field(min_length=1, max_length=50)]


class Proposal(ProposalPayload):
    approval_id: Digest


class ProposalValidation(StrictRecord):
    valid: Literal[True]
    approval_id: Digest
    source: ProposalSource


def identity(selection: ProjectSelection, snapshot: ProjectSnapshot) -> ProposalSource:
    return {
        "path": str(selection.path),
        "selection_id": selection.selection_id,
        "source_sha256": snapshot.source_sha256,
        "controller": snapshot.controller.get("Name"),
        "software_revision": snapshot.root.get("SoftwareRevision"),
    }


def unique_named(items: Iterable[Element], name: str, kind: str) -> Element:
    matches = [item for item in items if item.get("Name", "").casefold() == name.casefold()]
    if not matches:
        raise ProjectReadError("not_found", f"{kind} {name!r} was not found.")
    if len(matches) != 1:
        raise ProjectReadError("ambiguous_target", f"{kind} {name!r} matches more than one component.")
    return matches[0]


def resolve_target(controller: Element, target: Target) -> tuple[Target, Element]:
    if target["kind"] == "controller":
        return {"kind": "controller"}, controller
    scope = controller
    if target["kind"] in ("program", "program_tag", "routine"):
        scope = unique_named(controller.findall("Programs/Program"), target["program"], "Program")
        program = scope.attrib["Name"]
        if target["kind"] == "program":
            return {"kind": "program", "program": program}, scope
        if target["kind"] == "routine":
            routine = unique_named(component_entries(scope, "Routines", "Routine"), target["name"], "Routine")
            if has_protection(routine):
                raise ProjectReadError("invalid_proposal", "Protected routine descriptions are not supported.")
            language = routine.get("Type", "").upper()
            if language not in ("RLL", "ST") or routine.find(f"{language}Content") is None:
                raise ProjectReadError("invalid_proposal", "Routine documentation requires a saved Ladder or Structured Text routine.")
            return {"kind": "routine", "program": program, "name": routine.attrib["Name"]}, routine
    tag = unique_named(component_entries(scope, "Tags", "Tag"), target["name"], "Tag")
    if has_protection(tag):
        raise ProjectReadError("invalid_proposal", "Protected tag descriptions are not supported.")
    name = tag.attrib["Name"]
    if target["kind"] == "program_tag":
        return {"kind": "program_tag", "program": program, "name": name}, tag
    return {"kind": "controller_tag", "name": name}, tag


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def create_proposal(selection: ProjectSelection, snapshot: ProjectSnapshot, operations: Operations) -> Proposal:
    check_documentation_boundary(snapshot.root)
    normalized: Operations = []
    preview: list[PreviewEntry] = []
    seen: set[bytes] = set()
    for change in operations:
        target, element = resolve_target(snapshot.controller, change["target"])
        key = canonical_json(target)
        if key in seen:
            raise ProjectReadError("ambiguous_target", "A proposal may address each description only once.")
        seen.add(key)
        descriptions = element.findall("Description")
        if len(descriptions) > 1 or any(len(node) or node.attrib for node in descriptions):
            raise ProjectReadError("invalid_proposal", "The target has an unsupported description structure.")
        before = (descriptions[0].text or "") if descriptions else None
        after = change["description"]
        normalized.append({"operation": "set_description", "target": target, "description": after})
        preview.append({"operation": "set_description", "target": target, "before": before, "after": after})
    payload: ProposalPayload = {
        "schema_version": 1,
        "source": identity(selection, snapshot),
        "operations": normalized,
        "preview": preview,
    }
    return {**payload, "approval_id": sha256(canonical_json(payload)).hexdigest()}


def validate_proposal(
    selection: ProjectSelection, snapshot: ProjectSnapshot, proposal: Proposal, expected_approval_id: str,
) -> ProposalValidation:
    source = identity(selection, snapshot)
    if source["path"] != proposal["source"]["path"] or source["selection_id"] != proposal["source"]["selection_id"]:
        raise ProjectReadError("selection_changed", "The proposal belongs to a different project selection.")
    if source["source_sha256"] != proposal["source"]["source_sha256"]:
        raise ProjectReadError("project_changed", "The proposal refers to an older saved project. Create a new preview.")
    rebuilt = create_proposal(selection, snapshot, proposal["operations"])
    if canonical_json(rebuilt) != canonical_json(proposal) or rebuilt["approval_id"] != expected_approval_id:
        raise ProjectReadError("invalid_proposal", "The proposal does not match the reviewed content and approval identity.")
    return {"valid": True, "approval_id": rebuilt["approval_id"], "source": source}
