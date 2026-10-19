"""Offline regressions for append-only Markdown archiving; never writes GitHub."""
import base64
import importlib.util
from pathlib import Path
import tempfile
import unittest
from urllib.parse import unquote, urlsplit, parse_qs


SCRIPT = (Path(__file__).resolve().parents[1] / 'plugins/organize-knowledge/skills/'
          'obsidian-concept-notes/scripts/archive_github_notes.py')
spec = importlib.util.spec_from_file_location('archive_github_notes', SCRIPT)
archive_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive_module)


class FakeGitHub:
    def __init__(self):
        self.files = {}
        self.commits = {}
        self.puts = []
        self.private = True
        self.push = True
        self.failure = None
        self.forbid_reads = False
        self.corrupt_readback = False
        self.wrong_commit = False

    def __call__(self, endpoint, method='GET', body=None):
        root = 'repos/example/private-notes'
        if endpoint == root:
            return {'private': self.private, 'permissions': {'push': self.push},
                    'default_branch': 'main', 'archived': False}
        if endpoint.startswith(root + '/contents/'):
            parsed = urlsplit(endpoint)
            path = unquote(parsed.path.split('/contents/', 1)[1])
            ref = parse_qs(parsed.query).get('ref', ['main'])[0]
            if method == 'PUT':
                self.puts.append((path, body))
                assert 'sha' not in body, 'Updating is forbidden'
                if path in self.files:
                    raise archive_module.ApiError(422)
                if self.failure in {'permission', 'partial'} and (
                        self.failure == 'permission' or 'bad' in path):
                    raise archive_module.ApiError(403)
                if self.failure == 'timeout_no_commit':
                    raise archive_module.ApiError()
                commit = '%040x' % (len(self.commits) + 1)
                data = base64.b64decode(body['content'])
                self.files[path] = data
                self.commits[commit] = (path, data)
                if self.failure == 'timeout_after_commit':
                    raise archive_module.ApiError()
                return {'commit': {'sha': commit}}
            if self.forbid_reads:
                raise archive_module.ApiError(403)
            if ref == 'main':
                data = self.files.get(path)
                if data is None:
                    prefix = path + '/' if path else ''
                    children = {}
                    for filename in self.files:
                        if not filename.startswith(prefix):
                            continue
                        tail = filename[len(prefix):]
                        name = tail.split('/', 1)[0]
                        children[name] = {'path': prefix + name,
                                          'type': 'dir' if '/' in tail else 'file'}
                    if children or not path:
                        return list(children.values())
            else:
                item = self.commits.get(ref)
                data = item[1] if item and item[0] == path else None
                if self.corrupt_readback and data is not None:
                    data += b'corrupted'
            if data is None:
                raise archive_module.ApiError(404)
            return {'type': 'file', 'encoding': 'base64',
                    'content': base64.b64encode(data).decode(),
                    'sha': archive_module.blob_sha(data)}
        if endpoint.startswith(root + '/commits?'):
            path = parse_qs(urlsplit(endpoint).query)['path'][0]
            return [{'sha': commit} for commit, item in reversed(list(self.commits.items()))
                    if item[0] == path][:1]
        if endpoint.startswith(root + '/commits/'):
            commit = endpoint.rsplit('/', 1)[1]
            path, data = self.commits[commit]
            return {'sha': commit, 'files': [{'filename': 'other.md' if self.wrong_commit else path}]}
        raise AssertionError(endpoint)


class GitHubArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.note = Path(self.temp.name) / 'note.md'
        self.data = ('---\r\ntitle: "公差"\r\naliases: ["尺寸公差"]\r\n'
                     'related_candidates: ["上偏差", "下偏差"]\r\n---\r\n'
                     '# 公差\r\n\r\n$$T=D_{max}-D_{min}=ES-EI$$\r\n'
                     '$$\\frac{C_b}{C_b+C_m}F$$\r\n').encode('utf-8')
        self.note.write_bytes(self.data)
        self.fake = FakeGitHub()

    def run_archive(self, *paths):
        return archive_module.archive({'repository': 'example/private-notes', 'files': [
            {'file': str(self.note), 'path': path} for path in (paths or ['课程/公差.md'])]},
            api=self.fake, stamp='20261016T010203Z')

    def test_exact_bytes_preserve_yaml_formulas_and_crlf(self):
        result = self.run_archive()
        self.assertTrue(result['all_verified'])
        self.assertEqual(self.fake.files['课程/公差.md'], self.data)
        self.assertEqual(result['files'][0]['status'], 'created_verified')
        self.assertEqual(len(result['files'][0]['commit_sha']), 40)

    def test_existing_same_content_is_skipped_without_commit(self):
        self.fake.files['课程/公差.md'] = self.data
        result = self.run_archive()
        destination = result['files'][0]['path']
        self.assertEqual(destination, '课程/公差.md')
        self.assertEqual(self.fake.files['课程/公差.md'], self.data)
        self.assertEqual(result['files'][0]['status'], 'skipped_duplicate')
        self.assertEqual(result['skipped_duplicate_count'], 1)
        self.assertNotIn('commit_sha', result['files'][0])
        self.assertFalse(self.fake.puts)

    def test_identical_content_in_one_batch_is_not_saved_three_times(self):
        result = self.run_archive('课程/索引.md', '课程/公差.md', '课程/公差.md')
        self.assertEqual(len(result['files']), 3)
        self.assertTrue(result['all_verified'])
        self.assertEqual(len(self.fake.files), 1)
        self.assertEqual(result['created_count'], 1)
        self.assertEqual(result['skipped_duplicate_count'], 2)

    def test_different_content_with_same_name_gets_new_file(self):
        old = self.data + b'Previous explanation.\n'
        self.fake.files['课程/公差.md'] = old
        result = self.run_archive()
        self.assertTrue(result['all_verified'])
        self.assertNotEqual(result['files'][0]['path'], '课程/公差.md')
        self.assertEqual(self.fake.files['课程/公差.md'], old)
        self.assertEqual(result['created_count'], 1)
        self.assertTrue(all('sha' not in body for _, body in self.fake.puts))

    def test_same_content_with_different_filename_is_skipped(self):
        self.fake.files['课程/旧标题.md'] = self.data
        result = self.run_archive()
        self.assertTrue(result['all_verified'])
        self.assertEqual(result['files'][0]['matched_path'], '课程/旧标题.md')
        self.assertFalse(self.fake.puts)

    def test_line_endings_only_change_is_duplicate(self):
        self.fake.files['课程/公差.md'] = self.data
        self.note.write_bytes(self.data.replace(b'\r\n', b'\n'))
        result = self.run_archive()
        self.assertEqual(result['files'][0]['status'], 'skipped_duplicate')
        self.assertFalse(self.fake.puts)

    def test_existing_copy_in_subdirectory_is_found(self):
        self.fake.files['课程/旧版本/公差.md'] = self.data
        result = self.run_archive()
        self.assertEqual(result['files'][0]['matched_path'], '课程/旧版本/公差.md')
        self.assertFalse(self.fake.puts)

    def test_directory_at_listing_limit_is_not_assumed_complete(self):
        original = self.fake.__call__
        def limited(endpoint, method='GET', body=None):
            if method == 'GET' and '/contents/' in endpoint and unquote(urlsplit(endpoint).path).endswith('/课程'):
                return [{'type': 'file', 'path': '课程/old.md'}] * 1000
            return original(endpoint, method, body)
        result = archive_module.archive({'repository': 'example/private-notes', 'files': [
            {'file': str(self.note), 'path': '课程/公差.md'}]}, api=limited)
        self.assertFalse(result['all_verified'])
        self.assertIn('incomplete', result['files'][0]['error'])
        self.assertFalse(self.fake.puts)

    def test_changed_export_time_or_source_does_not_create_duplicate(self):
        old = self.data.replace(b'---\r\ntitle:', b'---\r\ncreated: "old"\r\nsource: "first chat"\r\ntitle:')
        new = self.data.replace(b'---\r\ntitle:', b'---\r\ncreated: "new"\r\nsource: "another chat"\r\ntitle:')
        self.fake.files['课程/公差.md'] = old
        self.note.write_bytes(new)
        result = self.run_archive()
        self.assertEqual(result['files'][0]['status'], 'skipped_duplicate')
        self.assertFalse(self.fake.puts)

    def test_changed_formula_number_or_candidate_is_new_content(self):
        self.fake.files['课程/公差.md'] = self.data
        for changed in [self.data + b'$$T=2(ES-EI)$$\n',
                        self.data.replace('下偏差'.encode(), '公差带'.encode())]:
            with self.subTest(changed=changed):
                self.note.write_bytes(changed)
                result = self.run_archive()
                self.assertEqual(result['files'][0]['status'], 'created_verified')

    def test_identical_content_in_different_courses_is_not_merged(self):
        result = self.run_archive('课程/课程一/概念.md', '课程/课程二/概念.md')
        self.assertEqual(result['created_count'], 2)
        self.assertEqual(result['skipped_duplicate_count'], 0)

    def test_duplicate_read_failure_does_not_blindly_upload(self):
        self.fake.files['课程/旧笔记.md'] = self.data
        original = self.fake.__call__
        def unreadable(endpoint, method='GET', body=None):
            if method == 'GET' and '旧笔记.md' in unquote(endpoint):
                raise archive_module.ApiError(403)
            return original(endpoint, method, body)
        result = archive_module.archive({'repository': 'example/private-notes', 'files': [
            {'file': str(self.note), 'path': '课程/新文件.md'}]}, api=unreadable)
        self.assertFalse(result['all_verified'])
        self.assertEqual(result['files'][0]['status'], 'failed')
        self.assertFalse(self.fake.puts)

    def test_public_repository_is_refused_before_writes(self):
        self.fake.private = False
        with self.assertRaises(archive_module.ArchiveError):
            self.run_archive()
        self.assertFalse(self.fake.puts)

    def test_missing_write_permission_is_refused(self):
        self.fake.push = False
        with self.assertRaises(archive_module.ArchiveError):
            self.run_archive()
        self.assertFalse(self.fake.puts)

    def test_one_failure_does_not_hide_or_block_other_notes(self):
        self.fake.failure = 'partial'
        result = self.run_archive('bad.md', 'good.md')
        self.assertFalse(result['all_verified'])
        self.assertEqual([item['status'] for item in result['files']], ['failed', 'created_verified'])
        self.assertNotIn('commit_sha', result['files'][0])

    def test_timeout_after_real_commit_is_resolved_without_duplicate_create(self):
        self.fake.failure = 'timeout_after_commit'
        result = self.run_archive()
        self.assertTrue(result['all_verified'])
        self.assertEqual(result['files'][0]['status'], 'existing_verified_after_uncertain_write')
        self.assertEqual(len(self.fake.puts), 1)

    def test_timeout_without_commit_remains_unknown(self):
        self.fake.failure = 'timeout_no_commit'
        result = self.run_archive()
        self.assertFalse(result['all_verified'])
        self.assertEqual(result['files'][0]['status'], 'unknown')
        self.assertNotIn('commit_sha', result['files'][0])

    def test_readback_mismatch_cannot_report_success(self):
        self.fake.corrupt_readback = True
        result = self.run_archive()
        self.assertFalse(result['all_verified'])
        self.assertEqual(result['files'][0]['status'], 'committed_unverified')
        self.assertIn('commit_sha', result['files'][0])

    def test_commit_must_include_actual_path(self):
        self.fake.wrong_commit = True
        result = self.run_archive()
        self.assertFalse(result['all_verified'])
        self.assertEqual(result['files'][0]['status'], 'committed_unverified')

    def test_permission_error_on_read_is_not_treated_as_missing_path(self):
        self.fake.forbid_reads = True
        result = self.run_archive()
        self.assertFalse(result['all_verified'])
        self.assertFalse(self.fake.puts)

    def test_invalid_paths_are_rejected_before_network(self):
        for value in ['/absolute.md', '../outside.md', 'a/../b.md', '.git/config.md',
                      'a//b.md', 'C:/notes.md', 'a\\b.md', 'CON.md', 'a.txt', 'a?.md']:
            with self.subTest(path=value), self.assertRaises(archive_module.ArchiveError):
                self.run_archive(value)
        self.assertFalse(self.fake.puts)


class ClassificationTests(unittest.TestCase):
    def entry(self, filename, name='机械设计', course_id='course-design', **extra):
        category = {'kind': 'course', 'name': name, 'notion_course_id': course_id}
        category.update(extra)
        return {'file': 'unused-local.md', 'filename': filename, 'classification': category}

    def test_different_topics_in_same_notion_course_stay_together(self):
        result = archive_module.resolve_note_paths([
            self.entry('螺栓连接.md'), self.entry('齿轮传动.md'), self.entry('课程索引.md')])
        self.assertEqual([item['path'] for item in result], [
            '课程/机械设计/螺栓连接.md', '课程/机械设计/齿轮传动.md', '课程/机械设计/课程索引.md'])

    def test_course_rename_reuses_existing_folder_by_page_id(self):
        result = archive_module.resolve_note_paths([
            self.entry('概念.md', name='机械设计新版'),
            self.entry('索引.md', existing_path='学习资料/机械设计')])
        self.assertEqual([item['path'] for item in result], [
            '学习资料/机械设计/概念.md', '学习资料/机械设计/索引.md'])

    def test_new_domain_gets_a_separate_category(self):
        note = self.entry('列表推导式.md')
        note['classification'] = {'kind': 'domain', 'name': 'Python 编程', 'course_status': 'no_match'}
        result = archive_module.resolve_note_paths([note])
        self.assertEqual(result[0]['path'], '领域/Python 编程/列表推导式.md')

    def test_confirmed_equivalent_domain_reuses_existing_folder(self):
        note = self.entry('列表推导式.md')
        note['classification'] = {'kind': 'domain', 'name': 'Python 编程', 'course_status': 'no_match',
                                  'existing_path': '领域/Python'}
        result = archive_module.resolve_note_paths([note])
        self.assertEqual(result[0]['path'], '领域/Python/列表推导式.md')

    def test_mixed_courses_and_domains_are_routed_per_note(self):
        domain = self.entry('单词记忆.md')
        domain['classification'] = {'kind': 'domain', 'name': '英语学习', 'course_status': 'no_match'}
        result = archive_module.resolve_note_paths([
            self.entry('螺栓.md'), self.entry('公差.md', name='互换性与技术测量', course_id='course-tolerance'),
            domain])
        self.assertEqual([item['path'].split('/')[1] for item in result], [
            '机械设计', '互换性与技术测量', '英语学习'])

    def test_same_name_different_course_ids_are_not_merged(self):
        result = archive_module.resolve_note_paths([
            self.entry('第一门课.md'), self.entry('另一门课.md', course_id='other-design')])
        self.assertNotEqual(result[0]['classification']['category_path'],
                            result[1]['classification']['category_path'])

    def test_unverified_course_or_failed_lookup_cannot_create_new_domain(self):
        bad_course = self.entry('测试.md', course_id='')
        bad_domain = self.entry('测试.md')
        bad_domain['classification'] = {'kind': 'domain', 'name': 'Python', 'course_status': 'unavailable'}
        for note in [bad_course, bad_domain]:
            with self.subTest(note=note), self.assertRaises(archive_module.ArchiveError):
                archive_module.resolve_note_paths([note])

    def test_conflicting_paths_and_unsafe_existing_folder_are_rejected(self):
        note = self.entry('螺栓.md')
        note['path'] = '领域/其他/螺栓.md'
        for item in [note, self.entry('螺栓.md', existing_path='../escape'),
                     self.entry('螺栓.md', existing_path='_tests/fixtures')]:
            with self.subTest(note=item), self.assertRaises(archive_module.ArchiveError):
                archive_module.resolve_note_paths([item])

    def test_one_course_cannot_map_to_two_existing_folders(self):
        with self.assertRaises(archive_module.ArchiveError):
            archive_module.resolve_note_paths([
                self.entry('a.md', existing_path='课程/机械设计'),
                self.entry('b.md', existing_path='课程/机械设计新版')])

    def test_classified_upload_preserves_bytes_and_reports_category(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'input.md'
            raw = ('---\ntitle: "螺栓"\nrelated_candidates: ["预紧力"]\n'
                   'category: "机械设计"\n---\n$$F_2=F_0+\\frac{C_b}{C_b+C_m}F$$\n').encode()
            file.write_bytes(raw)
            note = self.entry('螺栓.md')
            note['file'] = str(file)
            fake = FakeGitHub()
            result = archive_module.archive({'repository': 'example/private-notes', 'files': [note]}, api=fake)
            self.assertTrue(result['all_verified'])
            self.assertEqual(fake.files['课程/机械设计/螺栓.md'], raw)
            self.assertEqual(result['files'][0]['classification']['category_path'], '课程/机械设计')


if __name__ == '__main__':
    unittest.main()
