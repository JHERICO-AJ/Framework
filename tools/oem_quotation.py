"""Command line helper for the manual part of the OEM tests (see the internal QA note 'OEM_Guia_de_pruebas'). It only calls the framework:
the quotation comes from framework_api.services.quotation_setup and every database read from shared.datasource.quotation_db_source (read-only).

  python tools/oem_quotation.py new [TAG]           create a quotation signed by FPM/FSM, BU, CEO and the external OEM and take it to the OEM's turn.
                                                    The system emails the QA test mailbox (quotation_setup.OEM_TEST_EMAIL).
  python tools/oem_quotation.py check FSA0000xxxx   status, stage, signers, OEM links and the history of a quotation, straight from the database.
  python tools/oem_quotation.py seed-historical [N] create N (default 8, at most 8) test quotations that differ in OEM name, type of work, site and device and take
                                                    them to the OEM's turn, so the Historical Quotes tab has data for paging, filters and search (HU-05).
  python tools/oem_quotation.py seed-alarm <id>     give a draft made from an alarm (Alarms & Events -> Create Quotation -> Save Draft) the four signers and take it to the OEM.
  python tools/oem_quotation.py approve-links       paste, one per prompt, the Approve link of each email; each is approved as the OEM. Only test quotations
                                                    (title 'Workflow Progress test ...') are approved, and the order of the links does not matter."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from shared.config.credentials import _load_dotenv  # noqa: E402

_load_dotenv()          # the framework's own .env reader (the same one shared/config/settings.py uses)

from framework_api.client.role_session import RoleApiSession  # noqa: E402
from framework_api.services import quotation_setup  # noqa: E402
from framework_api.services.oem_decision_service import OemDecisionService  # noqa: E402
from framework_api.services.quotation_seed_data import SEED_VARIANTS  # noqa: E402
from shared.config.credentials import load_role_credentials  # noqa: E402
from shared.datasource import quotation_db_source as quotation_db  # noqa: E402
from shared.datasource.db_connection import open_readonly_connection  # noqa: E402

ROLES = ("AM", "FPM", "BU", "CEO")


def open_sessions():
    return {role: RoleApiSession(load_role_credentials(role)["email"], load_role_credentials(role)["password"]) for role in ROLES}


def create_waiting_on_oem(tag="MANUAL"):
    sessions = open_sessions()
    quotation_id, quote_no = quotation_setup.create_waiting_on_oem(sessions, tag, title_prefix="HU21-OEM")
    print(f"{quote_no}  id={quotation_id}\nIt waits on the OEM. Open the email sent to {quotation_setup.OEM_TEST_EMAIL} (look in Spam too).")


def seed_historical(count_text="8"):
    sessions = open_sessions()
    count = max(1, min(int(count_text), len(SEED_VARIANTS)))
    for tag, oem_name, type_of_work, site_key, device in SEED_VARIANTS[:count]:
        fields = quotation_setup.seed_variant_fields(oem_name, type_of_work, site_key, device)
        quotation_id, quote_no = quotation_setup.create_waiting_on_oem(sessions, f"SEED-{tag}", title_prefix="HU05-SEED", extra=fields)
        print(f"{quote_no}  {tag}  {oem_name} | {type_of_work} | {fields['siteName']} | device {device or '-'}")
    print(f"\n{count} quotations wait on the OEM. Open the emails sent to {quotation_setup.OEM_TEST_EMAIL}, then run: python tools/oem_quotation.py approve-links")


def seed_alarm(quotation_id):
    quote_no = quotation_setup.route_existing_to_oem(open_sessions(), quotation_id)
    print(f"{quote_no} waits on the OEM. Its email is in {quotation_setup.OEM_TEST_EMAIL}.")


def approve_one(service, link):
    """Approves the quotation of one OEM link, only if it is a test quotation. Returns a line to print."""
    page = service.open_page(link, "approve")
    text = OemDecisionService.page_text(page)
    quote_no = re.search(r"Quotation (FS[A-Z]\d{8})", text)
    title = re.search(r"Title (Workflow Progress test \S+)", text)
    if page.status_code != 200 or not quote_no:
        return f"this link cannot be used (HTTP {page.status_code}): already used, expired or not an OEM link"
    if not title:
        return f"{quote_no.group(1)}: NOT approved, it is not a test quotation (its title does not start with 'Workflow Progress test')"
    answer = service.decide(link, "approve", "")
    answer_text = OemDecisionService.page_text(answer)
    approved = answer.status_code == 200 and "Approved" in answer_text
    return f"{quote_no.group(1)}: {'approved' if approved else 'FAILED, HTTP ' + str(answer.status_code)} -- page says: {answer_text[:140]}"


def approve_links():
    service = OemDecisionService()
    while True:
        link = input("Paste an Approve link of an email (empty to finish): ").strip()
        if not link:
            return
        try:
            print("  ", approve_one(service, link))
        except ValueError as error:
            print("  ", error)


def show(title, rows):
    print(f"{title}:")
    for row in rows:
        print("  ", {key: str(value) for key, value in row.items()})


def check_quotation(quote_no):
    connection = open_readonly_connection()
    try:
        state = quotation_db.get_quotation_state(connection, quote_no)
        if state is None:
            sys.exit(f"{quote_no}: not found")
        show("quotation", [state])
        show("signers", quotation_db.get_approver_decisions_by_quote_no(connection, quote_no))
        show("OEM links (never the link itself)", quotation_db.get_oem_decision_tokens_by_quote_no(connection, quote_no))
        show("history", quotation_db.get_events_by_quote_no(connection, quote_no))
    finally:
        connection.close()


if __name__ == "__main__":
    arguments = sys.argv[1:]
    if arguments[:1] == ["new"]:
        create_waiting_on_oem(*arguments[1:2])
    elif arguments[:1] == ["check"] and len(arguments) == 2:
        check_quotation(arguments[1])
    elif arguments[:1] == ["seed-historical"]:
        seed_historical(*arguments[1:2])
    elif arguments[:1] == ["seed-alarm"] and len(arguments) == 2:
        seed_alarm(arguments[1])
    elif arguments[:1] == ["approve-links"]:
        approve_links()
    else:
        sys.exit(__doc__)
