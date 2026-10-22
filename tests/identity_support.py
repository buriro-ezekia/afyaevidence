"""Synthetic v2 database and signing keys for isolated integration tests only."""
import base64
from functools import lru_cache
import json
from pathlib import Path
import sqlite3
import time
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
from afyaevidence.identity_auth import IdentityConfig, IdentityError, OIDCVerifier

ISSUER = 'https://identity.example.invalid/realm'
AUDIENCE = 'afya-review'

@lru_cache(maxsize=1)
def signing_keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = private.public_key().public_numbers()
    enc = lambda n: base64.urlsafe_b64encode(n.to_bytes((n.bit_length()+7)//8, 'big')).rstrip(b'=').decode()
    public = dict(kty='RSA', alg='RS256', use='sig', kid='test-key', n=enc(numbers.n), e=enc(numbers.e))
    return private, public


def token(roles=None, subject='reviewer-1', changes=None, headers=None, key=None):
    now = int(time.time())
    claims = dict(iss=ISSUER, aud=AUDIENCE, sub=subject, jti='test-id', iat=now-1, nbf=now-1,
                  exp=now+299, roles=['reviewer'] if roles is None else roles)
    claims.update(changes or {})
    head = dict(kid='test-key', typ='at+jwt')
    head.update(headers or {})
    return jwt.encode(claims, key or signing_keys()[0], algorithm='RS256', headers=head)


class Transport:
    active = True
    fail = False
    def __init__(self):
        self.jwks = {'keys': [signing_keys()[1]]}
        self.active = True
        self.fail = False
        self.introspection_override = {}
        self.calls = []

    def json(self, url, *, body=None, headers=None):
        if self.fail:
            raise IdentityError('identity_provider_unavailable', 503)
        self.calls.append(url)
        if body is None:
            return self.jwks
        from urllib.parse import parse_qs
        encoded = parse_qs(body.decode())['token'][0]
        payload = encoded.split('.')[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + '='*(-len(payload)%4)))
        # Provider-side fixture only. Application verification is never disabled.
        return {'active': self.active, **{k: claims[k] for k in ('iss','aud','sub','exp')}, **self.introspection_override}


def verifier():
    transport = Transport()
    config = IdentityConfig(ISSUER, AUDIENCE, ISSUER + '/keys', ISSUER + '/introspect', 'test-client')
    return OIDCVerifier(config, 'test-only-not-a-real-secret', transport=transport), transport


def v2_database(path: Path):
    db = sqlite3.connect(path)
    db.executescript('''
    PRAGMA user_version=2;
    CREATE TABLE runs(run_id TEXT PRIMARY KEY,receipt_path TEXT NOT NULL UNIQUE,receipt_sha256 TEXT NOT NULL,
      snapshot_id TEXT NOT NULL,candidate_json TEXT NOT NULL,evidence_json TEXT NOT NULL,created_at TEXT NOT NULL,
      revision INTEGER NOT NULL DEFAULT 0,disposition TEXT,execution_json TEXT,provenance_status TEXT NOT NULL);
    CREATE TABLE reviews(run_id TEXT NOT NULL,revision INTEGER NOT NULL,event_key TEXT NOT NULL,reviewer TEXT NOT NULL,
      disposition TEXT NOT NULL,reason TEXT NOT NULL,at TEXT NOT NULL,PRIMARY KEY(run_id,revision),UNIQUE(run_id,event_key),
      FOREIGN KEY(run_id) REFERENCES runs(run_id));
    ''')
    candidate = dict(approval=None,review_status='awaiting_human_review',semantic_review_required=True,
                     summary='Synthetic reporting artefact',limitations=['synthetic_data','no_causal_attribution'])
    metrics = [dict(period=p,view=v,name=n,cohort='all_available',availability='available',value=val)
        for p in ('comparison','target') for v,n,val in [('canonical','positive_total',100),
        ('canonical','tested_total',500),('canonical','positivity_pct',20),('raw_diagnostic','positive_total',100 if p=='comparison' else 120)]]
    evidence = dict(metrics=metrics,evidence_records=[],snapshot_id='ss_test')
    execution = dict(data_mode='zetaris',model_mode='ollama',model='qwen2.5:1.5b',memory_mode='hmem_reference',execution_profile='cpu')
    for run in ('run_pending','run_legacy'):
        db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?,?,?)',(run,str(path.parent/(run+'.json')),'a'*64,'ss_test',
            json.dumps(candidate),json.dumps(evidence),'2026-10-22T10:00:00Z',0,None,json.dumps(execution),'receipt_top_level'))
    db.execute("UPDATE runs SET revision=1,disposition='accept' WHERE run_id='run_legacy'")
    db.execute('INSERT INTO reviews VALUES(?,?,?,?,?,?,?)',('run_legacy',1,'old-event','local_operator','accept',
        'Synthetic evidence accepted for review only.','2026-10-22T10:01:00Z'))
    db.commit()
    db.close()
