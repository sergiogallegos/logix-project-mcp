"""Load a saved project into the XML representation used by the MCP tools."""

import asyncio
import os
import stat
import sys
from collections import OrderedDict
from collections.abc import Coroutine
from contextlib import suppress
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, BinaryIO, Literal, NamedTuple, get_args
from xml.etree.ElementTree import Element, ParseError

from anyio import CancelScope
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

ProjectFormat = Literal["acd", "l5k", "l5x"]
PROJECT_EXTENSIONS = {f".{format_name}" for format_name in get_args(ProjectFormat)}
SDK_TIMEOUT_SECONDS = 90
COPY_CHUNK_SIZE = 1024 * 1024

ProjectErrorCode = Literal[
    "project_unavailable", "project_changed", "invalid_project", "unsupported_platform",
    "sdk_timeout", "sdk_error", "not_found", "destination_exists", "export_failed",
    "selection_required", "invalid_selection", "selection_changed", "ambiguous_target", "invalid_proposal",
    "artifact_changed", "artifact_unavailable", "unsupported_safety_content",
]


class ProjectReadError(Exception):
    """An expected saved-project failure with a message for the MCP client."""

    def __init__(self, code: ProjectErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class ProjectSnapshot(NamedTuple):
    root: Element
    controller: Element
    source_sha256: str


class SourceChanged(Exception):
    """The selected file changed while a snapshot was being copied."""


class NativeSnapshotCache:
    """Bounded, session-local cache of validated, immutable native export bytes."""

    def __init__(self, max_bytes: int = 128 * 1024 * 1024, max_entries: int = 4):
        self.max_bytes = max_bytes
        self.max_entries = max_entries
        self._entries: OrderedDict[tuple[Path, str], bytes] = OrderedDict()
        self._size = 0

    def get(self, key: tuple[Path, str]) -> bytes | None:
        value = self._entries.get(key)
        if value is not None:
            self._entries.move_to_end(key)
        return value

    def put(self, key: tuple[Path, str], value: bytes) -> None:
        if len(value) > self.max_bytes or self.max_entries < 1:
            return
        previous = self._entries.pop(key, None)
        if previous is not None:
            self._size -= len(previous)
        while self._entries and (self._size + len(value) > self.max_bytes or len(self._entries) >= self.max_entries):
            _, evicted = self._entries.popitem(last=False)
            self._size -= len(evicted)
        self._entries[key] = value
        self._size += len(value)


async def read_project(path: Path, cache: NativeSnapshotCache | None = None) -> ProjectSnapshot:
    """Inspect a verified copy and return the SHA-256 of its source bytes."""
    native = path.suffix.lower() != ".l5x"
    if native and sys.platform != "win32":
        raise ProjectReadError("unsupported_platform", "ACD and L5K inspection requires the Rockwell SDK on Windows.")

    cache_key = None
    export_bytes = None
    try:
        with TemporaryDirectory(prefix="logix-project-mcp-") as directory:
            snapshot = Path(directory) / f"source{path.suffix}"
            fingerprint = await snapshot_source(path, snapshot)
            if native and cache is not None:
                key = (path, fingerprint)
                export_bytes = cache.get(key)
                if export_bytes is None:
                    cache_key = key
            if export_bytes is not None:
                root = await finish_file_operation(asyncio.to_thread(parse_l5x_bytes, export_bytes))
            elif native:
                xml = Path(directory) / "snapshot.L5X"
                await export_snapshot(snapshot, xml, path.name)
                if cache is not None and xml.stat().st_size <= cache.max_bytes:
                    export_bytes = await finish_file_operation(asyncio.to_thread(xml.read_bytes))
                    root = await finish_file_operation(asyncio.to_thread(parse_l5x_bytes, export_bytes))
                else:
                    root = await finish_file_operation(asyncio.to_thread(parse_l5x, xml))
            else:
                root = await finish_file_operation(asyncio.to_thread(parse_l5x, snapshot))
    except OSError as exc:
        raise ProjectReadError("project_unavailable", f"Could not read {path.name}: {exc}") from exc
    except (ParseError, DefusedXmlException) as exc:
        raise ProjectReadError("invalid_project", f"Could not read {path.name}: {exc}") from exc

    controller = controller_from_l5x(root)
    if cache is not None and cache_key is not None and export_bytes is not None:
        cache.put(cache_key, export_bytes)
    return ProjectSnapshot(root, controller, fingerprint)


def controller_from_l5x(root: Element) -> Element:
    controller = root.find("Controller")
    if root.tag != "RSLogix5000Content" or controller is None:
        raise ProjectReadError("invalid_project", "Expected a Logix Designer project with a controller.")
    if root.get("TargetType", "Controller") != "Controller":
        raise ProjectReadError("invalid_project", "Select a full project export to inspect its controller.")
    return controller


async def snapshot_source(path: Path, snapshot: Path) -> str:
    try:
        return await finish_file_operation(asyncio.to_thread(copy_snapshot, path, snapshot))
    except SourceChanged as exc:
        raise ProjectReadError(
            "project_changed",
            f"{path.name} changed while it was being copied. Retry after the save completes."
        ) from exc
    except OSError as exc:
        raise ProjectReadError("project_unavailable", f"Could not read {path.name}: {exc}") from exc


async def finish_file_operation[T](operation: Coroutine[Any, Any, T]) -> T:
    # The thread may still hold an open file when the caller is cancelled.
    task = asyncio.create_task(operation)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        with CancelScope(shield=True), suppress(Exception):
            await task
        raise


def file_version(info: os.stat_result) -> tuple[int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def hash_source(source: BinaryIO, size: int, destination: BinaryIO | None = None) -> str:
    digest = sha256()
    remaining = size
    while remaining:
        chunk = source.read(min(remaining, COPY_CHUNK_SIZE))
        if not chunk:
            raise SourceChanged
        digest.update(chunk)
        if destination is not None:
            destination.write(chunk)
        remaining -= len(chunk)
    return digest.hexdigest()


def copy_snapshot(path: Path, snapshot: Path) -> str:
    expected = path.lstat()
    if not stat.S_ISREG(expected.st_mode):
        raise ProjectReadError("project_unavailable", f"{path.name} is no longer a regular saved project file.")
    version = file_version(expected)
    with path.open("rb", buffering=0) as source:
        if file_version(os.fstat(source.fileno())) != version:
            raise SourceChanged
        with snapshot.open("xb") as destination:
            fingerprint = hash_source(source, expected.st_size, destination)
        source.seek(0)
        # A Windows writer can change bytes before the last-write time is updated.
        if hash_source(source, expected.st_size) != fingerprint:
            raise SourceChanged
        if file_version(os.fstat(source.fileno())) != version:
            raise SourceChanged
    if file_version(path.lstat()) != version:
        raise SourceChanged
    return fingerprint


def parse_l5x(path: Path) -> Element:
    return ElementTree.parse(path, forbid_dtd=True).getroot()


def parse_l5x_bytes(data: bytes) -> Element:
    return ElementTree.fromstring(data, forbid_dtd=True)


async def export_snapshot(snapshot: Path, output: Path, source_name: str, component_xpath: str | None = None) -> None:
    selector = (component_xpath,) if component_xpath is not None else ()
    with output.with_suffix(".stderr").open("w+b") as stderr:
        # File-backed diagnostics let process exit be observed independently of pipe EOF.
        with CancelScope(shield=True):
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "logix_project_mcp._sdk_worker", str(snapshot), str(output), *selector,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=stderr,
            )
        try:
            async with asyncio.timeout(SDK_TIMEOUT_SECONDS):
                await process.wait()
        except TimeoutError as exc:
            raise ProjectReadError(
                "sdk_timeout",
                f"Logix Designer SDK did not finish exporting {source_name} "
                f"within {SDK_TIMEOUT_SECONDS} seconds."
            ) from exc
        finally:
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
                with CancelScope(shield=True):
                    await process.wait()

        if process.returncode:
            stderr.seek(0)
            detail = stderr.read(8192).decode("utf-8", errors="replace").strip()
            detail = detail or f"worker exited with code {process.returncode}"
            raise ProjectReadError("sdk_error", f"Logix Designer SDK could not export {source_name}: {detail}")
