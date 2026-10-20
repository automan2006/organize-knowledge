"""Create hash-addressed original images/PDFs; never overwrite remote bytes."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote
from archive_github_notes import ArchiveError, ApiError, gh_api, decode_file

EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
              ".heic", ".heif", ".tif", ".tiff", ".bmp"}


def archive_asset(repository, file, api=gh_api):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ArchiveError("Expected owner/repo")
    file = Path(file)
    suffix = file.suffix.lower()
    if suffix not in EXTENSIONS:
        raise ArchiveError("Unsupported original format")
    data = file.read_bytes()
    if not 0 < len(data) <= 900000:
        raise ArchiveError("Original exceeds this helper limit or is empty")
    digest = hashlib.sha256(data).hexdigest()
    root = "repos/" + repository
    repo = api(root)
    if repo.get("private") is not True or repo.get("archived") or repo.get("permissions", {}).get("push") is not True:
        raise ArchiveError("Private writable repository required")
    branch = repo["default_branch"]
    # Canonical extension prevents .jpg/.jpeg renaming from duplicating bytes.
    suffix = {".jpeg": ".jpg", ".tif": ".tiff"}.get(suffix, suffix)
    folder = "_assets/" + digest
    def get(path, ref=branch):
        return api(root + "/contents/" + quote(path, safe="/") + "?ref=" + quote(ref, safe=""))
    try:
        listing = get(folder)
    except ApiError as error:
        if error.status != 404:
            raise
        listing = []
    for item in listing:
        if item.get("type") == "file":
            prior = get(item["path"])
            if decode_file(prior) == data:
                return {"status": "duplicate_skipped", "path": item["path"],
                        "sha256": digest, "commit": None}
            raise ArchiveError("Hash directory contains unexpected bytes")
    path = folder + "/original" + suffix
    result = api(root + "/contents/" + quote(path, safe="/"), "PUT",
                 {"message": "Archive original learning material",
                  "content": base64.b64encode(data).decode("ascii"), "branch": branch})
    commit = result.get("commit", {}).get("sha")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ArchiveError("Upload returned no verified commit")
    if decode_file(get(path, commit)) != data:
        raise ArchiveError("Committed original differs from local bytes")
    return {"status": "created_verified", "path": path, "sha256": digest,
            "commit": commit}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--file", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(archive_asset(args.repository, args.file)))
    except (ArchiveError, OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"status": "failed_or_unverified",
                          "message": "Inspect remote state before retry; not claimed saved."}))
        raise SystemExit(1)
