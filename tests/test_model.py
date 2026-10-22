"""Fake HTTP transport checks; these are not actual Ollama/model acceptance."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from afyaevidence.model import OllamaProvider, ProviderError
from afyaevidence.agent import ACTION_SCHEMA


class Handler(BaseHTTPRequestHandler):
    body={}
    requests=[]
    def log_message(self,*args): pass
    def do_GET(self):
        encoded=json.dumps(type(self).body).encode()
        self.send_response(200);self.end_headers();self.wfile.write(encoded)
    def do_POST(self):
        type(self).requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
        self.do_GET()


class ModelTests(unittest.TestCase):
    def setUp(self):
        Handler.requests=[]
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.provider=OllamaProvider(endpoint='http://127.0.0.1:'+str(self.server.server_port),model='qwen2.5:3b')

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)

    def test_exact_nonstreaming_schema_request_and_missing_usage_is_none(self):
        Handler.body=dict(model='qwen2.5:3b',done=True,message=dict(content='{}'))
        response=self.provider.next_action([dict(role='user',content='test')],timeout=1)
        self.assertEqual({'prompt_eval_count':None,'eval_count':None},response['usage'])
        body=Handler.requests[0]
        self.assertFalse(body['stream'])
        self.assertEqual(ACTION_SCHEMA,body['format'])
        self.assertEqual(0,body['options']['temperature'])
        self.assertEqual(768,body['options']['num_predict'])

    def test_model_list_and_mismatched_model_or_incomplete_generation(self):
        Handler.body=dict(models=[dict(name='qwen2.5:3b')])
        self.assertEqual(['qwen2.5:3b'],self.provider.models())
        for model,done in (('different',True),('qwen2.5:3b',False)):
            Handler.body=dict(model=model,done=done,message=dict(content='{}'))
            with self.assertRaises(ProviderError): self.provider.next_action([],timeout=1)

    def test_timeout_and_transport_failure_are_sanitised(self):
        with patch.object(self.provider.opener,'open',side_effect=TimeoutError('secret-token')):
            with self.assertRaises(ProviderError) as error: self.provider.next_action([],timeout=1)
        self.assertNotIn('secret-token',str(error.exception))
        self.assertEqual('model_timeout',error.exception.code)

    def test_supplied_turn_schema_reaches_http_instead_of_global_schema(self):
        from afyaevidence.agent import obj
        schema=obj(dict(type=dict(type='string',const='tool_call'),
            tool=dict(type='string',const='compare_monthly_indicators'),
            arguments=obj(dict(view=dict(type='string',const='raw_diagnostic')))))
        Handler.body=dict(model='qwen2.5:3b',done=True,message=dict(content='{}'))
        self.provider.next_action([],timeout=1,action_schema=schema)
        self.assertEqual(schema,Handler.requests[0]['format'])
        self.assertNotIn('canonical',json.dumps(Handler.requests[0]['format']))

    def test_http_failure_is_distinct_without_exposing_body(self):
        import urllib.error
        error=urllib.error.HTTPError('http://local',500,'secret-token',None,None)
        with patch.object(self.provider.opener,'open',side_effect=error):
            with self.assertRaisesRegex(ProviderError,'model_http_error') as raised:
                self.provider.next_action([],timeout=1)
        self.assertNotIn('secret-token',str(raised.exception))

    def test_endpoint_credentials_paths_and_context_overflow_are_rejected(self):
        for endpoint in ('file:///etc/passwd','http://user:secret@localhost','http://localhost/api/chat','http://localhost?token=secret'):
            with self.assertRaises(ValueError): OllamaProvider(endpoint=endpoint)
        with self.assertRaises(ProviderError): self.provider.request('/api/chat',{'x':'x'*100001},timeout=1)
        with self.assertRaises(ProviderError): self.provider.request('/arbitrary',timeout=1)

    def test_oversized_and_invalid_usage_responses_fail(self):
        Handler.body=dict(model='qwen2.5:3b',done=True,message=dict(content='x'*16385))
        with self.assertRaises(ProviderError): self.provider.next_action([],timeout=1)
        Handler.body=dict(model='qwen2.5:3b',done=True,message=dict(content='{}'),eval_count=True)
        with self.assertRaises(ProviderError): self.provider.next_action([],timeout=1)


if __name__=='__main__': unittest.main()
