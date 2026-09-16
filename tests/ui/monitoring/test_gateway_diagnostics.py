"""Data & Monitoring - Gateway Diagnostics (Communication Status / Gateway ID /
MAC ID / Data Freshness), cross-layer against
GET /api/monitoring/summary/{site_id}'s `gatewayDiagnostics` object.

Exact cross-layer for the 4 main values (stable within a snapshot). The
mini-metrics that change every tick (Data latency, Last comms) are liveness-
only checks (populated with a plausible value), same convention as Fleet
Overview's Power tests for values too fast-moving to pin exactly.
"""
import re

import pytest

from shared.datasource.db_source import get_site_ids

pytestmark = pytest.mark.ui

SITE_NAME = "BOLIVIA"


@pytest.fixture(scope="session")
def bolivia_site_id(db_conn):
    return get_site_ids(db_conn, [SITE_NAME])[SITE_NAME]


@pytest.fixture
def bolivia_monitoring_page(require_omniops, monitoring_page):
    return monitoring_page.select_site(SITE_NAME)


@pytest.fixture
def api_summary(monitoring_service, bolivia_site_id):
    return monitoring_service.get_monitoring_summary(site_id=bolivia_site_id)


def test_communication_status_matches_api(bolivia_monitoring_page, api_summary):
    gw = bolivia_monitoring_page.gateway_diagnostics()
    assert gw.value("Communication Status") == api_summary.gateway_diagnostics.heartbeat_status


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-10, business rule clarified directly by "
           "the team): docs/OF-146.txt reads as if a missing heartbeat should "
           "ALWAYS force Disconnected, no matter how fresh the rest of the "
           "telemetry is (CA-09/CA-29's 'no digas que no bloquea si eso suena "
           "a Connected'). But the real intended rule -- confirmed directly, "
           "matching docs/OmniOps_Parameter_Mapping_V03's own EMS Heartbeat "
           "fallback ('If counter missing, use Last Communication Time "
           "only') -- is that a Fractal site with no heartbeat but FRESH "
           "telemetry should still read Connected (or Watch/Disconnected "
           "per the SAME 2x/5x age thresholds as Data Freshness), not a "
           "hardcoded Disconnected. Confirmed live via the raw API payload: "
           "heartBeatStatus='Disconnected' while dataFreshness='Fresh' and "
           "freshnessSeconds=4.8 (well under the connected threshold) at the "
           "same instant -- proves this is a backend calculation bug, not a "
           "UI display issue.")
def test_communication_status_follows_data_freshness_when_no_heartbeat(bolivia_monitoring_page, api_summary):
    """CA-09/CA-29 (docs/OF-146.txt) vs. docs/OmniOps_Parameter_Mapping_V03's
    EMS Heartbeat fallback -- see the xfail reason above for the full
    conflict and its resolution. BOLIVIA is Fractal (no heartbeat field at
    all, confirmed against docs/GUIA_CONSUMO_PROTO_FRACTAL.md), so with
    fresh telemetry it should read "Connected", mirroring Data Freshness's
    own word via the same age thresholds -- not a hardcoded "Disconnected"."""
    gw = bolivia_monitoring_page.gateway_diagnostics()
    freshness_word = api_summary.gateway_diagnostics.data_freshness
    expected = {"Fresh": "Connected", "Watch": "Watch", "Stale": "Disconnected"}[freshness_word]
    assert gw.value("Communication Status") == expected, (
        f"expected Communication Status to follow Data Freshness's own word "
        f"({freshness_word!r} -> {expected!r}) when there's no heartbeat, "
        f"per the confirmed fallback rule")


def test_gateway_id_matches_api(bolivia_monitoring_page, api_summary):
    gw = bolivia_monitoring_page.gateway_diagnostics()
    assert gw.value("Gateway ID") == api_summary.gateway_diagnostics.gateway_id


def test_mac_id_matches_api(bolivia_monitoring_page, api_summary):
    gw = bolivia_monitoring_page.gateway_diagnostics()
    assert gw.value("MAC ID") == api_summary.gateway_diagnostics.mac_id


def test_data_freshness_word_matches_api(bolivia_monitoring_page, monitoring_service, bolivia_site_id):
    """UI shows e.g. "Fresh (<7 sec)" -- a qualitative word plus a live
    seconds figure. Only the word ("Fresh"/"Watch"/"Stale") is asserted
    exactly; the seconds figure moves every tick.

    Retries a few times, re-reading BOTH sides fresh each time: per
    docs/OF-146.txt, the frontend ages this word using its OWN local clock
    every 1s from "Last comms" ("Envejecimiento de frescura: Calculo local
    en el navegador cada 1 s"), independent of the backend's own snapshot
    -- so right at a 2x/5x interval threshold boundary, the UI and a
    freshly-fetched API value can legitimately land on opposite sides of
    the word for a moment (confirmed 2026-09-07: saw "Watch" vs "Fresh").
    A stable mismatch across retries would still be a real bug."""
    gw = bolivia_monitoring_page.gateway_diagnostics()
    attempts = 3
    word, expected_word = None, None
    for attempt in range(attempts):
        expected_word = monitoring_service.get_monitoring_summary(
            site_id=bolivia_site_id).gateway_diagnostics.data_freshness
        text = gw.value("Data Freshness")
        word = text.split("(")[0].strip()
        if word == expected_word:
            return
        if attempt < attempts - 1:
            bolivia_monitoring_page.page.wait_for_timeout(2000)
    assert word == expected_word, (
        f"Data Freshness word never matched across {attempts} tries (~2s apart) "
        f"-- if this keeps happening well away from a threshold boundary, it's "
        f"a real bug, not just aging-clock jitter")


def test_mac_id_mini_metrics_are_populated(bolivia_monitoring_page):
    gw = bolivia_monitoring_page.gateway_diagnostics()
    latency = gw.mini_metric("MAC ID", "Data latency")
    last_comms = gw.mini_metric("MAC ID", "Last comms")
    assert latency and re.search(r"\d", latency), f"Data latency not populated: {latency!r}"
    assert last_comms and re.search(r"\d", last_comms), f"Last comms not populated: {last_comms!r}"


def test_data_freshness_mini_metrics_match_api(bolivia_monitoring_page, api_summary):
    """System ID / Sampling interval / Aggregation window are stable
    per-site config, not live-changing values -- exact cross-layer."""
    gw = bolivia_monitoring_page.gateway_diagnostics()
    assert gw.mini_metric("Data Freshness", "System ID") == api_summary.gateway_diagnostics.system_id
    sampling = gw.mini_metric("Data Freshness", "Sampling interval")
    aggregation = gw.mini_metric("Data Freshness", "Aggregation window")
    assert sampling == f"{api_summary.gateway_diagnostics.sampling_interval:g} s"
    assert aggregation == f"{api_summary.gateway_diagnostics.aggregation_window:g} s"
