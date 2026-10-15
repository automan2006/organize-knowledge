import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/organize-knowledge/skills/notion-course-notes/scripts'


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fit = load('fit_notion_equation')
uploader = load('upload_notion_image')


class FormulaTests(unittest.TestCase):
    def test_sizing_preserves_mathematical_content(self):
        source = r'\Large \displaystyle \boxed{F_2=F_0+\frac{C_b}{C_b+C_m}F}'
        result = fit.fit_equation(source)
        self.assertEqual(fit.SIZE_RE.sub('', source), fit.SIZE_RE.sub('', result['latex']))
        self.assertNotEqual(result['size'], r'\Large')

    def test_fraction_width_uses_layout_instead_of_source_length(self):
        self.assertLess(fit.fit_equation(r'\frac{a}{b}')['estimated_width_px'],
                        fit.fit_equation('abcdefghij')['estimated_width_px'])

    def test_long_and_unknown_structures_require_review(self):
        self.assertTrue(fit.fit_equation('F=ma' * 20)['needs_split_or_review'])
        self.assertTrue(fit.fit_equation(r'\unknown{x}')['needs_split_or_review'])

    def test_invalid_dimensions_are_rejected(self):
        with self.assertRaises(ValueError):
            fit.fit_equation('F=ma', width_px=0)


class ImageUploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.image = Path(self.temp.name) / 'input.png'
        self.raw = b'\x89PNG\r\n\x1a\nrequest-body-test'
        self.image.write_bytes(self.raw)
        self.prepared = {'upload_url': 'https://api.notion.com/v1/file_uploads/unit/send',
                         'upload_headers': {'authorization': 'Bearer FAKE'},
                         'content_type': 'image/png', 'file_upload_id': 'unit-id'}

    def test_sends_original_binary_and_required_header(self):
        req = uploader.build_request(self.image, self.prepared)
        self.assertIn(self.raw, req.data)
        self.assertIn(b'name="file"', req.data)
        self.assertEqual(req.get_header('Authorization'), 'Bearer FAKE')
        self.assertEqual(req.get_method(), 'POST')

    def test_untrusted_destinations_are_rejected(self):
        for url in ['http://api.notion.com/send', 'https://example.invalid/send',
                    'https://api.notion.com.example.invalid/send']:
            with self.subTest(url=url), self.assertRaises(uploader.UploadError):
                uploader.build_request(self.image, dict(self.prepared, upload_url=url))

    def test_redirect_does_not_forward_credentials(self):
        with self.assertRaises(uploader.UploadError):
            uploader.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.invalid')

    def test_empty_image_is_rejected(self):
        self.image.write_bytes(b'')
        with self.assertRaises(uploader.UploadError):
            uploader.build_request(self.image, self.prepared)

    def test_receipt_does_not_contain_upload_authorization(self):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = json.dumps({
            'markdown_source': 'file-upload://unit-id',
            'suggested_markdown': '<image src="file-upload://unit-id"></image>'
        }).encode()
        with patch.object(uploader.urllib.request, 'build_opener', return_value=opener):
            receipt = uploader.upload(self.image, self.prepared)
        self.assertEqual(receipt['status'], 'uploaded_not_attached')
        self.assertNotIn('authorization', json.dumps(receipt))
        self.assertNotIn('Bearer FAKE', json.dumps(receipt))


if __name__ == '__main__':
    unittest.main()
