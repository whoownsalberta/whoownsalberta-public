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

    def test_wiki_v1_with_open_data_exports(self):
        (self.site / "data").mkdir()
        data_files = {
            "data/wiki.json": '{"profile":"wiki-v1","mode":"public","entries":[]}\n',
            "data/entries.csv": "id,title\nexample-entry,Entry\n",
            "data/sources.csv": "id,title\nexample-source,Source\n",
        }
        for rel, content in data_files.items():
            path = self.site / rel
            path.write_text(content, encoding="utf-8")
            self.manifest["output_digests"][rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.save()
        verify_site(self.site)

        # Disallowed file inside data/ is rejected
        (self.site / "data/private.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unlisted public file"):
            verify_site(self.site)
        (self.site / "data/private.json").unlink()

        # Preview marker inside CSV export is rejected
        bad_csv = self.site / "data/entries.csv"
        bad_csv.write_text("PRIVATE PREVIEW — NOT FOR PUBLICATION\n", encoding="utf-8")
        self.manifest["output_digests"]["data/entries.csv"] = hashlib.sha256(bad_csv.read_bytes()).hexdigest()
        self.save()
        with self.assertRaisesRegex(ValueError, "forbidden preview/synthetic marker"):
            verify_site(self.site)

    def test_wiki_v1_with_story_first_articles(self):
        articles_dir = self.site / "articles"
        articles_dir.mkdir()
        # Empty articles/ directory is rejected
        with self.assertRaisesRegex(ValueError, "unexpected empty directory"):
            verify_site(self.site)

        art_path = articles_dir / "example-feature.html"
        art_path.write_text("<article><h1>Investigation</h1></article>", encoding="utf-8")
        self.manifest["output_digests"]["articles/example-feature.html"] = hashlib.sha256(
            art_path.read_bytes()
        ).hexdigest()
        self.save()
        verify_site(self.site)

        # Non-HTML file inside articles/ is rejected
        (articles_dir / "draft.md").write_text("# Private draft", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unlisted public file"):
            verify_site(self.site)
        (articles_dir / "draft.md").unlink()

        # Preview marker inside article HTML is rejected
        art_path.write_text("<div>PRIVATE PREVIEW — NOT FOR PUBLICATION</div>", encoding="utf-8")
        self.manifest["output_digests"]["articles/example-feature.html"] = hashlib.sha256(
            art_path.read_bytes()
        ).hexdigest()
        self.save()
        with self.assertRaisesRegex(ValueError, "forbidden preview/synthetic marker"):
            verify_site(self.site)

    def test_wiki_v1_with_og_card_and_share_kits(self):
        og_path = self.site / "og-card.jpg"
        og_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 16)
        self.manifest["output_digests"]["og-card.jpg"] = hashlib.sha256(og_path.read_bytes()).hexdigest()

        (self.site / "share/assets").mkdir(parents=True)
        kit_html = self.site / "share/example-kit.html"
        kit_html.write_text("<h1>Share Kit</h1>", encoding="utf-8")
        panel_png = self.site / "share/assets/01-panel.png"
        panel_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
        self.manifest["output_digests"]["share/example-kit.html"] = hashlib.sha256(kit_html.read_bytes()).hexdigest()
        self.manifest["output_digests"]["share/assets/01-panel.png"] = hashlib.sha256(panel_png.read_bytes()).hexdigest()
        self.save()
        verify_site(self.site)

        # Fake non-JPEG og-card.jpg is rejected
        og_path.write_bytes(b"NOT_A_JPEG")
        self.manifest["output_digests"]["og-card.jpg"] = hashlib.sha256(b"NOT_A_JPEG").hexdigest()
        self.save()
        with self.assertRaisesRegex(ValueError, "invalid JPEG image"):
            verify_site(self.site)

        # Restore og-card.jpg, test fake non-PNG share asset is rejected
        og_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 16)
        self.manifest["output_digests"]["og-card.jpg"] = hashlib.sha256(og_path.read_bytes()).hexdigest()
        panel_png.write_bytes(b"NOT_A_PNG")
        self.manifest["output_digests"]["share/assets/01-panel.png"] = hashlib.sha256(b"NOT_A_PNG").hexdigest()
        self.save()
        with self.assertRaisesRegex(ValueError, "invalid PNG image"):
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


class WikiV1MultiTopicSiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.site = Path(self.temp.name) / "site"
        for sub in ("articles", "topics", "entries", "sources", "data", "share/assets"):
            (self.site / sub).mkdir(parents=True)
        files = {
            "index.html": "<h1>Investigations &amp; Research Wiki</h1>",
            "search.html": "<h1>Search</h1>",
            "style.css": "body { color: #111; }",
            "og-card.jpg": b"\xff\xd8\xff\xe0" + b"\x00" * 16,
            "articles/alpha-story.html": "<article><h1>Alpha</h1></article>",
            "articles/beta-story.html": "<article><h1>Beta</h1></article>",
            "topics/alpha-topic.html": "<h1>Alpha Topic</h1>",
            "topics/beta-topic.html": "<h1>Beta Topic</h1>",
            "entries/alpha-entry.html": "<h1>Alpha Entry</h1>",
            "entries/beta-entry.html": "<h1>Beta Entry</h1>",
            "sources/alpha-source.html": "<h1>Alpha Source</h1>",
            "sources/beta-source.html": "<h1>Beta Source</h1>",
            "share/alpha-kit.html": "<h1>Alpha Share Kit</h1>",
            "share/assets/01-alpha.png": b"\x89PNG\r\n\x1a\n" + b"\x00" * 16,
            "data/wiki.json": '{"profile":"wiki-v1-site","mode":"public","entries":[]}\n',
            "data/entries.csv": "id,title\nalpha-entry,Alpha Entry\n",
            "data/sources.csv": "id,title\nalpha-source,Alpha Source\n",
        }
        output_digests = {}
        for rel, content in files.items():
            path = self.site / rel
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content, encoding="utf-8")
            output_digests[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.manifest = {
            "profile": "wiki-v1-site",
            "mode": "public",
            "scopes": [
                {"scope_id": "alpha-scope", "factual_digest": SHA, "publication_digest": SHA},
                {"scope_id": "beta-scope", "factual_digest": SHA, "publication_digest": SHA},
            ],
            "renderer_digest": SHA,
            "decision_digests": {
                "factual:alpha-scope": SHA,
                "publication:alpha-scope": SHA,
                "factual:beta-scope": SHA,
                "publication:beta-scope": SHA,
                "renderer:wiki-v1-renderer": SHA,
            },
            "output_digests": output_digests,
        }
        self.save()

    def save(self):
        (self.site / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_valid_wiki_v1_site_artifact(self):
        verify_site(self.site)

    def test_single_scope_in_site_profile_is_rejected(self):
        self.manifest["scopes"] = [self.manifest["scopes"][0]]
        del self.manifest["decision_digests"]["factual:beta-scope"]
        del self.manifest["decision_digests"]["publication:beta-scope"]
        self.save()
        with self.assertRaisesRegex(ValueError, "requires at least 2 scopes"):
            verify_site(self.site)

    def test_unsorted_or_duplicate_scopes_are_rejected(self):
        self.manifest["scopes"] = list(reversed(self.manifest["scopes"]))
        self.save()
        with self.assertRaisesRegex(ValueError, "sorted unique scope_ids"):
            verify_site(self.site)

    def test_missing_scope_decision_is_rejected(self):
        del self.manifest["decision_digests"]["publication:beta-scope"]
        self.save()
        with self.assertRaisesRegex(ValueError, "exact slice and renderer keys"):
            verify_site(self.site)

    def test_preview_mode_in_site_profile_is_rejected(self):
        self.manifest["mode"] = "preview"
        self.save()
        with self.assertRaisesRegex(ValueError, "non-public mode"):
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
