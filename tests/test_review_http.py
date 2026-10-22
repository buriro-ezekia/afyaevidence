"""Live loopback HTTP checks; no external services or credentials."""
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
import http.client
import json
import sys
import threading
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from afyaevidence.review_server import connect, handler_factory, import_receipt

@contextmanager
def server(db_path, token):
    httpd=ThreadingHTTPServer(("127.0.0.1",0),handler_factory(db_path,token))
    worker=threading.Thread(target=httpd.serve_forever,daemon=True)
    worker.start()
    try:
        yield httpd.server_address[1]
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=3)

def request(port, method, path, token=None, payload=None):
    conn=http.client.HTTPConnection("127.0.0.1",port,timeout=3)
    headers={}
    if token is not None:headers["Authorization"]="Bearer "+token
    body=None
    if payload is not None:
        headers["Content-Type"]="application/json"
        body=json.dumps(payload)
    conn.request(method,path,body=body,headers=headers)
    response=conn.getresponse()
    value=response.read()
    status=response.status
    conn.close()
    return status,json.loads(value) if value and response.getheader("Content-Type","").startswith("application/json") else value

class HttpReviewTests(unittest.TestCase):
    def test_unauthenticated_invalid_token_and_valid_reviewer_flow(self):
        with TemporaryDirectory() as d:
            base=Path(d)
            receipt=base/"r.json"
            receipt.write_text(json.dumps(dict(
                run_id="run_http",execution_status="ready_for_review",
                evidence_bundle=dict(snapshot_id="snapshot_http",metrics=[],evidence_records=[]),
                candidate_brief=dict(approval=None,review_status="awaiting_human_review",
                                     semantic_review_required=True,summary="Synthetic review"))))
            dbfile=base/"db.sqlite3"
            with connect(dbfile) as db:import_receipt(db,receipt,root=base)
            token="s"*48
            with server(dbfile,token) as port:
                url="/api/runs/run_http"
                self.assertEqual(request(port,"GET",url)[0],401)
                self.assertEqual(request(port,"GET",url,"wrong")[0],401)
                self.assertEqual(request(port,"GET",url,token)[0],200)
                payload=dict(expected_revision=0,event_key="http_event",disposition="accept",
                             reason="Synthetic evidence was reviewed by local operator.")
                self.assertEqual(request(port,"POST",url+"/reviews",None,payload)[0],401)
                self.assertEqual(request(port,"POST",url+"/reviews",token,payload)[0],200)
                self.assertTrue(request(port,"POST",url+"/reviews",token,payload)[1]["replayed"])
                self.assertEqual(request(port,"POST",url+"/reviews",token,{**payload,"event_key":"other"})[0],409)
                status,body=request(port,"GET",url,token)
                self.assertEqual(status,200)
                self.assertEqual(body["revision"],1)
                self.assertEqual(len(body["history"]),1)
                self.assertIsNone(body["candidate"]["approval"])

if __name__=="__main__":unittest.main()
