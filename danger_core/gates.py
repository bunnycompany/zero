# zero/danger_core/gates.py
#
# Gate verification (the trick worth stealing from Prime Agent): after a
# mutating tool runs for real, check the postcondition before claiming
# success. "Done" should mean "I looked afterwards and it is so", not
# "the function returned".
#
# Gates are deterministic, cheap, and read-only. A gate failure does not
# retry (mutations never auto-retry); it turns the turn into an honest
# failure the user hears about.

from danger_core import policy


def _read(path):
    try:
        return policy.resolve_confined(path).read_text()
    except Exception:
        return None


def gate_write_file(args, result):
    """The file must exist and hold exactly what we said we wrote."""
    content = _read(args.get("path", ""))
    if content is None:
        return False, "the file is not there afterwards"
    if content != args.get("content", ""):
        return False, "the file exists but its content is not what was written"
    return True, "read the file back and it matches"


def gate_edit_file(args, result):
    """The replacement text must actually be present afterwards."""
    content = _read(args.get("path", ""))
    if content is None:
        return False, "the file is not there afterwards"
    new = args.get("new_text", "")
    if new and new not in content:
        return False, "the edit is not present in the file afterwards"
    return True, "read the file back and the edit is present"


# tool name -> postcondition. READ tools need no gate (they either returned
# data or errored); run_command's own exit code is its verdict.
GATES = {
    "write_file": gate_write_file,
    "edit_file": gate_edit_file,
}


def verify(tool_name, args, result):
    """(ok, evidence). Tools without a gate pass vacuously — but say so,
    because 'unverified' and 'verified' are different kinds of true."""
    gate = GATES.get(tool_name)
    if gate is None:
        return True, "no gate for this tool"
    try:
        return gate(args, result)
    except Exception as e:  # a broken gate must not break the turn
        return False, f"could not verify: {e}"
