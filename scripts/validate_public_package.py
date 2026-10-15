"""Validate this public source and optionally a plugin ZIP; no network calls."""

import argparse
import json
from pathlib import Path
import re
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins/organize-knowledge'
UUID = re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', re.I)
COMPACT_NOTION_PAGE = re.compile(r'https?://(?:app\.|www\.)?notion\.(?:so|com)/(?:p/)?[^\s"<>)]*[0-9a-f]{32}', re.I)
TOKEN = re.compile(r'(?:gh[pousr]_[A-Za-z0-9_]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{20,}|Bearer\s+[A-Za-z0-9._-]{20,})')


def check_text(name, text):
    for regex, label in [(UUID, 'literal account/page UUID'),
                         (COMPACT_NOTION_PAGE, 'private Notion page address'),
                         (TOKEN, 'possible live credential')]:
        if regex.search(text):
            raise ValueError(f'{name}: found {label}')
    if re.search(r'[A-Za-z]:\\(?:Users|桌面文件)\\', text):
        raise ValueError(f'{name}: found a machine-specific path')


def validate_source():
    manifest = json.loads((PLUGIN/'plugin.json').read_text(encoding='utf-8'))
    legacy = json.loads((PLUGIN/'.codex-plugin/plugin.json').read_text(encoding='utf-8'))
    assert manifest['$schema'] == 'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json'
    assert manifest['name'] == legacy['name'] == 'organize-knowledge'
    assert manifest['version'] == legacy['version']
    assert 'email' not in manifest['author'] and 'email' not in legacy['author']
    ext = manifest['extensions']['com.openai']
    assert ext['interface'] == legacy['interface']
    assert len(ext['interface']['shortDescription']) <= 30
    assert 'apps' not in ext and 'apps' not in legacy and not (PLUGIN/'.app.json').exists()
    skills = list((PLUGIN/'skills').glob('*/SKILL.md'))
    assert len(skills) == 3
    for skill in skills:
        metadata = json.loads(skill.read_text(encoding='utf-8').split('---', 2)[1])
        assert metadata['name'] == skill.parent.name and metadata['description']
    marketplace = json.loads((ROOT/'.agents/plugins/marketplace.json').read_text(encoding='utf-8'))
    assert (ROOT/marketplace['plugins'][0]['source']['path']).resolve() == PLUGIN.resolve()
    scanned = 0
    for path in ROOT.rglob('*'):
        relative = path.relative_to(ROOT)
        if not path.is_file() or any(part in {'.git', '__pycache__', 'dist'} for part in relative.parts):
            continue
        if path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}:
            raise ValueError(f'{relative}: source must not contain private raster screenshots')
        text = path.read_text(encoding='utf-8')
        check_text(str(relative), text)
        if path.suffix in {'.json', '.yaml'}:
            json.loads(text)  # Agent YAML metadata in this project uses the JSON subset.
        if path.suffix == '.md':
            for link in re.findall(r'\]\(([^)]+)\)', text):
                if not re.match(r'(?:https?:|notion:|collection:|#)', link):
                    destination = (path.parent/link).resolve()
                    assert destination.is_relative_to(ROOT.resolve()) and destination.exists(), (relative, link)
        scanned += 1
    return scanned


def validate_archive(path):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert 'organize-knowledge/plugin.json' in names
        assert 'organize-knowledge/LICENSE' in names
        assert len([name for name in names if name.endswith('/SKILL.md')]) == 3
        for name in names:
            assert name.startswith('organize-knowledge/')
            assert not any(part in {'..', '.git', '__pycache__'} for part in Path(name).parts)
            assert not name.endswith(('.app.json', '.pyc', '.jpg', '.png'))
            check_text(name, archive.read(name).decode('utf-8'))
        return len(names)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args()
    result = {'source_files_checked': validate_source()}
    if args.archive:
        result['archive_files_checked'] = validate_archive(args.archive)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
