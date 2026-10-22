"""POSIX host-only reviewed-note outbox and scoped Meterless H-MEM client.

Only recall may later be model-visible. Writes require a persisted review event.
"""
from __future__ import annotations

from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import sqlite3
import subprocess
import time
import uuid

from .contracts import normalise
from .snapshot import digest

PIN = '1742dec56a66e58eef9dda2d2b865823758ca8cd'


class MemoryError(RuntimeError):
    """Unavailable or invalid memory must remain visible, never an empty success."""


@dataclass(frozen=True)
class Scope:
    dataset_family: str
    district_id: str

    def __post_init__(self):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,60}', self.dataset_family) or not re.fullmatch(r'D[0-9]{3}', self.district_id):
            raise ValueError('Invalid memory scope')

    @property
    def key(self):
        return digest([self.dataset_family, self.district_id])


class ReviewStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS memory_reviews (
                review_id TEXT PRIMARY KEY, scope TEXT NOT NULL, payload TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS memory_outbox (
                review_id TEXT PRIMARY KEY REFERENCES memory_reviews(review_id), memory_id TEXT);
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def record_reviewed_note(self, *, scope, review_id, snapshot_id, analysis_id,
                             note, reviewed_at_utc, reviewer):
        # Host/operator API, never an agent tool. Actor identity here is asserted,
        # not an authenticated clinical identity; future review UI supplies it.
        normalise(reviewed_at_utc, 'timestamp')
        if (not re.fullmatch(r'rv_[0-9a-f]{32}', review_id) or
            not re.fullmatch(r'ss_[0-9a-f]{64}', snapshot_id) or
            not re.fullmatch(r'an_[0-9a-f]{64}', analysis_id) or
            not isinstance(note, str) or not 1 <= len(note) <= 2000 or
            not isinstance(reviewer, str) or not 1 <= len(reviewer) <= 100):
            raise ValueError('Invalid reviewed-note event')
        payload = dict(scope=scope.key, review_id=review_id, snapshot_id=snapshot_id,
                       analysis_id=analysis_id, content=note, reviewed_at_utc=reviewed_at_utc,
                       reviewer=reviewer, decision='accepted_for_follow_up',
                       source='afya-review:'+review_id)
        encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT payload FROM memory_reviews WHERE review_id=?', (review_id,)).fetchone()
            if existing:
                if existing[0] != encoded:
                    raise MemoryError('Conflicting review ID')
            else:
                if db.execute('SELECT COUNT(*) FROM memory_reviews WHERE scope=?', (scope.key,)).fetchone()[0] >= 100:
                    raise MemoryError('Memory scope event limit exceeded')
                db.execute('INSERT INTO memory_reviews VALUES (?,?,?)', (review_id, scope.key, encoded))
                db.execute('INSERT INTO memory_outbox(review_id) VALUES (?)', (review_id,))
        return review_id

    def events(self, scope):
        with self.db() as db:
            rows = db.execute('SELECT payload FROM memory_reviews WHERE scope=? ORDER BY review_id', (scope.key,)).fetchall()
        if len(rows) > 100:
            raise MemoryError('Memory scope event limit exceeded')
        return [json.loads(row[0]) for row in rows]

    def receipts(self, scope):
        with self.db() as db:
            return dict(db.execute('SELECT r.review_id,o.memory_id FROM memory_reviews r JOIN memory_outbox o ON r.review_id=o.review_id WHERE r.scope=? AND o.memory_id IS NOT NULL', (scope.key,)))

    def pending(self, scope):
        with self.db() as db:
            ids = {r[0] for r in db.execute('SELECT r.review_id FROM memory_reviews r JOIN memory_outbox o ON r.review_id=o.review_id WHERE r.scope=? AND o.memory_id IS NULL', (scope.key,))}
        return [e for e in self.events(scope) if e['review_id'] in ids]

    def acknowledge(self, review_id, memory_id):
        with self.db() as db:
            row = db.execute('SELECT memory_id FROM memory_outbox WHERE review_id=?', (review_id,)).fetchone()
            if row is None or row[0] not in (None, memory_id):
                raise MemoryError('Unknown or conflicting outbox receipt')
            db.execute('UPDATE memory_outbox SET memory_id=? WHERE review_id=?', (memory_id, review_id))


def verify_upstream(bridge_dir):
    try:
        lock = json.loads((bridge_dir / 'upstream.lock.json').read_text())
        if lock['commit'] != PIN or lock['license'] != 'Apache-2.0':
            raise MemoryError('Unexpected H-MEM revision')
        for file, sha in lock['files'].items():
            if Path(file).is_absolute() or '..' in Path(file).parts:
                raise MemoryError('Invalid upstream lock path')
            if hashlib.sha256((bridge_dir/'upstream'/file).read_bytes()).hexdigest() != sha:
                raise MemoryError('Pinned upstream source differs')
    except (ValueError, KeyError, OSError):
        raise MemoryError('Cannot verify pinned H-MEM source') from None


class HmemBridge:
    def __init__(self, *, root, bridge_dir, scope, reviews, node='node', timeout=10):
        self.root, self.bridge_dir = Path(root).resolve(), Path(bridge_dir).resolve()
        self.scope, self.reviews, self.node, self.timeout = scope, reviews, node, timeout
        self.directory = self.root / scope.key
        self.process = self.lock = None
        self.buffer = b''

    def __enter__(self):
        try:
            verify_upstream(self.bridge_dir)
            self.directory.mkdir(parents=True, exist_ok=True)
            self.lock = (self.directory / '.scope.lock').open('a+b')
            deadline = time.monotonic() + self.timeout
            while True:
                try:
                    fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise MemoryError('Memory scope lock unavailable')
                    time.sleep(0.02)
            self.process = subprocess.Popen([self.node, '--experimental-transform-types',
                str(self.bridge_dir/'helper.mjs'), str(self.directory)], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
            health = self._request('health', {})
            if health.get('commit') != PIN:
                raise MemoryError('Wrong H-MEM engine revision')
            self._validated_audit()
            return self
        except BaseException as exc:
            self.close()
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise MemoryError('H-MEM unavailable, corrupt or scope locked; no fallback') from None

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
            finally:
                for stream in (self.process.stdin, self.process.stdout):
                    if stream:
                        with suppress(OSError): stream.close()
                self.process = None
        if self.lock:
            fcntl.flock(self.lock.fileno(), fcntl.LOCK_UN)
            self.lock.close()
            self.lock = None

    def _request(self, op, args):
        if self.process is None:
            raise MemoryError('Memory helper is not running')
        request_id = uuid.uuid4().hex
        encoded = (json.dumps(dict(id=request_id, op=op, args=args), separators=(',', ':'))+'\n').encode()
        if len(encoded) > 65536:
            raise MemoryError('Request size exceeded')
        try:
            self.process.stdin.write(encoded)
            self.process.stdin.flush()
            deadline = time.monotonic() + self.timeout
            with selectors.DefaultSelector() as selector:
                selector.register(self.process.stdout, selectors.EVENT_READ)
                while b'\n' not in self.buffer:
                    remaining = deadline-time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise MemoryError('Memory helper timed out')
                    chunk = os.read(self.process.stdout.fileno(), 8192)
                    if not chunk:
                        raise MemoryError('Memory helper exited')
                    self.buffer += chunk
                    if len(self.buffer) > 65536:
                        raise MemoryError('Memory helper response exceeded limit')
            line, self.buffer = self.buffer.split(b'\n', 1)
            response = json.loads(line)
            if response.get('id') != request_id or response.get('ok') is not True or not isinstance(response.get('result'),dict):
                raise MemoryError('Memory helper rejected the operation')
            return response['result']
        except (ValueError, OSError, KeyError):
            raise MemoryError('Invalid memory helper protocol') from None

    def _validated_audit(self):
        audit = self._request('audit', {})
        events = {e['source']: e for e in self.reviews.events(self.scope)}
        seen = set()
        for record in audit.get('records', []):
            event = events.get(record.get('source'))
            if event is None or record.get('source') in seen:
                raise MemoryError('Memory has missing or duplicate source review provenance')
            seen.add(record['source'])
            if type(record.get('timestamp')) not in (int, float):
                raise MemoryError('Memory timestamp is invalid')
            provenance = record.get('provenance', {})
            if (record.get('chatId') != self.scope.key or record.get('content') != event['content'] or
                provenance.get('label') != event['review_id'] or
                provenance.get('refs') != [event['snapshot_id'],event['analysis_id']]):
                raise MemoryError('Memory source event does not match')
            if not any(entry.get('memoryId') == record.get('id') and entry.get('action') == 'create'
                       for entry in audit.get('ledger', [])):
                raise MemoryError('Memory creation audit is missing')
        records_by_source = {r['source']:r for r in audit['records']}
        for review_id, memory_id in self.reviews.receipts(self.scope).items():
            record = records_by_source.get('afya-review:'+review_id)
            if record is None or record['id'] != memory_id:
                raise MemoryError('Acknowledged memory projection is missing or changed')
        return audit

    def sync(self, *, after_write=None):
        for event in self.reviews.pending(self.scope):
            args = {key:event[key] for key in ('source','content','scope','review_id','reviewed_at_utc','snapshot_id','analysis_id')}
            result = self._request('remember_reviewed_note', args)
            self._validated_audit()
            if after_write:
                after_write()  # Testable crash window before the durable receipt.
            self.reviews.acknowledge(event['review_id'], result['memory_id'])
        return dict(pending=len(self.reviews.pending(self.scope)))

    def audit(self):
        return self._validated_audit()

    def recall(self, query, *, memory_as_of_utc):
        normalise(memory_as_of_utc, 'timestamp')
        if not isinstance(query,str) or not 1 <= len(query) <= 1000:
            raise ValueError('Bounded recall query required')
        audit = self._validated_audit()
        events = {e['source']:e for e in self.reviews.events(self.scope) if e['reviewed_at_utc']<=memory_as_of_utc}
        cutoff = datetime.strptime(memory_as_of_utc, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp()*1000
        eligible = {r['source'] for r in audit['records'] if r.get('timestamp',float('inf'))<=cutoff and r['source'] in events}
        result = self._request('recall', dict(query=query,scope=self.scope.key,eligible_sources=sorted(eligible)))
        notes=[]
        for record in result.get('memories',[]):
            event=events.get(record.get('source'))
            if record.get('source') not in eligible or event is None or record.get('scope')!=self.scope.key or record.get('content')!=event['content']:
                raise MemoryError('Recalled provenance/scope failed validation')
            notes.append(dict(**record, reviewed_at_utc=event['reviewed_at_utc'], snapshot_id=event['snapshot_id'],
                analysis_id=event['analysis_id'], role='historical_review_context', untrusted=True,
                current_measurement=False))
        if len(notes)>3:
            raise MemoryError('Recall cap exceeded')
        return dict(mode='hmem_reference',memory_as_of_utc=memory_as_of_utc,notes=notes,
                    limitations='Mock hash embeddings; historical untrusted context, not current measurements')
