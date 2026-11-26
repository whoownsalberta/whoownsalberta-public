"""Boundary tests use fictional temporary files only."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from verify_public import verify_site

SHA = "0" * 64


class VerifySiteTests(unittest.TestCase):
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

    def test_changed_output_is_rejected(self):
        (self.site / "index.html").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            verify_site(self.site)

    def test_extra_file_is_rejected(self):
        (self.site / "private.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unlisted public file"):
            verify_site(self.site)

    def test_missing_review_digest_is_rejected(self):
        self.manifest["review_digests"] = {"other": SHA}
        self.save()
        with self.assertRaisesRegex(ValueError, "input and review IDs differ"):
            verify_site(self.site)

    def test_duplicate_manifest_key_is_rejected(self):
        path = self.site / "manifest.json"
        path.write_text(path.read_text(encoding="utf-8").replace('"profile":', '"profile":"public-v1", "profile":'), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            verify_site(self.site)

    def test_symlink_is_rejected(self):
        (self.site / "articles").symlink_to(self.site, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            verify_site(self.site)


class HoldingPageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.site = Path(self.temp.name) / "site"
        self.site.mkdir()
        source = Path(__file__).resolve().parents[1] / "site" / "index.html"
        (self.site / "index.html").write_bytes(source.read_bytes())
        self.manifest = {
            "profile": "holding-v1",
            "output_digests": {"index.html": hashlib.sha256(source.read_bytes()).hexdigest()},
        }
        self.save()

    def save(self):
        (self.site / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_exact_holding_page(self):
        verify_site(self.site)

    def test_changed_holding_page_is_rejected(self):
        (self.site / "index.html").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "holding page: digest mismatch"):
            verify_site(self.site)

    def test_holding_page_cannot_contain_article(self):
        articles = self.site / "articles"
        articles.mkdir()
        (articles / "draft.html").write_text("draft", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "holding site: unexpected files"):
            verify_site(self.site)


class WikiSiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.site = Path(self.temp.name) / "site"
        self.site.mkdir()
        for name in ("index.html", "search.html", "topics/topic-example.html",
                     "entries/entry-example.html", "sources/source-example.html"):
            path = self.site / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"<h1>Fictional {name}</h1>", encoding="utf-8")
        self.manifest = {
            "profile": "wiki-v1", "scope_digest": SHA, "inventory_digest": SHA,
            "renderer_digest": SHA, "factual_review_digest": SHA,
            "decision_digests": {"scope": SHA, "source:source-example": SHA,
                                 "entry:entry-example": SHA, "page:topic-example": SHA},
            "output_digests": {str(path.relative_to(self.site)): hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in self.site.rglob("*.html")},
        }
        self.save()

    def save(self):
        (self.site / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_matching_wiki_artifact(self):
        verify_site(self.site)

    def test_missing_search_is_rejected(self):
        (self.site / "search.html").unlink()
        self.manifest["output_digests"].pop("search.html")
        self.save()
        with self.assertRaisesRegex(ValueError, "unexpected output paths"):
            verify_site(self.site)

    def test_article_in_wiki_manifest_is_rejected(self):
        path = self.site / "articles/other.html"
        path.parent.mkdir()
        path.write_text("fictional")
        self.manifest["output_digests"]["articles/other.html"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.save()
        with self.assertRaisesRegex(ValueError, "unexpected output paths"):
            verify_site(self.site)

    def test_private_file_and_stale_digest_are_rejected(self):
        (self.site / "private.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "unlisted public file"):
            verify_site(self.site)
        (self.site / "private.json").unlink()
        (self.site / "entries/entry-example.html").write_text("changed")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            verify_site(self.site)

    def test_missing_display_decision_digest_is_rejected(self):
        self.manifest["decision_digests"].pop("entry:entry-example")
        self.save()
        with self.assertRaisesRegex(ValueError, "decision keys do not match"):
            verify_site(self.site)

    def test_missing_source_and_extra_entry_decisions_are_rejected(self):
        self.manifest["decision_digests"].pop("source:source-example")
        self.save()
        with self.assertRaisesRegex(ValueError, "decision keys do not match"):
            verify_site(self.site)
        self.manifest["decision_digests"]["source:source-example"] = SHA
        extra = self.site / "entries/entry-extra.html"
        extra.write_text("fictional")
        self.manifest["output_digests"]["entries/entry-extra.html"] = hashlib.sha256(extra.read_bytes()).hexdigest()
        self.save()
        with self.assertRaisesRegex(ValueError, "decision keys do not match"):
            verify_site(self.site)

    def test_unknown_and_duplicate_scope_decision_keys_are_rejected(self):
        self.manifest["decision_digests"]["unknown:entry-example"] = SHA
        self.save()
        with self.assertRaisesRegex(ValueError, "decision keys do not match"):
            verify_site(self.site)
        self.manifest["decision_digests"].pop("unknown:entry-example")
        self.manifest["decision_digests"]["scope:another"] = SHA
        self.save()
        with self.assertRaisesRegex(ValueError, "decision keys do not match"):
            verify_site(self.site)

    def test_private_factual_target_key_is_rejected(self):
        self.manifest["decision_digests"]["factual:research/private/secret.json#person"] = SHA
        self.save()
        with self.assertRaisesRegex(ValueError, "decision keys do not match"):
            verify_site(self.site)


if __name__ == "__main__":
    unittest.main()
