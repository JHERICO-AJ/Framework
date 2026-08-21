"""Reconcile alarms between the API and the UI.

Cross-layer helper: given the open alarms from the API (AlarmsService, list of
Alarm models) and the rows shown on screen (AlarmsPage, list of AlarmRow), it
tells whether the screen shows the same alarms the API reports.

Used by the alarms-UI test and by `tools.probar --with-ui`.
Comparison key: (alarm name, device) — normalized (trimmed, lowercased).
"""
from __future__ import annotations


def _norm(text):
    return (text or "").strip().lower()


def compare_alarms(api_alarms, ui_rows):
    """Return which alarms are in both, only in the API, or only in the UI.

    api_alarms: list of Alarm (from AlarmsService)
    ui_rows:    list of AlarmRow (from AlarmsPage.rows())
    -> {"in_both": set, "api_only": set, "ui_only": set} of (name, device) keys.
       api_only = API has it but the screen does NOT show it (UI bug).
       ui_only  = the screen shows it but the API does NOT have it (phantom row).
    """
    api_keys = {(_norm(a.name), _norm(a.device_name)) for a in api_alarms if a.is_open}
    ui_keys = {(_norm(r.name), _norm(r.device)) for r in ui_rows}
    return {
        "in_both": api_keys & ui_keys,
        "api_only": api_keys - ui_keys,
        "ui_only": ui_keys - api_keys,
    }
