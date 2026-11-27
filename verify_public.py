"""Verify the public repository boundary and generated artifact without secrets."""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ID = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")
ARTICLE = re.compile(r"articles/[a-z][a-z0-9]*(?:-[a-z0-9]+)*\.html\Z")
WIKI_FILE = re.compile(
    r"(?:index|search)\.html\Z|style\.css\Z|og-card\.jpg\Z|"
    r"data/(?:wiki\.json|entries\.csv|sources\.csv)\Z|"
    r"share/assets/[a-z0-9][a-z0-9-]*\.(?:png|jpg)\Z|"
    r"(?:articles|topics|entries|sources|share)/[a-z][a-z0-9]*(?:-[a-z0-9]+)*\.html\Z"
)
WIKI_DIRS = {"articles", "topics", "entries", "sources", "data", "share", "share/assets"}
ROOT_FILES = {
    "README.md", "CONTRIBUTING.md", "RELEASE_DISABLED", "verify_public.py",
    "tests/test_verify_public.py", ".github/workflows/verify.yml",
    ".github/workflows/deploy-pages.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/ISSUE_TEMPLATE/correction.yml",
    ".github/ISSUE_TEMPLATE/primary-source-tip.yml",
    ".github/ISSUE_TEMPLATE/dataset-importer.yml",
}
HOLDING_SHA256 = "52e5943605d9b874a60bb11564d538090ab429be04b19c33572ea1571cf9b6e8"
PUBLIC_V1_FIELDS = {
    "profile", "input_digests", "selection_digest", "review_digests",
    "output_digests",
}
WIKI_V1_FIELDS = {
    "profile", "mode", "scope_id", "factual_digest", "publication_digest",
    "renderer_digest", "decision_digests", "output_digests",
}
WIKI_V1_SITE_FIELDS = {
    "profile", "mode", "scopes", "renderer_digest",
    "decision_digests", "output_digests",
}
WIKI_V1_SITE_SCOPE_FIELDS = {
    "scope_id", "factual_digest", "publication_digest",
}
FORBIDDEN_MARKERS = (
    "PRIVATE PREVIEW — NOT FOR PUBLICATION",
    "synthetic_fixture",
    "test_only",
)


def fail(message):
    raise ValueError(message)


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_manifest(path):
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=unique_pairs,
        parse_constant=lambda value: fail(f"invalid JSON constant: {value}"),
    )


def check_sha(value, label):
    if not isinstance(value, str) or not HEX.fullmatch(value):
        fail(f"{label}: invalid SHA-256 digest")


def digest_map(value, label):
    if not isinstance(value, dict) or not value:
        fail(f"{label}: expected nonempty object")
    for key, digest in value.items():
        if not isinstance(key, str) or not key or not isinstance(digest, str) or not HEX.fullmatch(digest):
            fail(f"{label}: invalid key or SHA-256 digest")


def verify_output_hashes(site, found, outputs):
    if set(outputs) != found - {"manifest.json"}:
        fail("manifest: output file set differs from site/")
    for name, expected in outputs.items():
        actual = hashlib.sha256((site / name).read_bytes()).hexdigest()
        if actual != expected:
            fail(f"digest mismatch: {name}")


def verify_wiki_v1(site, found, dirs, manifest):
    profile = manifest["profile"]
    if profile == "wiki-v1":
        if set(manifest) != WIKI_V1_FIELDS:
            fail("wiki-v1 manifest: unexpected fields")
        if manifest["mode"] != "public":
            fail(f"wiki-v1 manifest: non-public mode {manifest['mode']!r}")
        scope_id = manifest["scope_id"]
        if not isinstance(scope_id, str) or not ID.fullmatch(scope_id):
            fail("wiki-v1 manifest: invalid scope_id")
        for field in ("factual_digest", "publication_digest", "renderer_digest"):
            check_sha(manifest[field], field)
        scope_ids = [scope_id]
    elif profile == "wiki-v1-site":
        if set(manifest) != WIKI_V1_SITE_FIELDS:
            fail("wiki-v1-site manifest: unexpected fields")
        if manifest["mode"] != "public":
            fail(f"wiki-v1-site manifest: non-public mode {manifest['mode']!r}")
        check_sha(manifest["renderer_digest"], "renderer_digest")
        scopes = manifest["scopes"]
        if not isinstance(scopes, list) or len(scopes) < 2:
            fail("wiki-v1-site manifest: requires at least 2 scopes")
        scope_ids = []
        for idx, item in enumerate(scopes):
            if not isinstance(item, dict) or set(item) != WIKI_V1_SITE_SCOPE_FIELDS:
                fail(f"wiki-v1-site manifest: invalid scope entry at index {idx}")
            sid = item["scope_id"]
            if not isinstance(sid, str) or not ID.fullmatch(sid):
                fail(f"wiki-v1-site manifest: invalid scope_id at index {idx}")
            check_sha(item["factual_digest"], f"scopes[{idx}].factual_digest")
            check_sha(item["publication_digest"], f"scopes[{idx}].publication_digest")
            scope_ids.append(sid)
        if len(scope_ids) != len(set(scope_ids)) or scope_ids != sorted(scope_ids):
            fail("wiki-v1-site manifest: scopes must have sorted unique scope_ids")
    else:
        fail(f"manifest: unexpected profile {profile!r}")

    digest_map(manifest["decision_digests"], "decision_digests")
    expected_decisions = {"renderer:wiki-v1-renderer"}
    for sid in scope_ids:
        expected_decisions.add(f"factual:{sid}")
        expected_decisions.add(f"publication:{sid}")
    if set(manifest["decision_digests"]) != expected_decisions:
        fail(f"{profile} manifest: decision_digests must match exact slice and renderer keys")

    digest_map(manifest["output_digests"], "output_digests")
    outputs = manifest["output_digests"]
    if not {"index.html", "search.html", "style.css"} <= outputs.keys():
        fail("wiki-v1 manifest: missing required core files")
    for name in outputs:
        if not WIKI_FILE.fullmatch(name):
            fail(f"unlisted public file: {name}")
    for prefix in ("topics/", "entries/", "sources/"):
        if not any(name.startswith(prefix) for name in outputs):
            fail(f"wiki-v1 manifest: missing {prefix} output")

    for directory in dirs:
        if directory not in WIKI_DIRS:
            fail(f"unexpected directory in site/: {directory}")
        if not any((site / directory).iterdir()):
            fail(f"unexpected empty directory in site/: {directory}")
    for name in found - {"manifest.json"}:
        if not WIKI_FILE.fullmatch(name):
            fail(f"unlisted public file: {name}")

    verify_output_hashes(site, found, outputs)

    for name in outputs:
        if name == "og-card.jpg" or name.startswith("share/assets/"):
            raw = (site / name).read_bytes()
            if name.endswith(".jpg") and not raw.startswith(b"\xff\xd8\xff"):
                fail(f"invalid JPEG image: {name}")
            if name.endswith(".png") and not raw.startswith(b"\x89PNG\r\n\x1a\n"):
                fail(f"invalid PNG image: {name}")
            continue
        text = (site / name).read_text(encoding="utf-8")
        for marker in FORBIDDEN_MARKERS:
            if marker in text:
                fail(f"forbidden preview/synthetic marker in {name}")


def verify_site(site):
    if not site.is_dir() or site.is_symlink():
        fail("site/ must be a real directory")
    found = set()
    dirs = set()
    for path in sorted(site.rglob("*")):
        if path.is_symlink():
            fail(f"symlink in site/: {path.relative_to(site)}")
        rel = path.relative_to(site).as_posix()
        if path.is_dir():
            dirs.add(rel)
        elif path.is_file():
            found.add(rel)
        else:
            fail(f"unsupported file in site/: {rel}")
    if "manifest.json" not in found or "index.html" not in found:
        fail("site/ requires manifest.json and index.html")
    manifest = load_manifest(site / "manifest.json")
    if not isinstance(manifest, dict):
        fail("manifest: expected object")

    profile = manifest.get("profile")
    if profile == "holding-v1":
        if set(manifest) != {"profile", "output_digests"}:
            fail("holding manifest: unexpected fields")
        if found != {"index.html", "manifest.json"} or dirs:
            fail("holding site: unexpected files")
        if manifest["output_digests"] != {"index.html": HOLDING_SHA256}:
            fail("holding manifest: unexpected digest")
        if hashlib.sha256((site / "index.html").read_bytes()).hexdigest() != HOLDING_SHA256:
            fail("holding page: digest mismatch")
        return

    if profile in ("wiki-v1", "wiki-v1-site"):
        verify_wiki_v1(site, found, dirs, manifest)
        return

    if profile == "public-v1":
        for name in found - {"manifest.json"}:
            if name != "index.html" and not ARTICLE.fullmatch(name):
                fail(f"unlisted public file: {name}")
        if set(manifest) != PUBLIC_V1_FIELDS:
            fail("manifest: unexpected fields")
        digest_map(manifest["input_digests"], "input_digests")
        digest_map(manifest["review_digests"], "review_digests")
        digest_map(manifest["output_digests"], "output_digests")
        if "renderer" not in manifest["input_digests"]:
            fail("input_digests: missing renderer")
        if set(manifest["input_digests"]) - {"renderer"} != set(manifest["review_digests"]):
            fail("manifest: input and review IDs differ")
        check_sha(manifest["selection_digest"], "selection_digest")
        verify_output_hashes(site, found, manifest["output_digests"])
        return

    fail(f"manifest: unexpected profile {profile!r}")


def verify_repository(root):
    if (root / "RELEASE_DISABLED").exists():
        if (root / "site").exists():
            fail("RELEASE_DISABLED and site/ cannot coexist")
    else:
        verify_site(root / "site")
    files = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached"], cwd=root).decode("utf-8").split("\0")
    for name in filter(None, files):
        if name not in ROOT_FILES and not name.startswith("site/"):
            fail(f"tracked file outside public allowlist: {name}")
        if name.startswith("site/") and not (root / name).is_file():
            fail(f"missing tracked public file: {name}")


if __name__ == "__main__":
    try:
        verify_repository(Path(__file__).resolve().parent)
    except (ValueError, OSError, UnicodeError, subprocess.CalledProcessError) as exc:
        print(f"public artifact verification failed: {exc}", file=sys.stderr)
        sys.exit(1)
    print("public artifact verified")
