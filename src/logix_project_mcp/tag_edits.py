"""Review a single offline edit to a private scalar DINT tag in a full L5X."""

import re
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal, NotRequired
from xml.etree.ElementTree import Element

from pydantic import Field

from .documentation import ElementSpan, description_spans
from .edit_review import EditReceipt, publish_reviewed, run_review_cli
from .inventory import has_protection
from .project import ProjectReadError, ProjectSnapshot, controller_from_l5x, parse_l5x_bytes
from .proposals import Digest, Name, ProposalSource, StrictRecord, canonical_json, check_documentation_boundary, identity, unique_named
from .selection import ProjectSelection


Identifier = Annotated[str, Field(max_length=40, pattern=r"^([A-Za-z][A-Za-z0-9]*|_[A-Za-z0-9]+)(_[A-Za-z0-9]+)*$")]
Dint = Annotated[int, Field(ge=-2147483648, le=2147483647)]


class TagLocation(StrictRecord):
    name: Identifier
    program: NotRequired[Name]


class ValueChange(TagLocation):
    operation: Literal["create", "set_value"]
    value: Dint


class Rename(TagLocation):
    operation: Literal["rename"]
    new_name: Identifier


class Remove(TagLocation):
    operation: Literal["remove"]


TagChange = Annotated[ValueChange | Rename | Remove, Field(discriminator="operation")]


class TagState(StrictRecord):
    name: str
    value: Dint
    description: str | None


class TagPreview(StrictRecord):
    schema_version: Literal[1]
    source: ProposalSource
    change: TagChange
    data_type: Literal["DINT"]
    before: TagState | None
    after: TagState | None
    approval_id: Digest


TagReceipt = EditReceipt[TagPreview]


def unsupported(message: str) -> ProjectReadError:
    return ProjectReadError("invalid_proposal", message)


def tag_container(controller: Element, change: TagChange) -> Element:
    scope = controller
    if "program" in change:
        scope = unique_named(controller.findall("Programs/Program"), change["program"], "Program")
    containers = scope.findall("Tags")
    if len(containers) != 1:
        raise unsupported("Select a scope with one exported Tags collection.")
    return containers[0]


def read_state(tag: Element) -> TagState:
    required = {"TagType": "Base", "DataType": "DINT", "Radix": "Decimal", "ExternalAccess": "None"}
    optional = {"Constant": "false", "OpcUaAccess": "None", "Usage": "Local"}
    if (any(tag.get(k) != v for k, v in required.items())
            or any(tag.get(k, v) != v for k, v in optional.items())
            or tag.attrib.keys() - (required.keys() | optional.keys() | {"Name"})
            or any(child.tag not in {"Data", "Description"} for child in tag)):
        raise unsupported("Choose a private, nonconstant, scalar decimal DINT base tag with local usage.")
    descriptions = tag.findall("Description")
    if len(descriptions) > 1 or any(len(node) or node.attrib for node in descriptions):
        raise unsupported("The tag has unsupported documentation.")
    values = {}
    for data in tag.findall("Data"):
        fmt = data.get("Format")
        if set(data.attrib) != {"Format"} or fmt in values:
            raise unsupported("The tag has unsupported or repeated data representations.")
        if fmt == "L5K" and not len(data):
            raw = (data.text or "").strip()
        elif fmt == "Decorated" and len(data) == 1:
            value = data[0]
            if (value.tag != "DataValue" or len(value) or set(value.attrib) != {"DataType", "Radix", "Value"}
                    or value.get("Radix") != "Decimal" or value.get("DataType") != "DINT"):
                raise unsupported("The tag has unsupported decorated data.")
            raw = value.attrib["Value"]
        else:
            raise unsupported("Select a tag with decimal scalar L5K or Decorated data.")
        if not re.fullmatch(r"-?[0-9]{1,10}", raw) or not -2147483648 <= int(raw) <= 2147483647:
            raise unsupported("The saved value is outside the supported decimal DINT range.")
        values[fmt] = int(raw)
    if len(set(values.values())) != 1:
        raise unsupported("The tag's saved representations are absent or disagree.")
    return {"name": tag.attrib["Name"], "value": next(iter(values.values())), "description": tag.findtext("Description")}


def require_unused(root: Element, name: str, declaration: Element | None, *, operand: Element | None = None) -> None:
    # Scan unknown XML fields too. An unresolved use could bind to a new declaration.
    token = re.compile(rf"(?<!\w){re.escape(name)}(?!\w)", re.ASCII | re.IGNORECASE)
    for node in root.iter():
        for key, value in node.attrib.items():
            if node is declaration and key == "Name":
                continue
            if token.search(value):
                raise unsupported(f"{name!r} has a possible reference or name collision in the saved export.")
        if (node is not operand and node.tag != "Description" and token.search(node.text or "")) or token.search(node.tail or ""):
            raise unsupported(f"{name!r} occurs in saved project content.")


def check_edit_source(selection: ProjectSelection, root: Element) -> None:
    if selection.path.suffix.lower() != ".l5x":
        raise unsupported("Select a full UTF-8 L5X export for this edit.")
    check_documentation_boundary(root)
    if has_protection(root) or any(n.get("IsEncrypted", "").lower() in ("true", "1") for n in root.iter()):
        raise unsupported("Opaque project content prevents checking references.")


def preview_tag(selection: ProjectSelection, snapshot: ProjectSnapshot, change: TagChange) -> TagPreview:
    check_edit_source(selection, snapshot.root)
    container = tag_container(snapshot.controller, change)
    name = change["name"]
    op = change["operation"]
    if op == "create":
        require_unused(snapshot.root, name, None)
        before = None
        after = {"name": name, "value": change["value"], "description": None}
    else:
        tag = unique_named(container.findall("Tag"), name, "Tag")
        before = read_state(tag)
        require_unused(snapshot.root, name, tag)
        after = None
        if op == "rename":
            require_unused(snapshot.root, change["new_name"], tag)
            after = {**before, "name": change["new_name"]}
        elif op == "set_value":
            after = {**before, "value": change["value"]}
    if before == after:
        raise unsupported("The requested change matches the saved tag.")
    payload = {"schema_version": 1, "source": identity(selection, snapshot), "change": change,
               "data_type": "DINT", "before": before, "after": after}
    return {**payload, "approval_id": sha256(canonical_json(payload)).hexdigest()}


def data_xml(fmt: str, value: int) -> bytes:
    if fmt == "L5K":
        return f'<Data Format="L5K"><![CDATA[{value}]]></Data>'.encode("ascii")
    return f'<Data Format="Decorated"><DataValue DataType="DINT" Radix="Decimal" Value="{value}"/></Data>'.encode("ascii")


def attribute_edit(data: bytes, span: ElementSpan, attribute: bytes, replacement: bytes) -> tuple[int, int, bytes]:
    # All accepted attributes of these opening elements have constrained scalar values.
    match = re.search(rb"\s" + attribute + rb"""\s*=\s*(["'])(.*?)\1""", data[span.start:span.opening_end], re.S)
    if match is None:
        raise unsupported("Could not locate the reviewed attribute in the opening element.")
    return span.start + match.start(2), span.start + match.end(2), replacement


def build_copy(data: bytes, selection: ProjectSelection, reviewed: TagPreview, approval_id: str) -> bytes:
    root = parse_l5x_bytes(data)
    controller = controller_from_l5x(root)
    snapshot = ProjectSnapshot(root, controller, sha256(data).hexdigest())
    change = reviewed["change"]
    if identity(selection, snapshot) != reviewed["source"]:
        raise unsupported("The saved source or selection has changed. Preview the current selection again.")
    if preview_tag(selection, snapshot, change) != reviewed or approval_id != reviewed["approval_id"]:
        raise unsupported("The proposal differs from the retained preview.")
    spans = description_spans(data, root)
    container = tag_container(controller, change)
    op = change["operation"]
    if op == "create":
        new_tag = (f'<Tag Name="{change["name"]}" TagType="Base" DataType="DINT" Radix="Decimal" '
                   'Constant="false" ExternalAccess="None">').encode("ascii")
        new_tag += data_xml("L5K", change["value"]) + data_xml("Decorated", change["value"]) + b"</Tag>"
        span = spans[container]
        if span.empty:
            edits = [(span.opening_end - 2, span.opening_end, b">" + new_tag + b"</Tags>")]
        else:
            edits = [(span.opening_end, span.opening_end, new_tag)]
    else:
        tag = unique_named(container.findall("Tag"), change["name"], "Tag")
        span = spans[tag]
        if op == "remove":
            edits = [(span.start, span.end, b"")]
        elif op == "rename":
            edits = [attribute_edit(data, span, b"Name", change["new_name"].encode("ascii"))]
        else:
            edits = []
            value = str(change["value"]).encode("ascii")
            for node in tag.findall("Data"):
                if node.attrib["Format"] == "Decorated":
                    edits.append(attribute_edit(data, spans[node[0]], b"Value", value))
                else:
                    start = spans[node].opening_end
                    inner = data[start:spans[node].end]
                    match = re.fullmatch(rb"\s*(?:<!\[CDATA\[\s*)?(-?[0-9]+)(?:\s*\]\]>)?\s*</Data\s*>", inner)
                    if match is None:
                        raise unsupported("The L5K value has unsupported markup.")
                    edits.append((start + match.start(1), start + match.end(1), value))
    for start, end, replacement in reversed(edits):
        data = data[:start] + replacement + data[end:]
    saved = tag_container(controller_from_l5x(parse_l5x_bytes(data)), change)
    expected = reviewed["after"]
    if (op in ("rename", "remove") and (expected is None or expected["name"].casefold() != change["name"].casefold())
            and any(n.get("Name", "").casefold() == change["name"].casefold() for n in saved.findall("Tag"))):
        raise unsupported("The old declaration is still present in the staged export.")
    if expected is not None and read_state(unique_named(saved.findall("Tag"), expected["name"], "Tag")) != expected:
        raise unsupported("The staged declaration differs from the preview.")
    return data


async def review_copy(current: Callable[[], ProjectSelection], proposal: TagPreview, approval_id: str,
                      output: Path, confirm: Callable[[TagReceipt], bool]) -> TagReceipt | None:
    return await publish_reviewed(current, proposal, approval_id, output, confirm, build_copy)


def main():
    run_review_cli(__doc__, TagPreview, build_copy)


if __name__ == "__main__":
    main()
