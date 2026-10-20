"""Inventory original bytes; optional pypdf extraction does not perform OCR."""
import argparse
import hashlib
import json
from pathlib import Path


def inspect(path):
    path = Path(path)
    data = path.read_bytes()
    result = {"filename": path.name, "bytes": len(data),
              "sha256": hashlib.sha256(data).hexdigest(),
              "status": "needs_visual_review"}
    if path.suffix.lower() == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise ValueError("Invalid PDF signature")
        try:
            from pypdf import PdfReader
        except ImportError:
            result.update(status="extractor_unavailable", page_count=None)
            return result
        reader = PdfReader(path)
        if reader.is_encrypted:
            result.update(status="encrypted", page_count=None)
            return result
        pages = []
        for number, page in enumerate(reader.pages, 1):
            try:
                text = page.extract_text() or ""
                pages.append({"page": number, "text": text,
                              "status": "needs_visual_review" if text.strip()
                              else "needs_ocr_or_visual_reading"})
            except Exception:
                pages.append({"page": number, "status": "extraction_failed"})
        result.update(page_count=len(reader.pages), pages=pages)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file")
    parser.add_argument("--output", required=True, help="Private local JSON output")
    args = parser.parse_args()
    Path(args.output).write_text(json.dumps(inspect(args.file), ensure_ascii=False,
                                           indent=2), encoding="utf-8")
