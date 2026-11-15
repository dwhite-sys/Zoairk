import os

import pytest

from tools import setup_domain


@pytest.mark.parametrize("raw,clean", [("play.example.com", ("play.example.com", "")),
                                       ("https://Play.Example.com/", ("play.example.com", "")),
                                       ("zoairk.byui-ai.org:443", ("zoairk.byui-ai.org", "")),
                                       ("https://www.byui-ai-society.site/zoairk/", ("www.byui-ai-society.site", "/zoairk"))])
def test_clean_domain_accepts(raw, clean):
    assert setup_domain.clean_domain(raw) == clean


@pytest.mark.parametrize("raw", ["localhost", "not a domain", "-bad.com", "example", "a..b.com", "ok.com/bad path"])
def test_clean_domain_rejects(raw):
    with pytest.raises(ValueError):
        setup_domain.clean_domain(raw)


def test_render_files():
    files = setup_domain.render("play.example.com", 9000, "ann", "/srv/zoairk")
    assert "ZOAIRK_PUBLIC_URL=https://play.example.com" in files["zoairk.env"]
    assert "ZOAIRK_HOST=127.0.0.1" in files["zoairk.env"] and "ZOAIRK_WS_PORT=9000" in files["zoairk.env"]
    assert files["Caddyfile"].startswith("play.example.com {") and "127.0.0.1:9000" in files["Caddyfile"]
    assert "User=ann" in files["zoairk.service"] and "EnvironmentFile=/srv/zoairk/zoairk.env" in files["zoairk.service"]


def test_server_reads_env_file(tmp_path, monkeypatch):
    import server
    env = tmp_path / "zoairk.env"
    env.write_text("# comment\nZOAIRK_TEST_SETTING=from-file\nZOAIRK_TEST_KEEP=from-file\n")
    monkeypatch.setenv("ZOAIRK_TEST_KEEP", "from-env")
    monkeypatch.delenv("ZOAIRK_TEST_SETTING", raising=False)
    server._load_env_file(str(env))
    assert os.environ["ZOAIRK_TEST_SETTING"] == "from-file"
    assert os.environ["ZOAIRK_TEST_KEEP"] == "from-env"          # real environment wins
    monkeypatch.delenv("ZOAIRK_TEST_SETTING")


def test_render_under_a_path():
    files = setup_domain.render("www.byui-ai-society.site", 8765, "drew", "/srv/zoairk", "/zoairk")
    assert "ZOAIRK_PUBLIC_URL=https://www.byui-ai-society.site/zoairk" in files["zoairk.env"]
    assert "handle_path /zoairk/*" in files["Caddyfile"] and "redir /zoairk /zoairk/" in files["Caddyfile"]
