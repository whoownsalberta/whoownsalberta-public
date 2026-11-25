"""Verify the public repository boundary and generated artifact without secrets."""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HEX = re.compile(r"[0-9a-f]{64}\Z")
ARTICLE = re.compile(r"articles/[a-z][a-z0-9]*(?:-[a-z0-9]+)*\.html\Z")
ROOT_FILES = {
    "README.md", "RELEASE_DISABLED", "verify_public.py",
    "tests/test_verify_public.py", ".github/workflows/verify.yml",
}
FIELDS = {
    "profile", "input_digests", "selection_digest", "review_digests",
    "output_digests",
}


def fail(message):
    raise ValueError(message)


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def digest_map(value, label):
    if not isinstance(value, dict) or not value:
        fail(f"{label}: expected nonempty object")
    for key, digest in value.items():
        if not isinstance(key, str) or not key or not isinstance(digest, str) or not HEX.fullmatch(digest):
            fail(f"{label}: invalid key or SHA-256 digest")


def permitted_output(path):
    return path == "index.html" or bool(ARTICLE.fullmatch(path))


def verify_site(site):
    if not site.is_dir() or site.is_symlink():
        fail("site/ must be a real directory")
    found = set()
    for path in site.rglob("*"):
        if path.is_symlink():
            fail(f"symlink in site/: {path.relative_to(site)}")
        if path.is_file():
            name = path.relative_to(site).as_posix()
            if name != "manifest.json" and not permitted_output(name):
                fail(f"unlisted public file: {name}")
            found.add(name)
        elif not path.is_dir():
            fail(f"unsupported file in site/: {path.relative_to(site)}")
    if "manifest.json" not in found or "index.html" not in found:
        fail("site/ requires manifest.json and index.html")
    manifest = json.loads((site / "manifest.json").read_text(encoding="utf-8"),
                          object_pairs_hook=unique_pairs)
    if not isinstance(manifest, dict) or set(manifest) != FIELDS:
        fail("manifest: unexpected fields")
    if manifest["profile"] != "public-v1":
        fail("manifest: unexpected profile")
    digest_map(manifest["input_digests"], "input_digests")
    digest_map(manifest["review_digests"], "review_digests")
    digest_map(manifest["output_digests"], "output_digests")
    if "renderer" not in manifest["input_digests"]:
        fail("input_digests: missing renderer")
    if set(manifest["input_digests"]) - {"renderer"} != set(manifest["review_digests"]):
        fail("manifest: input and review IDs differ")
    if not isinstance(manifest["selection_digest"], str) or not HEX.fullmatch(manifest["selection_digest"]):
        fail("selection_digest: invalid SHA-256 digest")
    outputs = manifest["output_digests"]
    if set(outputs) != found - {"manifest.json"}:
        fail("manifest: output file set differs from site/")
    for name, expected in outputs.items():
        actual = hashlib.sha256((site / name).read_bytes()).hexdigest()
        if actual != expected:
            fail(f"digest mismatch: {name}")


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
