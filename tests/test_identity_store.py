from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from afyaevidence.identity_auth import Principal,IdentityError
from afyaevidence import identity_store as store
from identity_support import v2_database, ISSUER


class IdentityStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'reviews.db';v2_database(self.path)
        self.p=Principal(ISSUER,'reviewer-a',('reviewer',))
        self.args=dict(run_id='run_pending',expected_revision=0,event_key='one',disposition='accept',reason='Synthetic evidence reviewed carefully.')

    def test_migration_preserves_legacy_identity_and_metadata(self):
        with closing(sqlite3.connect(self.path)) as db:before=db.execute('SELECT * FROM reviews').fetchall()
        with closing(store.connect(self.path)) as db:
            data=store.get_run(db,'run_legacy')
            self.assertEqual(db.execute('SELECT * FROM reviews').fetchall(),before)
            self.assertEqual(data['history'][0]['identity']['kind'],'legacy_unverified')
            self.assertEqual(data['execution']['memory_mode'],'hmem_reference')
            self.assertEqual(data['revision'],1)
            self.assertIsNone(data['candidate']['approval'])

    def test_verified_identity_recorded_and_replay_bound(self):
        with closing(store.connect(self.path)) as db:
            store.review(db,principal=self.p,**self.args)
            self.assertTrue(store.review(db,principal=self.p,**self.args)['replayed'])
            data=store.get_run(db,'run_pending')
            self.assertEqual(data['history'][0]['identity']['subject'],'reviewer-a')
            self.assertEqual(data['history'][0]['identity']['kind'],'verified_oidc')
            with self.assertRaisesRegex(ValueError,'idempotency_conflict'):
                store.review(db,principal=Principal(ISSUER,'reviewer-b',('reviewer',)),**self.args)

    def test_viewer_and_admin_cannot_review(self):
        with closing(store.connect(self.path)) as db:
            for role in ('viewer','administrator'):
                with self.subTest(role=role),self.assertRaises(IdentityError):
                    store.review(db,principal=Principal(ISSUER,'p',(role,)),**self.args)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM verified_actors').fetchone()[0],0)

    def test_source_backup_unchanged_and_destination_not_overwritten(self):
        before=sha256(self.path.read_bytes()).hexdigest()
        target=self.root/'identity.db';store.copy_database(self.path,target)
        self.assertEqual(sha256(self.path.read_bytes()).hexdigest(),before)
        with self.assertRaises(FileExistsError):store.copy_database(self.path,target)
        with closing(store.connect(target)) as db:self.assertEqual(store.get_run(db,'run_legacy')['disposition'],'accept')

    def test_concurrent_reviewers_retain_one_grant(self):
        with closing(store.connect(self.path)):pass
        def submit(name):
            with closing(store.connect(self.path)) as db:
                try:return store.review(db,principal=Principal(ISSUER,name,('reviewer',)),**{**self.args,'event_key':name})
                except ValueError:return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(submit,['person1','person2']))
        self.assertEqual(sum(x is not None for x in results),1)
        with closing(store.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM verified_review_grants').fetchone()[0],1)

    def test_append_only_and_no_new_local_operator_writes(self):
        with closing(store.connect(self.path)) as db:
            for sql in ("DELETE FROM reviews", "UPDATE reviews SET reason='changed'", "INSERT INTO reviews VALUES('run_pending',1,'bad','local_operator','accept','bad reason','now')"):
                with self.subTest(sql=sql),self.assertRaises(sqlite3.IntegrityError):db.execute(sql)

    def test_invalid_values_never_create_identity(self):
        with closing(store.connect(self.path)) as db:
            for change in ({'expected_revision':True},{'reason':'short'},{'disposition':'approve_clinical'},{'event_key':'../oops'}):
                with self.subTest(change=change),self.assertRaises(ValueError):store.review(db,principal=self.p,**{**self.args,**change})

    def test_missing_database_and_wrong_schema_fail_closed(self):
        with self.assertRaises(FileNotFoundError):store.connect(self.root/'missing.db')
        with closing(sqlite3.connect(self.path)) as db:db.execute('PRAGMA user_version=3')
        with self.assertRaisesRegex(ValueError,'review_schema_v2_required'):store.connect(self.path)

if __name__=='__main__':unittest.main()
