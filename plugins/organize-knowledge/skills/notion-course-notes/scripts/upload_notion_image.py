"""Send a local image using the scoped response from Notion create_file_upload.

python upload_notion_image.py --file image.jpg --prepare-json PRIVATE_TEMP.json
Prints attachment Markdown only; never prints the upload URL or authorization.
Requires Python 3.9+ and its standard library, with HTTPS network access.
"""

import argparse
import json
import mimetypes
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid


class UploadError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise UploadError("Upload redirect rejected; request a fresh upload URL.")


def build_request(image_path, prepared):
    image_path = Path(image_path)
    if not image_path.is_file():
        raise UploadError("Original image file is unavailable.")
    if not 0 < image_path.stat().st_size <= 20 * 1024 * 1024:
        raise UploadError("Image is empty or exceeds the 20 MiB single-part limit.")
    parsed = urllib.parse.urlsplit(prepared.get("upload_url", ""))
    if (parsed.scheme != "https" or parsed.hostname != "api.notion.com"
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.fragment):
        raise UploadError("Expected the HTTPS api.notion.com upload URL from the Notion tool.")
    if prepared.get("upload_method", "POST") != "POST":
        raise UploadError("Expected a single POST upload.")
    if prepared.get("upload_form_field", "file") != "file":
        raise UploadError("Expected the file multipart field.")
    content_type = prepared.get("content_type") or mimetypes.guess_type(image_path.name)[0]
    allowed = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml",
               "image/heic", "image/heif", "image/tiff", "image/bmp"}
    if content_type not in allowed:
        raise UploadError("Expected a supported image MIME type.")
    headers = dict(prepared.get("upload_headers", {}))
    if not all(isinstance(k, str) and isinstance(v, str) and "\n" not in k + v
               and "\r" not in k + v for k, v in headers.items()):
        raise UploadError("Invalid upload headers.")
    if any(k.lower() in {"content-type", "content-length", "host"} for k in headers):
        raise UploadError("Unexpected transport headers; inspect the current upload tool schema.")
    # An ASCII filename avoids platform-specific multipart Unicode handling.
    suffix = image_path.suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
        raise UploadError("Expected an image filename extension.")
    filename = "image" + suffix
    boundary = "notion-image-" + uuid.uuid4().hex
    start = (f"--{boundary}\r\n"
             f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
             f"Content-Type: {content_type}\r\n\r\n").encode("ascii")
    body = start + image_path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("ascii")
    headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    return urllib.request.Request(prepared["upload_url"], body, headers, method="POST")


def upload(image_path, prepared):
    request = build_request(image_path, prepared)
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise UploadError(f"Upload rejected with HTTP {exc.code}; check expiry, file limits and access.") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise UploadError("Upload network failure; verify the upload status before retrying.") from None
    except (UnicodeError, json.JSONDecodeError):
        raise UploadError("Unrecognized upload response; verify status before retrying.") from None
    source = result.get("markdown_source")
    suggested = result.get("suggested_markdown")
    if not source and isinstance(result.get("file_upload"), dict):
        source = result["file_upload"].get("markdown_source")
        suggested = result["file_upload"].get("suggested_markdown")
    if not source:
        raise UploadError("No attachment source in upload response; inspect the current tool contract.")
    return {"file_upload_id": result.get("file_upload_id", prepared.get("file_upload_id")),
            "markdown_source": source, "suggested_markdown": suggested,
            "status": "uploaded_not_attached"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True)
    parser.add_argument("--prepare-json", required=True,
                        help="Private temporary JSON from Notion create_file_upload; '-' reads stdin.")
    parser.add_argument("--output", help="Optional private output receipt file.")
    args = parser.parse_args()
    try:
        raw = sys.stdin.read() if args.prepare_json == "-" else Path(args.prepare_json).read_text(encoding="utf-8-sig")
        result = upload(args.file, json.loads(raw))
        encoded = json.dumps(result, ensure_ascii=True)
        if args.output:
            Path(args.output).write_text(encoded + "\n", encoding="utf-8")
        print(encoded)
        return 0
    except (UploadError, ValueError, TypeError, KeyError, OSError):
        # Never include an exception's URL, headers, token, or server response body.
        print(json.dumps({"status": "upload_failed_or_unverified",
                          "message": "Upload did not produce a verified attachment receipt; check file access, current upload schema, network and expiry."}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
