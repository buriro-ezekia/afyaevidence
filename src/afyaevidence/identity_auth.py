"""Strict OIDC-provider access-token verification; no shared-token fallback.

This resource server is not an OIDC login client. Its operator must configure
an identity provider that issues RS256 access tokens and supports introspection.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import time
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, Request, build_opener

import jwt

MAX_TOKEN_BYTES = 16_384
MAX_PROVIDER_BYTES = 262_144
ROLES = frozenset({'viewer', 'reviewer', 'administrator'})


class IdentityError(Exception):
    """Only stable error codes, never tokens or provider responses."""
    def __init__(self, code='unauthorised', status=401):
        super().__init__(code)
        self.code, self.status = code, status


def strict_json(value):
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError('duplicate_json_key')
            result[key] = item
        return result
    return json.loads(value, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_json')))


def https_url(value):
    if not isinstance(value, str) or len(value) > 2048 or any(c.isspace() for c in value):
        raise ValueError('invalid_identity_url')
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.fragment or parsed.query):
        raise ValueError('invalid_identity_url')
    _ = parsed.port
    return value


@dataclass(frozen=True)
class IdentityConfig:
    issuer: str
    audience: str
    jwks_uri: str
    introspection_uri: str
    client_id: str
    secret_env: str = 'AFYA_OIDC_CLIENT_SECRET'
    roles_claim: str = 'roles'
    token_type: str = 'at+jwt'
    max_lifetime_seconds: int = 900

    def __post_init__(self):
        for name in ('issuer', 'jwks_uri', 'introspection_uri'):
            https_url(getattr(self, name))
        for name in ('audience', 'client_id', 'roles_claim'):
            value = getattr(self, name)
            if not isinstance(value, str) or not 1 <= len(value) <= 256 or any(ord(c) < 32 for c in value):
                raise ValueError('invalid_identity_configuration')
        if not re.fullmatch(r'[A-Z][A-Z0-9_]{2,100}', self.secret_env):
            raise ValueError('invalid_identity_secret_name')
        # Deliberately reject ID tokens. Provider must issue this access-token type.
        if self.token_type != 'at+jwt':
            raise ValueError('access_token_type_required')
        if type(self.max_lifetime_seconds) is not int or not 60 <= self.max_lifetime_seconds <= 3600:
            raise ValueError('invalid_token_lifetime')

    @classmethod
    def load(cls, path: Path):
        blob = path.read_bytes()
        if len(blob) > 8192:
            raise ValueError('identity_config_too_large')
        value = strict_json(blob)
        if not isinstance(value, dict):
            raise ValueError('invalid_identity_configuration')
        return cls(**value)


@dataclass(frozen=True)
class Principal:
    issuer: str
    subject: str
    roles: tuple[str, ...]

    @property
    def actor_id(self):
        data = json.dumps([self.issuer, self.subject], separators=(',', ':'), ensure_ascii=False)
        return 'oidc_' + sha256(data.encode()).hexdigest()

    def require(self, permission):
        allowed = {'read': ROLES, 'review': {'reviewer'}, 'recover': {'administrator'}}
        if permission not in allowed or not set(self.roles).intersection(allowed[permission]):
            raise IdentityError('forbidden', 403)

    def public(self):
        return dict(actor_id=self.actor_id, issuer=self.issuer, subject=self.subject,
                    roles=list(self.roles), identity_kind='verified_oidc')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise IdentityError('identity_provider_unavailable', 503)


class ProviderTransport:
    """Bounded HTTPS only; no redirects, ambient proxies or stale JWKS cache."""
    def __init__(self):
        from urllib.request import ProxyHandler
        self.opener = build_opener(ProxyHandler({}), HTTPSHandler(), NoRedirect())

    def json(self, url, *, body=None, headers=None):
        https_url(url)
        request = Request(url, data=body, headers=headers or {}, method='POST' if body is not None else 'GET')
        try:
            with self.opener.open(request, timeout=5) as response:
                if response.status != 200:
                    raise ValueError('provider_status')
                if response.headers.get_content_type() != 'application/json':
                    raise ValueError('provider_media_type')
                blob = response.read(MAX_PROVIDER_BYTES + 1)
            if len(blob) > MAX_PROVIDER_BYTES:
                raise ValueError('provider_body_size')
            data = strict_json(blob)
            if not isinstance(data, dict):
                raise ValueError('provider_body_shape')
            return data
        except Exception:
            raise IdentityError('identity_provider_unavailable', 503) from None


class OIDCVerifier:
    def __init__(self, config: IdentityConfig, client_secret: str, *, transport=None):
        if not isinstance(client_secret, str) or not client_secret or len(client_secret) > 4096:
            raise ValueError('identity_client_secret_required')
        self.config, self._secret = config, client_secret
        self.transport = transport or ProviderTransport()

    @classmethod
    def configured(cls, path: Path):
        config = IdentityConfig.load(path)
        return cls(config, os.environ.get(config.secret_env, ''))

    def verify(self, token: str) -> Principal:
        try:
            return self._verify(token)
        except IdentityError:
            raise
        except Exception:
            raise IdentityError() from None

    def _verify(self, token):
        if not isinstance(token, str) or not token or len(token.encode()) > MAX_TOKEN_BYTES:
            raise IdentityError()
        parts = token.split('.')
        if len(parts) != 3 or any(not re.fullmatch(r'[A-Za-z0-9_-]+', p) for p in parts):
            raise IdentityError()
        # Parse with duplicate rejection. Parsing alone never authorises a request.
        decoded = []
        for part in parts[:2]:
            decoded.append(strict_json(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4))))
        header, untrusted = decoded
        if not isinstance(header, dict) or not isinstance(untrusted, dict):
            raise IdentityError()
        if set(header) - {'alg', 'typ', 'kid'} or header.get('alg') != 'RS256' or header.get('typ') != self.config.token_type:
            raise IdentityError()
        kid = header.get('kid')
        if not isinstance(kid, str) or not 1 <= len(kid) <= 128:
            raise IdentityError()
        jwks = self.transport.json(self.config.jwks_uri)
        keys = jwks.get('keys')
        if not isinstance(keys, list) or not 1 <= len(keys) <= 32:
            raise IdentityError('identity_provider_unavailable', 503)
        matches = [k for k in keys if isinstance(k, dict) and k.get('kid') == kid]
        if len(matches) != 1:
            raise IdentityError()
        key = matches[0]
        if (key.get('kty') != 'RSA' or key.get('alg', 'RS256') != 'RS256'
                or key.get('use', 'sig') != 'sig' or 'd' in key
                or ('key_ops' in key and key['key_ops'] != ['verify'])):
            raise IdentityError()
        public_key = jwt.PyJWK.from_dict(key, algorithm='RS256').key
        if public_key.key_size < 2048:
            raise IdentityError()
        claims = jwt.decode(token, public_key, algorithms=['RS256'],
            issuer=self.config.issuer, audience=self.config.audience,
            options={'require': ['iss', 'aud', 'sub', 'exp', 'nbf', 'iat', 'jti'],
                     'strict_aud': True}, leeway=0)
        for key in ('iat', 'nbf', 'exp'):
            if type(claims[key]) is not int or not math.isfinite(claims[key]):
                raise IdentityError()
        if not claims['iat'] <= claims['nbf'] < claims['exp'] or not 0 < claims['exp'] - claims['iat'] <= self.config.max_lifetime_seconds:
            raise IdentityError()
        for key in ('sub', 'jti'):
            value = claims.get(key)
            if not isinstance(value, str) or not 1 <= len(value) <= 256 or any(ord(c) < 32 for c in value):
                raise IdentityError()
        roles = claims.get(self.config.roles_claim)
        if not isinstance(roles, list) or len(roles) > 20 or any(not isinstance(r, str) for r in roles):
            raise IdentityError('forbidden', 403)
        roles = tuple(sorted(set(roles).intersection(ROLES)))
        if not roles:
            raise IdentityError('forbidden', 403)
        # Online introspection is mandatory: a signed JWT alone cannot prove non-revocation.
        credentials = base64.b64encode((quote(self.config.client_id, safe='') + ':' + quote(self._secret, safe='')).encode()).decode()
        status = self.transport.json(self.config.introspection_uri,
            body=urlencode({'token': token, 'token_type_hint': 'access_token'}).encode(),
            headers={'Authorization': 'Basic ' + credentials,
                     'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'})
        if status.get('active') is not True:
            raise IdentityError()
        if status.get('sub') != claims['sub'] or status.get('iss') != claims['iss'] or status.get('aud') != claims['aud']:
            raise IdentityError()
        if type(status.get('exp')) is not int or status['exp'] != claims['exp'] or status['exp'] <= time.time():
            raise IdentityError()
        return Principal(claims['iss'], claims['sub'], roles)
