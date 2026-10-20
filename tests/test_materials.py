"""Offline material-routing and original-byte regressions."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from test_github_archive import FakeGitHub, archive_module

ROOT = Path(__file__).resolve().parents[1] / "plugins/organize-knowledge/skills"
sys.path.insert(0, str(ROOT / "obsidian-concept-notes/scripts"))
sys.modules["archive_github_notes"] = archive_module
import archive_github_assets as assets

spec = importlib.util.spec_from_file_location("inspect_material", ROOT / "study-chat-notes/scripts/inspect_material.py")
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)


class Materials(unittest.TestCase):
    def test_knowledge_route(self):
        item = {"filename": "note.md", "classification": {
            "kind": "knowledge", "name": "physics", "course_status": "no_match"}}
        self.assertTrue(archive_module.resolve_note_paths([item])[0]["path"].endswith("/physics/note.md"))

    def test_reading_route(self):
        item = {"filename": "note.md", "classification": {
            "kind": "reading", "name": "science", "book": "Book A",
            "book_status": "verified", "course_status": "no_match"}}
        self.assertTrue(archive_module.resolve_note_paths([item])[0]["path"].endswith("/science/Book A/note.md"))
        item["classification"]["book_status"] = "unknown"
        with self.assertRaises(archive_module.ArchiveError):
            archive_module.resolve_note_paths([item])

    def test_course_isolation(self):
        item = {"filename": "note.md", "classification": {
            "kind": "knowledge", "name": "physics", "course_status": "no_match",
            "existing_path": "\u8bfe\u7a0b/physics"}}
        with self.assertRaises(archive_module.ArchiveError):
            archive_module.resolve_note_paths([item])

    def test_original_and_rename_dedup(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "one.pdf"
            p.write_bytes(b"%PDF-1.4\r\noriginal\x00bytes")
            api = FakeGitHub()
            first = assets.archive_asset("example/private-notes", p, api)
            q = Path(folder) / "renamed.pdf"
            q.write_bytes(p.read_bytes())
            second = assets.archive_asset("example/private-notes", q, api)
            self.assertEqual(first["status"], "created_verified")
            self.assertEqual(second["status"], "duplicate_skipped")
            self.assertEqual(api.files[first["path"]], p.read_bytes())
            self.assertEqual(len(api.puts), 1)

    def test_public_and_large_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "one.png"
            p.write_bytes(b"image")
            api = FakeGitHub()
            api.private = False
            with self.assertRaises(archive_module.ArchiveError):
                assets.archive_asset("example/private-notes", p, api)
            p.write_bytes(b"x" * 900001)
            with self.assertRaises(archive_module.ArchiveError):
                assets.archive_asset("example/private-notes", p, api)
            self.assertFalse(api.puts)

    def test_corrupt_readback_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "one.pdf"
            p.write_bytes(b"%PDF-1.4\n")
            api = FakeGitHub()
            api.corrupt_readback = True
            with self.assertRaises(archive_module.ArchiveError):
                assets.archive_asset("example/private-notes", p, api)

    def test_inspection_does_not_claim_ocr(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "scan.png"
            p.write_bytes(b"synthetic")
            result = inspector.inspect(p)
            self.assertEqual(result["status"], "needs_visual_review")
            self.assertEqual(len(result["sha256"]), 64)

    def test_invalid_pdf(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "bad.pdf"
            p.write_bytes(b"not PDF")
            with self.assertRaises(ValueError):
                inspector.inspect(p)
