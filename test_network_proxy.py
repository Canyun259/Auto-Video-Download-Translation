import unittest
from unittest.mock import patch,Mock
from network_proxy import media_proxy,validate_proxy,apply_instagram_proxy

class ProxyTests(unittest.TestCase):
    @patch.dict('os.environ',{},clear=True)
    @patch('network_proxy.getproxies',return_value={'https':'http://127.0.0.1:7897'})
    def test_system_proxy(self,getproxies):
        self.assertEqual(media_proxy(),'http://127.0.0.1:7897')
        self.assertEqual(media_proxy('http://127.0.0.1:7890'),'http://127.0.0.1:7890')
    def test_validation(self):
        for value in ['127.0.0.1:7897','file:///tmp/proxy','http://localhost:bad']:
            with self.assertRaises(ValueError): validate_proxy(value)
    def test_instagram(self):
        loader=Mock();loader.context._session.proxies={}
        apply_instagram_proxy(loader,'http://127.0.0.1:7897')
        self.assertFalse(loader.context._session.trust_env)
        self.assertEqual(loader.context._session.proxies['https'],'http://127.0.0.1:7897')

if __name__=='__main__': unittest.main()
