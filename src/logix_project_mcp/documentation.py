"""Create a new L5X copy containing only reviewed description changes."""

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from xml.etree.ElementTree import Element, ParseError
from xml.parsers import expat
from xml.sax.saxutils import escape

from defusedxml.common import DefusedXmlException

from .project import (
    ProjectReadError, ProjectSnapshot, controller_from_l5x, finish_file_operation,
    parse_l5x_bytes, snapshot_source,
)
from .proposals import Digest, Proposal, ProposalSource, StrictRecord, resolve_target, validate_proposal
from .selection import ProjectSelection


class DocumentationCopy(StrictRecord):
    path: str
    format: Literal["l5x"]
    source: ProposalSource
    approval_id: Digest
    artifact_sha256: Digest


@dataclass
class ElementSpan:
    start: int
    opening_end: int
    end: int
    empty: bool


def tag_end(data: bytes, start: int) -> int:
    quote = None
    for position in range(start + 1, len(data)):
        char = data[position]
        if quote is not None:
            if char == quote:
                quote = None
        elif char in (34, 39):
            quote = char
        elif char == 62:
            return position + 1
    raise ProjectReadError("invalid_project", "An XML tag was not terminated.")


def description_spans(data: bytes, root: Element) -> dict[Element, ElementSpan]:
    """Map parsed elements to byte ranges without reserializing unrelated XML."""
    try:
        data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ProjectReadError("invalid_proposal", "Documentation copies require a UTF-8 L5X source.") from exc
    if b"\x00" in data:
        raise ProjectReadError("invalid_proposal", "Documentation copies require a UTF-8 L5X source.")
    parser = expat.ParserCreate()
    nodes = iter(root.iter())
    spans: dict[Element, ElementSpan] = {}
    stack: list[ElementSpan] = []

    def declaration(version, encoding, standalone):
        if encoding is not None and encoding.casefold() not in ("utf-8", "utf8"):
            raise ProjectReadError("invalid_proposal", "Documentation copies require a UTF-8 L5X source.")

    def start(name, attributes):
        node = next(nodes, None)
        if node is None or node.tag != name:
            raise ProjectReadError("invalid_project", "XML element positions do not match the parsed project.")
        start = parser.CurrentByteIndex
        opening_end = tag_end(data, start)
        empty = data[opening_end - 2:opening_end] == b"/>"
        span = ElementSpan(start, opening_end, opening_end, empty)
        spans[node] = span
        stack.append(span)

    def end(name):
        span = stack.pop()
        if not span.empty:
            span.end = tag_end(data, parser.CurrentByteIndex)

    def reject_doctype(*args):
        raise ProjectReadError("invalid_project", "DTD declarations are not supported.")

    parser.XmlDeclHandler = declaration
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.StartDoctypeDeclHandler = reject_doctype
    parser.Parse(data, True)
    if next(nodes, None) is not None or stack:
        raise ProjectReadError("invalid_project", "XML element positions do not match the parsed project.")
    return spans


def description_xml(text: str | None) -> bytes:
    if text is None:
        return b""
    # Character references preserve CR text through XML line-ending normalization.
    return ("<Description>" + escape(text, {"\r": "&#13;"}) + "</Description>").encode("utf-8")


def build_documentation_copy(
    data: bytes, selection: ProjectSelection, proposal: Proposal, expected_approval_id: str,
) -> bytes:
    root = parse_l5x_bytes(data)
    controller = controller_from_l5x(root)
    snapshot = ProjectSnapshot(root, controller, sha256(data).hexdigest())
    validate_proposal(selection, snapshot, proposal, expected_approval_id)
    spans = description_spans(data, root)
    replacements: list[tuple[int, int, bytes]] = []
    for change in proposal["preview"]:
        _, target = resolve_target(controller, change["target"])
        if change["before"] == change["after"]:
            continue
        replacement = description_xml(change["after"])
        original = target.find("Description")
        if original is not None:
            span = spans[original]
            replacements.append((span.start, span.end, replacement))
        else:
            span = spans[target]
            if span.empty:
                replacements.append((
                    span.opening_end - 2, span.opening_end,
                    b">" + replacement + b"</" + target.tag.encode("ascii") + b">",
                ))
            else:
                replacements.append((span.opening_end, span.opening_end, replacement))
    chunks = []
    previous = 0
    for start, end, replacement in sorted(replacements):
        if start < previous:
            raise ProjectReadError("invalid_proposal", "The proposed documentation ranges overlap.")
        chunks.extend((data[previous:start], replacement))
        previous = end
    chunks.append(data[previous:])
    artifact = b"".join(chunks)
    result = controller_from_l5x(parse_l5x_bytes(artifact))
    for change in proposal["preview"]:
        _, target = resolve_target(result, change["target"])
        description = target.find("Description")
        actual = (description.text or "") if description is not None else None
        if actual != change["after"]:
            raise ProjectReadError("export_failed", "The staged description differs from the reviewed preview.")
    return artifact


async def stage_documentation_copy(
    selection: ProjectSelection, current_selection: Callable[[], ProjectSelection],
    directory: Path, filename: str, proposal: Proposal, expected_approval_id: str,
) -> DocumentationCopy:
    if selection.path.suffix.lower() != ".l5x":
        raise ProjectReadError("invalid_proposal", "Documentation copies require a full saved L5X source.")
    destination = directory / filename
    if os.path.lexists(destination):
        raise ProjectReadError("destination_exists", f"{filename} already exists in the selected export directory.")
    try:
        with TemporaryDirectory(prefix=".logix-documentation-", dir=directory) as temporary:
            folder = Path(temporary)
            source, staged, latest = (folder / name for name in ("source.L5X", "review.L5X", "latest.L5X"))
            fingerprint = await snapshot_source(selection.path, source)
            if fingerprint != proposal["source"]["source_sha256"]:
                raise ProjectReadError("project_changed", "The saved project changed after the proposal was created.")

            def prepare():
                artifact = build_documentation_copy(source.read_bytes(), selection, proposal, expected_approval_id)
                staged.write_bytes(artifact)
                if staged.read_bytes() != artifact:
                    raise ProjectReadError("export_failed", "The staged copy differs from the verified documentation output.")
                return sha256(artifact).hexdigest()

            artifact_digest = await finish_file_operation(asyncio.to_thread(prepare))
            if await snapshot_source(selection.path, latest) != fingerprint:
                raise ProjectReadError("project_changed", "The saved project changed while the copy was staged.")
            if current_selection() != selection:
                raise ProjectReadError("selection_changed", "The shared project selection changed while the copy was staged.")
            try:
                if os.name == "nt":
                    os.rename(staged, destination)
                else:
                    os.link(staged, destination)
            except FileExistsError as exc:
                raise ProjectReadError("destination_exists", f"{filename} already exists in the selected export directory.") from exc
    except (ParseError, DefusedXmlException, expat.ExpatError) as exc:
        raise ProjectReadError("invalid_project", "The saved or staged L5X is not valid XML.") from exc
    except OSError as exc:
        raise ProjectReadError("export_failed", f"Could not stage {filename}: {exc}") from exc
    return {
        "path": str(destination), "format": "l5x", "source": proposal["source"],
        "approval_id": expected_approval_id, "artifact_sha256": artifact_digest,
    }
