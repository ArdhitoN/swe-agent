"""Tools that run *inside* the bug's container.

Run with the container's modern Python (/opt/miniconda3/bin/python). The project's own Python
(often much older, e.g. 3.6) is only used to check syntax, check imports and run tests, so the
checks match the code's real runtime.

Usage: python toolbox.py <command> <base64-encoded JSON arguments>
Prints human-readable text for the model, then one final line "@@RESULT@@ <json>" for the host.
"""

import ast
import base64
import json
import os
import re
import subprocess
import sys

REPO = os.environ.get("GATED_REPO", "/testbed")
PROJECT_PY = os.environ.get("GATED_PROJECT_PY", "/opt/miniconda3/envs/testbed/bin/python")
MAX_LINE = 240


def result(text, **data):
    print(text)
    print("@@RESULT@@ " + json.dumps(data))
    return data


def sh(cmd, cwd=REPO, timeout=600):
    """Run a shell command; return (exit_code, combined_output). A timeout returns code 124."""
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return 124, out + "\n[timed out after %ss]" % timeout


def head_tail(text, head=60, tail=60):
    lines = text.splitlines()
    if len(lines) <= head + tail:
        return text
    return "\n".join(lines[:head] + ["... [%d lines omitted] ..." % (len(lines) - head - tail)] + lines[-tail:])


def resolve(path):
    path = path.strip()
    return path if os.path.isabs(path) else os.path.join(REPO, path)


def is_test_path(path):
    rel = os.path.relpath(resolve(path), REPO)
    parts = rel.split(os.sep)
    name = parts[-1]
    return (
        parts[0] in ("tests", "test", "testing")
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
    )


# ---------------------------------------------------------------- reading

def cmd_search(pattern, path=".", max_results=50):
    """Search the repo (tracked files) for a regular expression."""
    path = path.strip() or "."
    code, out = sh("git grep -n -I -E -e %s -- %s" % (quote(pattern), quote(path)))
    if code not in (0, 1):
        return result("search failed: " + out[-500:], ok=False)
    lines = [l[:MAX_LINE] for l in out.splitlines() if l]
    shown = lines[:max_results]
    text = "\n".join(shown) if shown else "no matches"
    if len(lines) > max_results:
        text += "\n... %d more matches; narrow the pattern or path" % (len(lines) - max_results)
    return result(text, ok=True, matches=len(lines))


def cmd_outline(path):
    """List classes and functions with line numbers."""
    full = resolve(path)
    try:
        tree = ast.parse(open(full, encoding="utf-8").read())
    except Exception as e:
        return result("cannot outline %s: %s" % (path, e), ok=False)
    rows = []

    def walk(node, depth):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "class" if isinstance(child, ast.ClassDef) else "def"
                end = getattr(child, "end_lineno", child.lineno)
                rows.append("%sL%d-%d %s %s" % ("  " * depth, child.lineno, end, kind, child.name))
                walk(child, depth + 1)

    walk(tree, 0)
    return result("\n".join(rows) or "no classes or functions", ok=True)


def cmd_view(path, start=1, end=None):
    """Show numbered lines start..end (at most 150 lines)."""
    full = resolve(path)
    try:
        lines = open(full, encoding="utf-8", errors="replace").read().splitlines()
    except Exception as e:
        return result("cannot read %s: %s" % (path, e), ok=False)
    start = max(1, int(start))
    end = min(len(lines), int(end) if end else start + 99, start + 149)
    body = "\n".join("%6d  %s" % (i, lines[i - 1][:400]) for i in range(start, end + 1))
    return result("%s (lines %d-%d of %d)\n%s" % (path, start, end, len(lines), body), ok=True)


# ---------------------------------------------------------------- editing

def module_name(full):
    rel = os.path.relpath(full, REPO)
    if not rel.endswith(".py") or rel.startswith(".."):
        return None
    parts = rel[:-3].split(os.sep)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else None


def imports_ok(module):
    code, out = sh("%s -c %s" % (PROJECT_PY, quote("import " + module)), timeout=120)
    return code == 0, out


def check_python(full, before_text):
    """Syntax check with the project's Python; import check compared with the code before the edit."""
    code, out = sh("%s -m py_compile %s" % (PROJECT_PY, quote(full)), timeout=120)
    if code != 0:
        return "syntax error (checked with the project's Python):\n" + out[-1500:]
    module = module_name(full)
    if not module:
        return None
    ok_after, out_after = imports_ok(module)
    if ok_after:
        return None
    # Only blame the edit if the module imported fine before it.
    after_text = open(full, encoding="utf-8").read()
    open(full, "w", encoding="utf-8").write(before_text)
    ok_before, _ = imports_ok(module)
    open(full, "w", encoding="utf-8").write(after_text)
    if ok_before:
        return "the edit breaks `import %s`:\n%s" % (module, out_after[-1500:])
    return None


def snippet(text, index, length, context=4):
    start_line = text.count("\n", 0, index) + 1
    lines = text.splitlines()
    end_line = start_line + text.count("\n", index, index + length)
    lo, hi = max(1, start_line - context), min(len(lines), end_line + context)
    return "\n".join("%6d  %s" % (i, lines[i - 1]) for i in range(lo, hi + 1))


def cmd_edit(path, old, new):
    """Replace one exact, unique occurrence of `old` with `new`. Broken Python edits are undone."""
    full = resolve(path)
    if is_test_path(full):
        return result("refused: %s is a test file. Fix the source code, not the tests." % path, ok=False)
    try:
        text = open(full, encoding="utf-8").read()
    except Exception as e:
        return result("cannot read %s: %s" % (path, e), ok=False)
    if not old:
        return result("`old` is empty. Copy the exact text to replace (view the file first).", ok=False)
    count = text.count(old)
    if count == 0:
        return result("no exact match for `old` in %s. View the lines and copy them exactly (indentation too)." % path, ok=False)
    if count > 1:
        lines = sorted({text.count("\n", 0, m.start()) + 1 for m in re.finditer(re.escape(old), text)})
        return result(
            "`old` appears %d times (lines %s). Include more surrounding lines so it is unique." % (count, lines),
            ok=False,
        )
    index = text.index(old)
    new_text = text[:index] + new + text[index + len(old):]
    open(full, "w", encoding="utf-8").write(new_text)
    if full.endswith(".py"):
        problem = check_python(full, text)
        if problem:
            open(full, "w", encoding="utf-8").write(text)
            return result("edit undone, because " + problem, ok=False, reverted=True)
    return result("edited %s:\n%s" % (path, snippet(new_text, index, len(new))), ok=True)


def cmd_create(path, content):
    """Create a new source file (never overwrites, never in test folders)."""
    full = resolve(path)
    if is_test_path(full):
        return result("refused: %s is a test file." % path, ok=False)
    if os.path.exists(full):
        return result("refused: %s already exists; use edit instead." % path, ok=False)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    open(full, "w", encoding="utf-8").write(content)
    if full.endswith(".py"):
        code, out = sh("%s -m py_compile %s" % (PROJECT_PY, quote(full)), timeout=120)
        if code != 0:
            os.remove(full)
            return result("file not created, syntax error:\n" + out[-1500:], ok=False, reverted=True)
    return result("created %s" % path, ok=True)


# ---------------------------------------------------------------- running

def repo_kind():
    if os.path.exists(os.path.join(REPO, "tests", "runtests.py")):
        return "django"
    if os.path.isdir(os.path.join(REPO, "sphinx")):
        return "sphinx"
    return "pytest"


def test_command(targets):
    targets = " ".join(quote(t) for t in targets)
    if repo_kind() == "django":
        return "cd %s/tests && %s runtests.py --verbosity 2 --settings=test_sqlite --parallel 1 %s" % (REPO, PROJECT_PY, targets)
    return "cd %s && %s -m pytest -rA -p no:cacheprovider -q %s" % (REPO, PROJECT_PY, targets)


DJANGO_FAIL = re.compile(r"^(FAIL|ERROR): (\S+) \(([\w.]+)\)", re.M)
PYTEST_FAIL = re.compile(r"^(FAILED|ERROR) (\S+?)(?: - |$)", re.M)


def parse_failures(output):
    """Return (set of failing test ids, finished) from Django or pytest output."""
    if repo_kind() == "django":
        failed = {"%s.%s" % (cls, name) for _, name, cls in DJANGO_FAIL.findall(output)}
        finished = bool(re.search(r"^Ran \d+ tests? in", output, re.M))
    else:
        failed = {tid for _, tid in PYTEST_FAIL.findall(output)}
        finished = bool(re.search(r"=+ .*(passed|failed|error|no tests ran).* in [\d.]+s", output))
    return failed, finished


def run_tests_raw(targets, timeout=900):
    code, out = sh(test_command(targets), cwd=REPO, timeout=timeout)
    failed, finished = parse_failures(out)
    return code, out, failed, finished


def cmd_run_tests(targets):
    """Run some of the repo's existing tests with the repo's own test runner."""
    if isinstance(targets, str):
        targets = targets.split()
    code, out, failed, finished = run_tests_raw(targets)
    status = "finished" if finished else "did NOT finish (crash, import error or timeout)"
    text = "tests %s; %d failing\n%s" % (status, len(failed), head_tail(out, 40, 60))
    return result(text, ok=finished, failed=sorted(failed), finished=finished)


def cmd_run_script(path, timeout=120):
    """Run a script with the project's Python from the repo root; report its exit code."""
    code, out = sh("%s %s" % (PROJECT_PY, quote(resolve(path))), cwd=REPO, timeout=int(timeout))
    return result("exit code %d\n%s" % (code, head_tail(out, 40, 40)), ok=True, exit_code=code)


def changed_source_files():
    """Source files changed by the agent (tracked or new), excluding tests."""
    _, out = sh("git status --porcelain --untracked-files=all")
    files = []
    for line in out.splitlines():
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ")[1]
        if path.endswith(".py") and not is_test_path(path):
            files.append(path)
    return sorted(set(files))


def related_tests(files):
    """Existing test targets likely to cover the changed files (a cheap heuristic, capped at 3)."""
    kind = repo_kind()
    targets = []
    for f in files:
        parts = f[:-3].split("/")
        if kind == "django" and parts and parts[0] == "django":
            pkg = [p for p in parts[1:] if p not in ("__init__", "contrib", "core", "db", "utils")]
            tests_dir = os.path.join(REPO, "tests")
            names = sorted(n for n in os.listdir(tests_dir) if os.path.isdir(os.path.join(tests_dir, n)))
            found = []
            for key in pkg[::-1]:
                # exact names and simple variants first, then shared prefixes ("delete" <-> "deletion")
                for cand in (key, key + "_tests", key.rstrip("s"), key + "s"):
                    if cand in names and cand not in found:
                        found.append(cand)
                if not found and len(key) >= 5:
                    found += [n for n in names if n.split("_")[0] and key.startswith(n.split("_")[0])
                              and len(n.split("_")[0]) >= 5][:2]
                if found:
                    break
            if not found:
                # fall back to the test folders that mention the changed module most often
                dotted = ".".join(p for p in parts if p != "__init__")
                _, out = sh("git grep -l -F %s -- tests" % quote(dotted))
                counts = {}
                for path in out.splitlines():
                    seg = path.split("/")
                    if len(seg) > 2:
                        counts[seg[1]] = counts.get(seg[1], 0) + 1
                found = sorted(counts, key=lambda n: (-counts[n], n))[:2]
            targets += [t for t in found if t not in targets]
        elif kind != "django":
            stem = "_".join(p for p in parts[1:] if p != "__init__")
            for cand in sorted(os.listdir(os.path.join(REPO, "tests"))) if os.path.isdir(os.path.join(REPO, "tests")) else []:
                if cand.startswith("test_") and cand.endswith(".py") and stem and (stem in cand or parts[-1] in cand):
                    targets.append("tests/" + cand)
    return targets[:3]


def cmd_regression_check(targets=None):
    """Run related existing tests on the original code and on the changed code; report new failures."""
    files = changed_source_files()
    if not files:
        return result("no source changes to check", ok=False, regressions=[], targets=[])
    targets = targets or related_tests(files)
    if not targets:
        return result("no related existing tests found; regression check skipped", ok=True, regressions=[], targets=[])
    sh("git stash push --include-untracked -q")
    try:
        _, _, failed_before, finished_before = run_tests_raw(targets)
    finally:
        sh("git stash pop -q")
    _, out_after, failed_after, finished_after = run_tests_raw(targets)
    regressions = sorted(failed_after - failed_before)
    broke_run = finished_before and not finished_after
    ok = not regressions and not broke_run
    text = "related tests: %s\nfailing before: %d, failing after: %d, new failures: %d%s" % (
        " ".join(targets), len(failed_before), len(failed_after), len(regressions),
        "\nthe test run no longer finishes after the change" if broke_run else "",
    )
    if regressions:
        text += "\nnew failures:\n  " + "\n  ".join(regressions[:20]) + "\n" + head_tail(out_after, 0, 60)
    return result(text, ok=ok, regressions=regressions, targets=targets, broke_run=broke_run)


def quote(s):
    return "'" + str(s).replace("'", "'\"'\"'") + "'"


COMMANDS = {
    "search": cmd_search,
    "outline": cmd_outline,
    "view": cmd_view,
    "edit": cmd_edit,
    "create": cmd_create,
    "run_tests": cmd_run_tests,
    "run_script": cmd_run_script,
    "regression_check": cmd_regression_check,
}

if __name__ == "__main__":
    name = sys.argv[1]
    args = json.loads(base64.b64decode(sys.argv[2]).decode("utf-8")) if len(sys.argv) > 2 else {}
    try:
        COMMANDS[name](**args)
    except TypeError as e:
        result("bad arguments for %s: %s" % (name, e), ok=False)
