import asyncio
import os
import sys
import unittest
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

from anyio import CancelScope

from logix_project_mcp import project as reader

PROJECT = b'<RSLogix5000Content><Controller Name="First" /></RSLogix5000Content>'
UPDATED = PROJECT.replace(b"First", b"Later")


class ProjectTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.source = Path(directory) / "Selected.L5X"
        self.source.write_bytes(PROJECT)

    async def test_rejects_changed_bytes_even_with_same_size_and_mtime(self):
        original = self.source.stat()
        hash_source = reader.hash_source

        def change_after_copy(source, size, destination=None):
            digest = hash_source(source, size, destination)
            if destination is not None:
                self.source.write_bytes(UPDATED)
                os.utime(self.source, ns=(original.st_atime_ns, original.st_mtime_ns))
            return digest

        with patch.object(reader, "hash_source", side_effect=change_after_copy):
            with self.assertRaisesRegex(reader.ProjectReadError, "changed while it was being copied"):
                await reader.read_project(self.source)

        self.assertEqual(self.source.stat().st_mtime_ns, original.st_mtime_ns)
        result = await reader.read_project(self.source)
        self.assertEqual(result.controller.get("Name"), "Later")
        self.assertEqual(result.source_sha256, sha256(UPDATED).hexdigest())
        self.assertEqual(self.source.read_bytes(), UPDATED)

    async def test_cancelled_copy_finishes_before_snapshot_directory_is_removed(self):
        started = asyncio.Event()
        release = Event()
        loop = asyncio.get_running_loop()
        snapshots = []
        copy = reader.copy_snapshot

        def held_copy(path, snapshot):
            snapshots.append(snapshot.parent)
            loop.call_soon_threadsafe(started.set)
            if not release.wait(5):
                raise RuntimeError("test did not release the copy")
            return copy(path, snapshot)

        with patch.object(reader, "copy_snapshot", side_effect=held_copy):
            task = asyncio.create_task(reader.read_project(self.source))
            try:
                await asyncio.wait_for(started.wait(), 5)
                task.cancel()
                await asyncio.sleep(0)
                self.assertTrue(snapshots[0].is_dir())
                self.assertFalse(task.done())
            finally:
                release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task

        self.assertFalse(snapshots[0].exists())
        self.assertEqual((await reader.read_project(self.source)).source_sha256, sha256(PROJECT).hexdigest())


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.source = Path(directory) / "Selected.ACD"
        self.source.write_bytes(PROJECT)
        self.processes = []
        self.snapshots = []
        self.on_launch = None
        self.script = "import time; time.sleep(30)"
        spawn = asyncio.create_subprocess_exec

        async def fake_worker(executable, module_flag, module, snapshot, output, **kwargs):
            self.snapshots.append(Path(snapshot))
            self.assertNotEqual(Path(snapshot), self.source)
            process = await spawn(executable, "-c", self.script, snapshot, output, **kwargs)
            self.processes.append(process)
            if self.on_launch is not None:
                self.on_launch()
            return process

        stack = self.enterContext(ExitStack())
        stack.enter_context(patch.object(reader, "sys", SimpleNamespace(platform="win32", executable=sys.executable)))
        stack.enter_context(patch.object(reader.asyncio, "create_subprocess_exec", side_effect=fake_worker))

    async def asyncTearDown(self):
        for process in self.processes:
            if process.returncode is None:
                process.kill()
                await process.wait()

    async def check_recovery(self):
        self.assertEqual(len(self.processes), 1)
        self.assertIsNotNone(self.processes[0].returncode)
        self.assertFalse(self.snapshots[0].parent.exists())
        self.on_launch = None
        self.script = "import shutil, sys; shutil.copyfile(sys.argv[1], sys.argv[2])"

        result = await reader.read_project(self.source)
        self.assertEqual(result.controller.get("Name"), "First")
        self.assertEqual(result.source_sha256, sha256(PROJECT).hexdigest())
        self.assertEqual(self.source.read_bytes(), PROJECT)
        self.assertNotEqual(self.snapshots[0], self.snapshots[1])
        self.assertFalse(self.snapshots[1].parent.exists())

    async def test_timeout_reaps_stalled_worker_and_next_read_succeeds(self):
        with patch.object(reader, "SDK_TIMEOUT_SECONDS", 0.2):
            with self.assertRaisesRegex(reader.ProjectReadError, "did not finish exporting Selected.ACD"):
                await reader.read_project(self.source)
        await self.check_recovery()

    async def test_mcp_style_cancellation_reaps_worker_and_next_read_succeeds(self):
        with CancelScope() as request:
            self.on_launch = lambda: asyncio.get_running_loop().call_soon(request.cancel)
            await reader.read_project(self.source)
        self.assertTrue(request.cancelled_caught)
        await self.check_recovery()

    async def test_cancellation_during_worker_launch_reaps_worker(self):
        with CancelScope() as request:
            self.on_launch = request.cancel
            await reader.read_project(self.source)
        self.assertTrue(request.cancelled_caught)
        await self.check_recovery()
