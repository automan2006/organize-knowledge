"""Prepare an unchanged UTF-8 HTML chart for Notion's native HTML embed.

This does not upload, reconstruct a screenshot, execute JavaScript, or verify UI.
"""
import argparse
import hashlib
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys


CONTENT_LIMIT = 200 * 1024


class ChartError(ValueError):
    pass


class Inspector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.tags = set()
        self.resources = []
        self.controls = []
        self.handlers = set()

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        values = dict(attrs)
        if tag in {'input', 'select', 'textarea', 'button'}:
            self.controls.append({'tag': tag, 'type': values.get('type'), 'id': values.get('id')})
        for key, value in attrs:
            if key.startswith('on'):
                self.handlers.add(key)
            if value and (key == 'src' or tag == 'link' and key == 'href'):
                if not value.startswith(('data:', '#')):
                    self.resources.append({'tag': tag, 'attribute': key, 'reference': value})


def embed_markup(markdown_source, caption):
    """Use only the actual file-upload source returned by the Notion tool."""
    if not re.fullmatch(r'file-upload://[A-Za-z0-9-]+', markdown_source):
        raise ChartError('Expected an actual Notion file-upload source')
    return '<embed src="' + escape(markdown_source, quote=True) + '">' + escape(caption) + '</embed>'


def prepare(html_path, title, origin, source_description):
    path = Path(html_path)
    if path.suffix.lower() not in {'.html', '.htm'}:
        raise ChartError('An executable HTML source is required; an image cannot preserve interaction')
    if origin not in {'original', 'user_provided', 'ported', 'reconstructed'}:
        raise ChartError('Specify the real origin of this HTML')
    if not title.strip() or not source_description.strip():
        raise ChartError('A title and real source description are required')
    data = path.read_bytes()
    try:
        content = data.decode('utf-8')
    except UnicodeDecodeError as error:
        raise ChartError('Export a UTF-8 HTML document before preparing the upload') from error
    inspector = Inspector()
    inspector.feed(content)
    if not {'html', 'body'}.issubset(inspector.tags) or not re.search(r'</html\s*>', content, re.I):
        raise ChartError('Export the complete HTML document and dependencies, not a fragment or screenshot')
    dependencies = list(inspector.resources)
    for match in re.finditer(r'(?:url\(\s*[\'"]?([^\s\)\'\"]+)|@import\s+[\'"]([^\'\"]+))', content, re.I):
        value = match[1] or match[2]
        if value and not value.startswith(('data:', '#')):
            dependencies.append({'tag': 'style', 'attribute': 'resource', 'reference': value})
    runtime_markers = [name for pattern, name in [
        (r'\bfetch\s*\(', 'fetch'), (r'\bimport\s*(?:\(|[\w{*])', 'module-import'),
        (r'window\s*\.\s*parent', 'parent-window'),
        (r'window\s*\.\s*openai', 'host-openai-runtime'),
        (r'\b(?:WebSocket|XMLHttpRequest)\b', 'network-runtime')]
        if re.search(pattern, content)]
    digest = hashlib.sha256(data).hexdigest()
    plan = {
        'title': title, 'origin': origin, 'source_description': source_description,
        'html_filename': path.name, 'html_sha256': digest, 'size_bytes': len(data),
        'attachment_format': 'text/html', 'notion_block': 'embed',
        'transport': 'create_attachment.content' if len(data) <= CONTENT_LIMIT else 'file_upload_required',
        'dependency_references': dependencies, 'runtime_markers': runtime_markers,
        'controls_detected': inspector.controls, 'event_attributes_detected': sorted(inspector.handlers),
        'portability': 'review_required' if dependencies or runtime_markers else 'no_static_dependency_detected',
        'github_asset_relative_path': 'assets/interactive/' + digest + '.html',
        'verification': {'source_bytes': 'preserved', 'uploaded': False, 'embed_inserted': False,
                         'interaction_tested': False, 'iphone_tested': False},
    }
    if len(data) <= CONTENT_LIMIT:
        plan['create_attachment'] = {'filename': path.name, 'content_type': 'text/html', 'content': content}
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html', type=Path, required=True)
    parser.add_argument('--title', required=True)
    parser.add_argument('--origin', choices=['original', 'user_provided', 'ported', 'reconstructed'], required=True)
    parser.add_argument('--source-description', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        plan = prepare(args.html, args.title, args.origin, args.source_description)
    except (ChartError, OSError) as error:
        print(json.dumps({'status': 'not_prepared', 'error': str(error)}, ensure_ascii=True))
        return 1
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    # Never dump the complete source or any source-embedded credentials to the chat.
    print(json.dumps({key: plan[key] for key in ['html_sha256', 'size_bytes', 'transport', 'origin',
                                              'portability', 'verification']}, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
