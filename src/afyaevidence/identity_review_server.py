"""Opt-in loopback OIDC resource server (port 8011), separate from development port 8010.

JWT access tokens are revalidated, including mandatory online introspection,
for every authenticated request. No cookie session, password login or token store.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sqlite3
import threading
from urllib.parse import urlsplit

from .identity_auth import IdentityError, OIDCVerifier, strict_json
from . import identity_store
from .identity_page import PAGE, CSS, JS

MAX_BODY = 32_768
CSP = "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"


class BoundedServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, handler):
        if address[0] != '127.0.0.1':
            raise ValueError('loopback_only')
        self.slots = threading.BoundedSemaphore(16)
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            try:
                request.sendall(b'HTTP/1.0 503 Service Unavailable\r\nContent-Length: 0\r\n\r\n')
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


def handler_factory(db_path, verifier, *, managed_state=None, backend=None):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'AfyaIdentity'
        sys_version = ''

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *args):
            pass  # Never log request paths, credentials, bodies or provider responses.

        def send_data(self, status, blob, content_type):
            self.send_response(status)
            for name, value in [('Content-Type', content_type), ('Content-Length', str(len(blob))),
                    ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'),
                    ('Referrer-Policy', 'no-referrer'), ('Content-Security-Policy', CSP)]:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(blob)

        def reply(self, status, data):
            self.send_data(status, json.dumps(data, ensure_ascii=True, allow_nan=False).encode(), 'application/json')

        def boundary(self):
            hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            if len(self.headers.get_all('Host', [])) != 1 or self.headers.get('Host') not in hosts:
                raise IdentityError('host_not_allowed', 403)
            origins = self.headers.get_all('Origin', [])
            if len(origins) > 1 or (origins and origins[0] not in {'http://' + host for host in hosts}):
                raise IdentityError('origin_not_allowed', 403)
            path = urlsplit(self.path)
            if path.scheme or path.netloc or path.query or path.fragment:
                raise IdentityError('invalid_route', 400)
            return path.path

        def authenticate(self, permission):
            headers = self.headers.get_all('Authorization', [])
            if len(headers) != 1 or not headers[0].startswith('Bearer '):
                raise IdentityError()
            principal = verifier.verify(headers[0][7:])
            principal.require(permission)
            return principal

        def body(self):
            types = self.headers.get_all('Content-Type', [])
            if len(types) != 1 or types[0].split(';')[0].strip().lower() != 'application/json':
                raise IdentityError('json_required', 415)
            lengths = self.headers.get_all('Content-Length', [])
            if len(lengths) != 1 or not lengths[0].isdigit() or self.headers.get_all('Transfer-Encoding'):
                raise IdentityError('invalid_body_framing', 400)
            count = int(lengths[0])
            if not 1 <= count <= MAX_BODY:
                raise IdentityError('invalid_body_size', 413)
            blob = self.rfile.read(count)
            if len(blob) != count:
                raise IdentityError('incomplete_body', 400)
            try:
                data = strict_json(blob)
            except (ValueError, UnicodeError, RecursionError):
                raise IdentityError('invalid_json', 400) from None
            if not isinstance(data, dict):
                raise IdentityError('invalid_json', 400)
            return data

        def error(self, exc):
            if isinstance(exc, IdentityError):
                self.reply(exc.status, dict(error=exc.code))
            elif isinstance(exc, TimeoutError):
                self.reply(408, dict(error='request_timeout'))
            elif isinstance(exc, sqlite3.Error):
                self.reply(503, dict(error='storage_unavailable'))
            elif isinstance(exc, ValueError):
                allowed = {'unknown_run', 'invalid_run', 'invalid_identifier', 'invalid_revision',
                    'invalid_disposition', 'reason_required', 'invalid_reason_unicode', 'already_reviewed',
                    'revision_conflict', 'idempotency_conflict', 'unknown_job', 'invalid_recovery_request'}
                code = str(exc) if str(exc) in allowed else 'invalid_request'
                self.reply(404 if code in {'unknown_run', 'unknown_job'} else 409, dict(error=code))
            else:
                self.reply(503, dict(error='operation_unavailable'))

        def do_GET(self):
            try:
                route = self.boundary()
                assets = {'/': (PAGE, 'text/html; charset=utf-8'), '/identity.css': (CSS, 'text/css'), '/identity.js': (JS, 'text/javascript')}
                if route in assets:
                    text, kind = assets[route]
                    self.send_data(200, text.encode(), kind)
                    return
                principal = self.authenticate('read')
                if route == '/api/me':
                    self.reply(200, principal.public())
                    return
                if route == '/api/managed/jobs' and managed_state is not None:
                    from .managed_worker import audit
                    self.reply(200, audit(managed_state))
                    return
                match = re.fullmatch(r'/api/runs/([A-Za-z0-9_-]{1,100})', route)
                if match:
                    with closing(identity_store.connect(db_path)) as db:
                        self.reply(200, identity_store.get_run(db, match[1]))
                else:
                    self.reply(404, dict(error='not_found'))
            except Exception as exc:
                self.error(exc)

        def do_POST(self):
            try:
                route = self.boundary()
                recovery = re.fullmatch(r'/api/managed/jobs/(mw_[a-f0-9]{32})/reconcile', route)
                permission = 'recover' if recovery else 'review'
                self.authenticate(permission)
                payload = self.body()
                principal = self.authenticate(permission)  # Recheck revocation after body read.
                if recovery and managed_state is not None:
                    if set(payload) != {'expected_revision', 'event_key', 'reason'}:
                        raise IdentityError('invalid_fields', 400)
                    from .managed_worker import reconcile
                    result = reconcile(managed_state, recovery[1], principal=principal, backend=backend, **payload)
                else:
                    match = re.fullmatch(r'/api/runs/([A-Za-z0-9_-]{1,100})/reviews', route)
                    if not match:
                        self.reply(404, dict(error='not_found'))
                        return
                    if set(payload) != {'expected_revision', 'event_key', 'disposition', 'reason'}:
                        raise IdentityError('invalid_fields', 400)
                    with closing(identity_store.connect(db_path)) as db:
                        result = identity_store.review(db, run_id=match[1], principal=principal, **payload)
                self.reply(200, result)
            except Exception as exc:
                self.error(exc)
    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True, help='Use a backed-up identity copy, not the original review database')
    parser.add_argument('--identity-config', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8011)
    parser.add_argument('--managed-state', type=Path)
    args = parser.parse_args(argv)
    verifier = OIDCVerifier.configured(args.identity_config)
    with closing(identity_store.connect(args.db)):
        pass
    server = BoundedServer(('127.0.0.1', args.port), handler_factory(args.db, verifier, managed_state=args.managed_state))
    print(f'IDENTITY_REVIEW_UI=http://127.0.0.1:{args.port}/', flush=True)
    print('AUTH_MODE=oidc_access_token\nIDENTITY_PROVIDER_LIVE_ACCEPTANCE=NOT_YET_TESTED', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
