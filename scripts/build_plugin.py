"""Build a single-plugin release ZIP outside its plugin directory."""

from pathlib import Path
import json
import zipfile

from validate_public_package import PLUGIN, ROOT, validate_archive, validate_source


def main():
    validate_source()
    version = json.loads((PLUGIN/'plugin.json').read_text(encoding='utf-8'))['version']
    dist = ROOT/'dist'
    dist.mkdir(exist_ok=True)
    target = dist/f'organize-knowledge-{version}.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(PLUGIN.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                archive.write(path, 'organize-knowledge/'+path.relative_to(PLUGIN).as_posix())
    count = validate_archive(target)
    print(json.dumps({'archive':str(target),'files':count}, ensure_ascii=True))


if __name__ == '__main__':
    main()
