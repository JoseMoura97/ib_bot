"""Exercise the backup shell against isolated Git repositories, never production."""
import os
from pathlib import Path
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "infra/scripts/backup_altdata_snapshots.sh"


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture
def backup(tmp_path):
    repo = tmp_path / "repo"
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    git(repo, "config", "user.name", "Backup test")
    git(repo, "config", "user.email", "backup@example.invalid")
    (repo / "seed").write_text("baseline\n")
    git(repo, "add", "seed")
    git(repo, "commit", "-m", "baseline")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "origin", "main")
    initial = git(remote, "rev-parse", "main")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    for name, body in {
        "docker": 'echo docker >> "$BACKUP_TEST_CALLS"\n'
                  'if [ "${BACKUP_TEST_SWITCH:-0}" = 1 ]; then git switch -c unexpected >&2; fi\n'
                  'printf "isolated archive fixture\\n"\n',
        "pg_restore": 'echo pg_restore >> "$BACKUP_TEST_CALLS"\n'
                      'echo "TABLE DATA public altdata_snapshots"\n',
    }.items():
        command = bin_dir / name
        command.write_text("#!/bin/sh\nset -eu\n" + body)
        command.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
           "IB_ALTDATA_PROJECT_ROOT": str(repo), "BACKUP_TEST_CALLS": str(calls)}
    return repo, remote, initial, env, calls


@pytest.mark.parametrize("state", ["feature", "detached", "dirty"])
def test_refuses_before_dump_or_publication(backup, state):
    repo, remote, initial, env, calls = backup
    if state == "feature":
        git(repo, "switch", "-c", "feature/lab")
        (repo / "feature").write_text("must never reach main\n")
        git(repo, "add", "feature")
        git(repo, "commit", "-m", "lab only")
    elif state == "detached":
        git(repo, "checkout", "--detach")
    else:
        (repo / "seed").write_text("unrelated dirty work\n")
    before = git(repo, "rev-parse", "HEAD")
    result = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)
    assert result.returncode == 2, result.stderr
    assert "refusing" in result.stderr
    assert not calls.exists()
    assert not (repo / "backups").exists()
    assert git(repo, "rev-parse", "HEAD") == before
    assert git(remote, "rev-parse", "main") == initial


def test_main_publishes_only_backup(backup):
    repo, remote, initial, env, calls = backup
    result = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert git(repo, "branch", "--show-current") == "main"
    assert git(remote, "rev-parse", "main") == git(repo, "rev-parse", "HEAD") != initial
    changed = git(repo, "diff", "--name-only", initial, "HEAD").splitlines()
    assert len(changed) == 1 and changed[0].startswith("backups/altdata_snapshots/")
    assert git(repo, "status", "--porcelain") == ""
    assert calls.read_text().splitlines() == ["docker", "pg_restore"]


def test_branch_change_during_dump_cannot_publish(backup):
    repo, remote, initial, env, calls = backup
    env["BACKUP_TEST_SWITCH"] = "1"
    result = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)
    assert result.returncode == 2, result.stderr
    assert "current=unexpected" in result.stderr
    assert git(remote, "rev-parse", "main") == initial
    assert git(repo, "rev-parse", "HEAD") == initial
    assert git(repo, "diff", "--cached", "--name-only") == ""
