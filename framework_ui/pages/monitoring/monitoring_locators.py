"""Selectors specific to the Data & Monitoring screen shell (page-level, not
any of its sections -- those live in their own components/*_locators.py
files).

Confirmed against the real deployed app (2026-09-04): a direct goto() to
"/monitoring?timeRange=24h" bounces back to "/" on the real deployed app
(same SPA deep-link limitation already documented for FleetOverviewPage) --
must navigate via the sidebar link from an already-loaded page instead.
"""
SIDEBAR_LINK_TEXT = "Data & Monitoring"
# The site selector is a plain native <select>, first one on the page.
SITE_SELECT = "select"
# The global time-range selector ("Last 24 hours"/"Last 7 days"/"Last 30
# days") is the 2nd plain <select> on the page. Confirmed 2026-09-09 this
# does NOT affect the Telemetry Data Table's own fixed 24h Live window
# (docs/OF-141.txt CA-09) -- they're deliberately independent.
TIME_RANGE_SELECT = "select >> nth=1"
# The page shell wrapper -- always present regardless of whether the
# selected site has any devices (confirmed 2026-09-04: the default site can
# show "No devices available" with zero ".device-card" elements, so that
# would be a bad marker here unlike Fleet Overview's always-populated sites
# table).
LOADED_MARKER = ".monitoring-page"
