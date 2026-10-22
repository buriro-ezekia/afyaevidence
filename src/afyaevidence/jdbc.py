"""Read-only JDBC gateway. Call in a fresh process; never fork an active JVM."""
from pathlib import Path
import re

from .contracts import SCHEMAS, normalise
from .snapshot import SourceError, freeze, read_manifest

DRIVER_CLASS = "com.zetaris.lightning.jdbc.LightningDriver"
DRIVER_FILENAME = "ndp-jdbc-driver-2.4.3.1-7eff043-driver.jar"
DEFAULT_URL = "jdbc:zetaris:lightning@localhost:10000"
CAP = 2000


class JdbcGateway:
    def __init__(self, *, jar, username="admin@zetaris.com", password, database,
                 url=DEFAULT_URL, connect=None):
        self.jar = Path(jar)
        if not self.jar.is_absolute() or not self.jar.is_file() or self.jar.name != DRIVER_FILENAME:
            raise SourceError("An existing absolute path to the supplied Zetaris JAR is required")
        match = re.fullmatch(r"jdbc:zetaris:lightning@(?:[A-Za-z0-9_.-]+|\[[0-9A-Fa-f:]+\]):([0-9]{1,5})", url)
        if not match or not 1 <= int(match[1]) <= 65535:
            raise SourceError("Invalid Zetaris JDBC URL")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", database):
            raise SourceError("Invalid logical database identifier")
        if not username.strip() or not password.strip():
            raise SourceError("Non-empty credentials are required")
        self.username, self.password, self.database, self.url = username, password, database, url
        self._connect = connect

    def collect(self, directory):
        manifest, sha = read_manifest(directory)
        connection = cursor = None
        try:
            connect = self._connect
            if connect is None:
                import jaydebeapi
                connect = jaydebeapi.connect
            connection = connect(DRIVER_CLASS, self.url, [self.username, self.password], str(self.jar))
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            one = cursor.fetchone()
            if one is None or len(one) != 1 or str(one[0]) != "1":
                raise SourceError("JDBC connection check failed")
            tables = {}
            for table, schema in SCHEMAS.items():
                query = f"SELECT {', '.join(f for f, _ in schema)} FROM {self.database}.{table} LIMIT {CAP + 1}"
                cursor.execute(query)
                rows = []
                while len(rows) <= CAP:
                    batch = cursor.fetchmany(min(256, CAP + 1 - len(rows)))
                    if not batch:
                        break
                    rows.extend(batch)
                if len(rows) > CAP:
                    raise SourceError(f"{table}: source row cap exceeded")
                decoded = []
                for row in rows:
                    if len(row) != len(schema):
                        raise SourceError(f"{table}: column count mismatch")
                    decoded.append({field: normalise(value if value is None or
                        isinstance(value, (str, bool, int)) or hasattr(value, "isoformat") else str(value), kind)
                        for (field, kind), value in zip(schema, row)})
                tables[table] = decoded
            return freeze(manifest, sha, tables, "zetaris", self.database)
        except SourceError:
            raise
        except Exception:
            raise SourceError("JDBC source unavailable or invalid; no fixture fallback; raw errors withheld") from None
        finally:
            for resource in (cursor, connection):
                if resource is not None:
                    try:
                        resource.close()
                    except Exception:
                        pass
