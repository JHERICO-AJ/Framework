"""Quotation module -- WO Snapshot, UI vs its MySQL backend (OP-19 / HU-08).

Confirmed 2026-09-22 via network capture: Quotation's own module doesn't
depend on the BESS simulator/edge stack at all (no ModbusReader, no
require_stack) -- only OmniOps itself (require_omniops) plus this read-only
MySQL connection (quotation_db_conn, real QA data, SELECT-only).
"""
import pytest

from framework_ui.pages.quotation.components import wo_snapshot_locators as loc
from shared.datasource.quotation_db_source import get_project_by_site

pytestmark = pytest.mark.cross_layer

ALARM_NAME = "PCS DC Bus Overvoltage"


# Original analysis kept for the record (2026-09-23): the OmniOps/Fractal alarm sites have no matching row in
# amxcpprojects, and OEM Name pre-fills with a value that looks fabricated. No acceptance criterion covers it.
@pytest.mark.skip(reason="SKIPPED 2026-10-05 (Qase #802, defect #78 closed as a suggestion not adopted): no acceptance criterion defines OEM Name pre-fill beyond editable + mandatory (AC-5.3.1/5.3.2); the developer explained the value comes from the database; and every alarm site on the QA environment currently resolves to a customer, so the no-matching-record precondition of this case cannot be reproduced.")
def test_oem_name_is_blank_not_fabricated_when_no_matching_project_exists(quotation_page, quotation_db_conn):
    wo_snapshot = quotation_page.create_quotation_from_alarm(ALARM_NAME).wo_snapshot()
    try:
        site_name_value = wo_snapshot.field(loc.LABEL_SITE_NAME).input_value()
        project = get_project_by_site(quotation_db_conn, site_name_value)
        assert project is None, (
            f"expected no amxcpprojects row for Site={site_name_value!r} (this test "
            f"targets the no-matching-record case) -- got {project!r}, re-check "
            f"which alarm/site this test should use")

        oem_name_value = wo_snapshot.field(loc.LABEL_OEM_NAME).input_value()
        assert oem_name_value == "", (
            f"expected OEM Name to be left blank (no real OEM data exists for "
            f"this site), got a fabricated value instead: {oem_name_value!r}")
    finally:
        quotation_page.close_form()
