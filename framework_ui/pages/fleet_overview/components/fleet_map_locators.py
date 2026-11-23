"""Selectors for the Fleet Map section: site markers (Leaflet, rendered as
SVG <path> elements) and the fullscreen toggle.

Confirmed against the real deployed app (2026-08-26, popup confirmed
2026-08-31):
- Status is NOT a data-status attribute — it's encoded as a CSS custom
  property name in the marker's own "fill"/"stroke" attribute, literally
  fill="var(--offline)" / var(--warning) / var(--critical) / etc. Each site
  renders as TWO <path class="leaflet-interactive"> siblings sharing the
  same fill variable: a translucent HALO (fill-opacity="0.15") and a solid
  DOT (fill-opacity="1") on top of it. Playwright's real-click actionability
  check refuses the halo (the dot on top intercepts pointer events) — click
  the DOT, not "the first path for this status".
- The expand button (top-right of the map) triggers the browser's NATIVE
  Fullscreen API (confirmed via document.fullscreenElement), not a custom
  modal with a backdrop. Clicking outside it while fullscreen does NOT close
  it (tested empirically).
- The site info popup (Qase #14) DOES exist and DOES open on click — it was
  missed twice before because: (a) the default Playwright viewport
  (1280x720) lets fixed UI elements overlap the map, blocking a real click
  on the marker (force clicks landed but the popup's OWN click handler
  never fired), and (b) the popup pane exists in the DOM immediately but
  its content renders an instant later — reading it too early finds an
  empty ".leaflet-popup-pane". See BrowserFactory's 1920x1080 viewport fix
  and FleetMap.wait_for_popup_content() below.
"""
MARKER = "path.leaflet-interactive"
FULLSCREEN_BUTTON = ".leaflet-control-fullscreen-button"
MAP_CONTAINER = ".leaflet-map"
POPUP_PANE = ".leaflet-popup-pane"
POPUP = ".leaflet-popup"
POPUP_HEADER = ".popup-header"
POPUP_SUBTITLE = ".popup-subtitle"
POPUP_STATUS_PILL = ".popup-subtitle .status-pill"
POPUP_ROW = ".popup-row"
