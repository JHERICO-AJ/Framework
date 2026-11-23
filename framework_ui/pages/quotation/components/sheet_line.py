"""SheetLine -- one line of the Budget Summary sheet."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SheetLine:
    section: str          # '' for the lines above the first section title
    label: str
    quotation: str        # text of the Quotation/Revenue cell ('' when the line has no figure)
    expense: "str | None"  # text of the Expense cell, None when the sheet has no Expense column
    spans_both: bool      # a text line whose value cell spans both columns (GSP #, Quote#, Type of Work...)
