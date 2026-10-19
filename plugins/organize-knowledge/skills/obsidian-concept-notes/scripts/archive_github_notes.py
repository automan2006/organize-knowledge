"""Create immutable Markdown files in a private GitHub repo using authenticated gh.

Input JSON: {"repository":"owner/repo", "files":[{"file":"local.md",
"path":"课程/概念.md"}]}. No tokens or Markdown transformations are involved.
"""

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import unicodedata
from urllib.parse import quote


class ArchiveError(Exception):
    pass


class ApiError(ArchiveError):
    def __init__(self, status=None):
        self.status = status
        super().__init__('GitHub API failed (HTTP %s)' % (status or 'unknown'))


def gh_api(endpoint, method='GET', body=None):
    command = ['gh', 'api', '--hostname', 'github.com', endpoint,
               '--method', method, '-H', 'Accept: application/vnd.github+json']
    if body is not None:
        command += ['--input', '-']
    try:
        result = subprocess.run(command, input=None if body is None else
                                json.dumps(body).encode('utf-8'),
                                capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ApiError() from error
    if result.returncode:
        match = re.search(rb'HTTP (\d{3})', result.stderr + result.stdout)
        raise ApiError(int(match[1]) if match else None)
    try:
        return json.loads(result.stdout)
    except (ValueError, UnicodeDecodeError) as error:
        raise ApiError() from error


def validate_path(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise ArchiveError('Use a relative POSIX Markdown path')
    path = PurePosixPath(value)
    if (path.is_absolute() or any(part in {'', '.', '..'} for part in value.split('/'))
            or path.suffix.lower() != '.md'):
        raise ArchiveError('Unsafe or non-Markdown destination')
    for part in path.parts:
        if (re.search(r'[<>:"|?*\x00-\x1f]', part) or part.endswith((' ', '.'))
                or part.startswith('.') or
                re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', part, re.I)):
            raise ArchiveError('Destination is not portable to Windows/Obsidian')
    return value


def blob_sha(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def decode_file(value):
    if not isinstance(value, dict) or value.get('type') != 'file' or value.get('encoding') != 'base64':
        raise ArchiveError('Remote response is not a readable Markdown file')
    return base64.b64decode(value['content'])


VOLATILE_FIELDS = {'created', 'updated', 'created_at', 'updated_at', 'exported_at',
                   'archived_at', 'archive_date', 'generated_at', 'source',
                   'source_chat', 'source_chat_url', 'source_message_id',
                   'source_locator', 'plugin_version', 'content_fingerprint'}


def content_fingerprint(data):
    """Conservative equality; never removes math, code, units or related candidates.

    Semantic rewordings must be compared by the agent before invoking this helper.
    Only line endings and explicitly named generated/provenance fields are ignored.
    """
    text = data.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
    lines = text.split('\n')
    if lines and lines[0] == '---' and '---' in lines[1:]:
        end = lines.index('---', 1)
        kept = []
        dropping = False
        for line in lines[1:end]:
            key = re.match(r'^([A-Za-z_][A-Za-z0-9_-]*):', line)
            if key:
                dropping = key[1] in VOLATILE_FIELDS
            elif dropping and line and not line[0].isspace() and not line.startswith('#'):
                # Unknown YAML shape: use stricter raw equality instead of guessing.
                return hashlib.sha256(text.rstrip('\n').encode()).hexdigest()
            if not dropping:
                kept.append(line)
        text = '\n'.join(['---'] + kept + ['---'] + lines[end + 1:])
    return hashlib.sha256(text.rstrip('\n').encode()).hexdigest()


def resolve_note_paths(entries):
    """Route verified course/domain decisions without changing Markdown bytes.

    The agent supplies semantic classification and live Notion/repo evidence.
    This function groups a course ID, reuses known folders, and validates paths.
    Legacy explicit paths remain supported for manual destinations and tests.
    """
    planned = []
    known_paths = {}
    owners = {}
    for entry in entries:
        category = entry.get('classification')
        if category is None:
            planned.append((entry, None, None))
            continue
        kind = category.get('kind')
        name = category.get('name', '').strip()
        if kind not in {'course', 'domain'} or not name:
            raise ArchiveError('Expected a verified course or domain classification')
        if kind == 'course':
            course_id = category.get('notion_course_id', '').strip().replace('-', '').lower()
            if not course_id:
                raise ArchiveError('Course routing requires the real Notion course page ID')
            key = ('course', course_id)
        else:
            if category.get('course_status') != 'no_match':
                raise ArchiveError('Do not create a domain when course matching is unverified')
            key = ('domain', unicodedata.normalize('NFKC', name).casefold())
        existing = category.get('existing_path')
        if existing is not None:
            validate_path(existing + '/category-check.md')
            if PurePosixPath(existing).parts[0] in {'_tests', '待分类'}:
                raise ArchiveError('A test/pending folder is not a confirmed category')
            if key in known_paths and known_paths[key] != existing:
                raise ArchiveError('One course/domain maps to conflicting existing folders')
            folded = existing.casefold()
            if folded in owners and owners[folded] != key:
                raise ArchiveError('Different courses/domains cannot share one category folder')
            known_paths[key] = existing
            owners[folded] = key
        planned.append((entry, category, key))

    output = []
    for entry, category, key in planned:
        if category is None:
            output.append(entry)
            continue
        folder = known_paths.get(key)
        if folder is None:
            name = unicodedata.normalize('NFKC', category['name']).strip()
            leaf = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', name).strip(' .')
            if not leaf:
                raise ArchiveError('Classification name cannot form a folder')
            if re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', leaf, re.I):
                leaf = '笔记-' + leaf
            folder = ('课程/' if key[0] == 'course' else '领域/') + leaf
            if folder.casefold() in owners and owners[folder.casefold()] != key:
                folder += '--' + hashlib.sha256(key[1].encode()).hexdigest()[:8]
            validate_path(folder + '/category-check.md')
            known_paths[key] = folder
            owners[folder.casefold()] = key
        filename = entry.get('filename')
        if not isinstance(filename, str) or '/' in filename or '\\' in filename:
            raise ArchiveError('Classified notes require a single Markdown filename')
        path = validate_path(folder + '/' + filename)
        if entry.get('path') is not None and entry['path'] != path:
            raise ArchiveError('Explicit path conflicts with the resolved course/domain')
        output.append(dict(entry, path=path, classification=dict(category, category_path=folder)))
    return output


def archive(manifest, api=gh_api, stamp=None):
    repository = manifest.get('repository', '')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ArchiveError('Expected owner/repo on github.com')
    entries = manifest.get('files')
    if not isinstance(entries, list) or not entries:
        raise ArchiveError('No notes supplied')
    prepared = []
    for entry in resolve_note_paths(entries):
        path = validate_path(entry['path'])
        data = Path(entry['file']).read_bytes()
        text = data.decode('utf-8')
        if not text.startswith(('---\n', '---\r\n')) or not re.search(r'(?m)^---\r?$', text[4:]):
            raise ArchiveError('Markdown must include YAML frontmatter')
        if len(data) > 900000:
            raise ArchiveError('Note exceeds verified Contents API size; split before upload')
        prepared.append((path, data, entry.get('classification')))
    root = 'repos/' + repository
    repo = api(root)
    if repo.get('private') is not True:
        raise ArchiveError('Refusing to archive private notes to a public/unverified repository')
    if repo.get('archived') or repo.get('permissions', {}).get('push') is not True:
        raise ArchiveError('Repository is archived or write permission is unverified')
    branch = manifest.get('branch') or repo['default_branch']
    if not isinstance(branch, str) or not branch:
        raise ArchiveError('Default branch is unverified')
    stamp = stamp or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    report = {'repository': repository, 'branch': branch, 'files': []}
    claimed = set()
    contents_by_scope = {}

    def endpoint(path, ref):
        return root + '/contents/' + quote(path, safe='/') + '?ref=' + quote(ref, safe='')

    def read(path, ref):
        try:
            return api(endpoint(path, ref))
        except ApiError as error:
            if error.status == 404:
                return None
            raise

    def scope_index(scope):
        if scope in contents_by_scope:
            return contents_by_scope[scope]
        index = {}
        pending = [scope]
        visited = set()
        while pending:
            folder = pending.pop()
            if folder in visited:
                continue
            visited.add(folder)
            listing = read(folder, branch)
            if listing is None:
                continue
            if not isinstance(listing, list) or len(listing) >= 1000:
                raise ArchiveError('Duplicate check incomplete: directory listing needs a full tree scan')
            for item in listing:
                path = item.get('path', '')
                if (scope and not path.startswith(scope + '/')) or path.startswith('/') or '..' in path.split('/'):
                    raise ArchiveError('Unexpected path in duplicate-check listing')
                if item.get('type') == 'dir':
                    pending.append(path)
                elif item.get('type') == 'file' and path.lower().endswith('.md'):
                    remote = read(path, branch)
                    if remote is None:
                        raise ArchiveError('Duplicate-check candidate changed while reading')
                    data = decode_file(remote)
                    if remote.get('sha') != blob_sha(data):
                        raise ArchiveError('Duplicate-check file hash mismatch')
                    index.setdefault(content_fingerprint(data), {'path': path, 'sha': remote['sha']})
        contents_by_scope[scope] = index
        return index

    def duplicate_receipt(receipt, match):
        receipt.update(status='skipped_duplicate', path=match['path'],
                       matched_path=match['path'], existing_blob_sha=match['sha'],
                       file_url='https://github.com/' + repository + '/blob/' +
                       quote(branch, safe='') + '/' + quote(match['path'], safe='/'),
                       new_commit=False)

    for original, data, category in prepared:
        receipt = {'requested_path': original, 'path': original, 'status': 'failed',
                   'sha256': hashlib.sha256(data).hexdigest(),
                   'content_fingerprint': content_fingerprint(data)}
        if category is not None:
            receipt['classification'] = category
        report['files'].append(receipt)
        candidate = original
        created = False
        races = 0
        try:
            scope = category['category_path'] if category else str(PurePosixPath(original).parent)
            if scope == '.':
                scope = ''
            receipt['dedup_scope'] = scope
            index = scope_index(scope)
            if receipt['content_fingerprint'] in index:
                duplicate_receipt(receipt, index[receipt['content_fingerprint']])
                continue
            # Sequential creates. A directory or existing file also reserves its path.
            for number in range(100):
                if number:
                    path = PurePosixPath(original)
                    suffix = '--' + stamp + '-' + receipt['sha256'][:8]
                    if number > 1:
                        suffix += '-' + str(number)
                    candidate = str(path.with_name(path.stem + suffix + path.suffix))
                receipt['path'] = candidate
                if candidate.casefold() in claimed:
                    continue
                existing = read(candidate, branch)
                if existing is not None:
                    if isinstance(existing, dict) and existing.get('type') == 'file':
                        old = decode_file(existing)
                        if content_fingerprint(old) == receipt['content_fingerprint']:
                            if existing.get('sha') != blob_sha(old):
                                raise ArchiveError('Duplicate-check file hash mismatch')
                            duplicate_receipt(receipt, {'path': candidate, 'sha': existing['sha']})
                            break
                    continue
                claimed.add(candidate.casefold())
                body = {'message': 'Archive study note: ' + candidate,
                        'content': base64.b64encode(data).decode('ascii'), 'branch': branch}
                # Deliberately never supply sha: the server must reject any overwrite.
                try:
                    response = api(root + '/contents/' + quote(candidate, safe='/'), 'PUT', body)
                except ApiError as error:
                    if error.status is None:
                        receipt['status'] = 'unknown'
                    existing = read(candidate, branch)
                    if error.status in {409, 422} and existing is not None:
                        if isinstance(existing, dict) and existing.get('type') == 'file':
                            old = decode_file(existing)
                            if content_fingerprint(old) == receipt['content_fingerprint']:
                                if existing.get('sha') != blob_sha(old):
                                    raise ArchiveError('Duplicate-check file hash mismatch')
                                duplicate_receipt(receipt, {'path': candidate, 'sha': existing['sha']})
                                break
                        races += 1
                        if races > 2:
                            raise ArchiveError('Repeated concurrent filename conflicts; stopped')
                        continue  # Another writer won; preserve it and choose a new name.
                    if existing is not None and decode_file(existing) == data:
                        history = api(root + '/commits?path=' + quote(candidate, safe='') +
                                      '&sha=' + quote(branch, safe='') + '&per_page=1')
                        if not history:
                            raise ArchiveError('File exists but its commit is unverified')
                        receipt['commit_sha'] = history[0]['sha']
                        receipt['status'] = 'existing_verified_after_uncertain_write'
                        break
                    receipt['status'] = 'unknown' if error.status is None else 'failed'
                    receipt['error'] = str(error)
                    break
                created = True
                receipt['status'] = 'committed_unverified'
                receipt['commit_sha'] = response['commit']['sha']
                break
            else:
                raise ArchiveError('Unable to find an unused destination after 100 checks')

            if receipt['status'] == 'skipped_duplicate':
                index[receipt['content_fingerprint']] = {'path': receipt['path'],
                                                       'sha': receipt['existing_blob_sha']}
                continue
            commit = receipt.get('commit_sha')
            if not commit:
                continue
            remote = read(candidate, commit)
            if (remote is None or decode_file(remote) != data or
                    remote.get('sha') != blob_sha(data)):
                raise ArchiveError('Committed file content does not match the generated note')
            details = api(root + '/commits/' + quote(commit, safe=''))
            if (details.get('sha') != commit or not any(
                    item.get('filename') == candidate for item in details.get('files', []))):
                raise ArchiveError('Commit does not contain this note')
            receipt['commit_url'] = 'https://github.com/' + repository + '/commit/' + commit
            receipt['file_url'] = ('https://github.com/' + repository + '/blob/' + commit + '/' +
                                   quote(candidate, safe='/'))
            if created:
                receipt['status'] = 'created_verified'
            index[receipt['content_fingerprint']] = {'path': candidate, 'sha': blob_sha(data)}
        except (ArchiveError, KeyError, ValueError, OSError) as error:
            receipt['error'] = str(error)
            if receipt.get('commit_sha'):
                receipt['status'] = 'committed_unverified'
    report['all_verified'] = all(item['status'] in {
        'created_verified', 'existing_verified_after_uncertain_write', 'skipped_duplicate'} for item in report['files'])
    report['created_count'] = sum(item['status'] == 'created_verified' for item in report['files'])
    report['skipped_duplicate_count'] = sum(item['status'] == 'skipped_duplicate' for item in report['files'])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
        report = archive(manifest)
    except (ArchiveError, ValueError, KeyError, OSError) as error:
        report = {'all_verified': False, 'error': str(error), 'files': []}
    args.receipt.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report['all_verified'] else 1


if __name__ == '__main__':
    sys.exit(main())
