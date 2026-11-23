"""`quotation_page` signed in as the AM (QUOTATION_AM_EMAIL), the only role that creates quotations.

The default `quotation_page` of tests/conftest.py uses the main OmniOps account (OMNIOPS_EMAIL, an admin). The regression of HU-08, HU-09, HU-10 and HU-11 must run
as the AM (decision of 2026-11-09), so those modules import this fixture, which overrides the default one by name:

    from tests.ui.quotation.am_page import quotation_page  # noqa: F401

It uses role_page (the _role_browser session), so a pytest run that also asks for logged_in_page in the same process hits the 'Sync API inside asyncio loop'
conflict: run these files on their own (see docs/commands/COMANDOS_TESTS.md)."""
import pytest

from framework_ui.pages.quotation.quotation_page import QuotationPage


@pytest.fixture
def quotation_page(role_page):
    return QuotationPage(role_page("AM")).open()
