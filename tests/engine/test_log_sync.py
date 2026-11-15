import json
import subprocess

from tools import sync_logs


def test_anonymize_replaces_names_everywhere():
    recs = [{"player": "Drew", "input": "punch Jerry", "replies": [{"text": "Jerry attacks Drew for 4 damage."}]},
            {"player": "Ann", "input": '"Drew, run!"', "replies": [{"text": "Ann shouts at drew."}]}]
    out = sync_logs.anonymize(recs, "k")
    blob = json.dumps(out)
    assert "Drew" not in blob and "drew" not in blob and "Ann" not in blob
    assert "Jerry" in blob                                      # NPC names stay
    d = sync_logs.anon_id("Drew", "k")
    assert out[0]["player"] == d and d in out[1]["input"] and d in out[1]["replies"][0]["text"]
    assert sync_logs.anon_id("Drew", "k") != sync_logs.anon_id("Drew", "other-salt")


def test_sync_pushes_to_play_logs_branch(tmp_path, monkeypatch):
    run = lambda *a, cwd: subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True)
    bare, repo, logs = tmp_path / "remote.git", tmp_path / "repo", tmp_path / "logs"
    run("init", "--bare", "-q", str(bare), cwd=tmp_path)
    run("init", "-q", str(repo), cwd=tmp_path)
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        run("config", k, v, cwd=repo)
    (repo / "README").write_text("code")
    run("add", "README", cwd=repo); run("commit", "-qm", "code", cwd=repo)
    run("remote", "add", "origin", str(bare), cwd=repo)
    logs.mkdir()
    (logs / "2026-11-14.jsonl").write_text(json.dumps({"player": "Drew", "input": "hi"}) + "\n")
    monkeypatch.setattr(sync_logs, "ROOT", str(repo))
    monkeypatch.setattr(sync_logs, "LOG_DIR", str(logs))
    monkeypatch.setattr(sync_logs, "WORKTREE", str(repo / ".play-logs-worktree"))
    assert "pushed" in sync_logs.sync()
    published = run("show", "play-logs:logs/2026-11-14.jsonl", cwd=bare).stdout
    assert "Drew" not in published and "player-" in published
    assert run("ls-tree", "--name-only", "play-logs", cwd=bare).stdout.split() == ["logs"]   # no code on the branch
    assert sync_logs.sync() == "no new log lines"
