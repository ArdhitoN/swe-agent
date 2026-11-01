from lift_eval.config import load_env, load_experiment


def test_experiment_config_has_locked_fields():
    cfg = load_experiment()
    assert cfg["model"]["name"] == "openai/gpt-5-mini-2025-08-07"
    assert cfg["budget"]["per_bug_max_calls"] == 250
    assert cfg["budget"]["per_bug_max_cost_usd"] == 3.0
    assert cfg["runs"] == {"A": 5, "B": 3}


def test_load_env_does_not_overwrite(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\nFOO_TEST_KEY=from_file\nBAR_TEST_KEY='quoted'\n")
    monkeypatch.setenv("FOO_TEST_KEY", "already_set")
    monkeypatch.delenv("BAR_TEST_KEY", raising=False)
    monkeypatch.setenv("SWE_AGENT_ENV_FILE", str(env_file))
    load_env()
    import os

    assert os.environ["FOO_TEST_KEY"] == "already_set"
    assert os.environ["BAR_TEST_KEY"] == "quoted"
