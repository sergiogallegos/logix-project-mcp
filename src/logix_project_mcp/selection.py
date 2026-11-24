"""Local, explicitly configured saved-project selection."""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated, Literal, NamedTuple, NotRequired, TypedDict
from uuid import uuid4

from pydantic import ConfigDict, Field, TypeAdapter, ValidationError

from .project import PROJECT_EXTENSIONS, ProjectReadError, ProjectSnapshot

SelectionId = Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]


class SelectionRecord(TypedDict):
    __pydantic_config__ = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    path: str
    selection_id: SelectionId


class SelectionIdentity(TypedDict):
    path: str
    selection_id: SelectionId
    controller: NotRequired[str | None]
    software_revision: NotRequired[str | None]


class SelectionResult(TypedDict, total=False):
    selection: SelectionIdentity


class ProjectSelection(NamedTuple):
    path: Path
    selection_id: str | None = None

    def identity(self, snapshot: ProjectSnapshot | None = None) -> SelectionResult:
        if self.selection_id is None:
            return {}
        identity: SelectionIdentity = {"path": str(self.path), "selection_id": self.selection_id}
        if snapshot is not None:
            identity["controller"] = snapshot.controller.get("Name")
            identity["software_revision"] = snapshot.root.get("SoftwareRevision")
        return {"selection": identity}


def validate_project_path(path: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
        if resolved.suffix.lower() in PROJECT_EXTENSIONS and resolved.is_file():
            return resolved
    except (OSError, RuntimeError, ValueError):
        pass
    raise ProjectReadError("project_unavailable", "Choose an existing .ACD, .L5K, or full .L5X project file.")


def read_selection(file: Path) -> ProjectSelection:
    try:
        record = TypeAdapter(SelectionRecord).validate_json(file.read_bytes(), strict=True)
        path = Path(record["path"])
        if not path.is_absolute() or path.suffix.lower() not in PROJECT_EXTENSIONS or "\x00" in str(path):
            raise ValueError("Invalid project path")
    except FileNotFoundError as exc:
        raise ProjectReadError("selection_required", "Share a saved project using the local project selection helper.") from exc
    except (OSError, ValidationError, ValueError) as exc:
        raise ProjectReadError("invalid_selection", "The selection file is invalid or unavailable. Choose a valid selection file locally.") from exc
    return ProjectSelection(path, record["selection_id"])


def publish_selection(file: Path, path: Path) -> ProjectSelection:
    # Protect unrelated files if the configured selection filename is already occupied.
    if file.suffix.lower() != ".json":
        raise ProjectReadError("invalid_selection", "Choose a .json file for the shared selection.")
    try:
        if os.path.lexists(file):
            read_selection(file)
        file.parent.mkdir(parents=True, exist_ok=True)
        selection = ProjectSelection(path, uuid4().hex)
        record: SelectionRecord = {"schema_version": 1, "path": str(path), "selection_id": selection.selection_id}
        staged = None
        try:
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=file.parent, delete=False) as temporary:
                staged = Path(temporary.name)
                json.dump(record, temporary, ensure_ascii=False)
            os.replace(staged, file)
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)
    except OSError as exc:
        raise ProjectReadError("invalid_selection", f"Could not update the shared selection: {exc}") from exc
    return selection
