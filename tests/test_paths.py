from __future__ import annotations

import hashlib
import multiprocessing
import os
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

import orchestration.lib.paths as paths_module
from orchestration.lib.paths import open_output_leaf, prepare_scope, validate_relative_path


FIXTURE_ROOT = (Path(os.path.sep) / "tmp").resolve() / "mothership-paths-tests"


class _TrackedScandir:
    def __init__(self, iterator: object) -> None:
        self._iterator = iterator
        self.exhausted = False
        self.closed = False

    def __iter__(self) -> _TrackedScandir:
        return self

    def __next__(self) -> os.DirEntry[str]:
        try:
            return next(self._iterator)  # type: ignore[arg-type]
        except StopIteration:
            self.exhausted = True
            raise

    def __enter__(self) -> _TrackedScandir:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        if self.closed:
            return
        try:
            self._iterator.close()  # type: ignore[attr-defined]
        finally:
            self.closed = True


def _tracking_scandir() -> tuple[list[_TrackedScandir], object]:
    real_scandir = os.scandir
    tracked: list[_TrackedScandir] = []

    def scan(path: object) -> _TrackedScandir:
        proxy = _TrackedScandir(real_scandir(path))  # type: ignore[arg-type]
        tracked.append(proxy)
        return proxy

    return tracked, scan


def _fifo_probe(task_root: str, run_root: str, result: multiprocessing.Queue) -> None:
    try:
        prepare_scope(
            {"prompt_path": "prompt.txt", "context_paths": ["pipe"]},
            Path(task_root),
            Path(run_root),
            False,
        )
    except ValueError:
        result.put("rejected")
    except BaseException as error:
        result.put(f"unexpected:{type(error).__name__}")
    else:
        result.put("accepted")


class PathTests(unittest.TestCase):
    def setUp(self) -> None:
        os.makedirs(FIXTURE_ROOT, mode=0o700, exist_ok=True)
        os.chmod(FIXTURE_ROOT, 0o700)
        self.temp = tempfile.TemporaryDirectory(dir=FIXTURE_ROOT)
        self.root = Path(self.temp.name)
        self.task = self.root / "task"
        self.run = self.root / "run"
        self.task.mkdir(0o700)
        self.run.mkdir(0o700)
        (self.task / "prompt.txt").write_bytes(b"prompt")
        (self.task / "one.txt").write_bytes(b"one")
        (self.task / "nested").mkdir(0o700)
        (self.task / "nested/two.txt").write_bytes(b"two")

    def tearDown(self) -> None:
        paths_module._COMPONENT_SWAP_HOOK = None
        paths_module._STAGE_VERIFY_HOOK = None
        self.temp.cleanup()
        FIXTURE_ROOT.rmdir()

    def data(self, **extra: object) -> dict[str, object]:
        value: dict[str, object] = {
            "prompt_path": "prompt.txt",
            "context_paths": ["one.txt", "nested/two.txt"],
            "max_context_files": 32,
            "max_context_bytes": 1_048_576,
        }
        value.update(extra)
        return value

    def assert_no_stage(self) -> None:
        self.assertFalse((self.run / "staged-context").exists())
        self.assertFalse((self.run / "staged-context").is_symlink())

    def test_relative_path_contract(self) -> None:
        # Accepting a non-normalized, dot, or unsafe path must make this fail.
        invalid = (None, 1, "", "/x", ".", "..", "x/./y", "x/../y", "x//y", "x/", "x\\y", "x\x00y")
        for value in invalid:
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValueError):
                    validate_relative_path(value)  # type: ignore[arg-type]
        self.assertEqual("nested/file", str(validate_relative_path("nested/file")))

    def test_normalized_absolute_separate_roots_are_required(self) -> None:
        # Normalizing, resolving, or accepting overlapping roots must make this fail.
        sibling = self.root / "sibling"
        sibling.mkdir()
        invalid_pairs = (
            (Path("relative"), self.run),
            (Path(str(self.task) + "/../task"), self.run),
            (self.task, self.task),
        )
        nested_run = self.task / "inside-run"
        nested_run.mkdir()
        nested_task = self.run / "inside-task"
        nested_task.mkdir()
        invalid_pairs += ((self.task, nested_run), (nested_task, self.run))
        for task_root, run_root in invalid_pairs:
            with self.subTest(task_root=task_root, run_root=run_root):
                with self.assertRaises(ValueError):
                    prepare_scope(self.data(), task_root, run_root, False)

    def test_root_leaf_and_ancestor_symlinks_are_rejected(self) -> None:
        # Resolving a root symlink before descriptor traversal must make this fail.
        task_link = self.root / "task-link"
        task_link.symlink_to(self.task, target_is_directory=True)
        with self.assertRaises(ValueError):
            prepare_scope(self.data(), task_link, self.run, False)
        ancestor = self.root / "ancestor-link"
        ancestor.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            prepare_scope(self.data(), ancestor / "task", self.run, False)

    def test_input_and_output_parent_symlinks_are_rejected(self) -> None:
        # Following an input or output-parent symlink must make this fail.
        (self.task / "input-link").symlink_to(self.task / "one.txt")
        with self.assertRaises(ValueError):
            prepare_scope(self.data(context_paths=["input-link"]), self.task, self.run, False)
        outside = self.root / "outside"
        outside.mkdir()
        (self.run / "output-link").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            open_output_leaf(self.run, "output-link/out.bin")
        self.assertEqual([], list(outside.iterdir()))

    def test_prompt_context_context_and_existing_output_hardlinks_are_rejected(self) -> None:
        # Missing any inode-alias comparison must make this fail.
        os.link(self.task / "prompt.txt", self.task / "prompt-hard")
        with self.assertRaises(ValueError):
            prepare_scope(self.data(context_paths=["prompt-hard"]), self.task, self.run, False)
        os.link(self.task / "one.txt", self.task / "one-hard")
        with self.assertRaises(ValueError):
            prepare_scope(self.data(context_paths=["one.txt", "one-hard"]), self.task, self.run, False)
        os.link(self.task / "one.txt", self.run / "existing-output")
        with self.assertRaises(ValueError):
            prepare_scope(self.data(context_paths=["one.txt"]), self.task, self.run, False)

    def test_existing_output_scandir_is_closed_on_early_link_rejection(self) -> None:
        # Leaving the output walk's iterator open after a link rejection must make this fail.
        target = self.root / "existing-output-target"
        target.mkdir()
        marker = target / "marker"
        marker.write_bytes(b"untouched-existing-output-target")
        (self.run / "existing-output-link").symlink_to(target, target_is_directory=True)
        tracked, tracking_scandir = _tracking_scandir()
        try:
            with patch.object(paths_module.os, "scandir", new=tracking_scandir):
                with self.assertRaises(ValueError):
                    prepare_scope(self.data(), self.task, self.run, False)
            self.assertTrue((self.run / "existing-output-link").is_symlink())
            self.assertEqual(b"untouched-existing-output-target", marker.read_bytes())
            self.assertTrue(tracked)
            self.assertTrue(
                all(iterator.exhausted or iterator.closed for iterator in tracked),
                [(iterator.exhausted, iterator.closed) for iterator in tracked],
            )
        finally:
            for iterator in tracked:
                iterator.close()

    def test_fifo_public_api_rejection_has_one_visible_two_second_hang_guard(self) -> None:
        # Removing O_NONBLOCK from the input open must make this child hang and fail.
        os.mkfifo(self.task / "pipe")
        result: multiprocessing.Queue = multiprocessing.Queue()
        process = multiprocessing.Process(target=_fifo_probe, args=(str(self.task), str(self.run), result))
        process.start()
        process.join(2.0)
        if process.is_alive():
            process.terminate()
            process.join()
            self.fail("FIFO input open exceeded the single two-second hang guard")
        self.assertEqual(0, process.exitcode)
        self.assertEqual("rejected", result.get(timeout=0.5))

    def test_socket_capability_branch_and_regular_descriptor_validator(self) -> None:
        # Accepting an actual socket or device descriptor as regular must make this fail.
        socket_path = self.task / "fixture.sock"
        listener = socket.socket(socket.AF_UNIX)
        bind_result = "supported"
        try:
            try:
                listener.bind(str(socket_path))
            except PermissionError as error:
                bind_result = f"denied:{error.errno}"
            if bind_result == "supported":
                with self.assertRaises(ValueError):
                    prepare_scope(self.data(context_paths=["fixture.sock"]), self.task, self.run, False)
            else:
                self.assertTrue(bind_result.startswith("denied:"))
        finally:
            listener.close()
        print(f"FIXTURE_AF_UNIX_BIND={bind_result}")
        validator = getattr(paths_module, "_regular_descriptor", None)
        self.assertIsNotNone(validator)
        assert validator is not None
        left, right = socket.socketpair()
        try:
            with self.assertRaises(ValueError):
                validator(left.fileno())
        finally:
            left.close()
            right.close()
        device_fd = os.open("/dev/null", os.O_RDONLY | paths_module._NONBLOCK)
        try:
            with self.assertRaises(ValueError):
                validator(device_fd)
        finally:
            os.close(device_fd)

    def test_file_count_and_byte_boundaries(self) -> None:
        # Off-by-one file or aggregate-byte limits must make this fail.
        empty = self.task / "empty"
        empty.write_bytes(b"")
        zero = prepare_scope(self.data(context_paths=[], max_context_files=0, max_context_bytes=0), self.task, self.run, False)
        self.assertEqual((), zero.files)
        exact = prepare_scope(self.data(context_paths=["one.txt"], max_context_files=1, max_context_bytes=3), self.task, self.run, False)
        self.assertEqual(3, exact.files[0].size)
        empty_result = prepare_scope(self.data(context_paths=["empty"], max_context_files=1, max_context_bytes=0), self.task, self.run, False)
        self.assertEqual(0, empty_result.files[0].size)
        with self.assertRaises(ValueError):
            prepare_scope(self.data(context_paths=["one.txt"], max_context_files=0), self.task, self.run, False)
        with self.assertRaises(ValueError):
            prepare_scope(self.data(context_paths=["one.txt"], max_context_bytes=2), self.task, self.run, False)
        with self.assertRaises(ValueError):
            prepare_scope(self.data(context_paths=["one.txt"] * 33, max_context_files=99), self.task, self.run, False)

    def test_streaming_overflow_is_bounded_and_has_no_post_sentinel_read(self) -> None:
        # Reading after the first over-budget sentinel or consuming a full excess chunk must make this fail.
        payload = b"x" * (paths_module._CHUNK + 4)
        (self.task / "large").write_bytes(payload)
        original_read = os.read
        reads: list[int] = []

        def tracked_read(fd: int, amount: int) -> bytes:
            reads.append(amount)
            return original_read(fd, amount)

        with patch.object(paths_module.os, "read", side_effect=tracked_read):
            with self.assertRaises(ValueError):
                prepare_scope(
                    self.data(context_paths=["large"], max_context_bytes=paths_module._CHUNK + 3),
                    self.task,
                    self.run,
                    False,
                )
        self.assertEqual(1, reads.count(4))
        self.assertNotIn(paths_module._CHUNK, reads[reads.index(4) + 1 :])

    def test_aggregate_overflow_in_later_file_stops_at_sentinel(self) -> None:
        # Resetting the aggregate budget for each file must make this fail.
        (self.task / "first").write_bytes(b"abcd")
        (self.task / "second").write_bytes(b"efgh")
        original_read = os.read
        requested: list[int] = []

        def tracked_read(fd: int, amount: int) -> bytes:
            requested.append(amount)
            return original_read(fd, amount)

        with patch.object(paths_module.os, "read", side_effect=tracked_read):
            with self.assertRaises(ValueError):
                prepare_scope(
                    self.data(context_paths=["first", "second"], max_context_bytes=7),
                    self.task,
                    self.run,
                    False,
                )
        self.assertEqual(4, requested[-1])

    def test_sensitive_filename_catalog_is_case_insensitive(self) -> None:
        # Removing any sensitive basename or extension class must make this fail.
        names = (
            ".env",
            ".ENV.local",
            "id_rsa",
            "ID_DSA",
            "id_ecdsa",
            "id_ed25519",
            "client.pem",
            "client.KEY",
            "client.p12",
            "client.pfx",
            "authorization.txt",
            "my-credential.txt",
            "session-token.txt",
            "shared-secret.txt",
        )
        for name in names:
            with self.subTest(name=name):
                (self.task / name).write_bytes(b"placeholder")
                with self.assertRaises(ValueError):
                    prepare_scope(self.data(context_paths=[name]), self.task, self.run, False)

    def test_sensitive_content_catalog_and_chunk_splits(self) -> None:
        # Dropping a marker class or fixed-boundary streaming state must make this fail.
        fragments = (
            b"-----BEGIN " + b"PRIVATE KEY-----",
            b"Authorization: " + b"Bearer " + b"placeholder",
            b"provider_api" + b"_key = placeholder",
            b"cloud-provider" + b"-key: placeholder",
            b"secret-access" + b"-key = placeholder",
            b"access" + b"_token=placeholder",
            b"refresh-token" + b": placeholder",
            b"secret" + b" = placeholder",
        )
        for index, marker in enumerate(fragments):
            name = f"ordinary-{index}.txt"
            (self.task / name).write_bytes(marker)
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    prepare_scope(self.data(context_paths=[name]), self.task, self.run, False)
        split = b"x" * (paths_module._CHUNK - 5) + b"access" + b"_token=placeholder"
        (self.task / "split-marker.txt").write_bytes(split)
        with self.assertRaises(ValueError):
            prepare_scope(self.data(context_paths=["split-marker.txt"]), self.task, self.run, False)

    def test_quoted_sensitive_assignment_names_are_rejected(self) -> None:
        fragments = (
            b'{"api_key": "placeholder"}',
            b"{'secret-access-key' : 'placeholder'}",
            b'"provider_api_key"\t=\t"placeholder"',
        )
        for index, marker in enumerate(fragments):
            name = f"quoted-sensitive-{index}.txt"
            (self.task / name).write_bytes(marker)
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    prepare_scope(self.data(context_paths=[name]), self.task, self.run, False)
        quoted_prefix = b'"api_key'
        split = b"." * (paths_module._CHUNK - len(quoted_prefix)) + quoted_prefix
        (self.task / "quoted-sensitive-split.txt").write_bytes(
            split + b'": "placeholder"'
        )
        with self.assertRaises(ValueError):
            prepare_scope(
                self.data(context_paths=["quoted-sensitive-split.txt"]),
                self.task,
                self.run,
                False,
            )

    def test_arbitrary_identifier_secret_assignment_crosses_many_chunks(self) -> None:
        # Reintroducing a fixed tail for assignment identifiers must make this fail.
        identifier = b"_" + (b"a" * (paths_module._CHUNK + 600)) + b"_secret"
        payload = identifier + (b" " * 300) + b"= placeholder"
        (self.task / "long-assignment.txt").write_bytes(payload)
        with self.assertRaises(ValueError):
            prepare_scope(self.data(context_paths=["long-assignment.txt"]), self.task, self.run, False)

    def test_measurement_is_zero_write_and_rows_are_utf8_sorted(self) -> None:
        # Writing during measurement or sorting by locale/path order must make this fail.
        (self.task / "z.txt").write_bytes(b"z")
        (self.task / "é.txt").write_bytes("é".encode())
        with patch.object(paths_module.os, "write", side_effect=AssertionError("measurement wrote")):
            measured = prepare_scope(
                self.data(context_paths=["é.txt", "z.txt", "one.txt"]),
                self.task,
                self.run,
                False,
            )
        expected_order = sorted(("é.txt", "z.txt", "one.txt"), key=lambda value: value.encode("utf-8"))
        self.assertEqual(expected_order, [item.relative_path for item in measured.files])
        rows = b"".join(
            f"{item.relative_path}\t{item.size}\t{item.sha256}\n".encode("utf-8")
            for item in measured.files
        )
        self.assertEqual(hashlib.sha256(rows).hexdigest(), measured.scope_sha256)
        self.assertEqual([], list(self.run.iterdir()))

    def test_nested_stage_modes_hashes_inodes_and_input_immutability(self) -> None:
        # Copying prompt, sharing inodes, changing inputs, or weakening stage modes must make this fail.
        inputs = (self.task / "prompt.txt", self.task / "one.txt", self.task / "nested/two.txt")
        original = {
            path.relative_to(self.task): (
                path.read_bytes(),
                stat.S_IMODE(path.stat().st_mode),
                path.stat().st_mtime_ns,
            )
            for path in inputs
        }
        scope = prepare_scope(self.data(), self.task, self.run, True)
        staged = scope.staged_root
        self.assertIsNotNone(staged)
        assert staged is not None
        self.assertEqual(0o555, stat.S_IMODE(staged.stat().st_mode))
        self.assertEqual(0o555, stat.S_IMODE((staged / "nested").stat().st_mode))
        self.assertFalse((staged / "prompt.txt").exists())
        for item in scope.files:
            source = self.task / item.relative_path
            output = staged / item.relative_path
            self.assertEqual(source.read_bytes(), output.read_bytes())
            self.assertEqual(item.size, output.stat().st_size)
            self.assertEqual(item.sha256, hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertNotEqual((source.stat().st_dev, source.stat().st_ino), (output.stat().st_dev, output.stat().st_ino))
            self.assertEqual(0o444, stat.S_IMODE(output.stat().st_mode))
        after = {
            path.relative_to(self.task): (
                path.read_bytes(),
                stat.S_IMODE(path.stat().st_mode),
                path.stat().st_mtime_ns,
            )
            for path in inputs
        }
        self.assertEqual(original, after)

    def test_short_writes_are_completed(self) -> None:
        # Assuming os.write consumes the full block must make this fail.
        original_write = os.write

        def short_write(fd: int, block: bytes) -> int:
            return original_write(fd, block[:2])

        with patch.object(paths_module.os, "write", side_effect=short_write):
            scope = prepare_scope(self.data(context_paths=["one.txt"]), self.task, self.run, True)
        assert scope.staged_root is not None
        self.assertEqual(b"one", (scope.staged_root / "one.txt").read_bytes())

    def test_growth_after_measurement_reads_only_expected_bytes_plus_sentinel(self) -> None:
        # Writing a growth sentinel into the stage must make this fail.
        opens = 0
        original_write = os.write
        written = 0

        def swap(name: str) -> None:
            nonlocal opens
            if name == "one.txt":
                opens += 1
                if opens == 2:
                    with (self.task / "one.txt").open("ab") as stream:
                        stream.write(b"x")

        def tracked_write(fd: int, block: bytes) -> int:
            nonlocal written
            result = original_write(fd, block)
            written += result
            return result

        paths_module._COMPONENT_SWAP_HOOK = swap
        with patch.object(paths_module.os, "write", side_effect=tracked_write):
            with self.assertRaises(ValueError):
                prepare_scope(self.data(context_paths=["one.txt"]), self.task, self.run, True)
        self.assertEqual(3, written)
        self.assert_no_stage()

    def test_same_byte_inode_swap_between_measurement_and_copy_fails(self) -> None:
        # Checking bytes without binding the measured inode must make this fail.
        opens = 0

        def swap(name: str) -> None:
            nonlocal opens
            if name == "one.txt":
                opens += 1
                if opens == 2:
                    original = self.task / "one.original"
                    (self.task / "one.txt").rename(original)
                    (self.task / "one.txt").write_bytes(b"one")

        paths_module._COMPONENT_SWAP_HOOK = swap
        with self.assertRaises(ValueError):
            prepare_scope(self.data(context_paths=["one.txt"]), self.task, self.run, True)
        self.assert_no_stage()

    def test_file_and_directory_chmod_failures_leave_no_stage(self) -> None:
        # Masking chmod failures or retaining partial stage content must make this fail.
        real_fchmod = os.fchmod
        for failed_mode in (0o444, 0o555):
            with self.subTest(failed_mode=oct(failed_mode)):
                calls = 0

                def failing_fchmod(fd: int, mode: int) -> None:
                    nonlocal calls
                    if mode == failed_mode:
                        calls += 1
                        if calls == 1:
                            raise OSError("injected chmod failure")
                    real_fchmod(fd, mode)

                with patch.object(paths_module.os, "fchmod", side_effect=failing_fchmod):
                    with self.assertRaises(OSError):
                        prepare_scope(self.data(), self.task, self.run, True)
                self.assert_no_stage()

    def test_later_stage_lock_failure_cleans_the_real_partially_locked_tree(self) -> None:
        # Failing to unlock traversed owned directories before child deletion must make this fail.
        outside = self.root / "outside-partial-lock"
        outside.mkdir()
        marker = outside / "marker"
        marker.write_bytes(b"untouched-partial-lock-target")
        marker_info = marker.stat()
        marker_snapshot = (
            marker.read_bytes(),
            stat.S_IMODE(marker_info.st_mode),
            marker_info.st_dev,
            marker_info.st_ino,
            marker_info.st_mtime_ns,
        )
        real_fchmod = os.fchmod
        lock_calls = 0
        stage_root_lock_error = OSError("injected stage-root lock failure")

        def fail_second_lock(fd: int, mode: int) -> None:
            nonlocal lock_calls
            if mode == 0o555:
                lock_calls += 1
                if lock_calls == 2:
                    raise stage_root_lock_error
            real_fchmod(fd, mode)

        with patch.object(paths_module.os, "fchmod", side_effect=fail_second_lock):
            with self.assertRaises(OSError) as caught:
                prepare_scope(self.data(), self.task, self.run, True)
        self.assertEqual(2, lock_calls)
        self.assertIs(stage_root_lock_error, caught.exception)
        self.assertIsNone(caught.exception.__context__)
        current_marker = marker.stat()
        self.assertEqual(
            marker_snapshot,
            (
                marker.read_bytes(),
                stat.S_IMODE(current_marker.st_mode),
                current_marker.st_dev,
                current_marker.st_ino,
                current_marker.st_mtime_ns,
            ),
        )
        self.assertEqual(["marker"], [path.name for path in outside.iterdir()])
        self.assert_no_stage()

    def test_stage_replacement_symlink_is_unlinked_without_touching_target(self) -> None:
        # Traversing a replacement symlink during cleanup must make this fail.
        target = self.root / "replacement-target"
        target.mkdir()
        marker = target / "marker"
        marker.write_bytes(b"untouched")
        real_fchmod = os.fchmod
        swapped = False

        def failing_fchmod(fd: int, mode: int) -> None:
            nonlocal swapped
            if mode == 0o444 and not swapped:
                swapped = True
                (self.run / "staged-context").rename(self.root / "moved-owned-stage")
                (self.run / "staged-context").symlink_to(target, target_is_directory=True)
                raise OSError("injected replacement")
            real_fchmod(fd, mode)

        with patch.object(paths_module.os, "fchmod", side_effect=failing_fchmod):
            with self.assertRaises(OSError):
                prepare_scope(self.data(context_paths=["one.txt"]), self.task, self.run, True)
        self.assert_no_stage()
        self.assertEqual(b"untouched", marker.read_bytes())

    def test_stage_replacement_real_directory_is_never_traversed(self) -> None:
        # Recursing into an identity-mismatched replacement directory must make this fail.
        marker_name = "replacement-marker"
        real_fchmod = os.fchmod
        swapped = False

        def failing_fchmod(fd: int, mode: int) -> None:
            nonlocal swapped
            if mode == 0o444 and not swapped:
                swapped = True
                (self.run / "staged-context").rename(self.root / "moved-real-stage")
                (self.run / "staged-context").mkdir()
                (self.run / "staged-context" / marker_name).write_bytes(b"untouched")
                raise OSError("injected replacement")
            real_fchmod(fd, mode)

        with patch.object(paths_module.os, "fchmod", side_effect=failing_fchmod):
            with self.assertRaises(OSError):
                prepare_scope(self.data(context_paths=["one.txt"]), self.task, self.run, True)
        marker = self.run / "staged-context" / marker_name
        self.assertTrue(marker.exists())
        self.assertEqual(b"untouched", marker.read_bytes())

    def test_nested_stage_directory_identity_is_bound_from_creation(self) -> None:
        # Rebinding ownership from the final scandir view must make this fail.
        replacement_node: tuple[int, int] | None = None

        def replace_nested_directory() -> None:
            nonlocal replacement_node
            staged = self.run / "staged-context"
            (staged / "nested").rename(self.root / "moved-owned-nested")
            replacement = staged / "nested"
            replacement.mkdir()
            marker = replacement / "replacement-marker"
            marker.write_bytes(b"replacement-directory")
            info = replacement.stat()
            replacement_node = (info.st_dev, info.st_ino)

        paths_module._STAGE_VERIFY_HOOK = replace_nested_directory
        with self.assertRaises(ValueError):
            prepare_scope(self.data(), self.task, self.run, True)
        replacement = self.run / "staged-context/nested"
        self.assertEqual(b"replacement-directory", (replacement / "replacement-marker").read_bytes())
        info = replacement.stat()
        self.assertEqual(replacement_node, (info.st_dev, info.st_ino))

    def test_nested_stage_file_identity_is_bound_from_creation(self) -> None:
        # Treating a different final regular inode as the owned copy must make this fail.
        replacement_node: tuple[int, int] | None = None

        def replace_nested_file() -> None:
            nonlocal replacement_node
            staged_file = self.run / "staged-context/nested/two.txt"
            staged_file.rename(self.root / "moved-owned-two.txt")
            staged_file.write_bytes(b"replacement-file")
            info = staged_file.stat()
            replacement_node = (info.st_dev, info.st_ino)

        paths_module._STAGE_VERIFY_HOOK = replace_nested_file
        with self.assertRaises(ValueError):
            prepare_scope(self.data(), self.task, self.run, True)
        replacement = self.run / "staged-context/nested/two.txt"
        self.assertEqual(b"replacement-file", replacement.read_bytes())
        info = replacement.stat()
        self.assertEqual(replacement_node, (info.st_dev, info.st_ino))

    def test_nested_stage_directory_symlink_is_removed_without_traversal(self) -> None:
        # Following an owned-directory replacement symlink during cleanup must make this fail.
        target = self.root / "nested-directory-target"
        target.mkdir()
        marker = target / "marker"
        marker.write_bytes(b"untouched-directory-target")

        def replace_nested_directory() -> None:
            staged = self.run / "staged-context"
            (staged / "nested").rename(self.root / "moved-owned-directory")
            (staged / "nested").symlink_to(target, target_is_directory=True)

        paths_module._STAGE_VERIFY_HOOK = replace_nested_directory
        with self.assertRaises(ValueError):
            prepare_scope(self.data(), self.task, self.run, True)
        self.assert_no_stage()
        self.assertEqual(b"untouched-directory-target", marker.read_bytes())

    def test_nested_stage_file_symlink_is_removed_without_traversal(self) -> None:
        # Following an owned-file replacement symlink during cleanup must make this fail.
        target = self.root / "nested-file-target"
        target.write_bytes(b"untouched-file-target")

        def replace_nested_file() -> None:
            staged_file = self.run / "staged-context/nested/two.txt"
            staged_file.rename(self.root / "moved-owned-file")
            staged_file.symlink_to(target)

        paths_module._STAGE_VERIFY_HOOK = replace_nested_file
        with self.assertRaises(ValueError):
            prepare_scope(self.data(), self.task, self.run, True)
        self.assert_no_stage()
        self.assertEqual(b"untouched-file-target", target.read_bytes())

    def test_unexpected_nested_stage_entry_is_not_promoted_to_owned(self) -> None:
        # Accepting or deleting an entry absent from the creation ledger must make this fail.
        unexpected_node: tuple[int, int] | None = None

        def insert_unexpected_entry() -> None:
            nonlocal unexpected_node
            unexpected = self.run / "staged-context/nested/unexpected.bin"
            unexpected.write_bytes(b"unowned-entry")
            info = unexpected.stat()
            unexpected_node = (info.st_dev, info.st_ino)

        paths_module._STAGE_VERIFY_HOOK = insert_unexpected_entry
        with self.assertRaises(ValueError):
            prepare_scope(self.data(), self.task, self.run, True)
        unexpected = self.run / "staged-context/nested/unexpected.bin"
        self.assertEqual(b"unowned-entry", unexpected.read_bytes())
        info = unexpected.stat()
        self.assertEqual(unexpected_node, (info.st_dev, info.st_ino))

    def test_stage_verification_scandirs_are_closed_on_nested_early_rejection(self) -> None:
        # Leaving any recursive verification iterator open after rejection must make this fail.
        unexpected_node: tuple[int, int] | None = None

        def insert_unexpected_entry() -> None:
            nonlocal unexpected_node
            unexpected = self.run / "staged-context/nested/unexpected-tracked.bin"
            unexpected.write_bytes(b"unowned-tracked-entry")
            info = unexpected.stat()
            unexpected_node = (info.st_dev, info.st_ino)

        paths_module._STAGE_VERIFY_HOOK = insert_unexpected_entry
        tracked, tracking_scandir = _tracking_scandir()
        try:
            with patch.object(paths_module.os, "scandir", new=tracking_scandir):
                with self.assertRaises(ValueError):
                    prepare_scope(self.data(), self.task, self.run, True)
            unexpected = self.run / "staged-context/nested/unexpected-tracked.bin"
            self.assertEqual(b"unowned-tracked-entry", unexpected.read_bytes())
            info = unexpected.stat()
            self.assertEqual(unexpected_node, (info.st_dev, info.st_ino))
            self.assertTrue(tracked)
            self.assertTrue(
                all(iterator.exhausted or iterator.closed for iterator in tracked),
                [(iterator.exhausted, iterator.closed) for iterator in tracked],
            )
        finally:
            for iterator in tracked:
                iterator.close()

    def test_output_creation_modes_and_preexisting_types(self) -> None:
        # Reusing a target or applying incorrect private/custom modes must make this fail.
        with open_output_leaf(self.run, "nested/out.bin") as output:
            output.write(b"x")
        self.assertEqual(0o700, stat.S_IMODE((self.run / "nested").stat().st_mode))
        self.assertEqual(0o600, stat.S_IMODE((self.run / "nested/out.bin").stat().st_mode))
        with open_output_leaf(self.run, "custom.bin", 0o640) as output:
            output.write(b"y")
        self.assertEqual(0o640, stat.S_IMODE((self.run / "custom.bin").stat().st_mode))
        (self.run / "existing-dir").mkdir()
        (self.run / "existing-link").symlink_to(self.run / "custom.bin")
        os.mkfifo(self.run / "existing-fifo")
        for name in ("custom.bin", "existing-dir", "existing-link", "existing-fifo"):
            with self.subTest(name=name):
                with self.assertRaises(OSError):
                    open_output_leaf(self.run, name)

    def test_final_output_operation_errors_preserve_identity_and_zero_residue(self) -> None:
        # Wrapping open, chmod, or fdopen errors or retaining owned residue must make this fail.
        unrelated = self.root / "unrelated-output-target"
        unrelated.write_bytes(b"untouched-output-target")
        unrelated_info = unrelated.stat()
        unrelated_node = (unrelated_info.st_dev, unrelated_info.st_ino)
        real_open = os.open
        real_fchmod = os.fchmod

        open_error = OSError("injected output open")

        def fail_output_open(
            path: object,
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            if path == "open.bin" and flags & os.O_CREAT:
                raise open_error
            return real_open(path, flags, mode, dir_fd=dir_fd)  # type: ignore[arg-type]

        with patch.object(paths_module.os, "open", side_effect=fail_output_open):
            with self.assertRaises(OSError) as caught:
                open_output_leaf(self.run, "open/a/open.bin")
        self.assertIs(open_error, caught.exception)
        self.assertFalse((self.run / "open").exists())

        chmod_error = OSError("injected output chmod")

        def fail_output_chmod(fd: int, mode: int) -> None:
            if mode == 0o640:
                raise chmod_error
            real_fchmod(fd, mode)

        with patch.object(paths_module.os, "fchmod", side_effect=fail_output_chmod):
            with self.assertRaises(OSError) as caught:
                open_output_leaf(self.run, "chmod/a/chmod.bin", 0o640)
        self.assertIs(chmod_error, caught.exception)
        self.assertFalse((self.run / "chmod").exists())

        fdopen_error = OSError("injected output fdopen")
        with patch.object(paths_module.os, "fdopen", side_effect=fdopen_error):
            with self.assertRaises(OSError) as caught:
                open_output_leaf(self.run, "fdopen/a/fdopen.bin")
        self.assertIs(fdopen_error, caught.exception)
        self.assertFalse((self.run / "fdopen").exists())

        self.assertEqual(b"untouched-output-target", unrelated.read_bytes())
        current = unrelated.stat()
        self.assertEqual(unrelated_node, (current.st_dev, current.st_ino))

    def test_output_descriptor_value_error_is_preserved_after_cleanup(self) -> None:
        # Converting an internal descriptor-validation ValueError must make this fail.
        validation_error = ValueError("injected regular descriptor validation")
        with patch.object(paths_module, "_regular_descriptor", side_effect=validation_error):
            with self.assertRaises(ValueError) as caught:
                open_output_leaf(self.run, "validation/a/out.bin")
        self.assertIs(validation_error, caught.exception)
        self.assertFalse((self.run / "validation").exists())

    def test_output_cleanup_error_does_not_replace_primary_error(self) -> None:
        # Letting a cleanup exception replace or chain over the primary open failure must make this fail.
        real_open = os.open
        primary = OSError("primary output failure")

        def fail_output_open(
            path: object,
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            if path == "out.bin" and flags & os.O_CREAT:
                raise primary
            return real_open(path, flags, mode, dir_fd=dir_fd)  # type: ignore[arg-type]

        with (
            patch.object(paths_module.os, "open", side_effect=fail_output_open),
            patch.object(paths_module, "_remove_created", side_effect=OSError("cleanup failure")),
        ):
            with self.assertRaises(OSError) as caught:
                open_output_leaf(self.run, "cleanup/a/out.bin")
        self.assertIs(primary, caught.exception)
        self.assertIsNone(caught.exception.__context__)

    def test_mid_parent_creation_failure_removes_only_owned_parents(self) -> None:
        # Losing the created-parent ledger on a mid-traversal error must make this fail.
        existing = self.run / "existing"
        existing.mkdir()
        real_mkdir = os.mkdir

        def fail_second(name: object, mode: int = 0o777, *, dir_fd: int | None = None) -> None:
            if name == "second":
                raise OSError("injected parent failure")
            real_mkdir(name, mode, dir_fd=dir_fd)

        with patch.object(paths_module.os, "mkdir", side_effect=fail_second):
            with self.assertRaises(ValueError):
                open_output_leaf(self.run, "existing/first/second/out.bin")
        self.assertTrue(existing.is_dir())
        self.assertFalse((existing / "first").exists())

    def test_output_component_substitution_fails_without_touching_target(self) -> None:
        # Following a substituted newly-created output parent must make this fail.
        outside = self.root / "outside-output"
        outside.mkdir()
        marker = outside / "marker"
        marker.write_bytes(b"untouched")
        swapped = False

        def swap(name: str) -> None:
            nonlocal swapped
            if name == "new-parent" and not swapped and (self.run / "new-parent").exists():
                swapped = True
                (self.run / "new-parent").rename(self.root / "moved-output-parent")
                (self.run / "new-parent").symlink_to(outside, target_is_directory=True)

        paths_module._COMPONENT_SWAP_HOOK = swap
        with self.assertRaises(ValueError):
            open_output_leaf(self.run, "new-parent/out.bin")
        self.assertEqual(b"untouched", marker.read_bytes())
        self.assertFalse((outside / "out.bin").exists())


if __name__ == "__main__":
    unittest.main()
