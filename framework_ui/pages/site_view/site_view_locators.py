"""Selectors for the Site View -- Single Site screen shell (/site?timeRange=24h).

Confirmed against the real deployed app (2026-09-18): a direct goto() to
"/site?timeRange=24h" would hit the same SPA deep-link bounce-back already
documented for FleetOverviewPage/MonitoringPage -- navigate via the sidebar
link from an already-loaded page instead.
"""
SIDEBAR_LINK_TEXT = "Site View"
# The site selector is a plain native <select>, first one on the page.
SITE_SELECT = "select"
# Present regardless of which site is selected -- confirmed via the header
# "SITE STATUS" card, always rendered once a site is chosen.
LOADED_MARKER = "text=SITE STATUS"
