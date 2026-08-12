from __future__ import annotations

import hashlib
from importlib import resources
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock


CHECKS = {
    "executor_example": "passed",
    "golden_path": "passed",
    "inventory": "passed",
    "protocol_registry": "passed",
    "schema_digests": "passed",
}
EXPECTED = {
    "schema_version": "mothership.verify.v1",
    "status": "passed",
    "version": "0.2.1",
    "checks": CHECKS,
    "authority_effect": False,
    "execution_effect": False,
}


class VerifyTests(unittest.TestCase):
    def test_verified_installation_returns_one_closed_result(self) -> None:
        from mothership.verify import verify_installation

        self.assertEqual(EXPECTED, verify_installation())

    def test_inventory_is_complete_sorted_and_self_excluding(self) -> None:
        root = resources.files("mothership.resources")
        inventory = json.loads(root.joinpath("inventory.json").read_text("utf-8"))
        self.assertEqual({"schema_version", "resources"}, set(inventory))
        self.assertEqual("mothership.inventory.v1", inventory["schema_version"])
        paths = [entry["path"] for entry in inventory["resources"]]
        self.assertEqual(sorted(paths), paths)
        self.assertEqual(len(paths), len(set(paths)))
        self.assertNotIn("inventory.json", paths)
        for entry in inventory["resources"]:
            raw = root.joinpath(entry["path"]).read_bytes()
            with self.subTest(path=entry["path"]):
                self.assertEqual({"path", "sha256", "size"}, set(entry))
                self.assertEqual(len(raw), entry["size"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), entry["sha256"])

    def _copy_resources(self, destination: Path) -> Path:
        source = Path(str(resources.files("mothership.resources")))
        target = destination / "resources"
        shutil.copytree(source, target)
        return target

    def _rewrite_inventory_entry(self, root: Path, relative_path: str) -> None:
        inventory_path = root / "inventory.json"
        inventory = json.loads(inventory_path.read_text("utf-8"))
        raw = (root / relative_path).read_bytes()
        for entry in inventory["resources"]:
            if entry["path"] == relative_path:
                entry["size"] = len(raw)
                entry["sha256"] = hashlib.sha256(raw).hexdigest()
                break
        inventory_path.write_text(
            json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _verify_copy(self, root: Path) -> dict[str, object]:
        from mothership.verify import verify_installation

        with mock.patch("importlib.resources.files", return_value=root):
            return verify_installation()

    def test_each_resource_class_detects_byte_tampering(self) -> None:
        targets = (
            "protocols/registry.json",
            "protocols/schemas/router-manifest.1.0.schema.json",
            "golden-path/03-router-manifest.json",
            "config/executors.json",
        )
        for relative_path in targets:
            with self.subTest(relative_path=relative_path), tempfile.TemporaryDirectory() as directory:
                root = self._copy_resources(Path(directory))
                path = root / relative_path
                path.write_bytes(path.read_bytes() + b" ")
                result = self._verify_copy(root)
                self.assertEqual("failed", result["status"])
                self.assertEqual(["inventory_digest_mismatch"], result["errors"])
                serialized = json.dumps(result)
                self.assertNotIn(str(root), serialized)

    def test_inventory_rejects_missing_extra_and_duplicate_entries(self) -> None:
        mutations = ("missing", "extra", "duplicate")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = self._copy_resources(Path(directory))
                inventory_path = root / "inventory.json"
                inventory = json.loads(inventory_path.read_text("utf-8"))
                if mutation == "missing":
                    inventory["resources"].pop()
                elif mutation == "duplicate":
                    inventory["resources"].append(dict(inventory["resources"][0]))
                else:
                    (root / "extra.json").write_text("{}\n", encoding="utf-8")
                inventory_path.write_text(json.dumps(inventory) + "\n", encoding="utf-8")
                result = self._verify_copy(root)
                self.assertEqual("failed", result["status"])
                self.assertEqual(["inventory_shape_mismatch"], result["errors"])

    def test_inventory_rejects_missing_or_extra_jsonl_resources(self) -> None:
        """Catches an inventory scan that omits packaged JSONL evidence."""

        for mutation in ("missing", "extra"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = self._copy_resources(Path(directory))
                if mutation == "missing":
                    (root / "flight/safe-run/events.jsonl").unlink()
                else:
                    (root / "flight/safe-run/extra.jsonl").write_bytes(b"{}\n")

                result = self._verify_copy(root)

                self.assertEqual("failed", result["status"])
                self.assertEqual(["inventory_shape_mismatch"], result["errors"])

    def test_inventory_rejects_changed_jsonl_resource_bytes(self) -> None:
        """Catches digest validation that checks JSON but not JSONL resources."""

        with tempfile.TemporaryDirectory() as directory:
            root = self._copy_resources(Path(directory))
            path = root / "flight/safe-run/events.jsonl"
            path.write_bytes(path.read_bytes() + b" ")

            result = self._verify_copy(root)

        self.assertEqual("failed", result["status"])
        self.assertEqual(["inventory_digest_mismatch"], result["errors"])

    def test_semantically_active_executor_snapshot_fails_after_rehash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._copy_resources(Path(directory))
            relative_path = "config/executors.json"
            path = root / relative_path
            document = json.loads(path.read_text("utf-8"))
            document["codex-cli"]["state"] = "ready"
            path.write_text(json.dumps(document) + "\n", encoding="utf-8")
            self._rewrite_inventory_entry(root, relative_path)
            result = self._verify_copy(root)
        self.assertEqual("failed", result["status"])
        self.assertEqual(["executor_example_invalid"], result["errors"])


if __name__ == "__main__":
    unittest.main()
