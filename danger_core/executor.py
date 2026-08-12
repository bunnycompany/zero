# zero/danger_core/executor.py

import logging
import time

from danger_core import gates, policy
from danger_core.tools import ToolDispatcher
from zero import ns


class DangerCore:
    def __init__(self):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("DangerCore")
        self.dispatcher = ToolDispatcher()
        self.max_retries = 3

        # name -> (callable, tier, required args, description shown to the brain)
        d = self.dispatcher
        self.registry = {
            "no_op": (d.no_op, policy.READ, [], "Do nothing. Use when no action is warranted."),
            "read_file": (d.read_file, policy.READ, ["path"], "Read a text file. args: {path}"),
            "list_dir": (d.list_dir, policy.READ, [], "List a directory. args: {path}"),
            "search_code": (d.search_code, policy.READ, ["pattern"], "Search files with ripgrep. args: {pattern, scope?}"),
            "edit_file": (d.edit_file, policy.WRITE, ["path", "old_text", "new_text"], "Replace old_text (literal, must occur exactly once) with new_text. args: {path, old_text, new_text}"),
            "write_file": (d.write_file, policy.WRITE, ["path", "content"], "Create or overwrite a file. args: {path, content}"),
            "run_command": (d.run_command, policy.DANGER, ["cmd"], "Run a subprocess (argv list). args: {cmd}"),
        }

    def tool_manifest(self):
        """What the brain is shown: name, tier, description."""
        return [
            {"tool": name, "tier": tier, "description": desc}
            for name, (_, tier, _, desc) in self.registry.items()
        ]

    def _checkpoint(self, phase, last_tool=None):
        """Durability record: what the executor was doing if the process dies."""
        ns.write_doc("checkpoint", "executor", {"phase": phase, "last_tool": last_tool})

    def _validate_action(self, tool_name, args):
        """Reject-and-log, never coerce: a malformed call from the model must
        show up as a rejection rate in the journal, not get silently repaired."""
        if tool_name not in self.registry:
            return f"unknown tool '{tool_name}'"
        if not isinstance(args, dict):
            return f"args must be an object, got {type(args).__name__}"
        _, _, required, _ = self.registry[tool_name]
        missing = [k for k in required if k not in args]
        if missing:
            return f"missing required args: {missing}"
        return None

    def execute_tool(self, tool_name, args, source="human"):
        self._checkpoint("executing", tool_name)
        # A command's origin caps what it may do: remote asks can read and
        # report, but never auto-mutate, regardless of the real mode.
        raw_mode = policy.current_mode()
        mode = policy.effective_mode(raw_mode, source)
        ns.log("executor", "proposed", tool=tool_name, args=args, mode=mode, source=source)

        reason = self._validate_action(tool_name, args)
        if reason:
            self._checkpoint("error", tool_name)
            ns.log("executor", "rejected", tool=tool_name, reason=reason)
            return {"status": "error", "message": f"rejected: {reason}"}

        fn, tier, _, _ = self.registry[tool_name]

        if not policy.may_execute(tier, mode):
            # Shadow is a feature, not a failure: the loop runs end-to-end and
            # the journal records what WOULD have happened.
            self._checkpoint("idle")
            ns.log("executor", "shadowed", tool=tool_name, tier=tier, mode=mode)
            return {"status": "shadowed", "message": f"{tool_name} ({tier}) not executed in mode '{mode}'"}

        attempts = self.max_retries if tier == policy.READ else 1  # never auto-retry a mutation
        last_error = None
        for attempt in range(attempts):
            try:
                result = fn(**args)
                # Gate: for a mutating tool, look afterwards and confirm the
                # postcondition. "Done" must mean verified, not just returned.
                ok, evidence = gates.verify(tool_name, args, result)
                if not ok:
                    self._checkpoint("error", tool_name)
                    ns.log("executor", "gate_failed", tool=tool_name, evidence=evidence)
                    return {"status": "error", "message": f"it ran but didn't take: {evidence}",
                            "result": result, "gate_failed": True}
                self._checkpoint("idle")
                ns.log("executor", "executed", tool=tool_name,
                       result=str(result)[:500], verified=evidence)
                return {"status": "success", "result": result, "verified": evidence}
            except PermissionError as e:
                # policy violations are final — retrying cannot help
                self._checkpoint("error", tool_name)
                ns.log("executor", "denied", tool=tool_name, reason=str(e))
                return {"status": "error", "message": f"denied: {e}"}
            except Exception as e:
                last_error = e
                self.logger.warning(f"Attempt {attempt + 1} failed: {e}")
                if attempt + 1 < attempts:
                    time.sleep(1)

        self._checkpoint("error", tool_name)
        ns.log("executor", "failed", tool=tool_name, error=str(last_error))
        return {"status": "error", "message": f"failed after {attempts} attempt(s): {last_error}"}
