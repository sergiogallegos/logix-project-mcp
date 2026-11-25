"""Locally review and finalize an already staged documentation-only artifact."""

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from pydantic import TypeAdapter, ValidationError

from .documentation import DocumentationCopy, DocumentationVerification, verify_documentation_copy
from .export import validate_filename
from .project import ProjectReadError, snapshot_source
from .proposals import Digest, Proposal, StrictRecord, canonical_json
from .selection import ProjectSelection, read_selection, validate_project_path


class ReviewContent(StrictRecord):
    schema_version: Literal[1]
    proposal: Proposal
    artifact: DocumentationVerification
    approval_path: str


class ReviewPreview(ReviewContent):
    review_id: Digest


class ApprovalRecord(ReviewPreview):
    decision: Literal["approved_documentation_copy"]
    approved_at: str


def approval_path_for(artifact: Path) -> Path:
    return artifact.with_name(artifact.name + ".approval.json")


def review_preview(proposal: Proposal, verified: DocumentationVerification, approval_path: Path) -> ReviewPreview:
    content: ReviewContent = {
        "schema_version": 1, "proposal": proposal, "artifact": verified, "approval_path": str(approval_path),
    }
    return {**content, "review_id": sha256(canonical_json(content)).hexdigest()}


def publish_approval(path: Path, record: ApprovalRecord) -> None:
    try:
        with TemporaryDirectory(prefix=".logix-review-", dir=path.parent) as temporary:
            staged = Path(temporary) / "approval.json"
            staged.write_bytes(canonical_json(record) + b"\n")
            try:
                if os.name == "nt":
                    os.rename(staged, path)
                else:
                    os.link(staged, path)
            except FileExistsError as exc:
                raise ProjectReadError("destination_exists", "An approval record already exists for this artifact.") from exc
    except OSError as exc:
        raise ProjectReadError("export_failed", "Could not publish the local approval record.") from exc


def review_path(artifact: Path, selection: ProjectSelection) -> Path:
    # Resolve the parent, not the final entry: the snapshot reader rejects symlinks.
    artifact = artifact.parent.resolve() / artifact.name
    validate_filename(artifact.name)
    if artifact.suffix.lower() != ".l5x":
        raise ValueError("Choose a staged full L5X documentation copy.")
    if artifact.exists() and artifact.samefile(selection.path):
        raise ProjectReadError("invalid_proposal", "Review a separate staged copy, not the saved source.")
    return artifact


async def check_approval(
    selection: ProjectSelection, current_selection: Callable[[], ProjectSelection],
    artifact: Path, expected_review_id: str,
) -> ReviewPreview:
    artifact = review_path(artifact, selection)
    approval_path = approval_path_for(artifact)
    with TemporaryDirectory(prefix="logix-check-approval-") as temporary:
        snapshot = Path(temporary) / "approval.json"
        fingerprint = await snapshot_source(approval_path, snapshot)
        record = TypeAdapter(ApprovalRecord).validate_json(snapshot.read_bytes(), strict=True)
        approved = record["artifact"]
        if (record["review_id"] != expected_review_id or record["approval_path"] != str(approval_path)
                or approved["path"] != str(artifact)):
            raise ValueError("The approval record does not match the retained review ID or selected paths.")
        verified = await verify_documentation_copy(
            selection, current_selection, artifact.parent, artifact.name, record["proposal"],
            approved["approval_id"], approved["artifact_sha256"],
        )
        preview = review_preview(record["proposal"], verified, approval_path)
        if verified != approved or preview["review_id"] != expected_review_id:
            raise ValueError("The recorded approval differs from the verified review content.")
        if await snapshot_source(approval_path, Path(temporary) / "latest.json") != fingerprint:
            raise ValueError("The approval record changed during verification.")
    return preview


async def review_artifact(
    selection: ProjectSelection, current_selection: Callable[[], ProjectSelection],
    artifact: Path, proposal: Proposal, receipt: DocumentationCopy,
    confirm: Callable[[ReviewPreview], bool],
) -> ApprovalRecord | None:
    artifact = review_path(artifact, selection)
    if receipt["path"] != str(artifact) or receipt["source"] != proposal["source"] or receipt["approval_id"] != proposal["approval_id"]:
        raise ProjectReadError("invalid_proposal", "The selected artifact, creation receipt and proposal do not match.")
    approval_path = approval_path_for(artifact)
    if os.path.lexists(approval_path):
        raise ProjectReadError("destination_exists", "An approval record already exists for this artifact.")

    async def verify() -> DocumentationVerification:
        return await verify_documentation_copy(
            selection, current_selection, artifact.parent, artifact.name, proposal,
            receipt["approval_id"], receipt["artifact_sha256"],
        )

    verified = await verify()
    preview = review_preview(proposal, verified, approval_path)
    if not confirm(deepcopy(preview)):
        return None
    if await verify() != verified:
        raise ProjectReadError("artifact_changed", "The artifact changed after the local review.")
    record: ApprovalRecord = {
        **preview, "decision": "approved_documentation_copy",
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }
    # No receipt is published until validation and a fresh local confirmation succeed.
    publish_approval(approval_path, record)
    return record


def terminal_confirm(preview: ReviewPreview) -> bool:
    # JSON escaping also keeps terminal control characters in project text inert.
    print(json.dumps(preview, ensure_ascii=True, indent=2), file=sys.stderr)
    print("Review the exact documentation changes, source, artifact and destination above.", file=sys.stderr)
    print("Vendor verification has not been performed by this command.", file=sys.stderr)
    print("Type APPROVE to finalize this documentation copy; anything else declines: ", end="", file=sys.stderr, flush=True)
    return sys.stdin.readline().strip() == "APPROVE"


def main() -> None:
    parser = argparse.ArgumentParser(description="Review and finalize an existing documentation-only L5X copy locally.")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--project", type=Path, help="The saved source project")
    selection.add_argument("--selection-file", type=Path, help="The current shared selection JSON")
    parser.add_argument("--check", metavar="REVIEW_ID", help="Recheck a finalized copy using the review ID retained at approval")
    parser.add_argument("--proposal", type=Path, help="The preview tool's structured JSON result")
    parser.add_argument("--receipt", type=Path, help="The copy creation tool's structured JSON result")
    parser.add_argument("artifact", type=Path, help="The existing staged documentation copy")
    args = parser.parse_args()
    if args.check is not None and (args.proposal or args.receipt):
        parser.error("--check reads the existing approval record. Omit --proposal and --receipt.")
    if args.check is None and not (args.proposal and args.receipt):
        parser.error("Approval requires both --proposal and --receipt.")
    if args.check is None and not sys.stdin.isatty():
        parser.error("Local review requires an interactive terminal; automated confirmation is not supported.")
    try:
        if args.project is not None:
            fixed = ProjectSelection(validate_project_path(args.project))
            current = lambda: fixed
        else:
            selection_file = args.selection_file.resolve()
            current = lambda: read_selection(selection_file)
        if args.check is not None:
            verified = asyncio.run(check_approval(current(), current, args.artifact, args.check))
            print(json.dumps(verified, ensure_ascii=True))
            return
        proposal = TypeAdapter(Proposal).validate_json(args.proposal.read_bytes(), strict=True)
        receipt = TypeAdapter(DocumentationCopy).validate_json(args.receipt.read_bytes(), strict=True)
        result = asyncio.run(review_artifact(current(), current, args.artifact, proposal, receipt, terminal_confirm))
        if result is None:
            print("Documentation copy not approved; no approval record was written.", file=sys.stderr)
            raise SystemExit(2)
        print(json.dumps(result, ensure_ascii=True))
    except ValidationError as exc:
        print("Invalid approval record." if args.check is not None else
              "The proposal or creation receipt is not valid structured JSON.", file=sys.stderr)
        raise SystemExit(1) from exc
    except (ProjectReadError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
