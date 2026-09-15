"""FleetMap — reusable component: the fleet map with per-site status markers
and the click-to-open site info popup."""
from __future__ import annotations

import re

from framework_ui.base.base_component import BaseComponent
from framework_ui.pages.fleet_overview.components import fleet_map_locators as loc


class FleetMap(BaseComponent):
    def markers(self):
        return self.page.locator(loc.MARKER)

    def marker_status(self, index):
        """Reads the status encoded in the marker's own fill attribute
        (fill="var(--warning)" -> "warning"). None if unparseable."""
        fill = self.markers().nth(index).get_attribute("fill") or ""
        match = re.match(r"var\(--([\w-]+)\)", fill)
        return match.group(1) if match else None

    def marker_by_status(self, status):
        """First marker path whose fill var matches this status, or None."""
        locator = self.page.locator(f'{loc.MARKER}[fill="var(--{status})"]')
        return locator.first if locator.count() > 0 else None

    def clickable_marker_by_site_name(self, site_name):
        """Same "solid dot, not the halo" targeting as
        clickable_marker_by_status, but matched by SITE NAME instead of
        status -- for cases that need a SPECIFIC site (e.g. cross-layer
        Power checks), not just "any Critical site". Each marker carries
        `aria-describedby="leaflet-tooltip-N"` pointing at its hover
        tooltip element -- but confirmed 2026-09-02: that attribute isn't
        present in the DOM until the marker has actually been hovered at
        least once (Leaflet creates the tooltip on demand, not eagerly).
        Hovers each candidate marker first, then reads the attribute.

        NOTE: if multiple sites' markers are stacked at/near the same
        coordinates (all 6 BOLIVIA sites sharing near-identical lat/lng is
        a known past config gap here), hovering by bounding box may land
        on whichever marker is topmost at that pixel, not necessarily the
        Nth one in DOM order -- this method can misidentify a site in that
        case. It's reliable once sites have distinct coordinates.

        Returns None if no marker matches."""
        dots = self.page.locator(f'{loc.MARKER}[fill-opacity="1"]')
        for i in range(dots.count()):
            dot = dots.nth(i)
            self.hover_marker(dot)
            self.page.wait_for_timeout(200)
            tooltip_id = dot.get_attribute("aria-describedby")
            if not tooltip_id:
                continue
            name = self.page.locator(f"#{tooltip_id}").inner_text().strip()
            if name == site_name:
                return dot
        return None

    def clickable_marker_by_status(self, status):
        """Same as marker_by_status, but only the solid DOT (fill-opacity=1)
        -- the translucent halo sitting under it blocks a real click (see
        fleet_map_locators.py's docstring). Use this one to actually click
        a marker; use marker_by_status for the color assertions."""
        locator = self.page.locator(
            f'{loc.MARKER}[fill="var(--{status})"][fill-opacity="1"]')
        return locator.first if locator.count() > 0 else None

    def marker_computed_color(self, marker_locator):
        """Resolves the CSS var to an actual rgb(...) string (SVG fill, not
        backgroundColor — these are <path> elements)."""
        return marker_locator.evaluate("el => getComputedStyle(el).fill")

    def open_fullscreen(self):
        self.page.locator(loc.FULLSCREEN_BUTTON).click()

    def is_fullscreen(self):
        return self.page.evaluate("!!document.fullscreenElement")

    # ---- site info popup (Qase #14) ----
    # Real spec, confirmed via OF-345 (Jira user story, provided 2026-09-01)
    # + reproduced live the same day:
    #   HOVER a marker  -> popup opens (preview)
    #   CLICK a marker  -> map zooms to that site AND the popup stays
    #                      "fixed" (pinned) even after the mouse moves away
    #   CLICK elsewhere -> DOES dismiss it (confirmed live 2026-09-01, after
    #                      the user reported seeing it close manually) --
    #                      but the click has to land on the map's own
    #                      background/tile surface, not just "somewhere in
    #                      the container": corner-area clicks (85-90% across)
    #                      consistently did NOT close it across repeated
    #                      tries, while a click at the map's CENTER did,
    #                      every time. Likely the corners were landing
    #                      outside the rendered tile bounds at that zoom
    #                      level (blank container background, no Leaflet
    #                      click handler there) or on a map control.
    #                      click_map_background() uses the center.

    def hover_marker(self, marker_locator):
        """A REAL mouse move to the marker's center (not Locator.hover(),
        for the same reason click_marker uses a raw mouse click -- see its
        docstring)."""
        box = marker_locator.bounding_box()
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        self.page.mouse.move(cx, cy)

    def click_marker(self, marker_locator):
        """A REAL mouse click at the marker's exact center — NOT
        Locator.click()/force=True. Confirmed 2026-08-31: Playwright's
        synthetic force-click bypasses the actionability check but doesn't
        reliably trigger the popup's own click handler; a real
        page.mouse.click at the resolved coordinates does. Also triggers
        the map's zoom-to-site (confirmed 2026-09-01: the marker's own
        bounding box goes stale/zero-size right after, consistent with the
        map re-centering/re-rendering)."""
        box = marker_locator.bounding_box()
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        self.page.mouse.click(cx, cy)

    def wait_for_popup_content(self, timeout=8000):
        """The popup PANE exists in the DOM immediately on click, but its
        content (the actual .leaflet-popup) renders an instant later --
        reading it too early finds an empty pane, not an error. Wait for
        real children instead of a fixed sleep. Confirmed 2026-08-31: even
        "the pane has children" fired too early sometimes -- the pane and
        its first rows can render before the LAST row ("Active Alarms")
        does. Uses Playwright's own Locator.wait_for (polls + retries
        against live DOM state) rather than a one-shot wait_for_function,
        which proved flaky across repeated runs."""
        self.page.locator(loc.POPUP_ROW).filter(has_text="Active Alarms").first.wait_for(
            state="visible", timeout=timeout)

    def is_popup_open(self):
        return self.page.locator(loc.POPUP).count() > 0

    def popup_site_name(self):
        """The header has a trailing icon <span> right after the name
        (confirmed 2026-08-31: <div class="popup-header">BOLIVIA<span>...
        </span></div>) -- .inner_text() on the whole div pulls that in too,
        so read only the div's own direct text node."""
        return self.page.locator(loc.POPUP_HEADER).evaluate(
            "el => Array.from(el.childNodes)"
            ".filter(n => n.nodeType === Node.TEXT_NODE)"
            ".map(n => n.textContent).join('').trim()"
        )

    def popup_status(self):
        return self.page.locator(loc.POPUP_STATUS_PILL).inner_text().strip()

    def popup_fields(self):
        """{'Location': '31.26, -98.55', 'Last Seen': 'Just now', 'SOC': '-%',
        'Power': '-5365 kW', 'Active Alarms': '11'} -- parsed from the
        popup's label/value rows.

        Reads ALL rows in a single page.evaluate() instead of one
        Locator.inner_text() call per cell (confirmed 2026-09-01: with live
        telemetry re-rendering the popup mid-read, a several-calls-in-a-loop
        approach can have React swap the DOM out between calls, timing out
        on a stale locator -- one atomic JS snapshot avoids that race)."""
        return self.page.locator(loc.POPUP).evaluate(
            f"""el => {{
                const fields = {{}};
                el.querySelectorAll('{loc.POPUP_ROW}').forEach(row => {{
                    const label = row.querySelector('span')?.textContent?.trim();
                    const value = row.querySelector('strong')?.textContent?.trim();
                    if (label) fields[label] = value;
                }});
                return fields;
            }}"""
        )

    def popup_power_kw(self):
        """Parses the popup's "Power" row ("-5365 kW") into a float, same
        regex approach as SitesList.power_kw for consistency. None for the
        empty-cell placeholder ("-"/"—")."""
        text = self.popup_fields().get("Power", "")
        match = re.search(r"-?[\d,]+\.?\d*", text)
        return float(match.group(0).replace(",", "")) if match else None

    def click_map_background(self):
        """Dismisses a pinned popup by clicking the map's own background
        (not a marker, not the popup) -- see the class-level comment above
        click_marker for why this specifically uses the center point."""
        map_box = self.page.locator(loc.MAP_CONTAINER).first.bounding_box()
        self.page.mouse.click(
            map_box["x"] + map_box["width"] / 2,
            map_box["y"] + map_box["height"] / 2,
        )

