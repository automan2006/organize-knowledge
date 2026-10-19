"""HTML preparation checks; no live Notion calls or JavaScript execution."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = (Path(__file__).resolve().parents[1] /
          'plugins/organize-knowledge/skills/notion-course-notes/scripts/prepare_notion_html.py')
spec = importlib.util.spec_from_file_location('prepare_notion_html', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class HTMLPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.html = Path(self.temp.name) / 'chart.html'
        self.raw = ('<!doctype html>\r\n<html><body><label>T<input id="T" type="range" '
                    'oninput="update(this.value)"></label><output id="v">2</output>'
                    '<svg onpointermove="read(event)"></svg><script>'
                    'function update(v){document.getElementById("v").textContent=v;}'
                    'function read(e){return e.clientX;}</script></body></html>\r\n').encode()
        self.html.write_bytes(self.raw)

    def prepare(self, origin='original'):
        return module.prepare(self.html, '交互图表', origin, 'unit test fixture')

    def test_source_and_event_code_are_not_rewritten(self):
        plan = self.prepare()
        self.assertEqual(plan['create_attachment']['content'].encode(), self.raw)
        self.assertEqual(plan['notion_block'], 'embed')
        self.assertIn('onpointermove', plan['event_attributes_detected'])
        self.assertEqual(plan['controls_detected'][0]['type'], 'range')

    def test_uses_actual_upload_source_in_native_embed_and_escapes_caption(self):
        markup = module.embed_markup('file-upload://unit-upload', '<原图> & 参数')
        self.assertEqual(markup, '<embed src="file-upload://unit-upload">&lt;原图&gt; &amp; 参数</embed>')
        for source in ['screenshot.jpg', 'https://example.com/chart', 'file-upload://bad" onclick="bad']:
            with self.subTest(source=source), self.assertRaises(module.ChartError):
                module.embed_markup(source, 'title')

    def test_screenshot_and_html_fragments_are_rejected(self):
        image = self.html.with_suffix('.jpg')
        image.write_bytes(b'fake-image')
        with self.assertRaises(module.ChartError):
            module.prepare(image, '图', 'original', 'test')
        self.html.write_text('<svg><text>截图不是程序</text></svg>', encoding='utf-8')
        with self.assertRaises(module.ChartError):
            self.prepare()

    def test_external_resources_and_host_runtime_are_flagged_for_review(self):
        source = self.raw.decode().replace('<body>', '<body><link rel="stylesheet" href="style.css">'
            '<script src="https://example.com/chart.js"></script><script>window.openai.callTool()</script>')
        self.html.write_text(source, encoding='utf-8')
        plan = self.prepare('ported')
        self.assertEqual(plan['portability'], 'review_required')
        self.assertIn('host-openai-runtime', plan['runtime_markers'])
        self.assertEqual(len(plan['dependency_references']), 2)

    def test_preparation_never_claims_upload_or_mobile_interaction_passed(self):
        plan = self.prepare()
        self.assertFalse(plan['verification']['uploaded'])
        self.assertFalse(plan['verification']['embed_inserted'])
        self.assertFalse(plan['verification']['interaction_tested'])
        self.assertFalse(plan['verification']['iphone_tested'])

    def test_large_utf8_source_requires_file_upload_and_is_not_truncated(self):
        self.html.write_text('<!doctype html><html><body>' + '学' * 70000 + '</body></html>', encoding='utf-8')
        plan = self.prepare()
        self.assertGreater(plan['size_bytes'], module.CONTENT_LIMIT)
        self.assertEqual(plan['transport'], 'file_upload_required')
        self.assertNotIn('create_attachment', plan)
        self.assertEqual(plan['size_bytes'], self.html.stat().st_size)

    def test_origin_and_provenance_are_explicit(self):
        for origin in ['original', 'user_provided', 'ported', 'reconstructed']:
            self.assertEqual(self.prepare(origin)['origin'], origin)
        with self.assertRaises(module.ChartError):
            self.prepare('screenshot')
        with self.assertRaises(module.ChartError):
            module.prepare(self.html, 'title', 'original', '')

    def test_cli_summary_does_not_print_the_source(self):
        marker = '<!-- unit-test-private-source-marker -->'
        self.html.write_bytes(self.raw.replace(b'</body>', marker.encode() + b'</body>'))
        output = self.html.parent / 'plan.json'
        result = subprocess.run([sys.executable, str(SCRIPT), '--html', str(self.html), '--title', 'chart',
            '--origin', 'original', '--source-description', 'unit fixture', '--output', str(output)],
            capture_output=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(marker, result.stdout)
        self.assertIn(marker, json.loads(output.read_text(encoding='utf-8'))['create_attachment']['content'])


if __name__ == '__main__':
    unittest.main()
