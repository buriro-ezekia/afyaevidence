"""Additive identity/audit tables over a *copy* of the existing v2 review DB.

Existing candidate/evidence/history rows are never relabelled or overwritten.
An identity service database rejects new anonymous review inserts.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3

from .identity_auth import Principal

ID = re.compile(r'^[A-Za-z0-9_-]{1,100}$')
DECISIONS = {'accept', 'request_more_evidence', 'reject'}


def now():
    return datetime.now(timezone.utc).isoformat()


def connect(path: Path):
    path = path.resolve(strict=True)
    db = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=10, isolation_level=None)
    try:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=10000')
        if db.execute('PRAGMA user_version').fetchone()[0] != 2:
            raise ValueError('review_schema_v2_required')
        required = {'execution_json', 'provenance_status', 'candidate_json', 'evidence_json', 'revision'}
        if not required <= {row[1] for row in db.execute('PRAGMA table_info(runs)')}:
            raise ValueError('review_schema_v2_required')
        # No migration of original reviews: absence of a grant means legacy unverified identity.
        db.execute('BEGIN IMMEDIATE')
        for sql in (
            '''CREATE TABLE IF NOT EXISTS identity_extension (version INTEGER PRIMARY KEY CHECK(version=1))''',
            '''CREATE TABLE IF NOT EXISTS verified_actors (
                actor_id TEXT PRIMARY KEY, issuer TEXT NOT NULL, subject TEXT NOT NULL,
                created_at TEXT NOT NULL, UNIQUE(issuer,subject))''',
            '''CREATE TABLE IF NOT EXISTS verified_review_grants (
                run_id TEXT NOT NULL, revision INTEGER NOT NULL,
                actor_id TEXT NOT NULL REFERENCES verified_actors(actor_id),
                roles_json TEXT NOT NULL, authenticated_at TEXT NOT NULL,
                PRIMARY KEY(run_id,revision),
                FOREIGN KEY(run_id,revision) REFERENCES reviews(run_id,revision))''',
            '''CREATE TRIGGER IF NOT EXISTS identity_reviews_require_actor
                BEFORE INSERT ON reviews WHEN NOT EXISTS (
                    SELECT 1 FROM verified_actors WHERE actor_id=NEW.reviewer)
                BEGIN SELECT RAISE(ABORT,'verified_actor_required'); END''',
            '''CREATE TRIGGER IF NOT EXISTS identity_reviews_no_update BEFORE UPDATE ON reviews
                BEGIN SELECT RAISE(ABORT,'immutable_review'); END''',
            '''CREATE TRIGGER IF NOT EXISTS identity_reviews_no_delete BEFORE DELETE ON reviews
                BEGIN SELECT RAISE(ABORT,'immutable_review'); END''',
            '''CREATE TRIGGER IF NOT EXISTS identity_actors_no_update BEFORE UPDATE ON verified_actors
                BEGIN SELECT RAISE(ABORT,'immutable_actor'); END''',
            '''CREATE TRIGGER IF NOT EXISTS identity_actors_no_delete BEFORE DELETE ON verified_actors
                BEGIN SELECT RAISE(ABORT,'immutable_actor'); END''',
            '''CREATE TRIGGER IF NOT EXISTS identity_grants_no_update BEFORE UPDATE ON verified_review_grants
                BEGIN SELECT RAISE(ABORT,'immutable_grant'); END''',
            '''CREATE TRIGGER IF NOT EXISTS identity_grants_no_delete BEFORE DELETE ON verified_review_grants
                BEGIN SELECT RAISE(ABORT,'immutable_grant'); END''',
            '''INSERT OR IGNORE INTO identity_extension VALUES(1)''',
        ):
            db.execute(sql)
        db.execute('COMMIT')
        return db
    except BaseException:
        if db.in_transaction:
            db.execute('ROLLBACK')
        db.close()
        raise


def valid_id(value):
    return isinstance(value, str) and ID.fullmatch(value) is not None


def get_run(db, run_id):
    if not valid_id(run_id):
        raise ValueError('invalid_run')
    db.execute('BEGIN')
    try:
        row = db.execute('''SELECT snapshot_id,receipt_sha256,candidate_json,evidence_json,
            revision,disposition,execution_json,provenance_status FROM runs WHERE run_id=?''', (run_id,)).fetchone()
        if row is None:
            raise ValueError('unknown_run')
        history = []
        for h in db.execute('''SELECT r.revision,r.reviewer,r.disposition,r.reason,r.at,
                a.issuer,a.subject,g.roles_json,g.authenticated_at
                FROM reviews r LEFT JOIN verified_review_grants g
                ON g.run_id=r.run_id AND g.revision=r.revision
                LEFT JOIN verified_actors a ON a.actor_id=g.actor_id
                WHERE r.run_id=? ORDER BY r.revision''', (run_id,)):
            identity = (dict(kind='verified_oidc', issuer=h[5], subject=h[6], roles=json.loads(h[7]), authenticated_at=h[8])
                        if h[5] is not None else dict(kind='legacy_unverified', label=h[1]))
            history.append(dict(revision=h[0], reviewer=h[1], disposition=h[2], reason=h[3], at=h[4], identity=identity))
        return dict(run_id=run_id, snapshot_id=row[0], receipt_sha256=row[1],
                    candidate=json.loads(row[2]), evidence=json.loads(row[3]), revision=row[4], disposition=row[5],
                    execution=json.loads(row[6]) if row[6] else {}, provenance_status=row[7], history=history)
    finally:
        db.execute('ROLLBACK')


def review(db, *, principal: Principal, run_id, expected_revision, event_key, disposition, reason):
    principal.require('review')
    if not valid_id(run_id) or not valid_id(event_key):
        raise ValueError('invalid_identifier')
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError('invalid_revision')
    if not isinstance(disposition, str) or disposition not in DECISIONS:
        raise ValueError('invalid_disposition')
    if not isinstance(reason, str) or not 10 <= len(reason.strip()) <= 2000:
        raise ValueError('reason_required')
    try:
        reason = reason.strip()
        reason.encode('utf-8')
    except UnicodeError:
        raise ValueError('invalid_reason_unicode') from None
    db.execute('BEGIN IMMEDIATE')
    try:
        row = db.execute('SELECT revision,disposition FROM runs WHERE run_id=?', (run_id,)).fetchone()
        if row is None:
            raise ValueError('unknown_run')
        prior = db.execute('''SELECT revision,disposition,reason,reviewer FROM reviews
            WHERE run_id=? AND event_key=?''', (run_id, event_key)).fetchone()
        if prior:
            if prior != (expected_revision + 1, disposition, reason, principal.actor_id):
                raise ValueError('idempotency_conflict')
            result = dict(run_id=run_id, revision=prior[0], disposition=disposition, replayed=True)
        else:
            if row[1] is not None:
                raise ValueError('already_reviewed')
            if row[0] != expected_revision:
                raise ValueError('revision_conflict')
            stamp = now()
            actor = db.execute('SELECT issuer,subject FROM verified_actors WHERE actor_id=?', (principal.actor_id,)).fetchone()
            if actor and actor != (principal.issuer, principal.subject):
                raise ValueError('actor_identity_conflict')
            if not actor:
                db.execute('INSERT INTO verified_actors VALUES(?,?,?,?)',
                           (principal.actor_id, principal.issuer, principal.subject, stamp))
            revision = expected_revision + 1
            db.execute('INSERT INTO reviews VALUES(?,?,?,?,?,?,?)',
                       (run_id, revision, event_key, principal.actor_id, disposition, reason, stamp))
            db.execute('INSERT INTO verified_review_grants VALUES(?,?,?,?,?)',
                       (run_id, revision, principal.actor_id, json.dumps(list(principal.roles)), stamp))
            db.execute('UPDATE runs SET revision=?,disposition=? WHERE run_id=? AND revision=?',
                       (revision, disposition, run_id, expected_revision))
            result = dict(run_id=run_id, revision=revision, disposition=disposition, replayed=False)
        db.execute('COMMIT')
        return result
    except BaseException:
        db.execute('ROLLBACK')
        raise


def copy_database(source: Path, destination: Path):
    """SQLite backup, including committed WAL data; never overwrite either file."""
    import os
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if destination == source:
        raise ValueError('separate_database_required')
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src:
            with closing(sqlite3.connect(destination)) as dst:
                src.backup(dst)
        with closing(connect(destination)):
            pass
    except BaseException:
        # Retain failed backup for inspection, never delete user state automatically.
        raise
    return destination
