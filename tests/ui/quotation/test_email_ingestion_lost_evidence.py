"""Evidence for the lost-email defect (HU-02 criteria 3 and 8): the list of Quotes in Progress for the batch HU02L-143948 (10 emails in the folder, 9 drafts). Screenshot reports/hu02/ev_lost_list.png."""
import os

import pytest

from tests.ui.quotation.am_page import quotation_page  # noqa: F401  (the AM)

pytestmark = [pytest.mark.ui]


def test_ev_accents_list(quotation_page):
    """The 10 drafts of the batch HU02S-135835 (WO Title 'HU02S-135835-NN ñ é # &'): which titles lost the letters."""
    quotation_page.open(refresh=True)
    quotes = quotation_page.historical_quotes()
    quotes.open_in_progress()
    quotes.type_in_search("HU02S-135835")
    quotes.search_with_enter("HU02S-135835")
    quotation_page.page.wait_for_timeout(2500)
    quotation_page.page.screenshot(path=os.path.join("reports", "hu02", "ev_accents_list.png"))


def test_ev_lost_list(quotation_page):
    prefix = os.environ.get("EV_PREFIX", "HU02L-143948")
    quotation_page.open(refresh=True)
    quotes = quotation_page.historical_quotes()
    quotes.open_in_progress()
    quotes.type_in_search(prefix)
    quotes.search_with_enter(prefix)
    quotation_page.page.wait_for_timeout(2500)
    quotation_page.page.screenshot(path=os.path.join("reports", "hu02", "ev_lost_list.png"))
    assert quotation_page.page.get_by_text(prefix).count() == 9
