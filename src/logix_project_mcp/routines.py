"""Read routine source and diagram structure from a saved L5X snapshot."""

from collections.abc import Callable
from typing import Literal, TypedDict
from xml.etree.ElementTree import Element

from .inventory import has_protection, program_qualified_name


class LadderRung(TypedDict):
    number: str | None
    type: str | None
    text: str | None
    comment: str | None


class StructuredTextLine(TypedDict):
    number: str | None
    text: str


class DiagramElement(TypedDict):
    kind: str
    attributes: dict[str, str]
    text: str | None
    children: list["DiagramElement"]


class RoutineSection(TypedDict):
    attributes: dict[str, str]


class LadderSection(RoutineSection):
    rungs: list[LadderRung]


class StructuredTextSection(RoutineSection):
    lines: list[StructuredTextLine]


class DiagramSection(RoutineSection):
    elements: list[DiagramElement]


LogicSection = LadderSection | StructuredTextSection | DiagramSection


class RoutineInspection(TypedDict):
    program: str | None
    routine: str | None
    qualified_name: str | None
    language: str | None
    description: str | None
    status: Literal["readable", "protected", "unsupported"]
    message: str | None
    sections: list[LogicSection]


def ladder_section(content: Element) -> LadderSection:
    return {
        "attributes": dict(content.attrib),
        "rungs": [
            {
                "number": rung.get("Number"),
                "type": rung.get("Type"),
                "text": rung.findtext("Text"),
                "comment": rung.findtext("Comment"),
            }
            for rung in content.findall("Rung")
        ],
    }


def structured_text_section(content: Element) -> StructuredTextSection:
    return {
        "attributes": dict(content.attrib),
        "lines": [{"number": line.get("Number"), "text": line.text or ""} for line in content.findall("Line")],
    }


def diagram_element(element: Element) -> DiagramElement:
    return {
        "kind": element.tag,
        "attributes": dict(element.attrib),
        "text": element.text,
        "children": [diagram_element(child) for child in element],
    }


def diagram_section(content: Element) -> DiagramSection:
    return {"attributes": dict(content.attrib), "elements": [diagram_element(child) for child in content]}


SECTION_READERS: dict[str, Callable[[Element], LogicSection]] = {
    "RLL": ladder_section,
    "ST": structured_text_section,
    "FBD": diagram_section,
    "SFC": diagram_section,
}


def inspect_routine(program_name: str | None, routine: Element) -> RoutineInspection:
    name = routine.get("Name")
    language = routine.get("Type")
    format_code = (language or "").upper()
    inspection: RoutineInspection = {
        "program": program_name,
        "routine": name,
        "qualified_name": program_qualified_name(program_name, name),
        "language": language,
        "description": routine.findtext("Description"),
        "status": "unsupported",
        "message": None,
        "sections": [],
    }
    if has_protection(routine):
        inspection["status"] = "protected"
        inspection["message"] = "The saved export marks this routine as source-protected."
        return inspection

    reader = SECTION_READERS.get(format_code)
    if reader is None:
        inspection["message"] = "This routine has no supported language in the saved export."
        return inspection

    content_tag = f"{format_code}Content"
    sections = routine.findall(content_tag)
    if sections:
        inspection["status"] = "readable"
        inspection["sections"] = [reader(section) for section in sections]
    else:
        inspection["message"] = f"The saved export has no {content_tag} section for this routine."
    return inspection
