"""v4 root-signed registry, rotation, revocation, rollback and freshness tests."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

V4 = load("publisher_v4", ROOT/"scripts/offline_publisher_registry_v4.py")
V3 = load("signed_v3", ROOT/"scripts/offline_evidence_package_v3.py")
V2 = load("package_v2", ROOT/"scripts/offline_evidence_package_v2.py")
SAMPLE = load("fixture_v2", ROOT/"tests/test_offline_evidence_package_v2.py")


class PublisherRegistryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name)
        self.root_priv = V3.Ed25519PrivateKey.generate()
        self.signer_priv = V3.Ed25519PrivateKey.generate()
        self.root_key = self.path/"root_private.pem"
        self.root_public = self.path/"root_public.pem"
        self.publisher_key = self.path/"publisher.pem"
        self.package = self.path/"evidence.zip"
        self.signature = self.path/"evidence.sig.json"
        self.registry = self.path/"registry-v1.json"
        self.state = self.path/"recipient-state"
        self.now = datetime(2026, 10, 25, 8, 0, tzinfo=timezone.utc)
        def save_private(obj, path):
            path.write_bytes(obj.private_bytes(V3.serialization.Encoding.PEM,
                V3.serialization.PrivateFormat.PKCS8, V3.serialization.NoEncryption()))
            path.chmod(0o600)
        def save_public(obj, path):
            path.write_bytes(obj.public_key().public_bytes(V3.serialization.Encoding.PEM,
                             V3.serialization.PublicFormat.SubjectPublicKeyInfo))
        save_private(self.root_priv, self.root_key)
        save_public(self.root_priv, self.root_public)
        save_public(self.signer_priv, self.publisher_key)
        self.signer_key = self.path/"publisher-private.pem"
        save_private(self.signer_priv, self.signer_key)
        content=V2.build(SAMPLE.bytes_receipt(), self.now, 48)
        with ZipFile(self.package,"w") as archive:
            for name in V2.NAMES:
                archive.writestr(name, content[name])
        V3.sign(SimpleNamespace(package=self.package,private_key=self.signer_key,
                                signature=self.signature), self.now)
        self.make_registry(1,self.registry)
        self.verify_args=SimpleNamespace(root_public=self.root_public,
                registry=self.registry,state_dir=self.state,package=self.package,
                signature=self.signature)

    def make_registry(self, version, output, previous=None, revoke=None, publisher=None, publisher_pub=None):
        args=SimpleNamespace(root_private=self.root_key,
            publisher_public=publisher_pub or self.publisher_key,
            publisher=publisher or "district_publisher",version=version,
            valid_hours=48,previous_registry=previous,revoke=revoke,output=output)
        return V4.create_registry(args,self.now+timedelta(hours=version-1))

    def test_valid_verified_publisher(self):
        self.assertEqual(V4.verify_package(self.verify_args,self.now+timedelta(hours=1)),0)
        floor=json.loads((self.state/"last_registry.json").read_text())
        self.assertEqual(floor["version"],1)

    def test_unknown_root_rejected(self):
        other=V3.Ed25519PrivateKey.generate()
        key=self.path/"other.pem"
        key.write_bytes(other.public_key().public_bytes(V3.serialization.Encoding.PEM,
                         V3.serialization.PublicFormat.SubjectPublicKeyInfo))
        self.verify_args.root_public=key
        with self.assertRaises(ValueError):
            V4.verify_package(self.verify_args,self.now)

    def test_revoked_publisher_rejected_even_for_old_signature(self):
        self.assertEqual(V4.verify_package(self.verify_args,self.now),0)
        v2=self.path/"registry-v2.json"
        self.make_registry(2,v2,self.registry,V3.key_id(self.signer_priv.public_key()))
        self.verify_args.registry=v2
        with self.assertRaises(ValueError):
            V4.verify_package(self.verify_args,self.now+timedelta(hours=2))
        floor=json.loads((self.state/"last_registry.json").read_text())
        self.assertEqual(floor["version"],2)
        self.verify_args.registry=self.registry
        with self.assertRaises(ValueError):
            V4.verify_package(self.verify_args,self.now+timedelta(hours=2))

    def test_registry_content_tampering_rejected(self):
        doc=json.loads(self.registry.read_text())
        doc["publishers"][0]["status"]="revoked"
        self.registry.write_bytes(V2.canonical(doc))
        with self.assertRaises(Exception):
            V4.verify_package(self.verify_args,self.now)

    def test_registry_expiry_blocks_offline_use(self):
        with self.assertRaises(ValueError):
            V4.verify_package(self.verify_args,self.now+timedelta(hours=73))

    def test_registry_same_version_equivocation_rejected(self):
        self.assertEqual(V4.verify_package(self.verify_args,self.now),0)
        # Signed alternative registry at the SAME version is not permitted.
        different=self.path/"different.json"
        args=SimpleNamespace(root_private=self.root_key,
            publisher_public=self.publisher_key,publisher="district_publisher",
            version=1,valid_hours=24,previous_registry=None,revoke=None,output=different)
        V4.create_registry(args,self.now)
        self.verify_args.registry=different
        with self.assertRaises(ValueError):
            V4.verify_package(self.verify_args,self.now)

    def test_rotation_accepts_new_key_and_invalidates_old(self):
        new_key=V3.Ed25519PrivateKey.generate()
        new_public=self.path/"new-publisher.pem"
        new_public.write_bytes(new_key.public_key().public_bytes(V3.serialization.Encoding.PEM,
                             V3.serialization.PublicFormat.SubjectPublicKeyInfo))
        new_private=self.path/"new-private.pem"
        new_private.write_bytes(new_key.private_bytes(V3.serialization.Encoding.PEM,
                          V3.serialization.PrivateFormat.PKCS8,V3.serialization.NoEncryption()))
        new_private.chmod(0o600)
        updated=self.path/"registry-v2.json"
        self.make_registry(2,updated,self.registry,V3.key_id(self.signer_priv.public_key()),
                           publisher_pub=new_public)
        # An old signed package is blocked by revocation.
        self.verify_args.registry=updated
        with self.assertRaises(ValueError):
            V4.verify_package(self.verify_args,self.now+timedelta(hours=1))
        # v4 accepts a separate fresh package signed by the new publisher.
        new_sig=self.path/"new-package.sig.json"
        V3.sign(SimpleNamespace(package=self.package,private_key=new_private,
                                signature=new_sig),self.now+timedelta(hours=1))
        self.verify_args.signature=new_sig
        self.assertEqual(V4.verify_package(self.verify_args,self.now+timedelta(hours=2)),0)

    def test_malformed_or_insecure_rollback_state_blocks(self):
        self.state.mkdir(mode=0o700)
        (self.state/"last_registry.json").write_text("bad json")
        (self.state/"last_registry.json").chmod(0o600)
        with self.assertRaises((ValueError,json.JSONDecodeError)):
            V4.verify_package(self.verify_args,self.now)
        (self.state/"last_registry.json").unlink()
        self.state.chmod(0o777)
        with self.assertRaises(ValueError):
            V4.verify_package(self.verify_args,self.now)

    def test_revoked_key_cannot_be_reactivated_in_a_later_registry(self):
        self.assertEqual(V4.verify_package(self.verify_args,self.now),0)
        revoked=self.path/"registry-v2.json"
        self.make_registry(2,revoked,self.registry,V3.key_id(self.signer_priv.public_key()))
        self.verify_args.registry=revoked
        with self.assertRaises(ValueError):
            V4.verify_package(self.verify_args,self.now+timedelta(hours=2))
        # A forged but root-signed v3 reactivation must fail against local
        # recipient state, even if its signature and version are valid.
        restored=self.path/"registry-v3.json"
        self.make_registry(3,restored,revoked)
        doc=json.loads(restored.read_text())
        doc["publishers"][0]["status"]="active"
        payload={k:doc[k] for k in doc if k!="signature_b64"}
        import base64
        doc["signature_b64"]=base64.b64encode(
            self.root_priv.sign(V4.REGISTRY_DOMAIN+V4.canonical(payload))).decode()
        restored.write_bytes(V4.canonical(doc))
        self.verify_args.registry=restored
        with self.assertRaises(ValueError):
            V4.verify_package(self.verify_args,self.now+timedelta(hours=3))

    def test_writable_root_anchor_is_rejected(self):
        self.root_public.chmod(0o666)
        with self.assertRaises(ValueError):
            V4.verify_package(self.verify_args,self.now)

    def test_invalid_registry_signed_issuer_not_auto_trusted(self):
        doc=json.loads(self.registry.read_text())
        doc["root_key_id"]="f"*64
        self.registry.write_bytes(V2.canonical(doc))
        with self.assertRaises(ValueError):
            V4.verify_package(self.verify_args,self.now)


if __name__ == "__main__":
    unittest.main()
