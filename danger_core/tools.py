# zero/danger_core/tools.py

import difflib
import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from danger_core import policy


class ToolDispatcher:
    def __init__(self):
        self.logger = logging.getLogger("ToolDispatcher")

    # --- READ tier ----------------------------------------------------------

    def no_op(self, reason=""):
        """Doing nothing must be an expressible decision."""
        return {"status": "success", "output": f"no action taken{': ' + reason if reason else ''}"}

    def read_file(self, path):
        p = policy.resolve_confined(path)
        try:
            return {"status": "success", "content": p.read_text()}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def list_dir(self, path=None):
        p = policy.resolve_confined(path) if path else policy.allowed_root()
        try:
            entries = sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())
            return {"status": "success", "entries": entries}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def search_code(self, pattern, scope=None):
        scope_p = policy.resolve_confined(scope) if scope else policy.allowed_root()
        return self.run_command(["rg", "-n", "--no-follow", "-e", pattern, str(scope_p)])

    # --- WRITE tier ---------------------------------------------------------

    def edit_file(self, path, old_text, new_text, expect=1):
        """Literal string replacement. No regex, no sed, no shell.

        The `expect` guard is the load-bearing part: it converts "the model
        was vague and rewrote 40 lines" into a clean error.
        """
        p = policy.resolve_confined(path)
        try:
            src = p.read_text()
        except Exception as e:
            return {"status": "error", "message": str(e)}

        n = src.count(old_text)
        if n != expect:
            return {
                "status": "error",
                "message": f"expected {expect} occurrence(s) of old_text, found {n}",
            }

        backup = self._snapshot(p)
        updated = src.replace(old_text, new_text)
        self._atomic_write(p, updated)
        diff = "".join(
            difflib.unified_diff(
                src.splitlines(keepends=True),
                updated.splitlines(keepends=True),
                fromfile=str(p),
                tofile=str(p),
                n=2,
            )
        )
        return {"status": "success", "replaced": n, "backup": str(backup), "diff": diff[:2000]}

    def write_file(self, path, content):
        p = policy.resolve_confined(path)
        backup = self._snapshot(p) if p.exists() else None
        p.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(p, content)
        return {"status": "success", "backup": str(backup) if backup else None}

    # --- DANGER tier --------------------------------------------------------

    def run_command(self, cmd, timeout=30):
        """argv list only, never a shell. A hung subprocess must not hang the
        agent loop — the old version had no timeout and `patch` prompting on
        stdin froze it (the .rej debris in namespace/ was the evidence)."""
        if isinstance(cmd, str):
            return {"status": "error", "message": "cmd must be an argv list, not a string"}
        self.logger.info(f"Executing: {cmd}")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
            )
            return {"status": "success", "output": result.stdout}
        except subprocess.CalledProcessError as e:
            # rg exits 1 on "no matches" — that's a result, not a failure
            if cmd[0] == "rg" and e.returncode == 1:
                return {"status": "success", "output": ""}
            return {"status": "error", "message": e.stderr or f"exit {e.returncode}"}
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": f"timed out after {timeout}s"}
        except FileNotFoundError as e:
            return {"status": "error", "message": str(e)}

    # --- helpers ------------------------------------------------------------

    def _snapshot(self, p: Path) -> Path:
        """Copy to .zero-backups/<ts>/<relpath> before any mutation."""
        root = policy.allowed_root()
        rel = p.relative_to(root)
        dest = root / ".zero-backups" / time.strftime("%Y%m%d-%H%M%S") / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest)
        return dest

    def _atomic_write(self, p: Path, content: str):
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".tmp-", suffix=".swap")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, p)
        except BaseException:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise
