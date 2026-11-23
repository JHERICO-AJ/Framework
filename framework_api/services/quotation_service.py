"""QuotationService -- the QUOTATION domain of the API: create, submit, approve and reject a quotation.

Confirmed against the QA build of 2026-10-21 by capturing what the screen sends:
  GET  /api/quotations/next-quote-number?customerId=..&customerName=..   -> the Quote # the form shows
  POST /api/quotations                                                  -> creates the quotation (with its approvers, in route order)
  POST /api/quotations/{id}/submit            {"approverOverrideAcknowledged": false}
  POST /api/quotations/{id}/approve | reject  {"comment": "...", "diagnosis": {"cause": "...", "notes": "..."}}   (diagnosis optional)
Decision calls return the raw response: the tests assert the status code and the server's message.
"""
from __future__ import annotations

from framework_api.services.base_service import BaseService

ROLE_CODE = {"FPM": "FPM_FSM", "BU": "BU", "CEO": "CEO"}


class QuotationService(BaseService):
    PATH = "/api/quotations"

    def next_quote_number(self, customer_id, customer_name):
        r = self.client.get(f"{self.PATH}/next-quote-number", customerId=customer_id, customerName=customer_name)
        r.raise_for_status()
        body = r.json()
        return body if isinstance(body, str) else (body.get("quoteNo") or body.get("quoteNumber") or next(iter(body.values())))

    def create(self, payload):
        r = self.client.post(self.PATH, json=payload)
        r.raise_for_status()
        return r.json()

    def submit(self, quotation_id):
        return self.client.post(f"{self.PATH}/{quotation_id}/submit", json={"approverOverrideAcknowledged": False})

    def approve(self, quotation_id, comment="__omit__", diagnosis=None, **extra):
        return self._decide("approve", quotation_id, comment, diagnosis, extra)

    def reject(self, quotation_id, comment="__omit__", diagnosis=None, **extra):
        return self._decide("reject", quotation_id, comment, diagnosis, extra)

    def decide_raw(self, action, quotation_id, body):
        return self.client.post(f"{self.PATH}/{quotation_id}/{action}", json=body)

    def _decide(self, action, quotation_id, comment, diagnosis, extra):
        body = dict(extra)
        if comment != "__omit__":
            body["comment"] = comment
        if diagnosis is not None:
            body["diagnosis"] = diagnosis
        return self.client.post(f"{self.PATH}/{quotation_id}/{action}", json=body)
