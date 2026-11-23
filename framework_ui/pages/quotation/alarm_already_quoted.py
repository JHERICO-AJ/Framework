"""AlarmAlreadyQuoted -- raised when "Create Quotation" from an alarm is refused because that alarm already has a quotation."""

from __future__ import annotations


class AlarmAlreadyQuoted(Exception):
    """Raised when "Create Quotation" from an alarm shows the "Alarm already
    quoted" modal instead of opening a new form: the alarm already has an
    active quotation (Draft/Awaiting...) and a new one is only allowed once
    it is Approved, Rejected or Closed (rule confirmed by the developer
    2026-10-05). Carries the modal's text."""
