"""Pin the 13F options-mode default to delta_adjusted.

The default was deliberately set after Burry/Ackman/Marks reference regression
analysis. Don't let it silently flip without an explicit code review.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_sec_edgar_options_mode_default_is_delta_adjusted(monkeypatch):
    """The OS-env default for SEC_13F_OPTIONS_MODE, when unset, must produce
    delta-adjusted exposure (not 'filter', 'as_exposure', or legacy 'include')."""
    monkeypatch.delenv("SEC_13F_OPTIONS_MODE", raising=False)
    monkeypatch.delenv("SEC_13F_PUT_DELTA", raising=False)
    monkeypatch.delenv("SEC_13F_CALL_DELTA", raising=False)

    import sec_edgar
    importlib.reload(sec_edgar)
    client = sec_edgar.SECEdgarClient()

    # Minimal synthetic 13F XML — one common, one PUT, one CALL.
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>ACME COMMON</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>000000001</cusip>
    <value>100000</value>
    <sshPrnamt>1000</sshPrnamt>
    <sshPrnamtType>SH</sshPrnamtType>
  </infoTable>
  <infoTable>
    <nameOfIssuer>ACME PUT</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>000000002</cusip>
    <value>50000</value>
    <sshPrnamt>500</sshPrnamt>
    <sshPrnamtType>SH</sshPrnamtType>
    <putCall>Put</putCall>
  </infoTable>
  <infoTable>
    <nameOfIssuer>ACME CALL</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>000000003</cusip>
    <value>50000</value>
    <sshPrnamt>500</sshPrnamt>
    <sshPrnamtType>SH</sshPrnamtType>
    <putCall>Call</putCall>
  </infoTable>
</informationTable>
"""
    df = client._parse_13f_xml(xml)

    # PUT row: value should be negative and ~40% of original magnitude.
    put_rows = df[df["Name"].str.contains("PUT", na=False)]
    assert not put_rows.empty, "PUT row missing from parsed 13F"
    put_value = float(put_rows["Value"].iloc[0])
    assert put_value < 0, f"PUT value should be negative under delta_adjusted; got {put_value}"
    assert abs(abs(put_value) - 0.40 * 50000) < 1e-6, \
        f"PUT magnitude should be 0.40*50000=20000 under delta_adjusted; got {abs(put_value)}"

    # CALL row: value positive, scaled to 0.40 * original.
    call_rows = df[df["Name"].str.contains("CALL", na=False)]
    assert not call_rows.empty, "CALL row missing from parsed 13F"
    call_value = float(call_rows["Value"].iloc[0])
    assert call_value > 0, f"CALL value should be positive; got {call_value}"
    assert abs(call_value - 0.40 * 50000) < 1e-6, \
        f"CALL magnitude should be 0.40*50000=20000; got {call_value}"
