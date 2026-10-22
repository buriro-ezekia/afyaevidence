"""Immutable, bounded snapshots shared by fixture and live-source gateways."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from .contracts import ALGORITHM, SCHEMAS, canonical_digest, normalise_rows, read_csv


class SourceError(ValueError):
    """A source is unavailable or does not match the declared immutable batch."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def read_manifest(directory):
    try:
        raw = (Path(directory) / "manifest.json").read_bytes()
        if len(raw) > 65536:
            raise SourceError("Manifest exceeds size limit")
        manifest = json.loads(raw)
        if (manifest["schema_version"] != "aggregate-1" or
            manifest["canonical_algorithm"] != ALGORITHM or
            manifest["synthetic"] is not True or
            not re.fullmatch(r"fx_[0-9a-f]{8}", manifest["dataset_id"]) or
            set(manifest["tables"]) != set(SCHEMAS)):
            raise SourceError("Unsupported manifest")
        scope = manifest["scope"]
        if scope != dict(district_id="D001", first_month="2024-01-01", last_month="2025-12-01",
                         facility_count=6, expected_facility_months=144):
            raise SourceError("Unsupported synthetic scope")
        for table, schema in SCHEMAS.items():
            meta = manifest["tables"][table]
            count = meta["row_count"]
            if (meta["file"] != table + ".csv" or meta["field_order"] != [f for f, _ in schema] or
                type(count) is not int or not 0 <= count <= (6 if table == "facility_registry" else 432)):
                raise SourceError("Invalid source metadata")
            for field in ("byte_sha256", "canonical_sha256"):
                if not re.fullmatch(r"[0-9a-f]{64}", meta[field]):
                    raise SourceError("Invalid source digest")
        return manifest, hashlib.sha256(raw).hexdigest()
    except SourceError:
        raise
    except (OSError, ValueError, TypeError, KeyError):
        raise SourceError("Cannot validate snapshot manifest") from None


@dataclass(frozen=True)
class Snapshot:
    dataset_id: str
    snapshot_id: str
    data_mode: str
    manifest_sha256: str
    source_hashes: tuple
    _tables: tuple
    retrieved_at_utc: str | None = None
    source_namespace: str | None = None

    def rows(self, table):
        fields = [f for f, _ in SCHEMAS[table]]
        values = dict(self._tables)[table]
        return [dict(zip(fields, row)) for row in values]

    def tables(self):
        return {table: self.rows(table) for table in SCHEMAS}

    def to_dict(self):
        return dict(schema_version="snapshot-1", dataset_id=self.dataset_id,
                    snapshot_id=self.snapshot_id, data_mode=self.data_mode,
                    manifest_sha256=self.manifest_sha256, source_hashes=dict(self.source_hashes),
                    retrieved_at_utc=self.retrieved_at_utc, source_namespace=self.source_namespace,
                    tables=self.tables())

    def write(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(self.to_dict(), stream, sort_keys=True, ensure_ascii=False, allow_nan=False)
            stream.write("\n")


def freeze(manifest, manifest_sha256, tables, mode, source_namespace=None):
    if mode not in {"fixture", "zetaris"} or set(tables) != set(SCHEMAS):
        raise SourceError("Invalid snapshot mode or tables")
    stored, hashes = [], []
    for table, schema in SCHEMAS.items():
        try:
            rows = normalise_rows(table, tables[table])
            meta = manifest["tables"][table]
            if len(rows) != meta["row_count"] or any(r["dataset_id"] != manifest["dataset_id"] for r in rows):
                raise SourceError(f"{table}: count/dataset mismatch")
            content_hash = canonical_digest(table, rows)
            if content_hash != meta["canonical_sha256"]:
                raise SourceError(f"{table}: canonical hash mismatch")
            fields = [f for f, _ in schema]
            values = [tuple(r[f] for f in fields) for r in rows]
            values.sort(key=lambda row: json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            stored.append((table, tuple(values)))
            hashes.append((table, content_hash))
        except (ValueError, KeyError, TypeError):
            raise SourceError(f"{table}: schema or content mismatch") from None
    identity = digest(["snapshot-1", manifest["dataset_id"], hashes])
    return Snapshot(manifest["dataset_id"], "ss_" + identity, mode, manifest_sha256,
                    tuple(hashes), tuple(stored),
                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if mode == "zetaris" else None,
                    source_namespace)


class FixtureGateway:
    def collect(self, directory):
        manifest, sha = read_manifest(directory)
        tables = {}
        for table, meta in manifest["tables"].items():
            try:
                path = Path(directory) / meta["file"]
                if path.stat().st_size > 2_000_000:
                    raise SourceError("Fixture exceeds byte cap")
                content = path.read_bytes()
                if hashlib.sha256(content).hexdigest() != meta["byte_sha256"]:
                    raise SourceError(f"{table}: CSV byte hash mismatch")
                tables[table] = read_csv(table, content)
            except (OSError, ValueError, TypeError):
                raise SourceError(f"{table}: cannot validate fixture bytes") from None
        return freeze(manifest, sha, tables, "fixture")
