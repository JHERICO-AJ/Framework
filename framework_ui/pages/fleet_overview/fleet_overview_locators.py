"""Selectors specific to the Fleet Overview screen shell (page-level, not any
of the 5 sections — those live in their own components/*_locators.py files).

Confirmed against the real deployed app (2026-08-26): login redirects to "/"
with a "?timeRange=24h" query string — Fleet Overview IS the app's home page
after login, there is no separate "/fleet-overview" route.
"""
# Waited on by FleetOverviewPage.open() — the first row of the sites table is
# a reliable "the page actually rendered" signal (same convention as
# AlarmsPage.open(), which waits on its own table's first row).
LOADED_MARKER = ".sites-table tbody tr"
