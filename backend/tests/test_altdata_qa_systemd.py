from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_altdata_qa_failure_alert_bypasses_cross_run_cooldown():
    """A genuine timer failure must not be hidden by an earlier test alert."""
    unit = (REPO_ROOT / "infra/systemd/ib-altdata-qa-alert.service").read_text()

    assert "--notify-only" in unit
    assert "--cooldown-min 0" in unit
    assert "--cooldown-min 720" not in unit


def test_qa_entrypoint_runs_the_extend_capable_chain_verifier():
    """The timer entrypoint must preserve the committed manifest baseline."""
    unit = (REPO_ROOT / "infra/systemd/ib-altdata-qa.service").read_text()
    script = (REPO_ROOT / "infra/scripts/run_altdata_qa_daily.sh").read_text()

    assert "OnFailure=ib-altdata-qa-alert.service" in unit
    assert "verify_altdata_chain.py" in script
    assert "--extend" in script
