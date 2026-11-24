"""Compare named components and readable source in verified L5X snapshots."""

from collections.abc import Iterator
from difflib import unified_diff
from typing import Literal, NamedTuple, TypedDict
from xml.etree.ElementTree import Element, indent, tostring

from .inventory import PROTECTION_ELEMENTS, component_entries, has_protection, program_qualified_name
from .project import ProjectReadError
from .routines import inspect_routine

ComponentKind = Literal["controller", "task", "module", "data_type", "add_on_instruction", "program", "tag", "routine"]

_VOLATILE_ATTRIBUTES = {
    "ProjectCreationDate", "LastModifiedDate", "LastModifiedBy", "CreatedDate", "CreatedBy", "EditedDate", "EditedBy",
}
_EXPORT_CONTEXTS = {"Target", "Context", "Reference"}
_CONTROLLER_COLLECTIONS = {"Tasks", "Modules", "DataTypes", "AddOnInstructionDefinitions", "Programs", "Tags"}
_PROGRAM_COLLECTIONS = {"Tags", "Routines"}
_SOURCE_TEXT = {"Line", "Text", "Comment", "Description", "Data", "ForceData"}
_PROTECTED_METADATA = {"Name", "Type", "EncodedType", "Revision", "RevisionExtension", "Vendor"}


class ComponentIdentity(TypedDict):
    kind: ComponentKind
    scope: Literal["controller", "program"]
    program: str | None
    name: str | None
    qualified_name: str | None


class ComponentChange(TypedDict):
    component: ComponentIdentity
    change: Literal["added", "removed", "modified"]
    xml_diff: str
    source_diff: str | None


class ComparisonReport(TypedDict):
    changes: list[ComponentChange]
    protected_components: list[ComponentIdentity]


class Component(NamedTuple):
    kind: ComponentKind
    program: str | None
    element: Element

    def key(self) -> tuple[ComponentKind, str, str]:
        name = "" if self.kind == "controller" else self.element.get("Name", "").casefold()
        return self.kind, (self.program or "").casefold(), name

    def identity(self) -> ComponentIdentity:
        name = self.element.get("Name")
        qualified = program_qualified_name(self.program, name) if self.kind in {"tag", "routine"} else None
        return {
            "kind": self.kind,
            "scope": "controller" if self.program is None else "program",
            "program": self.program,
            "name": name,
            "qualified_name": qualified or name,
        }

    def protected(self) -> bool:
        return self.kind in {"routine", "add_on_instruction"} and has_protection(self.element)


def components(controller: Element, scope: str, program: str | None) -> Iterator[Component]:
    if scope != "program":
        yield Component("controller", None, controller)
        for kind, collection, tag in (
            ("task", "Tasks", "Task"),
            ("module", "Modules", "Module"),
            ("data_type", "DataTypes", "DataType"),
            ("add_on_instruction", "AddOnInstructionDefinitions", "AddOnInstructionDefinition"),
            ("tag", "Tags", "Tag"),
        ):
            for item in component_entries(controller, collection, tag):
                if kind == "data_type" and item.get("Class", "User").casefold() != "user":
                    continue
                yield Component(kind, None, item)
    if scope != "controller":
        for item in controller.findall("Programs/Program"):
            name = item.get("Name")
            if not name or (program is not None and name.casefold() != program.casefold()):
                continue
            yield Component("program", name, item)
            for tag in item.findall("Tags/Tag"):
                yield Component("tag", name, tag)
            for routine in component_entries(item, "Routines", "Routine"):
                yield Component("routine", name, routine)


def normalized_xml(element: Element, excluded: set[str], protected: bool = False) -> Element:
    attributes = {
        name: value for name, value in sorted(element.attrib.items())
        if name not in _VOLATILE_ATTRIBUTES and (not protected or name in _PROTECTED_METADATA)
        and (name != "Use" or value not in _EXPORT_CONTEXTS)
    }
    result = Element(element.tag, attributes)
    if not protected and element.text and (element.text.strip() or element.tag in _SOURCE_TEXT):
        result.text = element.text
    decorated = element.tag == "Tag" and element.find('Data[@Format="Decorated"]') is not None
    for child in element:
        if protected and child.tag not in {"Description", "Parameters"}:
            continue
        if child.tag in excluded or child.tag in PROTECTION_ELEMENTS:
            continue
        if decorated and child.tag == "Data" and child.get("Format") in {None, "L5K", "Raw"}:
            continue
        copy = normalized_xml(child, set())
        if child.tail and child.tail.strip():
            copy.tail = child.tail
        result.append(copy)
    return result


def xml_lines(component: Component | None, protected: bool) -> list[str]:
    if component is None:
        return []
    excluded = {"controller": _CONTROLLER_COLLECTIONS, "program": _PROGRAM_COLLECTIONS}.get(component.kind, set())
    xml = normalized_xml(component.element, excluded, protected)
    indent(xml)
    return tostring(xml, encoding="unicode").split("\n")


def readable_source(component: Component | None) -> list[str]:
    if component is None or component.kind != "routine":
        return []
    inspection = inspect_routine(component.program, component.element)
    result = []
    for section in inspection["sections"]:
        if "rungs" in section:
            edition = section["attributes"].get("OnlineEditType")
            result.append(f"RLL {edition}" if edition else "RLL")
            for rung in section["rungs"]:
                label = f"Rung {rung['number'] or '?'}"
                if rung["comment"] is not None:
                    result.extend(f"{label} comment  {line}" for line in rung["comment"].split("\n"))
                result.extend(f"{label}  {line}" for line in (rung["text"] or "").split("\n"))
        elif "lines" in section:
            edition = section["attributes"].get("OnlineEditType")
            result.append(f"ST {edition}" if edition else "ST")
            for line in section["lines"]:
                result.extend(f"Line {line['number'] or '?'}  {text}" for text in line["text"].split("\n"))
    return result


def diff(before: list[str], after: list[str]) -> str:
    return "\n".join(unified_diff(before, after, fromfile="before", tofile="after", lineterm=""))


def index_components(controller: Element, scope: str, program: str | None) -> dict[tuple[ComponentKind, str, str], Component]:
    indexed = {}
    for item in components(controller, scope, program):
        key = item.key()
        if key in indexed:
            identity = item.identity()
            raise ProjectReadError("invalid_project", f"Duplicate {item.kind} {identity['qualified_name']!r} in a saved project.")
        indexed[key] = item
    return indexed


def compare(
    before: Element, after: Element, scope: str = "all", program: str | None = None,
) -> ComparisonReport:
    baseline = index_components(before, scope, program)
    candidate = index_components(after, scope, program)
    if scope == "program" and not (baseline or candidate):
        raise ProjectReadError("not_found", f"Program {program!r} was not found in either saved project.")

    changes: list[ComponentChange] = []
    protected_components: list[ComponentIdentity] = []
    for key in sorted(baseline.keys() | candidate.keys()):
        left, right = baseline.get(key), candidate.get(key)
        component = right or left
        assert component is not None
        left_protected = left is not None and left.protected()
        right_protected = right is not None and right.protected()
        protected = left_protected or right_protected
        identity = component.identity()
        if protected:
            protected_components.append(identity)
        # Compare visible metadata on both sides whenever either side is protected.
        before_lines, after_lines = xml_lines(left, protected), xml_lines(right, protected)
        if before_lines == after_lines and left_protected == right_protected:
            continue
        xml_diff = diff(before_lines, after_lines)
        if not xml_diff:
            xml_diff = diff([f"Source protected {left_protected}"], [f"Source protected {right_protected}"])
        changes.append({
            "component": identity,
            "change": "added" if left is None else "removed" if right is None else "modified",
            "xml_diff": xml_diff,
            "source_diff": None if protected else diff(readable_source(left), readable_source(right)) or None,
        })
    return {"changes": changes, "protected_components": protected_components}
