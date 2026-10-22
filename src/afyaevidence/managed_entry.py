"""Private systemd service entrypoint. Consumes a bounded, owner-only launch file."""
import json
import os
from pathlib import Path
import stat
import sys


def main():
    if len(sys.argv) != 2 or os.geteuid() == 0:
        raise SystemExit(2)
    path = Path(sys.argv[1])
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'r', encoding='utf-8') as source:
        info = os.fstat(source.fileno())
        if info.st_uid != os.getuid() or info.st_mode & 0o077 or not stat.S_ISREG(info.st_mode):
            raise SystemExit(2)
        text = source.read(131073)
    if len(text.encode()) > 131072:
        raise SystemExit(2)
    job = json.loads(text)
    argv, env = job['argv'], job['env']
    if argv[:3] != [sys.executable, '-m', 'afyaevidence.agent_cli']:
        raise SystemExit(2)
    allowed = {'PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR', 'JAVA_HOME',
               'ZETARIS_USERNAME', 'ZETARIS_PASSWORD', 'PYTHONPATH', 'PYTHONUNBUFFERED'}
    if set(env) - allowed or any(not isinstance(v, str) for v in env.values()):
        raise SystemExit(2)
    path.unlink()  # Secrets never enter the job database, argv, journal or receipts.
    os.execve(sys.executable, argv, env)


if __name__ == '__main__':
    main()
