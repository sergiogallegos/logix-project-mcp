"""Find scoped declarations, comments, and references in a saved snapshot."""

import re
from bisect import bisect_right
from collections.abc import Iterable, Iterator
from itertools import islice
from typing import Literal, NamedTuple, TypedDict
from xml.etree.ElementTree import Element

from .inventory import component_entries, program_qualified_name
from .project import ProjectReadError
from .routines import DiagramElement, RoutineInspection, StructuredTextLine, inspect_routine

SymbolKind = Literal["tag", "routine", "data_type", "add_on_instruction"]
SearchKind = Literal["all", "tag", "symbol", "routine", "comment", "reference"]
MatchKind = Literal["tag", "symbol", "routine", "comment", "reference"]
ReferenceKind = Literal["operand", "alias_target", "data_type", "routine_call", "instruction_call"]

_NAME = r"[A-Za-z_]\w*"
_TAG = rf"(?:Program:(?P<program>{_NAME})\.)?(?P<name>{_NAME}(?::\w+)*)"
_TAG_NAME = re.compile(_TAG, re.IGNORECASE | re.ASCII)
# Member selectors and numeric literals cannot start a reference. Array index expressions can.
_TOKENS = re.compile(
    r"(?P<comment>//[^\n]*|\(\*[\s\S]*?(?:\*\)|\Z)|/\*[\s\S]*?(?:\*/|\Z))"
    r"|'(?:\$[^\n]|[^'$\n])*(?:'|(?=\n|\Z)|\$(?=\n|\Z))"
    r'|"(?:\$[^\n]|[^"$\n])*(?:"|(?=\n|\Z)|\$(?=\n|\Z))'
    rf"|(?P<symbol>(?<![\w.:#$]){_TAG})(?![\w:])",
    re.IGNORECASE | re.ASCII,
)
_CALL = re.compile(r"\s*\(\s*")
_EXCERPT_LENGTH = 240


class SymbolIdentity(TypedDict):
    kind: SymbolKind
    name: str
    program: str | None
    qualified_name: str


class SearchLocation(TypedDict):
    scope: Literal["controller", "program"]
    program: str | None
    routine: str | None
    declaration: str | None
    section: int | None
    online_edit_type: str | None
    rung: str | None
    line: str | None
    sheet: str | None
    element_id: str | None
    column: int | None


class SearchMatch(TypedDict):
    kind: MatchKind
    location: SearchLocation
    symbol: SymbolIdentity | None
    alias_targets: list[SymbolIdentity]
    reference_kind: ReferenceKind | None
    excerpt: str


class Declaration(NamedTuple):
    kind: SymbolKind
    name: str
    program: str | None
    element: Element

    def identity(self) -> SymbolIdentity:
        return {
            "kind": self.kind,
            "name": self.name,
            "program": self.program,
            "qualified_name": program_qualified_name(self.program, self.name) or self.name,
        }


def declarations(controller: Element) -> Iterator[Declaration]:
    for tag in controller.findall("Tags/Tag"):
        if name := tag.get("Name"):
            yield Declaration("tag", name, None, tag)
    for data_type in controller.findall("DataTypes/DataType"):
        if data_type.get("Class", "User").casefold() == "user" and (name := data_type.get("Name")):
            yield Declaration("data_type", name, None, data_type)
    for instruction in component_entries(controller, "AddOnInstructionDefinitions", "AddOnInstructionDefinition"):
        if name := instruction.get("Name"):
            yield Declaration("add_on_instruction", name, None, instruction)
    for program in controller.findall("Programs/Program"):
        if not (program_name := program.get("Name")):
            continue
        for tag in program.findall("Tags/Tag"):
            if name := tag.get("Name"):
                yield Declaration("tag", name, program_name, tag)
        for routine in component_entries(program, "Routines", "Routine"):
            if name := routine.get("Name"):
                yield Declaration("routine", name, program_name, routine)


def location(program: str | None, routine: str | None = None, declaration: str | None = None) -> SearchLocation:
    return {
        "scope": "controller" if program is None else "program",
        "program": program, "routine": routine, "declaration": declaration, "section": None, "online_edit_type": None,
        "rung": None, "line": None, "sheet": None, "element_id": None, "column": None,
    }


def match(
    kind: MatchKind,
    at: SearchLocation,
    text: str,
    declaration: Declaration | None = None,
    reference_kind: ReferenceKind | None = None,
    alias_targets: Iterable[Declaration] = (),
    excerpt_offset: int | None = None,
) -> SearchMatch:
    offset = (at["column"] or 1) - 1 if excerpt_offset is None else excerpt_offset
    start = max(0, offset - _EXCERPT_LENGTH // 2)
    return {
        "kind": kind,
        "location": at,
        "symbol": declaration.identity() if declaration else None,
        "reference_kind": reference_kind,
        "alias_targets": [target.identity() for target in alias_targets],
        "excerpt": text[start:start + _EXCERPT_LENGTH],
    }


def comment_matches(
    rule: re.Pattern[str], text: str, at: SearchLocation, declaration: Declaration | None = None,
) -> Iterator[SearchMatch]:
    if found := rule.search(text):
        yield match("comment", at, text, declaration, excerpt_offset=found.start())


class ProjectSearch:
    def __init__(self, controller: Element) -> None:
        self.controller = controller
        self.declarations = list(declarations(controller))
        self.by_name = {
            (item.kind, (item.program or "").casefold(), item.name.casefold()): item
            for item in self.declarations
        }

    def find(self, kind: SymbolKind, program: str | None, name: str) -> Declaration | None:
        return self.by_name.get((kind, (program or "").casefold(), name.casefold()))

    def tag_at(self, text: str, program: str | None) -> Declaration | None:
        token = _TAG_NAME.match(text)
        if token is None:
            return None
        explicit = token["program"]
        name = token["name"]
        scoped = self.find("tag", explicit or program, name)
        return scoped if explicit or scoped else self.find("tag", None, name)

    def alias_targets(self, tag: Declaration) -> Iterator[Declaration]:
        visited = {tag}
        while target_text := tag.element.get("AliasFor"):
            target = self.tag_at(target_text, tag.program)
            if target is None or target in visited:
                return
            yield target
            visited.add(target)
            tag = target

    def reference(
        self, target: Declaration, at: SearchLocation, text: str, kind: ReferenceKind,
    ) -> SearchMatch:
        aliases = self.alias_targets(target) if target.kind == "tag" else ()
        return match("reference", at, text, target, kind, aliases)

    def code_matches(
        self, text: str, at: SearchLocation, lines: list[StructuredTextLine] | None = None,
        comments: re.Pattern[str] | None = None, references: bool = True,
    ) -> Iterator[SearchMatch]:
        starts = [0]
        if lines is not None:
            for line in lines:
                starts.append(starts[-1] + len(line["text"]) + 1)

        program = at["program"]
        routine_argument = -1
        for token in _TOKENS.finditer(text):
            start = token.start()
            line_index = bisect_right(starts, start) - 1
            site = {**at, "column": start - starts[line_index] + 1}
            source_line = text
            if lines is not None:
                site["line"] = lines[line_index]["number"]
                source_line = lines[line_index]["text"]
            if comment := token["comment"]:
                if comments:
                    yield from comment_matches(comments, comment, site)
                continue
            if not references or not (symbol := token["symbol"]):
                continue
            call = _CALL.match(text, token.end())
            if start == routine_argument:
                if target := self.find("routine", program, symbol):
                    yield self.reference(target, site, source_line, "routine_call")
            elif call:
                if symbol.casefold() == "jsr":
                    routine_argument = call.end()
                if target := self.find("add_on_instruction", None, symbol):
                    yield self.reference(target, site, source_line, "instruction_call")
            elif target := self.tag_at(symbol, program):
                yield self.reference(target, site, source_line, "operand")

    def diagram_matches(
        self, element: DiagramElement, at: SearchLocation, comments: re.Pattern[str] | None, references: bool,
    ) -> Iterator[SearchMatch]:
        kind, attrs = element["kind"], element["attributes"]
        site = {**at, "element_id": attrs.get("ID", at["element_id"])}
        if kind == "Sheet":
            site["sheet"] = attrs.get("Number")
        if references and (operand := attrs.get("Operand")):
            yield from self.code_matches(operand, site)
        if comments and kind in {"Description", "Text", "Comment"} and (text := element["text"]):
            yield from comment_matches(comments, text, site)
        if kind == "STContent":
            lines: list[StructuredTextLine] = [
                {"number": line["attributes"].get("Number"), "text": line["text"] or ""}
                for line in element["children"] if line["kind"] == "Line"
            ]
            yield from self.code_matches("\n".join(line["text"] for line in lines), site, lines, comments, references)
            return
        for child in element["children"]:
            yield from self.diagram_matches(child, site, comments, references)

    def routine_matches(
        self, inspection: RoutineInspection, at: SearchLocation, comments: re.Pattern[str] | None, references: bool,
    ) -> Iterator[SearchMatch]:
        for index, section in enumerate(inspection["sections"]):
            site = {**at, "section": index, "online_edit_type": section["attributes"].get("OnlineEditType")}
            if "rungs" in section:
                for rung in section["rungs"]:
                    rung_site = {**site, "rung": rung["number"]}
                    if comments and (comment := rung["comment"]):
                        yield from comment_matches(comments, comment, rung_site)
                    if text := rung["text"]:
                        yield from self.code_matches(text, rung_site, comments=comments, references=references)
            elif "lines" in section:
                lines = section["lines"]
                yield from self.code_matches("\n".join(line["text"] for line in lines), site, lines, comments, references)
            else:
                for element in section["elements"]:
                    yield from self.diagram_matches(element, site, comments, references)

    def matches(
        self, kind: SearchKind, program: str | None, comments: re.Pattern[str] | None,
    ) -> Iterator[SearchMatch]:
        if comments:
            containers = [self.controller, *self.controller.findall("Programs/Program")]
            for container in containers:
                name = None if container is self.controller else container.get("Name")
                if program is not None and name != program:
                    continue
                if description := container.findtext("Description"):
                    yield from comment_matches(comments, description, location(name))

        for item in self.declarations:
            if program is not None and item.program != program:
                continue
            at = location(item.program, routine=item.name) if item.kind == "routine" else location(
                item.program, declaration=item.name,
            )
            declaration_kind = item.kind if item.kind in {"tag", "routine"} else "symbol"
            if kind in {"all", declaration_kind}:
                yield match(declaration_kind, at, item.name, item)
            if comments and (description := item.element.findtext("Description")):
                yield from comment_matches(comments, description, at, item)
            if item.kind == "routine" and kind in {"all", "comment", "reference"}:
                yield from self.routine_matches(inspect_routine(item.program, item.element), at, comments, kind != "comment")
            if item.kind == "tag" and kind in {"all", "reference"}:
                if (alias := item.element.get("AliasFor")) and (target := self.tag_at(alias, item.program)):
                    yield self.reference(target, at, f"{item.name} AliasFor {alias}", "alias_target")
                if data_type := item.element.get("DataType"):
                    target = self.find("data_type", None, data_type) or self.find("add_on_instruction", None, data_type)
                    if target:
                        yield self.reference(target, at, f"{item.name} DataType {data_type}", "data_type")

    def search(self, query: str, kind: SearchKind, program: str | None) -> Iterator[SearchMatch]:
        name = query.casefold()
        comments = re.compile(rf"(?<!\w){re.escape(query)}(?!\w)", re.IGNORECASE) if kind in {"all", "comment"} else None
        for result in self.matches(kind, program, comments):
            if result["kind"] == "comment":
                yield result
            elif symbol := result["symbol"]:
                if kind in {"all", result["kind"]} and any(
                    name in {item["name"].casefold(), item["qualified_name"].casefold()}
                    for item in [symbol, *result["alias_targets"]]
                ):
                    yield result

    def references(self, name: str, kind: SymbolKind, program: str | None) -> Iterator[SearchMatch]:
        target = self.find(kind, program, name)
        if target is None:
            raise ProjectReadError("not_found", f"No {kind} named {name!r} exists in the selected scope.")
        identity = target.identity()
        for result in self.matches("reference", None, None):
            if identity == result["symbol"] or identity in result["alias_targets"]:
                yield result


def page(matches: Iterable[SearchMatch], offset: int, limit: int) -> tuple[list[SearchMatch], int | None]:
    entries = list(islice(islice(matches, offset, None), limit + 1))
    return entries[:limit], offset + limit if len(entries) > limit else None
