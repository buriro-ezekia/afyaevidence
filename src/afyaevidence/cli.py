"""Fresh-process operator entrypoint for deterministic fixture or JDBC analysis."""
import argparse
import getpass
import json
import os
from pathlib import Path
import sys

from .analysis import Request, investigate
from .jdbc import DEFAULT_URL, JdbcGateway
from .snapshot import FixtureGateway, SourceError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("fixture", "zetaris"))
    parser.add_argument("--snapshot", type=Path, required=True, help="Directory with manifest and, in fixture mode, CSVs")
    parser.add_argument("--database", default="AFYAEVIDENCE_REVISION")
    parser.add_argument("--jar", default=os.environ.get("ZETARIS_JDBC_JAR", ""))
    parser.add_argument("--url", default=os.environ.get("ZETARIS_JDBC_URL", DEFAULT_URL))
    parser.add_argument("--comparison-month", default="2025-10-01")
    parser.add_argument("--target-month", default="2025-11-01")
    parser.add_argument("--district", default="D001")
    parser.add_argument("--as-of", default="2026-01-15T00:00:00Z")
    parser.add_argument("--output", type=Path, help="Create a new JSON receipt; refuse overwrite")
    parser.add_argument("--snapshot-output", type=Path, help="Create a private full-batch snapshot archive; refuse overwrite")
    args = parser.parse_args(argv)
    try:
        request = Request(args.district, args.comparison_month, args.target_month, args.as_of)
        for path in (args.output, args.snapshot_output):
            if path and path.exists():
                raise SourceError("Output already exists; choose a new receipt path")
        if args.output and args.snapshot_output and args.output.resolve() == args.snapshot_output.resolve():
            raise SourceError("Snapshot and analysis outputs must be different paths")
        if args.mode == "fixture":
            gateway = FixtureGateway()
        else:
            username = os.environ.get("ZETARIS_USERNAME", "admin@zetaris.com")
            password = os.environ.get("ZETARIS_PASSWORD", "")
            if not password:
                if not sys.stdin.isatty():
                    raise SourceError("Use an interactive terminal or a local ZETARIS_PASSWORD setting")
                password = getpass.getpass("Zetaris JDBC password: ")
            gateway = JdbcGateway(jar=args.jar, username=username, password=password,
                                  database=args.database, url=args.url)
        snapshot = gateway.collect(args.snapshot)
        bundle = investigate(snapshot, request).to_dict()
        if args.snapshot_output:
            snapshot.write(args.snapshot_output)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(bundle, stream, indent=2, ensure_ascii=False, allow_nan=False)
                stream.write("\n")
        print(f"DATA_MODE={snapshot.data_mode}\nSNAPSHOT_ID={snapshot.snapshot_id}")
        for label in ("comparison", "target"):
            for view, values in (("CANONICAL", bundle["summary"][label]), ("RAW", bundle["summary"][label]["raw"])):
                print(f"{label.upper()}_{view}_TESTED={values['tested']}\n{label.upper()}_{view}_POSITIVE={values['positive']}")
        print(f"ANALYSIS_STATUS={bundle['status']}\nDETERMINISTIC_ANALYSIS=PASS")
        print("LIVE_ZETARIS=" + ("PASS" if snapshot.data_mode == "zetaris" else "NOT_RUN"))
        print("LIVE_MODEL=NOT_RUN\nLIVE_HMEM=NOT_RUN")
        if args.output:
            print(f"RECEIPT={args.output}")
        return 0
    except (KeyboardInterrupt, EOFError):
        print("DETERMINISTIC_ANALYSIS=INTERRUPTED", file=sys.stderr)
        return 2
    except Exception:
        print("DETERMINISTIC_ANALYSIS=FAIL\nSource, request or output could not be validated; no fallback; raw errors withheld.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
