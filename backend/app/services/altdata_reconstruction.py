"""Point-in-time reconstruction guards for alt-data snapshot vintages."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from app.models.altdata import AltDataSnapshot


def reconstruct_state_from_vintages(
    vintages: Iterable[AltDataSnapshot], *, as_of_day: date
) -> dict[str, AltDataSnapshot]:
    """Return each source's latest supplied vintage for ``as_of_day``.

    Callers must query the archive using the same cutoff.  This explicit
    validation makes a future vintage a hard error instead of silently leaking
    information into a historical reconstruction.
    """
    state: dict[str, AltDataSnapshot] = {}
    for vintage in vintages:
        captured_day = vintage.captured_at.date()
        if captured_day > as_of_day:
            raise ValueError(
                f"future vintage {vintage.id} captured on {captured_day} "
                f"cannot reconstruct {as_of_day}"
            )
        current = state.get(vintage.source)
        if current is None or (vintage.captured_at, vintage.id) > (
            current.captured_at,
            current.id,
        ):
            state[vintage.source] = vintage
    return state
