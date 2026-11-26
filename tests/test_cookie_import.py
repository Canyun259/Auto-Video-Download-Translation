import tempfile
import unittest
from pathlib import Path
from import_instagram_cookies import instagram_cookies

class CookieImportTests(unittest.TestCase):
    def parse(self, lines):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            file = Path(folder)/'test-cookies.txt'
            file.write_text('# Netscape HTTP Cookie File\n'+lines,encoding='utf-8')
            return instagram_cookies(file)

    def test_filters_unrelated_domains_and_handles_httponly(self):
        text = ''.join(f'.instagram.com\tTRUE\t/\tTRUE\t0\t{name}\tfake\n' for name in ['csrftoken','ds_user_id'])
        text += '#HttpOnly_.instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\tfake\n'
        text += '.other.example\tTRUE\t/\tTRUE\t0\tprivate\tnot-imported\n'
        self.assertEqual(set(self.parse(text)), {'sessionid','csrftoken','ds_user_id'})

    def test_rejects_wrong_domain(self):
        text = ''.join(f'.notinstagram.com\tTRUE\t/\tTRUE\t0\t{name}\tfake\n' for name in ['sessionid','csrftoken','ds_user_id'])
        with self.assertRaises(ValueError): self.parse(text)
