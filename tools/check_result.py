"""CheckResult -- the outcome of verifying one alarm rule (what was expected, what the API showed, and the verdict)."""

from __future__ import annotations

from shared.domain.verdict import PASS, PASS_HEALTHY, NOT_VERIFIABLE


class CheckResult:
    def __init__(self, rule_id, name):
        self.rule_id = rule_id
        self.name = name
        self.cause = None
        self.in_api = False
        self.verdict = NOT_VERIFIABLE
        self.last = None
        self.appeared_in_s = None
        self.time_ok = None

    @property
    def ok(self):
        return self.verdict in (PASS, PASS_HEALTHY, NOT_VERIFIABLE)
