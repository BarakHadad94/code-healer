import backend.config_loader as cl


def test_defaults_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cl, "_CONFIG_PATH", tmp_path / "nonexistent.yaml")
    config = cl.load_config()
    assert config["model"] == "claude-sonnet-4-6"
    assert "auth/" in config["sensitive_paths"]


def test_file_values_override_defaults(tmp_path, monkeypatch):
    f = tmp_path / "config.yaml"
    f.write_text("model: claude-opus-4-8\n")
    monkeypatch.setattr(cl, "_CONFIG_PATH", f)
    config = cl.load_config()
    assert config["model"] == "claude-opus-4-8"
    assert "auth/" in config["sensitive_paths"]  # default preserved


def test_empty_yaml_returns_defaults(tmp_path, monkeypatch):
    f = tmp_path / "config.yaml"
    f.write_text("")
    monkeypatch.setattr(cl, "_CONFIG_PATH", f)
    assert cl.load_config() == dict(cl._DEFAULTS)


def test_get_sensitive_paths_returns_strings(tmp_path, monkeypatch):
    f = tmp_path / "config.yaml"
    f.write_text("sensitive_paths:\n  - auth/\n  - payments/\n")
    monkeypatch.setattr(cl, "_CONFIG_PATH", f)
    paths = cl.get_sensitive_paths()
    assert all(isinstance(p, str) for p in paths)
    assert "auth/" in paths


def test_get_sensitive_paths_empty_list(tmp_path, monkeypatch):
    f = tmp_path / "config.yaml"
    f.write_text("sensitive_paths: []\n")
    monkeypatch.setattr(cl, "_CONFIG_PATH", f)
    assert cl.get_sensitive_paths() == []


def test_get_model_configured(tmp_path, monkeypatch):
    f = tmp_path / "config.yaml"
    f.write_text("model: claude-haiku-4-5-20251001\n")
    monkeypatch.setattr(cl, "_CONFIG_PATH", f)
    assert cl.get_model() == "claude-haiku-4-5-20251001"


def test_get_model_falls_back_to_default(tmp_path, monkeypatch):
    monkeypatch.setattr(cl, "_CONFIG_PATH", tmp_path / "missing.yaml")
    assert cl.get_model() == cl._DEFAULTS["model"]
