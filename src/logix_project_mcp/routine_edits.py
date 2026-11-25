"""Review a saved Ladder or Structured Text literal assignment in a new full L5X."""

import re
from hashlib import sha256
from typing import Annotated, Literal
from xml.etree.ElementTree import Element

from pydantic import Field

from .documentation import description_spans
from .edit_review import run_review_cli
from .project import ProjectSnapshot, controller_from_l5x, parse_l5x_bytes
from .proposals import Digest, Name, ProposalSource, StrictRecord, canonical_json, identity, unique_named
from .selection import ProjectSelection
from .tag_edits import Identifier, check_edit_source, read_state, require_unused, unsupported


class RoutineChange(StrictRecord):
    operation: Literal["create", "update"]
    program: Name
    routine: Identifier
    language: Literal["RLL", "ST"]
    statement: Annotated[str, Field(min_length=1, max_length=256)]


class RoutinePreview(StrictRecord):
    schema_version: Literal[1]
    source: ProposalSource
    change: RoutineChange
    destination_tag: str
    before: str | None
    after: str
    approval_id: Digest


_TAG = r"(?P<tag>[A-Za-z_][A-Za-z_0-9]{0,39})"
_VALUE = r"(?P<value>-?(?:0|[1-9][0-9]{0,9}))"
_FORM = {
    "RLL": rf"(?P<mnemonic>MOVE?)[ \t]*\([ \t]*{_VALUE}[ \t]*,[ \t]*{_TAG}[ \t]*\)[ \t]*;",
    "ST": rf"{_TAG}[ \t]*:=[ \t]*{_VALUE}[ \t]*;",
}


def assignment(language: str, text: str) -> re.Match:
    match = re.fullmatch(_FORM[language], text, re.I | re.ASCII)
    if match is None or not -2147483648 <= int(match["value"]) <= 2147483647:
        raise unsupported("Expected one MOVE(integer,tag); or tag := integer; with a signed decimal DINT literal.")
    return match


def collection(parent: Element, name: str) -> Element:
    items = parent.findall(name)
    if len(items) != 1:
        raise unsupported(f"Expected one saved {name} collection.")
    return items[0]


def code_node(routine: Element, language: str) -> Element:
    section_name = language + "Content"
    if (routine.get("Type") != language or set(routine.attrib) != {"Name", "Type"}
            or any(n.tag not in ("Description", section_name) for n in routine)):
        raise unsupported("The saved routine language, protection or structure is outside the supported assignment form.")
    section = collection(routine, section_name)
    if section.attrib:
        raise unsupported("Pending edits and annotated routine sections are unsupported.")
    if language == "RLL":
        if len(section) != 1 or section[0].tag != "Rung" or section[0].attrib != {"Number": "0", "Type": "N"}:
            raise unsupported("Expected one ordinary Ladder rung.")
        rung = section[0]
        if [n.tag for n in rung] not in (["Text"], ["Comment", "Text"]):
            raise unsupported("Expected one rung text and an optional saved rung comment.")
        node = rung.find("Text")
        if len(node) or node.attrib:
            raise unsupported("Unsupported Ladder text markup.")
        return node
    code = []
    for index, line in enumerate(section):
        text = (line.text or "").strip()
        if (line.tag != "Line" or line.attrib != {"Number": str(index)} or len(line)
                or "\n" in text or "\r" in text):
            raise unsupported("Expected consecutive plain ST lines.")
        if text and not text.startswith("//"):
            code.append(line)
    if len(code) != 1:
        raise unsupported("Expected one ST assignment with optional blank or line-comment lines.")
    return code[0]


def routine_context(snapshot: ProjectSnapshot, change: RoutineChange) -> tuple[Element, Element, Element | None]:
    program = unique_named(snapshot.controller.findall("Programs/Program"), change["program"], "Program")
    if (program.get("Type", "Normal").casefold() != "normal"
            or any(program.get(key, "").casefold() in ("true", "1") for key in ("TestEdits", "UseAsFolder"))):
        raise unsupported("Select an ordinary program without test edits.")
    routines = collection(program, "Routines")
    routine = None
    if change["operation"] == "update":
        routine = unique_named(routines.findall("Routine"), change["routine"], "Routine")
    return program, routines, routine


def preview_routine(selection: ProjectSelection, snapshot: ProjectSnapshot, change: RoutineChange) -> RoutinePreview:
    check_edit_source(selection, snapshot.root)
    program, _, routine = routine_context(snapshot, change)
    require_unused(snapshot.root, change["routine"], routine)
    language = change["language"]
    proposed = assignment(language, change["statement"])
    if language == "RLL":
        revision = snapshot.root.get("SoftwareRevision", "")
        if not re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]+)?", revision):
            raise unsupported("A saved software revision is required to select the Ladder move mnemonic.")
        mnemonic = "MOVE" if int(revision.split(".")[0]) >= 36 else "MOV"
        if proposed["mnemonic"].upper() != mnemonic:
            raise unsupported(f"Use {mnemonic} for the saved software revision {revision}.")
    tag = unique_named(collection(program, "Tags").findall("Tag"), proposed["tag"], "Private program tag")
    read_state(tag)
    before = None
    after = change["statement"]
    code = None
    if routine is not None:
        code = code_node(routine, language)
        before = code.text or ""
        # XML exports may wrap CDATA in formatting newlines.
        instruction = before.strip()
        if language == "ST":
            instruction = instruction.partition("//")[0].rstrip()
        saved = assignment(language, instruction)
        if saved["tag"].casefold() != proposed["tag"].casefold():
            raise unsupported("An update must retain the saved destination tag.")
        if int(saved["value"]) == int(proposed["value"]):
            raise unsupported("The proposed value matches the saved instruction.")
        offset = len(before) - len(before.lstrip())
        after = before[:offset + saved.start("value")] + proposed["value"] + before[offset + saved.end("value"):]
    require_unused(snapshot.root, tag.attrib["Name"], tag, operand=code)
    payload = {"schema_version": 1, "source": identity(selection, snapshot), "change": change,
               "destination_tag": f'Program:{program.attrib["Name"]}.{tag.attrib["Name"]}', "before": before, "after": after}
    return {**payload, "approval_id": sha256(canonical_json(payload)).hexdigest()}


def build_copy(data: bytes, selection: ProjectSelection, reviewed: RoutinePreview, approval_id: str) -> bytes:
    root = parse_l5x_bytes(data)
    snapshot = ProjectSnapshot(root, controller_from_l5x(root), sha256(data).hexdigest())
    if identity(selection, snapshot) != reviewed["source"]:
        raise unsupported("The source or selection changed. Preview the current save.")
    change = reviewed["change"]
    if preview_routine(selection, snapshot, change) != reviewed or reviewed["approval_id"] != approval_id:
        raise unsupported("The routine proposal differs from its retained preview.")
    _, routines, routine = routine_context(snapshot, change)
    language = change["language"]
    spans = description_spans(data, root)
    if routine is None:
        statement = f'<![CDATA[{reviewed["after"]}]]>'
        content = (f'<Rung Number="0" Type="N"><Text>{statement}</Text></Rung>' if language == "RLL"
                   else f'<Line Number="0">{statement}</Line>')
        element = (f'<Routine Name="{change["routine"]}" Type="{language}"><{language}Content>{content}'
                   f'</{language}Content></Routine>').encode("ascii")
        span = spans[routines]
        start = end = span.opening_end
        if span.empty:
            start -= 2
            element = b">" + element + b"</Routines>"
    else:
        node = code_node(routine, language)
        span = spans[node]
        inner = data[span.opening_end:span.end]
        prefix = re.match(rb"[ \t\r\n]*(?:<!\[CDATA\[[ \t\r\n]*)?", inner).end()
        saved = re.match(_FORM[language].encode("ascii"), inner[prefix:], re.I | re.ASCII)
        if saved is None:
            raise unsupported("The saved literal uses unsupported XML markup.")
        start = span.opening_end + prefix + saved.start("value")
        end = span.opening_end + prefix + saved.end("value")
        element = assignment(language, change["statement"])["value"].encode("ascii")
    output = data[:start] + element + data[end:]
    verified = controller_from_l5x(parse_l5x_bytes(output))
    program = unique_named(verified.findall("Programs/Program"), change["program"], "Program")
    staged = unique_named(program.findall("Routines/Routine"), change["routine"], "Routine")
    if code_node(staged, language).text != reviewed["after"]:
        raise unsupported("The staged routine differs from the preview.")
    return output


def main():
    run_review_cli(__doc__, RoutinePreview, build_copy)


if __name__ == "__main__":
    main()
