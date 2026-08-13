from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_altdata_qa_failure_alert_bypasses_cross_run_cooldown():
    """A genuine timer failure must not be hidden by an earlier test alert."""
    unit = (REPO_ROOT / "infra/systemd/ib-altdata-qa-alert.service").read_text()

    assert "--notify-only" in unit
    assert "--cooldown-min 0" in unit
    assert "--cooldown-min 720" not in unit
