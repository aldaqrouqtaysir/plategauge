"""Synthetic-only release tests: no model execution, hardware, or network."""

from __future__ import annotations

import hashlib
import io
import json
import stat
import subprocess
import tempfile
import time
import unittest
import urllib.request
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import verify_release as gate


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(payload, indent=2) + "\n").encode())


class ReleaseFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        self.inventory = self.root / "inventory.json"
        self.model = b"synthetic-not-a-model"
        self.sha_patch = patch.object(gate, "MODEL_SHA256", digest(self.model))
        self.size_patch = patch.object(gate, "MODEL_SIZE", len(self.model))
        self.sha_patch.start()
        self.size_patch.start()
        self.addCleanup(self.sha_patch.stop)
        self.addCleanup(self.size_patch.stop)
        names = gate.REQUIRED_FILES | gate.CAMERA_FILES | {"assets/index-a.js", "assets/index-a.css"}
        names |= {
            f"examples/synthetic-{index:03}.txt"
            for index in range(gate.CAMERA_FILE_COUNT - len(names))
        }
        for name in names:
            path = self.bundle / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.model if name == "models/plategauge.onnx" else name.encode())
        gate.create_inventory(self.bundle, self.inventory)

    def payload(self) -> dict[str, Any]:
        return gate.read_json(self.inventory)

    def rollback_payload(self) -> dict[str, Any]:
        """Independent synthetic legacy profile, including its historical resource."""
        payload = self.payload()
        payload["appSourceCommit"] = gate.ROLLBACK_SOURCE_COMMIT
        names = gate.ROLLBACK_REQUIRED_FILES | {"assets/index-a.js", "assets/index-a.css"}
        names |= {
            f"examples/rollback-{index:03}.txt"
            for index in range(gate.ROLLBACK_FILE_COUNT - len(names))
        }
        payload["files"] = [
            {
                "path": name,
                "size": len(self.model if name == "models/plategauge.onnx" else name.encode()),
                "sha256": digest(self.model if name == "models/plategauge.onnx" else name.encode()),
            }
            for name in sorted(names)
        ]
        return payload


class InventoryTests(ReleaseFixture):
    def test_synthetic_inventory_and_bundle_roundtrip(self) -> None:
        result = gate.verify_bundle(self.inventory, self.bundle)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["inventorySha256"], digest(self.inventory.read_bytes()))
        self.assertEqual(result["fileCount"], len(self.payload()["files"]))

    def test_inventory_creation_is_not_approval_and_never_overwrites(self) -> None:
        output = self.root / "fresh.json"
        result = gate.create_inventory(self.bundle, output)
        self.assertEqual(result["status"], "inventoried-not-approved")
        original = output.read_bytes()
        with self.assertRaises(gate.VerificationError):
            gate.create_inventory(self.bundle, output)
        self.assertEqual(output.read_bytes(), original)

    def test_inventory_output_inside_bundle_is_blocked(self) -> None:
        with self.assertRaises(gate.VerificationError):
            gate.create_inventory(self.bundle, self.bundle / "manifest.json")
        self.assertFalse((self.bundle / "manifest.json").exists())

    def test_strict_json_rejects_duplicates_nonfinite_bom_and_nonobject(self) -> None:
        for raw in (
            b'{"a":1,"a":2}',
            b'{"a":{"x":1,"x":2}}',
            b'{"a":NaN}',
            b'{"a":Infinity}',
            b"[]",
            b"null",
            b"\xef\xbb\xbf{}",
            b"",
            b"\xff",
        ):
            with self.subTest(raw=raw), self.assertRaises(gate.VerificationError):
                gate._json_bytes(raw)

    def test_invalid_inventory_schema_is_blocked(self) -> None:
        mutations: list[dict[str, Any]] = [
            {"schemaVersion": True},
            {"schemaVersion": 2},
            {"unknown": 1},
            {"appSourceCommit": "f" * 40},
            {"files": []},
            {"files": {}},
        ]
        for mutation in mutations:
            payload = self.payload()
            payload.update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(gate.VerificationError):
                gate.validate_inventory(payload)

    def test_path_traversal_aliases_and_windows_devices_are_blocked(self) -> None:
        for name in (
            "../a",
            "/a",
            "a//b",
            "./a",
            "a/../b",
            "a\\b",
            "C:/a",
            "a%2fb",
            "a?b",
            "a#b",
            "a\nb",
            ".git/config",
            "a/.env",
            "a/CON.txt",
            "a/nul",
            "a/com1.js",
            "a/end.",
            "a/",
            "a b",
            "a\x00b",
        ):
            payload = self.payload()
            payload["files"][0]["path"] = name
            with self.subTest(name=name), self.assertRaises(gate.VerificationError):
                gate.validate_inventory(payload)

    def test_size_hash_entry_and_case_collision_validation(self) -> None:
        for value in (True, -1, 1.5, "10", 0, gate.MAX_FILE_BYTES + 1):
            payload = self.payload()
            payload["files"][0]["size"] = value
            with self.subTest(size=value), self.assertRaises(gate.VerificationError):
                gate.validate_inventory(payload)
        for mutation in ({"sha256": "A" * 64}, {"sha256": "1"}, {"extra": "x"}):
            payload = self.payload()
            payload["files"][0].update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(gate.VerificationError):
                gate.validate_inventory(payload)
        for collision in (self.payload()["files"][0]["path"], "ASSETS/INDEX-A.CSS"):
            payload = self.payload()
            payload["files"].append({"path": collision, "size": 1, "sha256": "a" * 64})
            payload["files"].sort(key=lambda entry: entry["path"])
            with self.subTest(collision=collision), self.assertRaises(gate.VerificationError):
                gate.validate_inventory(payload)

    def test_unsorted_missing_required_and_changed_model_rejected(self) -> None:
        payload = self.payload()
        payload["files"].reverse()
        with self.assertRaises(gate.VerificationError):
            gate.validate_inventory(payload)
        for name in ("index.html", "legal/CAMERA_PRIVACY_NOTICE.md", "models/plategauge.onnx"):
            payload = self.payload()
            payload["files"] = [entry for entry in payload["files"] if entry["path"] != name]
            with self.subTest(name=name), self.assertRaises(gate.VerificationError):
                gate.validate_inventory(payload)
        payload = self.payload()
        next(entry for entry in payload["files"] if entry["path"] == "models/plategauge.onnx")[
            "sha256"
        ] = "f" * 64
        with self.assertRaises(gate.VerificationError):
            gate.validate_inventory(payload)

    def test_file_count_and_total_budgets(self) -> None:
        payload = self.payload()
        with patch.object(gate, "MAX_FILES", 1), self.assertRaises(gate.VerificationError):
            gate.validate_inventory(payload)
        with patch.object(gate, "MAX_TOTAL_BYTES", 1), self.assertRaises(gate.VerificationError):
            gate.validate_inventory(payload)

    def test_extra_changed_and_missing_bundle_files(self) -> None:
        extra = self.bundle / "unexpected.txt"
        extra.write_text("extra", encoding="utf-8")
        with self.assertRaises(gate.VerificationError):
            gate.verify_bundle(self.inventory, self.bundle)
        extra.unlink()
        original = (self.bundle / "index.html").read_bytes()
        (self.bundle / "index.html").write_bytes(b"changed")
        with self.assertRaises(gate.VerificationError):
            gate.verify_bundle(self.inventory, self.bundle)
        (self.bundle / "index.html").write_bytes(original)
        (self.bundle / "index.html").unlink()
        with self.assertRaises(gate.VerificationError):
            gate.verify_bundle(self.inventory, self.bundle)

    def test_symlink_and_junction_paths_rejected_before_read(self) -> None:
        for method in ("is_symlink", "is_junction"):
            with (
                patch.object(Path, method, return_value=True),
                self.subTest(method=method),
                self.assertRaises(gate.VerificationError),
            ):
                gate.inventory_bundle(self.bundle)

    def test_known_rollback_profile_has_no_camera_notice_requirement(self) -> None:
        payload = self.rollback_payload()
        self.assertTrue(gate.validate_inventory(payload))

    def test_camera_profile_rejects_retired_file_even_at_exact_count(self) -> None:
        for name in ("legal/AI_ASSISTANCE_LOG.md", "legal/ai_assistance_log.md"):
            payload = self.payload()
            next(entry for entry in payload["files"] if entry["path"].startswith("examples/"))[
                "path"
            ] = name
            payload["files"].sort(key=lambda entry: entry["path"])
            with self.subTest(name=name), self.assertRaisesRegex(gate.VerificationError, "retired"):
                gate.validate_inventory(payload)

    def test_rollback_profile_still_requires_historical_resource(self) -> None:
        payload = self.rollback_payload()
        next(entry for entry in payload["files"] if entry["path"] in gate.RETIRED_CAMERA_FILES)[
            "path"
        ] = "examples/replacement.txt"
        payload["files"].sort(key=lambda entry: entry["path"])
        with self.assertRaisesRegex(gate.VerificationError, "missing required"):
            gate.validate_inventory(payload)

    def test_camera_and_rollback_exact_counts_cannot_be_mixed(self) -> None:
        for payload in (self.payload(), self.rollback_payload()):
            payload["files"].pop()
            with self.assertRaisesRegex(gate.VerificationError, "exact release profile"):
                gate.validate_inventory(payload)


class ArchiveTests(ReleaseFixture):
    def test_pack_is_deterministic_and_roundtrips_exact_bytes(self) -> None:
        a = self.root / "a.zip"
        b = self.root / "b.zip"
        first = gate.pack_bundle(self.inventory, self.bundle, a)
        second = gate.pack_bundle(self.inventory, self.bundle, b)
        self.assertEqual(first["archiveSha256"], second["archiveSha256"])
        self.assertEqual(a.read_bytes(), b.read_bytes())
        destination = self.root / "extracted"
        result = gate.extract_bundle(self.inventory, a, first["archiveSha256"], destination)
        self.assertEqual(result["status"], "verified")
        for entry in self.payload()["files"]:
            self.assertEqual(
                (destination / entry["path"]).read_bytes(),
                (self.bundle / entry["path"]).read_bytes(),
            )

    def test_pack_and_extract_refuse_overwrite(self) -> None:
        archive = self.root / "a.zip"
        result = gate.pack_bundle(self.inventory, self.bundle, archive)
        with self.assertRaises(gate.VerificationError):
            gate.pack_bundle(self.inventory, self.bundle, archive)
        with self.assertRaises(gate.VerificationError):
            gate.extract_bundle(self.inventory, archive, result["archiveSha256"], self.bundle)

    def test_wrong_archive_hash_and_bad_zip_create_no_destination(self) -> None:
        archive = self.root / "a.zip"
        gate.pack_bundle(self.inventory, self.bundle, archive)
        destination = self.root / "out"
        with self.assertRaises(gate.VerificationError):
            gate.extract_bundle(self.inventory, archive, "f" * 64, destination)
        self.assertFalse(destination.exists())
        archive.write_bytes(b"not zip")
        with self.assertRaises(gate.VerificationError):
            gate.extract_bundle(self.inventory, archive, digest(archive.read_bytes()), destination)
        self.assertFalse(destination.exists())

    def test_archive_trailer_and_directory_bomb_rejected_before_parse(self) -> None:
        archive = self.root / "a.zip"
        gate.pack_bundle(self.inventory, self.bundle, archive)
        original = archive.read_bytes()
        for raw in (original + b"trailing bytes", original[:-12] + b"\xff\xff" + original[-10:]):
            archive.write_bytes(raw)
            with self.assertRaises(gate.VerificationError):
                gate.extract_bundle(self.inventory, archive, digest(raw), self.root / "no-output")
            self.assertFalse((self.root / "no-output").exists())

    def make_archive(self, mutation: str) -> Path:
        path = self.root / f"{mutation}.zip"
        entries = self.payload()["files"]
        with zipfile.ZipFile(path, "w") as archive:
            for index, entry in enumerate(entries):
                name = entry["path"]
                if index == 0 and mutation == "traversal":
                    name = "../escape"
                elif index == 0 and mutation == "duplicate":
                    name = entries[1]["path"]
                elif index == 0 and mutation == "case":
                    name = name.upper()
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                if index == 0 and mutation == "link":
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                if index == 0 and mutation == "extra":
                    info.extra = b"\x01\x00\x00\x00"
                if index == 0 and mutation == "compressed":
                    info.compress_type = zipfile.ZIP_DEFLATED
                raw = (self.bundle / entry["path"]).read_bytes()
                if index == 0 and mutation == "changed":
                    raw = bytes([raw[0] ^ 1]) + raw[1:]
                archive.writestr(info, raw)
            if mutation == "unexpected":
                archive.writestr("extra.txt", "extra")
        return path

    def test_malicious_archive_members_rejected_without_partial_extraction(self) -> None:
        for mutation in (
            "traversal",
            "duplicate",
            "case",
            "link",
            "extra",
            "compressed",
            "changed",
            "unexpected",
        ):
            with self.subTest(mutation=mutation):
                archive = self.make_archive(mutation)
                destination = self.root / f"out-{mutation}"
                with self.assertRaises(gate.VerificationError):
                    gate.extract_bundle(
                        self.inventory, archive, digest(archive.read_bytes()), destination
                    )
                self.assertFalse(destination.exists())


class FakeResponse(io.BytesIO):
    def __init__(self, raw: bytes, url: str) -> None:
        super().__init__(raw)
        self.status = 200
        self.url = url
        self.headers: dict[str, str] = {"Content-Length": str(len(raw))}

    def geturl(self) -> str:
        return self.url


class LiveTests(ReleaseFixture):
    def opener(self, mutation: str = "") -> Any:
        bundle = self.bundle

        class Opener:
            def open(self, request: urllib.request.Request, timeout: int) -> FakeResponse:
                self_request = request.full_url
                if not self_request.startswith(gate.PUBLIC_URL):
                    raise AssertionError("External request")
                if request.get_method() != "GET" or request.data is not None or timeout != 20:
                    raise AssertionError("Wrong bounded read-only request")
                name = self_request[len(gate.PUBLIC_URL) :] or "index.html"
                raw = (bundle / name).read_bytes()
                result = FakeResponse(raw, self_request)
                if mutation == "redirect":
                    result.url = "https://evil.invalid/file"
                elif mutation == "status":
                    result.status = 404
                elif mutation == "length":
                    result.headers["Content-Length"] = "99999"
                elif mutation == "encoding":
                    result.headers["Content-Encoding"] = "gzip"
                elif mutation == "wrong":
                    result = FakeResponse(b"x" * len(raw), self_request)
                elif mutation == "oversize":
                    result = FakeResponse(raw + b"x", self_request)
                    result.headers = {}
                elif mutation == "truncated":
                    result = FakeResponse(raw[:-1], self_request)
                    result.headers = {}
                return result

        return Opener()

    def test_mock_live_exact_bytes_pass_without_network(self) -> None:
        with patch.object(urllib.request, "build_opener", return_value=self.opener()):
            self.assertEqual(
                gate.verify_live(self.inventory, gate.PUBLIC_URL)["status"], "verified"
            )

    def test_live_rejects_every_destination_override(self) -> None:
        for url in (
            gate.PUBLIC_URL.rstrip("/"),
            "http://aldaqrouqtaysir.github.io/plategauge/",
            "https://evil.invalid/",
            gate.PUBLIC_URL + "?x",
            gate.PUBLIC_URL + "camera/",
        ):
            with self.subTest(url=url), self.assertRaises(gate.VerificationError):
                gate.verify_live(self.inventory, url)

    def test_mock_live_rejects_redirect_metadata_size_and_content_drift(self) -> None:
        for mutation in (
            "redirect",
            "status",
            "length",
            "encoding",
            "wrong",
            "oversize",
            "truncated",
        ):
            with (
                self.subTest(mutation=mutation),
                patch.object(urllib.request, "build_opener", return_value=self.opener(mutation)),
                self.assertRaises(gate.VerificationError),
            ):
                gate.verify_live(self.inventory, gate.PUBLIC_URL)

    def test_redirect_handler_refuses_to_follow(self) -> None:
        with self.assertRaises(gate.VerificationError):
            gate._NoRedirect().redirect_request(
                None, None, 302, "Found", {}, "https://evil.invalid/"
            )

    def test_mock_live_total_deadline_is_enforced(self) -> None:
        with (
            patch.object(urllib.request, "build_opener", return_value=self.opener()),
            patch.object(time, "monotonic", side_effect=[0, 301]),
            self.assertRaisesRegex(gate.VerificationError, "time budget"),
        ):
            gate.verify_live(self.inventory, gate.PUBLIC_URL)


class ApprovalTests(ReleaseFixture):
    def setUp(self) -> None:
        super().setUp()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Synthetic test")
        self.git("config", "user.email", "synthetic@example.invalid")
        self.git("config", "core.autocrlf", "false")
        (self.repo / "README.md").write_bytes(b"synthetic base\n")
        (self.repo / "web").mkdir()
        (self.repo / "web/protected.txt").write_bytes(b"unchanged application\n")
        for path, (previous_guard, _) in gate.WORKFLOW_GUARDS.items():
            file = self.repo / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b"jobs:\n  synthetic-job:\n" + previous_guard + b"    runs-on: ubuntu-24.04\n")
        self.commit("base")
        self.base = self.git("rev-parse", "HEAD").strip()
        self.app_patch = patch.object(gate, "APP_SOURCE_COMMIT", self.base)
        self.app_patch.start()
        self.addCleanup(self.app_patch.stop)
        payload = self.payload()
        payload["appSourceCommit"] = self.base
        write_json(self.repo / gate.INVENTORY_PATH, payload)
        write_json(self.repo / gate.ROLLBACK_INVENTORY_PATH, self.rollback_payload())
        write_json(self.repo / gate.EVIDENCE_PATH, {"status": "synthetic-test-only"})
        self.commit("operations")
        self.operations = self.git("rev-parse", "HEAD").strip()

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args], check=True, capture_output=True, timeout=30
        ).stdout.decode()

    def commit(self, message: str) -> None:
        self.git("add", "--all")
        self.git("commit", "--quiet", "-m", message)

    def approval(self, **overrides: Any) -> dict[str, Any]:
        payload = {
            "schemaVersion": 1,
            "decision": "approved",
            "approvedBy": gate.APPROVER,
            "approvedAt": "2026-09-23T09:00:00Z",
            "scope": "experimental-camera-publication",
            "releaseTag": gate.RELEASE_TAG,
            "appSourceCommit": self.base,
            "operationsSourceCommit": self.operations,
            "publicUrl": gate.PUBLIC_URL,
            "inventorySha256": digest((self.repo / gate.INVENTORY_PATH).read_bytes()),
            "rollbackInventorySha256": digest(
                (self.repo / gate.ROLLBACK_INVENTORY_PATH).read_bytes()
            ),
            "verificationEvidenceSha256": digest((self.repo / gate.EVIDENCE_PATH).read_bytes()),
            "bundleArchiveSha256": "a" * 64,
            "rollbackArchiveSha256": "b" * 64,
        }
        payload.update(overrides)
        return payload

    def approve(self, **overrides: Any) -> None:
        write_json(self.repo / gate.APPROVAL_PATH, self.approval(**overrides))
        self.commit("synthetic approval fixture, not real authority")

    def verify(self) -> dict[str, Any]:
        return gate.verify_approval(self.repo, Path(gate.APPROVAL_PATH), gate.RELEASE_TAG)

    def test_synthetic_approval_child_identity_passes(self) -> None:
        self.approve()
        self.assertEqual(self.verify()["operationsSourceCommit"], self.operations)

    def test_workflow_tag_binding_is_required_when_requested(self) -> None:
        self.approve()
        with self.assertRaises(gate.VerificationError):
            gate.verify_approval(
                self.repo, Path(gate.APPROVAL_PATH), gate.RELEASE_TAG, require_tag=True
            )
        self.git("tag", gate.RELEASE_TAG, self.operations)
        with self.assertRaises(gate.VerificationError):
            gate.verify_approval(
                self.repo, Path(gate.APPROVAL_PATH), gate.RELEASE_TAG, require_tag=True
            )

    def test_existing_correct_tag_passes_without_mutation(self) -> None:
        self.approve()
        self.git("tag", "-a", gate.RELEASE_TAG, "-m", "Synthetic-only tag")
        before = self.git("rev-parse", f"refs/tags/{gate.RELEASE_TAG}")
        result = gate.verify_approval(
            self.repo, Path(gate.APPROVAL_PATH), gate.RELEASE_TAG, require_tag=True
        )
        self.assertEqual(result["status"], "verified")
        self.assertEqual(self.git("rev-parse", f"refs/tags/{gate.RELEASE_TAG}"), before)

    def test_no_approval_is_never_implicitly_authorized(self) -> None:
        with self.assertRaises(gate.VerificationError):
            self.verify()

    def test_wrong_schema_scope_tag_parent_and_evidence_hash_block(self) -> None:
        for key, value in (
            ("schemaVersion", True),
            ("scope", "Gate D"),
            ("decision", "pending"),
            ("approvedBy", "AI"),
            ("releaseTag", "v1.0.2"),
            ("operationsSourceCommit", "f" * 40),
            ("inventorySha256", "f" * 64),
            ("approvedAt", "2026-09-23"),
            ("bundleArchiveSha256", "Z" * 64),
            ("rollbackInventorySha256", "f" * 64),
        ):
            with self.subTest(key=key):
                write_json(self.repo / gate.APPROVAL_PATH, self.approval(**{key: value}))
                with self.assertRaises(gate.VerificationError):
                    self.verify()

    def test_dirty_checkout_and_extra_approval_child_changes_block(self) -> None:
        self.approve()
        (self.repo / "untracked.txt").write_text("not clean")
        with self.assertRaises(gate.VerificationError):
            self.verify()
        self.commit("extra file not authorized by approval")
        with self.assertRaises(gate.VerificationError):
            self.verify()

    def test_protected_source_change_cannot_hide_in_operations(self) -> None:
        (self.repo / "web/protected.txt").write_bytes(b"changed\n")
        self.commit("invalid protected change")
        self.operations = self.git("rev-parse", "HEAD").strip()
        self.approve()
        with self.assertRaisesRegex(gate.VerificationError, "protected"):
            self.verify()

    def test_reverted_protected_change_is_still_blocked(self) -> None:
        (self.repo / "web/protected.txt").write_bytes(b"changed\n")
        self.commit("invalid protected change")
        (self.repo / "web/protected.txt").write_bytes(b"unchanged application\n")
        self.commit("restore endpoint cannot hide history")
        self.operations = self.git("rev-parse", "HEAD").strip()
        self.approve()
        with self.assertRaisesRegex(gate.VerificationError, "history.*protected"):
            self.verify()

    def test_exact_historical_workflow_guards_are_allowed(self) -> None:
        for path, (previous_guard, next_guard) in gate.WORKFLOW_GUARDS.items():
            file = self.repo / path
            file.write_bytes(file.read_bytes().replace(previous_guard, next_guard))
        self.commit("only approved legacy workflow guards")
        self.operations = self.git("rev-parse", "HEAD").strip()
        self.approve()
        self.assertEqual(self.verify()["status"], "verified")

    def test_broader_historical_workflow_changes_are_blocked(self) -> None:
        file = self.repo / ".github/workflows/release-pages.yml"
        file.write_bytes(file.read_bytes() + b"# unauthorized extra change\n")
        self.commit("unapproved legacy workflow change")
        self.operations = self.git("rev-parse", "HEAD").strip()
        self.approve()
        with self.assertRaisesRegex(gate.VerificationError, "Historical workflow"):
            self.verify()

    def test_removing_historical_exclusions_instead_of_adding_r3_is_blocked(self) -> None:
        path = ".github/workflows/weekly-smoke.yml"
        previous_guard, _ = gate.WORKFLOW_GUARDS[path]
        file = self.repo / path
        file.write_bytes(file.read_bytes().replace(
            previous_guard,
            b"    if: ${{ vars.PLATEGAUGE_ACTIVE_PROFILE != 'camera-experimental-r3' }}\n",
        ))
        self.commit("forbidden loss of r1 and r2 routing")
        self.operations = self.git("rev-parse", "HEAD").strip()
        self.approve()
        with self.assertRaisesRegex(gate.VerificationError, "Historical workflow"):
            self.verify()

    def test_prefix_widening_of_release_exclusions_is_blocked(self) -> None:
        path = ".github/workflows/release-pages.yml"
        previous_guard, _ = gate.WORKFLOW_GUARDS[path]
        file = self.repo / path
        file.write_bytes(file.read_bytes().replace(
            previous_guard,
            b"    if: ${{ github.event_name != 'release' || !startsWith(github.event.release.tag_name, 'camera-') }}\n",
        ))
        self.commit("forbidden wildcard release routing")
        self.operations = self.git("rev-parse", "HEAD").strip()
        self.approve()
        with self.assertRaisesRegex(gate.VerificationError, "Historical workflow"):
            self.verify()

    def test_duplicate_guard_insertion_is_blocked(self) -> None:
        path = ".github/workflows/weekly-smoke.yml"
        previous_guard, next_guard = gate.WORKFLOW_GUARDS[path]
        file = self.repo / path
        file.write_bytes(file.read_bytes().replace(previous_guard, previous_guard + next_guard))
        self.commit("forbidden duplicate routing keys")
        self.operations = self.git("rev-parse", "HEAD").strip()
        self.approve()
        with self.assertRaisesRegex(gate.VerificationError, "Historical workflow"):
            self.verify()

    def test_r1_release_records_cannot_change_in_r3_operations(self) -> None:
        old_record = self.repo / "release/camera/approval.json"
        old_record.parent.mkdir(parents=True, exist_ok=True)
        old_record.write_bytes(b"synthetic unauthorized historical rewrite\n")
        self.commit("forbidden historical approval path change")
        self.operations = self.git("rev-parse", "HEAD").strip()
        self.approve()
        with self.assertRaisesRegex(gate.VerificationError, "protected"):
            self.verify()

    def test_r2_release_records_cannot_change_in_r3_operations(self) -> None:
        old_record = self.repo / "release/camera-r2/approval.json"
        old_record.parent.mkdir(parents=True, exist_ok=True)
        old_record.write_bytes(b"synthetic unauthorized historical rewrite\n")
        self.commit("forbidden r2 historical approval path change")
        self.operations = self.git("rev-parse", "HEAD").strip()
        self.approve()
        with self.assertRaisesRegex(gate.VerificationError, "protected"):
            self.verify()

    def test_noncanonical_approval_path_is_blocked(self) -> None:
        self.approve()
        with self.assertRaises(gate.VerificationError):
            gate.verify_approval(self.repo, self.root / "approval.json", gate.RELEASE_TAG)
        with self.assertRaises(gate.VerificationError):
            gate.verify_approval(self.repo, Path(gate.APPROVAL_PATH), "v1.0.2")


if __name__ == "__main__":
    unittest.main()
