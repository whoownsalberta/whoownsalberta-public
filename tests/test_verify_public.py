"""Boundary tests use fictional temporary files only."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from verify_public import verify_site

SHA = "0" * 64


class WikiV1SiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.site = Path(self.temp.name) / "site"
        for sub in ("topics", "entries", "sources"):
            (self.site / sub).mkdir(parents=True)
        files = {
            "index.html": "<h1>Research wiki</h1>",
            "search.html": "<h1>Search</h1>",
            "style.css": "body { color: #111; }",
            "topics/example-topic.html": "<h1>Topic</h1>",
            "entries/example-entry.html": "<h1>Entry</h1>",
            "sources/example-source.html": "<h1>Source</h1>",
        }
        output_digests = {}
        for rel, content in files.items():
            path = self.site / rel
            path.write_text(content, encoding="utf-8")
            output_digests[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.manifest = {
            "profile": "wiki-v1",
            "mode": "public",
            "scope_id": "example-scope",
            "factual_digest": SHA,
            "publication_digest": SHA,
            "renderer_digest": SHA,
            "decision_digests": {
                "factual:example-scope": SHA,
                "publication:example-scope": SHA,
                "renderer:wiki-v1-renderer": SHA,
            },
            "output_digests": output_digests,
        }
        self.save()

    def save(self):
        (self.site / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_valid_wiki_v1_artifact(self):
        verify_site(self.site)

    def test_preview_mode_is_rejected(self):
        self.manifest["mode"] = "preview"
        self.save()
        with self.assertRaisesRegex(ValueError, "non-public mode"):
            verify_site(self.site)

    def test_preview_banner_text_is_rejected(self):
        path = self.site / "index.html"
        path.write_text("<div>PRIVATE PREVIEW — NOT FOR PUBLICATION</div>", encoding="utf-8")
        self.manifest["output_digests"]["index.html"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.save()
        with self.assertRaisesRegex(ValueError, "forbidden preview/synthetic marker"):
            verify_site(self.site)

    def test_changed_wiki_output_is_rejected(self):
        (self.site / "topics/example-topic.html").write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            verify_site(self.site)

    def test_extra_private_or_article_file_is_rejected(self):
        (self.site / "private.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unlisted public file"):
            verify_site(self.site)

    def test_unexpected_empty_directory_is_rejected(self):
        (self.site / "rogue").mkdir()
        with self.assertRaisesRegex(ValueError, "unexpected directory"):
            verify_site(self.site)

    def test_private_decision_key_is_rejected(self):
        self.manifest["decision_digests"]["factual:research/private.json#clm-1"] = SHA
        self.save()
        with self.assertRaisesRegex(ValueError, "exact slice and renderer keys"):
            verify_site(self.site)

    def test_missing_renderer_decision_is_rejected(self):
        del self.manifest["decision_digests"]["renderer:wiki-v1-renderer"]
        self.save()
        with self.assertRaisesRegex(ValueError, "exact slice and renderer keys"):
            verify_site(self.site)

    def test_duplicate_manifest_key_is_rejected(self):
        path = self.site / "manifest.json"
        path.write_text(
            path.read_text(encoding="utf-8").replace('"profile":', '"profile":"wiki-v1", "profile":'),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            verify_site(self.site)

    def test_symlink_is_rejected(self):
        (self.site / "topics/link.html").symlink_to(self.site / "index.html")
        with self.assertRaisesRegex(ValueError, "symlink"):
            verify_site(self.site)


class VerifyPublicV1Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.site = Path(self.temp.name) / "site"
        self.site.mkdir()
        (self.site / "index.html").write_text("<h1>Fictional</h1>", encoding="utf-8")
        self.manifest = {
            "profile": "public-v1",
            "input_digests": {"fictional-claim": SHA, "renderer": SHA},
            "selection_digest": SHA,
            "review_digests": {"fictional-claim": SHA},
            "output_digests": {
                "index.html": hashlib.sha256((self.site / "index.html").read_bytes()).hexdigest()
            },
        }
        self.save()

    def save(self):
        (self.site / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_matching_generated_files(self):
        verify_site(self.site)

    def test_missing_review_digest_is_rejected(self):
        self.manifest["review_digests"] = {"other": SHA}
        self.save()
        with self.assertRaisesRegex(ValueError, "input and review IDs differ"):
            verify_site(self.site)


class HoldingPageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.site = Path(self.temp.name) / "site"
        self.site.mkdir()
        body = b"<!doctype html><title>Fictional Holding</title>\n"
        self.holding_sha = hashlib.sha256(body).hexdigest()
        (self.site / "index.html").write_bytes(body)
        self.manifest = {
            "profile": "holding-v1",
            "output_digests": {"index.html": self.holding_sha},
        }
        self.save()

    def save(self):
        (self.site / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_exact_holding_page(self):
        with patch("verify_public.HOLDING_SHA256", self.holding_sha):
            verify_site(self.site)

    def test_changed_holding_page_is_rejected(self):
        (self.site / "index.html").write_text("changed", encoding="utf-8")
        with patch("verify_public.HOLDING_SHA256", self.holding_sha):
            with self.assertRaisesRegex(ValueError, "holding page: digest mismatch"):
                verify_site(self.site)

    def test_holding_page_cannot_contain_article(self):
        articles = self.site / "articles"
        articles.mkdir()
        (articles / "draft.html").write_text("draft", encoding="utf-8")
        with patch("verify_public.HOLDING_SHA256", self.holding_sha):
            with self.assertRaisesRegex(ValueError, "holding site: unexpected files"):
                verify_site(self.site)


if __name__ == "__main__":
    unittest.main()
