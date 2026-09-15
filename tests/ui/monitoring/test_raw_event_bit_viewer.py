"""Data & Monitoring - Raw Event Bit Viewer (docs/OF-381.txt): compacted
evt1/evt2/pcsevt1 bitfield words + a "Decode" modal listing only the
active (Set) bits. Always live, no 24h/7d/30d applicability (CA-05), same
pattern as Thermal Diagnostics/Site Load & Backup Context/PCS Energy
Statistics' non-applicability.

BOLIVIA (Fractal). Confirmed live 2026-09-13 (30s poll, no change): evt1
and evt2 are permanently "—" for this site. Initially assumed this was a
genuine, benign Fractal gap (docs/omniops_data_intake_BOLIVIA.xlsx's
Bitfield-Registers sheet has no ENABLED entry mapping to this panel's
Evt1/Evt2 -- true, but that only affects LABELS, not the raw value) --
but reading the real backend source (FractalRawDataMapper.cs) proved
otherwise:
    row.Evt1 = SnapshotMapperSupport.FormatEventBits(
        emu.AlarmWord1 != 0 ? emu.AlarmWord1 : emu.StatusWord1);
Evt1 IS genuinely mapped from live EMU telemetry (AlarmWord1, falling
back to StatusWord1) -- it's real, not absent. The actual bug is in
FormatEventBits itself (SnapshotMapperSupport.cs):
    public static string? FormatEventBits(uint bits) => bits == 0 ? null : bits.ToString("X8");
When the real telemetry value is a genuine 0 (all clear, no bits set --
confirmed live: EMU_STATUS_WORD_1..10 are all 0 for BOLIVIA right now),
this returns null -- collapsing "genuinely zero" and "no data received"
into the exact same downstream value, even though docs/OF-381.txt's own
formatBitWord table treats them as different, meaningful states ("Vacío/
nulo -> —" vs "Solo ceros -> 0×N"). Confirmed EmuAlarmWord1 carries real,
non-trivial diagnostic data (not a throwaway field) via
docs/fractal-alarms-coverage-open-by-id 1.md: alarm #70 (Lightning/SPD)
reads "EMU Status&Alarm · Alarm word 1 bit5 690V SPD" -- exactly the
field this panel's Evt1 is built from. An engineer using this panel
specifically to check EMS/PCS bitfields (the HU's own stated purpose)
can't tell "checked, all clear" from "no data available" -- a real loss
of diagnostic value, not a documentation gap.

pcsevt1 DOES have real data (a 1-bit-set 8-bit word). Investigated the
decode modal's "Raw" column showing a different-looking string than the
card's own compacted value ("00000102" vs "00000010") by reading the real
backend source (EventBitfieldDecoder.cs, BitfieldWordParser.cs): "Raw" is
the untouched source string exactly as ingested (RawHex = rawValue),
while the card's compacted value is the NORMALIZED binary after parsing
-- "00000102" isn't valid pure binary (has a '2'), so the parser correctly
falls through to hex parsing (0x102 = 258 decimal = binary "100000010"),
then truncates/pads to the 8-bit width, giving "00000010" -- an exact
match to what the card shows. Confirmed correct, not a defect.
"""
import re

import pytest

from shared.datasource.fractal_modbus_source import read_fractal_pcs_status_word_1

pytestmark = pytest.mark.ui

SITE_NAME = "BOLIVIA"
DASH = "—"


@pytest.fixture
def bolivia_monitoring_page(require_omniops, monitoring_page):
    return monitoring_page.select_site(SITE_NAME)


def test_card_title_and_subtitle(bolivia_monitoring_page):
    """CA-03: subtitle mentions EMS/PCS troubleshooting for engineers."""
    viewer = bolivia_monitoring_page.raw_event_bit_viewer()
    subtitle = viewer.subtitle().lower()
    assert "ems" in subtitle or "pcs" in subtitle, f"expected EMS/PCS mention in subtitle, got: {viewer.subtitle()!r}"


def test_no_time_range_badge_on_this_card(bolivia_monitoring_page):
    """CA-05: this panel is always live -- no 24h/7d/30d badge at all,
    same pattern already confirmed for Thermal Diagnostics/Site Load."""
    viewer = bolivia_monitoring_page.raw_event_bit_viewer()
    assert viewer.card().locator(".monitoring-time-range-badge").count() == 0, (
        "expected no time-range badge -- CA-05 says the range doesn't apply here")


def test_global_time_range_does_not_change_values(bolivia_monitoring_page):
    """CA-05: switching the page's global 24h/7d/30d selector must not
    change any of the 3 words or the decode button's set-bit count."""
    viewer = bolivia_monitoring_page.raw_event_bit_viewer()
    before = (viewer.word_value("evt1"), viewer.word_value("evt2"),
              viewer.word_value("pcsevt1"), viewer.decode_button_text())

    bolivia_monitoring_page.select_time_range("Last 7 days")
    bolivia_monitoring_page.page.wait_for_timeout(500)
    after = (viewer.word_value("evt1"), viewer.word_value("evt2"),
             viewer.word_value("pcsevt1"), viewer.decode_button_text())
    bolivia_monitoring_page.select_time_range("Last 24 hours")

    assert before == after, f"expected values unaffected by the global range, before={before}, after={after}"


def test_evt1_and_evt2_stay_consistently_dash_across_time(bolivia_monitoring_page):
    """NOT the same claim as before this was investigated further --
    this only confirms the OBSERVED state is stable/reproducible (not a
    one-off glitch), which is real regardless of whether "—" is itself
    correct. See test_evt1_shows_dash_instead_of_a_genuine_zero_word
    below for the confirmed defect this observation feeds into."""
    viewer = bolivia_monitoring_page.raw_event_bit_viewer()
    for _ in range(4):
        assert viewer.word_value("evt1") == DASH, f"expected evt1={DASH!r}, got: {viewer.word_value('evt1')!r}"
        assert viewer.word_value("evt2") == DASH, f"expected evt2={DASH!r}, got: {viewer.word_value('evt2')!r}"
        bolivia_monitoring_page.page.wait_for_timeout(5000)


@pytest.mark.xfail(
    strict=True,
    reason="CONFIRMED DEFECT (2026-09-13), found by reading the real "
           "backend source: FractalRawDataMapper.cs maps Evt1 from real "
           "live telemetry (emu.AlarmWord1, falling back to "
           "emu.StatusWord1) -- it is NOT an unmapped/absent field for "
           "Fractal, contrary to the initial assumption. The actual bug "
           "is in SnapshotMapperSupport.FormatEventBits: "
           "'bits == 0 ? null : bits.ToString(\"X8\")' -- a genuine "
           "all-clear 0 (confirmed live: BOLIVIA's EMU status words are "
           "all 0 right now) collapses to the exact same null/'—' shown "
           "for 'no data at all', even though docs/OF-381.txt's own "
           "compaction table treats 'vacío/nulo' and 'solo ceros' as "
           "different, meaningful states (dash vs '0×N'). Confirmed "
           "EmuAlarmWord1 is a real, meaningful field (not a throwaway "
           "one) via docs/fractal-alarms-coverage-open-by-id 1.md: alarm "
           "#70 (Lightning/SPD) reads 'EMU Alarm word 1 bit5 690V SPD' -- "
           "the exact field Evt1 is built from. An engineer using this "
           "panel to check EMS bitfields can't tell 'checked, all clear' "
           "from 'no data available'.")
def test_evt1_shows_dash_instead_of_a_genuine_zero_word(bolivia_monitoring_page):
    viewer = bolivia_monitoring_page.raw_event_bit_viewer()
    assert viewer.word_value("evt1") != DASH, (
        "expected evt1 to show a real zero word (e.g. '0×11') since the underlying EMU "
        "AlarmWord1/StatusWord1 telemetry is genuinely present (just all-clear), not absent")


def test_pcsevt1_shows_a_real_binary_word_with_hover_title(bolivia_monitoring_page):
    """CA-06/CA-07: pcsevt1 has real Fractal data -- an 8-bit binary
    string (width <=16, so it's NOT compacted to "K set / N bits" -- that
    compaction only applies to long words per formatBitWord). The value's
    hover title must match the visible text (CA-09: full raw string on hover)."""
    viewer = bolivia_monitoring_page.raw_event_bit_viewer()
    value = viewer.word_value("pcsevt1")
    if value == DASH:
        pytest.skip("pcsevt1 currently has no data for BOLIVIA")

    assert re.fullmatch(r"[01]{8}", value), f"expected an 8-bit binary string for pcsevt1, got: {value!r}"
    assert viewer.word_title_attr("pcsevt1") == value, (
        f"expected the hover title to match the visible value, title={viewer.word_title_attr('pcsevt1')!r}, "
        f"value={value!r}")


def test_pcsevt1_matches_the_real_pcs_status_word_from_the_simulator(bolivia_monitoring_page):
    """True cross-layer ground truth (UI vs the Fractal simulator
    directly, not just the DB/API): pcsevt1's raw value comes from live
    telemetry -- BOLIVIA's 3 PCS units' own status_word_1 Modbus register
    (confirmed live: all 3 report the identical value for this site).
    Data Intake plays NO role in the VALUE itself -- only in the bit
    LABELS (Bitfield Registers overrides), confirmed separately in
    test_decode_modal_row_uses_the_pcs_fallback_catalog_label. Uses the
    same convergence-window technique as other live-simulator checks in
    this project, since the word can change between reads."""
    viewer = bolivia_monitoring_page.raw_event_bit_viewer()

    for _ in range(6):
        ui_value = viewer.word_value("pcsevt1")
        if ui_value != DASH:
            words = {read_fractal_pcs_status_word_1(SITE_NAME, i) for i in range(3)}
            # Same truncate-to-width-then-pad rule as the real backend's
            # BitfieldWordParser.ToBinary: take the last 8 bits, then
            # left-pad -- not a plain 8-bit format (a register value >255
            # needs more than 8 bits before truncation).
            matches = any(format(w, "b")[-8:].rjust(8, "0") == ui_value for w in words)
            if matches:
                return
        bolivia_monitoring_page.page.wait_for_timeout(3000)

    pytest.fail(f"UI pcsevt1 ({ui_value!r}) never matched any of the 3 PCS units' real "
                f"status_word_1 register (as an 8-bit binary string) across several tries")


def test_decode_button_text_reflects_the_set_bit_count(bolivia_monitoring_page):
    """CA-10: "Open decode" (no sets) / "Open decode · N set" / "Open
    decode · N set (+M more)"."""
    viewer = bolivia_monitoring_page.raw_event_bit_viewer()
    text = viewer.decode_button_text()
    assert re.fullmatch(r"Open decode( · \d+ set( \(\+\d+ more\))?)?", text), (
        f"unexpected decode button text format: {text!r}")


def test_decode_modal_title_and_subtitle(bolivia_monitoring_page):
    """CA-11: title "Event bit decode"; subtitle explains Data Intake
    labels and that only Set bits are listed."""
    viewer = bolivia_monitoring_page.raw_event_bit_viewer()
    modal = viewer.open_decode()
    try:
        assert modal.title() == "Event bit decode"
        subtitle = modal.subtitle().lower()
        assert "data intake" in subtitle or "set" in subtitle, f"unexpected subtitle: {modal.subtitle()!r}"
    finally:
        modal.close()


def test_decode_modal_summary_matches_the_card(bolivia_monitoring_page):
    """CA-12: the modal repeats the same 3 compacted words shown on the
    card."""
    viewer = bolivia_monitoring_page.raw_event_bit_viewer()
    card_values = {
        "Evt1": viewer.word_value("evt1"),
        "Evt2": viewer.word_value("evt2"),
        "PcsEvt1": viewer.word_value("pcsevt1"),
    }
    modal = viewer.open_decode()
    try:
        modal_values = modal.summary_words()
        for field, card_val in card_values.items():
            assert modal_values.get(field) == card_val, (
                f"[{field}] card shows {card_val!r}, modal summary shows {modal_values.get(field)!r}")
    finally:
        modal.close()


def test_decode_modal_snapshot_timestamp_is_local(bolivia_monitoring_page):
    """CA-13: "Snapshot · {fecha/hora local}" -- confirms the meta line
    is present and looks like a real local date/time (DD/M/YYYY, H:MM:SS
    or similar), not raw UTC/ISO."""
    viewer = bolivia_monitoring_page.raw_event_bit_viewer()
    modal = viewer.open_decode()
    try:
        meta = modal.snapshot_meta_text()
        if meta is None:
            pytest.skip("no snapshot timestamp present")
        assert "snapshot" in meta.lower()
        assert re.search(r"\d{1,2}/\d{1,2}/\d{4}", meta), f"expected a D/M/YYYY-style date in: {meta!r}"
    finally:
        modal.close()


def test_decode_modal_only_lists_pcsevt1_group_when_only_it_has_set_bits(bolivia_monitoring_page):
    """CA-18: only fields with at least one Set bit get a group/table in
    the modal. Scalable to a future simulator change: derives "does
    pcsevt1 currently have any Set bit" from the decode button's own text
    (not a hardcoded assumption), and skips cleanly if it doesn't -- so
    this doesn't silently break if BOLIVIA's PCS status word ever reads
    all-zero."""
    viewer = bolivia_monitoring_page.raw_event_bit_viewer()
    if viewer.word_value("pcsevt1") == DASH:
        pytest.skip("pcsevt1 currently has no data -- can't check group listing")
    if not re.search(r"\d+ set", viewer.decode_button_text()):
        pytest.skip("pcsevt1 currently has no Set bits -- can't check group listing")

    modal = viewer.open_decode()
    try:
        fields = modal.group_field_names()
        assert fields == ["PcsEvt1"], f"expected only a PcsEvt1 group (evt1/evt2 have no set bits), got: {fields}"
    finally:
        modal.close()


def test_decode_modal_row_uses_the_pcs_fallback_catalog_label(bolivia_monitoring_page):
    """CA-20: label priority -- BOLIVIA's own Intake Bitfield Registers
    has no enabled entry for PcsEvt1 (confirmed in
    docs/omniops_data_intake_BOLIVIA.xlsx), so bit 1 must fall to the
    fixed PCS catalog label ("PCS Event Bit 1"), not a generic "Field bit
    n" string."""
    viewer = bolivia_monitoring_page.raw_event_bit_viewer()
    if viewer.word_value("pcsevt1") == DASH:
        pytest.skip("pcsevt1 currently has no data")

    modal = viewer.open_decode()
    try:
        rows = modal.rows_for_group("PcsEvt1")
        assert rows.count() >= 1, "expected at least 1 set-bit row for PcsEvt1"
        bit, label, alarm_rule, raw = modal.row_values("PcsEvt1", 0)
        assert label != f"PcsEvt1 bit {bit}", (
            f"expected a real PCS catalog label (not the generic 'Field bit n' fallback), got: {label!r}")
    finally:
        modal.close()


def test_decode_modal_close_does_not_change_site_or_range(bolivia_monitoring_page):
    """CA-17: closing the modal doesn't change the site selection or the
    page's global time-range badge."""
    viewer = bolivia_monitoring_page.raw_event_bit_viewer()
    badge_before = bolivia_monitoring_page.page.locator(".monitoring-time-range-badge").first.inner_text()

    modal = viewer.open_decode()
    modal.close()

    badge_after = bolivia_monitoring_page.page.locator(".monitoring-time-range-badge").first.inner_text()
    assert badge_before == badge_after, f"expected the global badge unaffected, before={badge_before!r}, after={badge_after!r}"
