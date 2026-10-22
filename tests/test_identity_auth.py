import base64
import json
from pathlib import Path
import sys
import time
import unittest
from cryptography.hazmat.primitives.asymmetric import rsa
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from afyaevidence.identity_auth import IdentityError, IdentityConfig, Principal, strict_json
from identity_support import token, verifier, signing_keys, ISSUER, AUDIENCE


class IdentityAuthTests(unittest.TestCase):
    def setUp(self):
        self.v, self.transport = verifier()

    def rejected(self, value):
        with self.assertRaises(IdentityError): self.v.verify(value)

    def test_signed_access_token_identity_and_roles(self):
        p = self.v.verify(token(['viewer','reviewer']))
        self.assertEqual(p.subject,'reviewer-1')
        self.assertEqual(p.roles,('reviewer','viewer'))
        self.assertEqual(len(self.transport.calls),2)

    def test_wrong_issuer_and_audience(self):
        for changes in ({'iss':ISSUER+'/other'},{'aud':'another'},{'aud':[AUDIENCE]}):
            with self.subTest(changes=changes): self.rejected(token(changes=changes))

    def test_expired_and_future_tokens(self):
        now=int(time.time())
        for change in ({'exp':now-5},{'nbf':now+100},{'iat':now+100}):
            with self.subTest(change=change): self.rejected(token(changes=change))

    def test_missing_nbf_uses_signed_iat_without_disabling_time_guards(self):
        import jwt
        now = int(time.time())
        claims = dict(iss=ISSUER, aud=AUDIENCE, sub='viewer-1',
                      jti='missing-nbf', iat=now-1, exp=now+299,
                      roles=['viewer'])
        def signed(**overrides):
            values = {**claims, **overrides}
            return jwt.encode(values, signing_keys()[0], algorithm='RS256',
                              headers={'kid':'test-key','typ':'at+jwt'})
        principal = self.v.verify(signed())
        self.assertEqual(principal.roles, ('viewer',))
        self.assertEqual(len(self.transport.calls), 2)
        for change in ({'iat':now+90}, {'exp':now-10},
                       {'iat':now-901}, {'nbf':now+90},
                       {'nbf':None}, {'nbf':True}, {'nbf':now-100}):
            with self.subTest(change=change):
                self.rejected(signed(**change))

    def test_wrong_signature(self):
        self.rejected(token(key=rsa.generate_private_key(public_exponent=65537,key_size=2048)))

    def test_wrong_type_and_algorithm(self):
        self.rejected(token(headers={'typ':'JWT'}))
        import jwt
        self.rejected(jwt.encode({'sub':'attack'},'not-a-real-test-key'*3,algorithm='HS256',headers={'kid':'test-key','typ':'at+jwt'}))

    def test_no_remote_key_header_or_critical_extension(self):
        for header in ({'jku':'https://evil.invalid/keys'},{'crit':['x']},{'x5u':'https://evil.invalid/key'}):
            with self.subTest(header=header): self.rejected(token(headers=header))

    def test_duplicate_json_rejected(self):
        with self.assertRaises(ValueError): strict_json('{"iss":"one","iss":"two"}')
        with self.assertRaises(ValueError): strict_json('{"x":NaN}')

    def test_missing_identity_and_timestamp_fields(self):
        for field in ('sub','jti','iat','nbf','exp'):
            with self.subTest(field=field): self.rejected(token(changes={field:None}))

    def test_non_integer_times_and_excessive_lifetime(self):
        for change in ({'iat':True},{'nbf':float(int(time.time())-1)},{'exp':int(time.time())+5000}):
            with self.subTest(change=change): self.rejected(token(changes=change))

    def test_roles_fail_closed(self):
        for roles in ([],['unknown'],'reviewer',[1]):
            with self.subTest(roles=roles): self.rejected(token(roles=roles))

    def test_admin_cannot_implicitly_review(self):
        p=self.v.verify(token(['administrator']))
        p.require('recover')
        p.require('read')
        with self.assertRaises(IdentityError): p.require('review')

    def test_revoked_token_denied(self):
        self.transport.active=False
        self.rejected(token())

    def test_provider_outage_denied_not_empty_success(self):
        self.transport.fail=True
        with self.assertRaises(IdentityError) as ctx:self.v.verify(token())
        self.assertEqual(ctx.exception.status,503)

    def test_duplicate_and_unknown_kid(self):
        self.rejected(token(headers={'kid':'unknown'}))
        self.transport.jwks['keys'] *= 2
        self.rejected(token())

    def test_wrong_key_purpose(self):
        self.transport.jwks={'keys':[{**signing_keys()[1],'use':'enc'}]}
        self.rejected(token())

    def test_issuer_subject_actor_binding(self):
        a=Principal(ISSUER,'person',('reviewer',))
        self.assertNotEqual(a.actor_id,Principal(ISSUER+'/another','person',('reviewer',)).actor_id)
        self.assertEqual(a.actor_id,Principal(ISSUER,'person',('viewer',)).actor_id)

    def test_configuration_no_http_or_inline_credentials(self):
        for uri in ('http://identity.invalid','https://user:pass@identity.invalid','https://identity.invalid/#fragment'):
            with self.subTest(uri=uri),self.assertRaises(ValueError):
                IdentityConfig(uri,AUDIENCE,ISSUER+'/keys',ISSUER+'/introspect','client')

    def test_oversized_and_malformed_tokens(self):
        for val in ('x'*20000,'',None,'one.two','one.two.###'):
            with self.subTest(value_type=type(val).__name__):self.rejected(val)

if __name__=='__main__':unittest.main()
