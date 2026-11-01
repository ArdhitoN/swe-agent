import base64
import json
import os
import subprocess
import sys

import pytest

from gated_agent.tools import TOOLBOX_SRC, blocked_reason, split_result


# ---------------------------------------------------------------- toolbox (runs locally on a temp repo)

@pytest.fixture
def repo(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "mod.py").write_text("def add(a, b):\n    return a - b\n\n\nclass K:\n    def m(self):\n        return 1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_mod.py").write_text("from pkg.mod import add\n\ndef test_add():\n    assert add(1, 2) == 3\n")
    subprocess.run("git init -q && git add -A && git -c user.email=a@b -c user.name=t commit -qm init", shell=True, cwd=tmp_path, check=True)
    return tmp_path


def toolbox(repo, name, **args):
    env = {**os.environ, "GATED_REPO": str(repo), "GATED_PROJECT_PY": sys.executable, "PYTHONPATH": str(repo)}
    payload = base64.b64encode(json.dumps(args).encode()).decode()
    out = subprocess.run([sys.executable, str(TOOLBOX_SRC), name, payload], capture_output=True, text=True, env=env)
    return split_result(out.stdout)


def test_edit_replaces_one_unique_match(repo):
    text, data = toolbox(repo, "edit", path="pkg/mod.py", old="return a - b", new="return a + b")
    assert data["ok"], text
    assert "return a + b" in (repo / "pkg" / "mod.py").read_text()


def test_edit_refuses_missing_and_ambiguous_matches(repo):
    assert not toolbox(repo, "edit", path="pkg/mod.py", old="nope", new="x")[1]["ok"]
    (repo / "pkg" / "mod.py").write_text("x = 1\nx = 1\n")
    text, data = toolbox(repo, "edit", path="pkg/mod.py", old="x = 1", new="x = 2")
    assert not data["ok"] and "2 times" in text


def test_edit_undoes_syntax_errors(repo):
    before = (repo / "pkg" / "mod.py").read_text()
    text, data = toolbox(repo, "edit", path="pkg/mod.py", old="return a - b", new="return a +")
    assert not data["ok"] and data.get("reverted")
    assert (repo / "pkg" / "mod.py").read_text() == before


def test_edit_refuses_test_files(repo):
    text, data = toolbox(repo, "edit", path="tests/test_mod.py", old="3", new="-1")
    assert not data["ok"] and "test file" in text


def test_search_outline_view(repo):
    assert toolbox(repo, "search", pattern="def add")[1]["matches"] == 1
    assert "class K" in toolbox(repo, "outline", path="pkg/mod.py")[0]
    assert "return a - b" in toolbox(repo, "view", path="pkg/mod.py", start=1, end=2)[0]


def test_run_script_reports_exit_code(repo):
    (repo / "repro.py").write_text("import sys\nfrom pkg.mod import add\nsys.exit(0 if add(1, 2) == 3 else 1)\n")
    assert toolbox(repo, "run_script", path=str(repo / "repro.py"))[1]["exit_code"] == 1


# ---------------------------------------------------------------- bash guard

@pytest.mark.parametrize("cmd", [
    "git log --all --oneline", "git fetch origin", "git checkout HEAD~3", "pip install django==4.0",
    "curl https://example.com", "python -c 'import urllib.request'", "sed -i 's/a/b/' x.py",
])
def test_blocked_commands(cmd):
    assert blocked_reason(cmd)


@pytest.mark.parametrize("cmd", [
    "git diff", "git status", "git log -5 --oneline", "git checkout -- django/x.py", "pip list",
    "python /tmp/repro.py", "grep -rn foo django/ | head",
])
def test_allowed_commands(cmd):
    assert blocked_reason(cmd) is None


def _related(root, files):
    import importlib.util

    os.environ["GATED_REPO"] = str(root)
    spec = importlib.util.spec_from_file_location("toolbox_under_test", TOOLBOX_SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.related_tests(files)


def test_related_tests_django_layout(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "runtests.py").write_text("")
    for name in ["delete", "delete_regress", "forms_tests", "auth_tests", "queries", "model_fields", "templates"]:
        (tmp_path / "tests" / name).mkdir()
        if name != "templates":  # a folder of template files, not tests
            (tmp_path / "tests" / name / "tests.py").write_text("")
    assert _related(tmp_path, ["django/db/models/deletion.py"]) == ["delete", "delete_regress"]
    assert _related(tmp_path, ["django/contrib/auth/forms.py"]) == ["auth_tests"]
    assert _related(tmp_path, ["django/db/models/query.py"]) == ["queries"]
    assert _related(tmp_path, ["django/db/models/fields/__init__.py"]) == ["model_fields"]


def test_related_tests_sphinx_layout(tmp_path):
    (tmp_path / "sphinx").mkdir()
    (tmp_path / "tests").mkdir()
    for name in ["test_ext_autodoc.py", "test_ext_autodoc_configs.py", "test_domain_py.py", "test_build.py"]:
        (tmp_path / "tests" / name).write_text("")
    assert _related(tmp_path, ["sphinx/domains/python.py"])[0] == "tests/test_domain_py.py"
    assert _related(tmp_path, ["sphinx/ext/autodoc/__init__.py"])[:2] == [
        "tests/test_ext_autodoc.py", "tests/test_ext_autodoc_configs.py"]


def test_edit_fixes_a_constant_indentation_mistake(repo):
    (repo / "pkg" / "mod.py").write_text("class K:\n    def m(self):\n        if True:\n            return 1\n")
    text, data = toolbox(repo, "edit", path="pkg/mod.py", old="    if True:\n        return 1", new="    if True:\n        return 2")
    assert data["ok"], text
    assert "+4 spaces" in text
    assert (repo / "pkg" / "mod.py").read_text().endswith("        if True:\n            return 2\n")


def test_edit_shows_exact_text_when_lines_differ(repo):
    text, data = toolbox(repo, "edit", path="pkg/mod.py", old="def add(a, b):\n    return a * b", new="x")
    assert not data["ok"] and "Exact text there" in text and "return a - b" in text
