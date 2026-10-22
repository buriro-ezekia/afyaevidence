from contextlib import closing
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from afyaevidence.identity_review_server import BoundedServer,handler_factory,CSP
from afyaevidence.identity_page import JS
from afyaevidence import identity_store
from identity_support import token,verifier,v2_database


class IdentityHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/'reviews.db';v2_database(self.db)
        self.verifier,self.provider=verifier()
        self.server=BoundedServer(('127.0.0.1',0),handler_factory(self.db,self.verifier))
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True);self.worker.start()
        self.addCleanup(self.stop)
        self.port=self.server.server_port
        self.payload=dict(expected_revision=0,event_key='http_once',disposition='accept',reason='Reviewed synthetic reporting evidence.')

    def stop(self):
        self.server.shutdown();self.server.server_close();self.worker.join(timeout=3)

    def request(self,method,path,bearer=None,payload=None,headers=None,raw=None):
        h=dict(headers or {})
        if bearer is not None:h['Authorization']='Bearer '+bearer
        body=raw
        if payload is not None:
            h.setdefault('Content-Type','application/json');body=json.dumps(payload,ensure_ascii=True).encode()
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        conn.request(method,path,body=body,headers=h)
        r=conn.getresponse();data=r.read();status=r.status;response_headers=dict(r.getheaders());conn.close()
        result=json.loads(data) if r.getheader('Content-Type','').startswith('application/json') else data.decode()
        return status,result,response_headers

    def test_missing_invalid_and_development_tokens_rejected(self):
        for bearer in (None,'development-secret'*4,'not-a-jwt'):
            with self.subTest(token_type=type(bearer).__name__):self.assertEqual(self.request('GET','/api/runs/run_pending',bearer)[0],401)

    def test_viewer_reads_but_cannot_submit(self):
        key=token(['viewer'])
        self.assertEqual(self.request('GET','/api/runs/run_pending',key)[0],200)
        self.assertEqual(self.request('POST','/api/runs/run_pending/reviews',key,self.payload)[0],403)

    def test_authenticated_person_and_role_are_server_derived(self):
        status,body,_=self.request('GET','/api/me',token(subject='named-person'))
        self.assertEqual(status,200);self.assertEqual(body['subject'],'named-person')
        self.assertNotIn('token',body)
        self.assertEqual(self.request('POST','/api/runs/run_pending/reviews',token(),{**self.payload,'reviewer':'fake'})[0],400)

    def test_record_replay_and_identity_history(self):
        key=token()
        url='/api/runs/run_pending/reviews'
        self.assertEqual(self.request('POST',url,key,self.payload)[0],200)
        self.assertTrue(self.request('POST',url,key,self.payload)[1]['replayed'])
        self.assertEqual(self.request('POST',url,token(subject='other'),self.payload)[0],409)
        record=self.request('GET','/api/runs/run_pending',key)[1]
        self.assertEqual(record['history'][0]['identity']['kind'],'verified_oidc')
        self.assertIsNone(record['candidate']['approval'])

    def test_unicode_maximum_is_valid(self):
        payload={**self.payload,'reason':'\U0001f30d'*2000}
        self.assertEqual(self.request('POST','/api/runs/run_pending/reviews',token(),payload)[0],200)

    def test_malformed_oversized_and_wrong_media(self):
        url='/api/runs/run_pending/reviews';key=token()
        self.assertEqual(self.request('POST',url,key,headers={'Content-Type':'application/json'},raw=b'{bad')[0],400)
        self.assertEqual(self.request('POST',url,key,headers={'Content-Type':'application/json'},raw=b'x'*32769)[0],413)
        self.assertEqual(self.request('POST',url,key,headers={'Content-Type':'text/plain'},raw=b'{}')[0],415)

    def test_host_origin_and_query_boundary(self):
        key=token()
        self.assertEqual(self.request('GET','/api/me',key,headers={'Host':'evil.invalid'})[0],403)
        self.assertEqual(self.request('GET','/api/me',key,headers={'Origin':'https://evil.invalid'})[0],403)
        self.assertEqual(self.request('GET','/api/me?token=should-not-work',key)[0],400)

    def test_revocation_and_provider_outage_apply_to_every_request(self):
        key=token();self.assertEqual(self.request('GET','/api/me',key)[0],200)
        self.provider.active=False;self.assertEqual(self.request('GET','/api/me',key)[0],401)
        self.provider.active=True;self.provider.fail=True
        status,body,_=self.request('GET','/api/me',key)
        self.assertEqual(status,503);self.assertEqual(body['error'],'identity_provider_unavailable')

    def test_legacy_review_stays_unverified_and_cannot_be_replaced(self):
        key=token()
        legacy=self.request('GET','/api/runs/run_legacy',key)[1]
        self.assertEqual(legacy['history'][0]['identity']['kind'],'legacy_unverified')
        self.assertEqual(self.request('POST','/api/runs/run_legacy/reviews',key,{**self.payload,'expected_revision':1})[0],409)

    def test_security_headers_no_inline_scripts_or_browser_token_store(self):
        status,body,headers=self.request('GET','/')
        self.assertEqual(status,200);self.assertEqual(headers['Content-Security-Policy'],CSP)
        self.assertNotIn("unsafe-inline",CSP)
        self.assertIn('src="/identity.js"',body)
        for unsafe in ('innerHTML','localStorage','sessionStorage'):
            self.assertNotIn(unsafe,JS)

if __name__=='__main__':unittest.main()
