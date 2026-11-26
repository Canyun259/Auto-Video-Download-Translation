import os
import unittest
from unittest.mock import patch
from mt_translation import translate

class Response:
    status_code = 200
    def raise_for_status(self): pass
    def json(self): return {'choices':[{'message':{'content':'你好'}}]}

class MTTests(unittest.TestCase):
    @patch.dict(os.environ, {'TRANSLATE_BASE_URL':'https://test.example/v1','TRANSLATE_API_KEY':'test','TRANSLATE_MODEL':'qwen-mt-flash'})
    def test_contract_timestamps_and_repeated_text(self):
        calls=[]
        def post(url, **kw):
            calls.append(kw['json'])
            return Response()
        result=translate([(1,2,'hello'),(5,6,'hello')],post=post,sleep=lambda _:None)
        self.assertEqual(result,[(1,2,'你好'),(5,6,'你好')])
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['messages'],[{'role':'user','content':'hello'}])
        self.assertNotIn('response_format',calls[0])
        self.assertEqual(calls[0]['translation_options']['target_lang'],'Chinese')

    @patch.dict(os.environ, {'TRANSLATE_BASE_URL':'https://test.example/v1','TRANSLATE_API_KEY':'test','TRANSLATE_MODEL':'qwen-mt-flash'})
    def test_rate_limit_retry(self):
        busy=Response(); busy.status_code=429
        responses=iter([busy,Response()])
        result=translate([(0,1,'hello')],post=lambda *a,**kw:next(responses),sleep=lambda _:None)
        self.assertEqual(result,[(0,1,'你好')])
