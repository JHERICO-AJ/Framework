"""Test-support: the Draft with two engineers used by the Budget Calculator API tests (HU-12). Kept out of the test file so that file holds only tests."""
import copy

from framework_api.services import quotation_setup as qs
from framework_api.services.quotation_service import QuotationService

Q = qs.engineer_cost


def put(session, quotation_id, body):
    return session.session.put(f"{session.base_url}{QuotationService.PATH}/{quotation_id}", json=body, timeout=session.timeout)


class Calc:
    """A Draft of the AM with two engineers and the figures of the HU-12 examples (Income and Expense)."""
    def __init__(self, am, api_roles, tag="CALC"):
        self.am = am
        self.id, self.no = qs.create_draft(am, api_roles, tag, title_prefix="HU12", extra=qs.select_extra(
            ("Employee L01200", Q("quotation", 100, 10, 150, 4, 1975, 500, 150), Q("expense", 60, 10, 0, 0, 800)),
            ("Pedro Aguilar", Q("quotation", 80, 20, 0, 0, 0, 99, 0), Q("expense", 50, 20))))
        self.body = am.get(f"{QuotationService.PATH}/{self.id}").json()
        self.pedro = [e["contractorName"] for e in self.body["select"]["selectedEngineers"]].index("Pedro Aguilar")     # the server does not keep the order of the selection

    def read(self):
        return self.am.get(f"{QuotationService.PATH}/{self.id}").json()

    def send(self, mutate, session=None):
        body = copy.deepcopy(self.body)
        mutate(body["select"]["selectedEngineers"], body)
        return put(session or self.am, self.id, body)
