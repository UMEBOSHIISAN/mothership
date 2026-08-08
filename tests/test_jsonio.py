from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from orchestration.lib.canonical import (
    canonical_json_bytes,
    canonical_json_sha256,
    sha256_bytes,
    sha256_file,
)
from orchestration.lib.errors import ContractError
from orchestration.lib.jsonio import load_strict, loads_strict


class StrictJsonTestCase(unittest.TestCase):
    def test_strict_decoder_accepts_utf8_json_without_losing_unicode(self) -> None:
        self.assertEqual(
            {"message": "梅干し", "value": 1},
            loads_strict(b'{"message":"\xe6\xa2\x85\xe5\xb9\xb2\xe3\x81\x97","value":1}'),
        )
        self.assertEqual([True, None, 1.0], loads_strict("[true,null,1.0]"))

    def test_strict_decoder_rejects_duplicate_invalid_nonfinite_and_wrong_inputs(self) -> None:
        invalid_values = (
            b'{"value":1,"value":2}',
            b'{"value":"\xff"}',
            b'{"value":NaN}',
            b'{"value":Infinity}',
            b'{"value":-Infinity}',
            bytearray(b"{}"),
        )
        for raw in invalid_values:
            with self.subTest(raw=raw):
                with self.assertRaises(ContractError):
                    loads_strict(raw)  # type: ignore[arg-type]

    def test_canonical_and_byte_hash_apis_are_exact_and_reject_invalid_values(self) -> None:
        expected = b'{"a":"\xe6\xa2\x85","nested":{"a":1,"z":2},"z":3}'
        value = {"z": 3, "nested": {"z": 2, "a": 1}, "a": "梅"}
        self.assertEqual(expected, canonical_json_bytes(value))
        self.assertEqual(hashlib.sha256(expected).hexdigest(), canonical_json_sha256(value))
        self.assertEqual(hashlib.sha256(expected).hexdigest(), sha256_bytes(expected))
        for invalid in ({"value": float("nan")}, {"value": "\ud800"}, object()):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ContractError):
                    canonical_json_bytes(invalid)
        with self.assertRaises(ContractError):
            sha256_bytes(bytearray(expected))  # type: ignore[arg-type]

    def test_file_apis_stream_regular_files_without_path_read_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = "x" * 200_000
            raw = ('"' + value + '"').encode("utf-8")
            path = root / "data.json"
            path.write_bytes(raw)
            with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("unsafe boundary")):
                self.assertEqual(value, load_strict(path))
                self.assertEqual(hashlib.sha256(raw).hexdigest(), sha256_file(path))

    def test_file_apis_reject_strings_symlinks_directories_and_special_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.json"
            target.write_bytes(b"{}")
            link = root / "link.json"
            link.symlink_to(target)
            fifo = root / "input.fifo"
            os.mkfifo(fifo)
            for function in (load_strict, sha256_file):
                for label, path in (
                    ("string", str(target)),
                    ("symlink", link),
                    ("directory", root),
                    ("fifo", fifo),
                ):
                    with self.subTest(function=function.__name__, label=label):
                        with self.assertRaises(ContractError):
                            function(path)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
