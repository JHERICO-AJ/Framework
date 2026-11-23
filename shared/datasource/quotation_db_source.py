"""Read-only queries for the Quotation module. Real QA data (not synthetic), so every query here is
SELECT-only -- never write through these connections.

Two backends (take the matching connection fixture):
  * amxcpwo / amxcpprojects -- the separate MySQL backend (quotation_db_conn; confirmed 2026-09-22 via network
    capture: the same tables the app's own /api/quotations and /api/amxcpcatalog/customers-projects endpoints
    read from).
  * quotation."Approvers" / quotation."Quotation" -- the `quotation` schema inside the OmniOps Postgres
    database (db_conn).
"""
from __future__ import annotations


def get_wo(conn, wo_number: str) -> dict | None:
    """A single Work Order / Quotation row from amxcpwo, keyed by its WO
    NUMBER (the 'WO' column -- distinct from 'CustWO', the customer-
    provided Quote #)."""
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM amxcpwo WHERE WO = %s", (wo_number,))
        return cur.fetchone()


def get_existing_wo_numbers(conn, limit: int = 20) -> list[str]:
    """Real, already-in-use WO NUMBER values -- for exercising the
    'reject a duplicate WO NUMBER' check against real data instead of
    scraping the landing list's UI."""
    with conn.cursor() as cur:
        cur.execute("SELECT WO FROM amxcpwo WHERE WO IS NOT NULL AND WO <> '' "
                     "ORDER BY StartDate DESC LIMIT %s", (limit,))
        return [row["WO"] for row in cur.fetchall()]


def get_project_by_site(conn, site_name: str) -> dict | None:
    """A single project/site row from amxcpprojects (the Customer/Site
    catalog backing the Quotation form's Customer -> Site Name cascade),
    keyed by its 'Site' column."""
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM amxcpprojects WHERE Site = %s", (site_name,))
        return cur.fetchone()


def get_approvers_by_quote_no(conn, quote_no: str) -> list[dict]:
    """The approvers saved for a quotation (table quotation."Approvers", ordered by Orden): who, their role, and
    EsAutoAsignado (true = assigned by the system from the approval default rules, false = added by the user).

    Takes the Postgres OmniOps connection (db_conn), not the MySQL one: the Quotation schema now lives inside
    omniOps_qa. Only the amxcp* catalog tables above are still on the separate MySQL backend."""
    from psycopg2.extras import RealDictCursor
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('SELECT a."Orden", a."Rol", a."NombreUsuario", a."Email", a."Estado", a."EsAutoAsignado" '
                    'FROM quotation."Approvers" a JOIN quotation."Quotation" q ON q."Id" = a."QuotationId" '
                    'WHERE q."QuoteNo" = %s ORDER BY a."Orden"', (quote_no,))
        return [dict(row) for row in cur.fetchall()]


def get_quotation_state(conn, quote_no: str) -> dict | None:
    """Status of a quotation (quotation."Quotation"): EstadoCotizacion (Draft/Awaiting/Returned/Rejected...) and
    EtapaWorkflow (Quoting / BU Reviewing / Vendor Reviewing...), plus its total."""
    from psycopg2.extras import RealDictCursor
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('SELECT "QuoteNo", "Title", "EstadoCotizacion", "EtapaWorkflow", "MontoTotal" '
                    'FROM quotation."Quotation" WHERE "QuoteNo" = %s', (quote_no,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_quotation_audit_fields(conn, quote_no: str) -> dict | None:
    """What an edit would touch (quotation."Quotation"): status, stage, total and the date of the last update. Read-only."""
    from psycopg2.extras import RealDictCursor
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('SELECT "QuoteNo", "EstadoCotizacion", "EtapaWorkflow", "MontoTotal", "FechaActualizacion" '
                    'FROM quotation."Quotation" WHERE "QuoteNo" = %s', (quote_no,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_events_by_quote_no(conn, quote_no: str) -> list[dict]:
    """The history events of a quotation (quotation."QuotationEvent"), oldest first: EventType (Created, Submitted,
    Approved, Rejected...), who did it (ActorName / ActorRole), the Comment (the approver's recommendation), the
    status after it and when."""
    from psycopg2.extras import RealDictCursor
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('SELECT e."EventType", e."ActorEmail", e."ActorName", e."ActorRole", e."Comment", e."StatusAfter", e."OccurredAt" '
                    'FROM quotation."QuotationEvent" e JOIN quotation."Quotation" q ON q."Id" = e."QuotationId" '
                    'WHERE q."QuoteNo" = %s ORDER BY e."OccurredAt", e."Id"', (quote_no,))
        return [dict(row) for row in cur.fetchall()]


def get_approver_decisions_by_quote_no(conn, quote_no: str) -> list[dict]:
    """Approvers of a quotation with their decision data (Estado Pending/Approved/Rejected, Comentario = the
    recommendation, FechaRespuesta), in route order."""
    from psycopg2.extras import RealDictCursor
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('SELECT a."Orden", a."Rol", a."NombreUsuario", a."Email", a."Estado", a."Comentario", a."FechaRespuesta" '
                    'FROM quotation."Approvers" a JOIN quotation."Quotation" q ON q."Id" = a."QuotationId" '
                    'WHERE q."QuoteNo" = %s ORDER BY a."Orden", a."FechaRespuesta" NULLS LAST', (quote_no,))
        return [dict(row) for row in cur.fetchall()]


def get_quotation_id(conn, quote_no: str) -> str | None:
    """The id (guid) the app uses in the quotation's own link, /quotation/<id>."""
    with conn.cursor() as cur:
        cur.execute('SELECT "Id" FROM quotation."Quotation" WHERE "QuoteNo" = %s', (quote_no,))
        row = cur.fetchone()
        return str(row[0]) if row else None


def get_oem_decision_tokens_by_quote_no(conn, quote_no: str) -> list[dict]:
    """The decision links sent to the external OEM (quotation."QuotationOemDecisionToken"), oldest first: who they were sent to, when
    they were created and expire, and whether each was used (UsedAt, Decision Approved/Rejected) or revoked (RevokedAt). The token itself is
    stored only as a hash and is NOT selected: the real link exists only in the email."""
    from psycopg2.extras import RealDictCursor
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('SELECT t."ApproverEmail", t."CreatedAt", t."ExpiresAt", t."UsedAt", t."RevokedAt", t."Decision" '
                    'FROM quotation."QuotationOemDecisionToken" t JOIN quotation."Quotation" q ON q."Id" = t."QuotationId" '
                    'WHERE q."QuoteNo" = %s ORDER BY t."CreatedAt"', (quote_no,))
        return [dict(row) for row in cur.fetchall()]


def get_outbound_notifications(conn, quote_no: str) -> list[dict]:
    """The notification emails the system queued for a quotation (notifications."OutboundNotification"), oldest first: Type (quotation.approval-requested,
    quotation.decision, quotation.oem-review-requested), RecipientEmail, Status (Sent/Failed), Attempts, Error and Data (jsonb: quoteNo, customerName, siteName,
    dateOn, decision, actorName, actorRole, comment, stage...). IdempotencyKey is unique per event and recipient."""
    from psycopg2.extras import RealDictCursor
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('SELECT "Type", "RecipientEmail", "RecipientName", "Status", "Attempts", "Error", "IdempotencyKey", "CreatedAtUtc", "ProcessedAtUtc", "Data" '
                    'FROM notifications."OutboundNotification" WHERE "Data"->>\'quoteNo\' = %s ORDER BY "CreatedAtUtc", "Id"', (quote_no,))
        return [dict(row) for row in cur.fetchall()]
