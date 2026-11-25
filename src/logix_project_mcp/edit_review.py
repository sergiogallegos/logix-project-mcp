"""Local interactive review and create-only publication of a checked L5X copy."""

import argparse
import asyncio
import json
import os
import re
import sys
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import TypeAdapter

from .export import validate_filename
from .project import ProjectReadError, snapshot_source
from .proposals import Digest, StrictRecord
from .selection import ProjectSelection, read_selection, validate_project_path


class EditReceipt[T](StrictRecord):
    proposal: T
    path: str
    artifact_sha256: Digest


async def publish_reviewed[T](
    current: Callable[[], ProjectSelection], proposal: T, approval_id: str, output: Path,
    confirm: Callable[[EditReceipt[T]], bool], build_copy: Callable[[bytes, ProjectSelection, T, str], bytes],
) -> EditReceipt[T] | None:
    selection = current()
    validate_filename(output.name)
    if (output.suffix.lower() != ".l5x" or re.search(r'[<>:"/\\|?*\x00-\x1f]', output.name)
            or os.path.lexists(output)):
        raise ProjectReadError("invalid_proposal", "Choose a new .L5X output filename.")
    with TemporaryDirectory(dir=output.parent, prefix=".logix-edit-") as temporary:
        folder = Path(temporary)
        source = folder / "source.L5X"
        original = await snapshot_source(selection.path, source)
        data = build_copy(source.read_bytes(), selection, proposal, approval_id)
        staged = folder / "staged.L5X"
        staged.write_bytes(data)
        receipt = {"proposal": proposal, "path": str(output), "artifact_sha256": sha256(data).hexdigest()}
        if not confirm(receipt):
            return None
        if await snapshot_source(selection.path, folder / "latest.L5X") != original or current() != selection:
            raise ProjectReadError("invalid_proposal", "The source or selection changed during review.")
        if staged.read_bytes() != data:
            raise ProjectReadError("invalid_proposal", "The staged artifact changed during review.")
        if os.name == "nt":
            os.rename(staged, output)
        else:
            os.link(staged, output)
        return receipt


def confirm_edit(receipt: EditReceipt) -> bool:
    print(json.dumps(receipt, indent=2, ensure_ascii=True), file=sys.stderr)
    print("Type APPROVE to publish this new offline L5X copy: ", file=sys.stderr, end="", flush=True)
    return sys.stdin.readline().strip() == "APPROVE"


def run_review_cli(description: str, schema, builder):
    parser = argparse.ArgumentParser(description=description)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--project", type=Path)
    source.add_argument("--selection-file", type=Path)
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument("--approval-id", required=True)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if not sys.stdin.isatty():
        parser.error("Review requires a local interactive terminal.")
    try:
        if args.project:
            fixed = ProjectSelection(validate_project_path(args.project))
            current = lambda: fixed
        else:
            current = lambda: read_selection(args.selection_file)
        proposal = TypeAdapter(schema).validate_json(args.proposal.read_bytes(), strict=True)
        result = asyncio.run(publish_reviewed(current, proposal, args.approval_id, args.output.absolute(), confirm_edit, builder))
        if result is None:
            raise SystemExit(2)
        print(json.dumps(result))
    except (ProjectReadError, OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
