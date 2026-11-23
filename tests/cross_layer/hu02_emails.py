"""The test emails of HU-02 (OP-18, Automatic quotation ingestion from Outlook): the text of each email, built from the format of the story (criterion 5, version of 2026-10-30)."""

FULL = [("OEM Name", "Workflow Progress Test OEM"), ("Customer", "Andes Renewables SpA"), ("WO Title", "{title}"), ("Site Name", "Valle Verde"),
        ("Type of Work", "Commissioning"), ("Site Location", "Camino El Sol 450, Rancagua"), ("Unit Info", "Powin Pod 5.0MWh BESS"), ("Units", "12"),
        ("Device", "PCS-07"), ("Severity", "Major"),
        ("#", "FSE Arrangement (Flat Rate)"), ("#", "Statement of FSE Resource"),
        ("Support Engineers", "2"), ("Working Hour / Tech Day", "10"), ("Estimated Working Days", "5"), ("Total Over Hours / Tech", "4"),
        ("Est. Start Time", "11/02/2026 08:00"), ("Est. End Time", "11/06/2026 18:00"),
        ("#", "Labor Costs"), ("Labor Cost / Hour", "$90.00"), ("Labor Over Cost / Hour", "$135.00"),
        ("#", "Onsite Support Costs"), ("Hotel Cost", "$1,500.00"), ("Per Diem", "$720.00"), ("Travel / Drive Time", "6"),
        ("#", "Reimbursable Costs"), ("Air Transportation", "$820.00"), ("Car Expense", "$390.00"), ("Material Expense", "$250.00"), ("Equipment Rental", "$300.00"),
        ("Miscellaneous", "$1,250.00"), ("Miscellaneous Note", "Site safety training and badges"),
        ("#", "Diagnosis"), ("Signal", "PCS-07 DC bus overvoltage alarm"), ("Trigger", "Alarm raised during cold commissioning checks"),
        ("Cause", "Loose DC busbar connection on rack 3"), ("Notes", "Bring insulated tooling and a phase rotation meter."),
        ("SOP / Steps", "1. Lock out and tag out the PCS. 2. Torque the DC busbar connections. 3. Run the insulation test. 4. Restart and monitor for 2 hours.")]


def render(title, fields=None, order=None, head="Dear team,\nPlease create a quotation with the data below.\n", tail="Best regards,\nMichael Turner"):
    """fields: list of (label, value) (value may use {title}); '#' is a section heading line."""
    rows = fields if fields is not None else FULL
    lines = [head.rstrip("\n")]
    for label, value in (order(rows) if order else rows):
        value = value.replace("{title}", title)
        lines.append(value if label == "#" else f"{label}: {value}")
    lines.append(tail)
    return "\n".join(lines)


def replaced(changes, base=None):
    out = []
    for label, value in (base or FULL):
        out.append((label, changes.get(label, value)) if label != "#" else (label, value))
    return out


def dropped(*labels, base=None):
    return [(l, v) for l, v in (base or FULL) if l not in labels]
