"""Offline publisher signature tests: trusted key, tampering, expiry, key policy."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

V3 = module("v3_signature", ROOT/"scripts/offline_evidence_package_v3.py")
V2 = module("v2_fixture", ROOT/"scripts/offline_evidence_package_v2.py")
DATA = module("v2_test_sample", ROOT/"tests/test_offline_evidence_package_v2.py")


class SignedPackagesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.keys = self.path/"keys"
        self.keys.mkdir(mode=0o700)
        self.trust = self.path/"trusted-publishers"
        self.trust.mkdir(mode=0o700)
        self.private = self.keys/"signer-private.pem"
        self.public = self.keys/"signer-public.pem"
        self.assertEqual(V3.keygen(SimpleNamespace(private_key=self.private, public_key=self.public)), 0)
        pub = V3.load_public(self.public)
        self.kid = V3.key_id(pub)
        (self.trust/(self.kid+".pem")).write_bytes(self.public.read_bytes())
        self.at = datetime.now(timezone.utc)
        self.package = self.path/"package.zip"
        files = V2.build(DATA.bytes_receipt(), self.at, 48)
        with ZipFile(self.package,"w") as z:
            for name in V2.NAMES:
                z.writestr(name,files[name])
        self.sig = self.path/"package.sig.json"
        self.sign_args = SimpleNamespace(package=self.package, private_key=self.private, signature=self.sig)
        self.verify_args = SimpleNamespace(package=self.package, signature=self.sig, trust_dir=self.trust)

    def test_valid_signature_and_trusted_key(self):
        self.assertEqual(V3.sign(self.sign_args, self.at),0)
        self.assertEqual(V3.verify(self.verify_args,self.at+timedelta(hours=1)),0)
        self.assertEqual(V3.verify(self.verify_args,self.at+timedelta(hours=49)),3)

    def test_modified_zip_rejected(self):
        V3.sign(self.sign_args,self.at)
        self.package.write_bytes(self.package.read_bytes()+b"tampered")
        with self.assertRaises(ValueError):
            V3.verify(self.verify_args,self.at)

    def test_signature_tampering_rejected(self):
        V3.sign(self.sign_args,self.at)
        doc=json.loads(self.sig.read_text())
        doc["signed_at_utc"]=(self.at+timedelta(seconds=5)).isoformat()
        self.sig.write_bytes(V3.canonical(doc))
        with self.assertRaises(Exception):
            V3.verify(self.verify_args,self.at+timedelta(seconds=10))

    def test_unknown_publisher_rejected(self):
        V3.sign(self.sign_args,self.at)
        empty=self.path/"unknown";empty.mkdir()
        with self.assertRaises((ValueError,OSError)):
            V3.verify(SimpleNamespace(package=self.package,signature=self.sig,trust_dir=empty),self.at)

    def test_mismatched_trusted_key_rejected(self):
        V3.sign(self.sign_args,self.at)
        other=V3.Ed25519PrivateKey.generate().public_key()
        dest=self.trust/(self.kid+".pem")
        dest.write_bytes(other.public_bytes(V3.serialization.Encoding.PEM,
                            V3.serialization.PublicFormat.SubjectPublicKeyInfo))
        with self.assertRaises(ValueError):
            V3.verify(self.verify_args,self.at)

    def test_private_key_insecure_permissions_refused(self):
        self.private.chmod(0o644)
        with self.assertRaises(ValueError):
            V3.sign(self.sign_args,self.at)

    def test_existing_signature_cannot_be_overwritten(self):
        V3.sign(self.sign_args,self.at)
        before=self.sig.read_bytes()
        with self.assertRaises(ValueError):
            V3.sign(self.sign_args,self.at)
        self.assertEqual(before,self.sig.read_bytes())

    def test_signature_cannot_misrepresent_publisher_key(self):
        V3.sign(self.sign_args,self.at)
        doc=json.loads(self.sig.read_text())
        doc["key_id"]="f"*64
        self.sig.write_bytes(V3.canonical(doc))
        with self.assertRaises((ValueError,OSError)):
            V3.verify(self.verify_args,self.at)

    def test_world_writable_trust_directory_is_rejected(self):
        V3.sign(self.sign_args,self.at)
        self.trust.chmod(0o777)
        with self.assertRaises(ValueError):
            V3.verify(self.verify_args,self.at)

    def test_public_key_symlink_is_rejected(self):
        V3.sign(self.sign_args,self.at)
        public = self.trust/(self.kid+".pem")
        public.unlink()
        public.symlink_to(self.public)
        with self.assertRaises(ValueError):
            V3.verify(self.verify_args,self.at)

    def test_malformed_base64_signature_is_rejected(self):
        V3.sign(self.sign_args,self.at)
        doc=json.loads(self.sig.read_text())
        doc["signature_b64"]="not-ASCII!-%%%="
        self.sig.write_bytes(V3.canonical(doc))
        with self.assertRaises(Exception):
            V3.verify(self.verify_args,self.at)

    def test_future_signature_time_rejected(self):
        V3.sign(self.sign_args,self.at)
        with self.assertRaises(ValueError):
            V3.verify(self.verify_args,self.at-timedelta(minutes=10))

if __name__ == "__main__":
    unittest.main()
