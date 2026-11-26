import ast
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from database_setup import ensure_schema
from url_import import import_url, import_error


class URLImportTests(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:')
        ensure_schema(self.c)
        # Keep the in-memory database open while the importer owns connections.
        self.connect_patch = patch('url_import.closing', lambda c: c)
        self.connect_patch.start()
        self.downloader = patch('url_import.YoutubeDL').start()
        self.extract = self.downloader.return_value.__enter__.return_value.extract_info
        self.extract.return_value = {'id': 'abc', 'extractor_key': 'Youtube', 'title': 'Test',
            'webpage_url': 'https://www.youtube.com/watch?v=abc', 'formats': [{'url': 'media'}],
            'upload_date': '20200101'}
        self.url = 'https://youtu.be/abc'

    def tearDown(self):
        patch.stopall()
        self.c.close()

    def run_import(self, url=None):
        return import_url(lambda: self.c, self.url if url is None else url, {'proxy': 'http://localhost:1234'})

    def test_import_old_video_without_monitoring_and_duplicate(self):
        self.c.execute('INSERT INTO scan_checkpoints VALUES(?,?,?)', (self.url, 9999999999, 9999999999))
        ident, created = self.run_import()
        self.assertTrue(created)
        self.assertEqual(self.c.execute('SELECT state,title FROM videos').fetchone(), ('waiting', 'Test'))
        self.c.execute("UPDATE videos SET state='done',published_at=NULL,title_zh='译名'")
        self.extract.return_value['uploader']='Existing creator'
        self.assertEqual(self.run_import(), (ident, False))
        self.assertEqual(self.c.execute('SELECT state,publisher,published_at,title_zh FROM videos').fetchone(),
                         ('done','Existing creator','2020-01-01（平台仅提供日期）','译名'))
        self.assertEqual(self.c.execute('SELECT since FROM scan_checkpoints').fetchone()[0], 9999999999)
        options = self.downloader.call_args.args[0]
        self.assertTrue(options['noplaylist'])
        self.assertEqual(options['proxy'], 'http://localhost:1234')
        self.extract.assert_called_with(self.url, download=False)

    def test_validation_and_failures_do_not_insert(self):
        for url in ('', 'bad', 'http://youtu.be/a', 'https://example.com/a', 'https://youtube.com.evil.test/a'):
            with self.subTest(url=url), self.assertRaises(ValueError): self.run_import(url)
        self.extract.assert_not_called()
        for info in (None, {'entries': []}, {'is_live': True}, {'id': 'image'}):
            self.extract.return_value = info
            with self.subTest(info=info), self.assertRaises(ValueError): self.run_import()
        self.extract.side_effect = RuntimeError('Connection timed out')
        with self.assertRaisesRegex(RuntimeError, 'timed out'): self.run_import()
        self.assertEqual(self.c.execute('SELECT count(*) FROM videos').fetchone()[0], 0)

    def test_deleted_video_reports_reason(self):
        self.run_import()
        self.c.execute('UPDATE videos SET hidden=1')
        with self.assertRaisesRegex(ValueError, '手动删除'): self.run_import()

    def test_error_hints_and_redaction(self):
        message = import_error(RuntimeError('login required cookie=secret https://example.com/private'))
        self.assertIn('登录', message)
        self.assertNotIn('secret', message)
        self.assertNotIn('https://', message)
        self.assertIn('代理', import_error(RuntimeError('Connection timed out')))


class URLImportUITests(unittest.TestCase):
    def test_success_duplicate_and_persistent_failure(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'local_ui.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'render_url_import')
        script = 'import streamlit as st\ndef db(): pass\ndef opts(): return {}\n' + ast.unparse(function) + '\nrender_url_import()'
        page = AppTest.from_string(script).run()
        page.text_input(key='import-url-input').set_value('https://youtu.be/abc')
        with patch('url_import.import_url', return_value=('abc', True)):
            page.button[0].click().run()
        self.assertFalse(page.exception)
        self.assertIn('待选择', page.success[0].value)
        with patch('url_import.import_url', return_value=('abc', False)):
            page.button[0].click().run()
        self.assertIn('无需重复', page.info[0].value)
        with patch('url_import.import_url', side_effect=RuntimeError('Connection timed out')):
            page.button[0].click().run()
        self.assertFalse(page.exception)
        self.assertIn('timed out', page.error[0].value)
        page.run()
        self.assertIn('代理', page.error[0].value)
        self.assertEqual(page.text_input[0].value, 'https://youtu.be/abc')


if __name__ == '__main__': unittest.main()
