"""AuraFlow — CA DE-34 (Report of New Employee(s)) Service

Generates the employer's DE-34 new-hire report from the tenant's
employer_profile + the employee's data (name/address from the hired
application, start date from the org membership, SSN from the onboarding
packet), and tracks which reports have been filed with the EDD (due within
20 days of the start date). Turnkey for any studio.
"""
import html as _html
import uuid
from datetime import date, datetime, timedelta, timezone

from app.db.session import get_tenant_db, get_global_db
from app.services.hiring import employer_service, onboarding_service

DE34_DUE_DAYS = 20


def _e(v) -> str:
    return _html.escape("" if v is None else str(v))


async def _hire_date(user_id: str, org_id: str) -> date | None:
    async with get_global_db() as db:
        row = await db.fetchrow(
            "SELECT hire_date, joined_at FROM af_global.organization_users WHERE user_id = $1 AND organization_id = $2",
            user_id, org_id,
        )
    if not row:
        return None
    if row["hire_date"]:
        return row["hire_date"]
    return row["joined_at"].date() if row["joined_at"] else None


async def _employee_record(db, user_id: str) -> dict | None:
    """Name + address from the hired application for this user."""
    return await db.fetchrow(
        """SELECT first_name, last_name, address_line1, address_line2, city, state, postal_code
           FROM job_applications WHERE hired_user_id = $1
           ORDER BY hired_at DESC LIMIT 1""",
        user_id,
    )


async def list_pending(org_id: str) -> list[dict]:
    """Hired employees with no DE-34 filed yet, with days-since-start + due date."""
    async with get_tenant_db() as db:
        rows = await db.fetch(
            """SELECT a.hired_user_id AS user_id, a.first_name, a.last_name,
                      a.hired_at, a.hired_role
               FROM job_applications a
               WHERE a.hired_user_id IS NOT NULL
                 AND NOT EXISTS (SELECT 1 FROM de34_filings f WHERE f.user_id = a.hired_user_id)
               ORDER BY a.hired_at ASC""",
        )
    out = []
    today = datetime.now(timezone.utc).date()
    for r in rows:
        start = await _hire_date(str(r["user_id"]), org_id)
        due = (start + timedelta(days=DE34_DUE_DAYS)) if start else None
        out.append({
            "user_id": str(r["user_id"]),
            "name": f"{r['first_name']} {r['last_name']}".strip(),
            "role": r["hired_role"],
            "start_date": start.isoformat() if start else None,
            "due_date": due.isoformat() if due else None,
            "days_remaining": (due - today).days if due else None,
            "overdue": bool(due and due < today),
        })
    return out


async def mark_filed(user_id: str, actor_user_id: str | None) -> dict:
    async with get_tenant_db() as db:
        await db.execute(
            """INSERT INTO de34_filings (id, user_id, filed_by)
               VALUES ($1, $2, $3)
               ON CONFLICT (user_id) DO UPDATE SET filed_at = NOW(), filed_by = EXCLUDED.filed_by""",
            str(uuid.uuid4()), user_id, actor_user_id,
        )
    return {"user_id": user_id, "filed": True}


async def generate_pdf(user_id: str, org_id: str):
    """Render the DE-34 report PDF. Returns (bytes, filename) or raises ValueError."""
    employer = await employer_service.get_profile()
    if not employer or not employer.get("edd_account_number"):
        raise ValueError("Set your EDD employer account number in the Employer Profile first.")
    async with get_tenant_db() as db:
        ee = await _employee_record(db, user_id)
    if not ee:
        raise ValueError("No hired employee record found.")
    ssn = await onboarding_service.get_employee_ssn(user_id)
    start = await _hire_date(user_id, org_id)

    ssn_disp = ssn if ssn else "(employee has not provided SSN yet)"
    ee_addr = ", ".join(x for x in [
        ee["address_line1"], ee["address_line2"],
        " ".join(x for x in [ee["city"], ee["state"], ee["postal_code"]] if x),
    ] if x)
    emp_addr = ", ".join(x for x in [
        employer.get("address_line1"), employer.get("address_line2"),
        " ".join(x for x in [employer.get("city"), employer.get("state"), employer.get("postal_code")] if x),
    ] if x)
    generated = datetime.now(timezone.utc).strftime("%B %d, %Y")

    html = f"""<!doctype html><html><head><meta charset='utf-8'><style>
      body {{ font-family: Helvetica, Arial, sans-serif; color:#1a1a1a; font-size:12px; padding:36px; }}
      h1 {{ font-size:17px; margin:0 0 2px; }} .sub {{ color:#555; margin-bottom:16px; }}
      h2 {{ font-size:13px; margin:16px 0 6px; border-bottom:1px solid #ccc; padding-bottom:3px; }}
      table {{ width:100%; border-collapse:collapse; margin:6px 0 12px; }}
      td {{ padding:6px 8px; border:1px solid #ccc; }} td.l {{ width:40%; background:#f6f6f4; font-weight:600; }}
    </style></head><body>
      <h1>Report of New Employee(s) — Form DE 34</h1>
      <div class='sub'>California Employment Development Department · Generated {_e(generated)}</div>
      <h2>Employer</h2>
      <table>
        <tr><td class='l'>Business name</td><td>{_e(employer.get('legal_name') or employer.get('dba_name'))}</td></tr>
        <tr><td class='l'>EDD employer account number</td><td>{_e(employer.get('edd_account_number'))}</td></tr>
        <tr><td class='l'>Federal EIN</td><td>{_e(employer.get('ein'))}</td></tr>
        <tr><td class='l'>Address</td><td>{_e(emp_addr)}</td></tr>
        <tr><td class='l'>Phone</td><td>{_e(employer.get('phone'))}</td></tr>
      </table>
      <h2>Employee</h2>
      <table>
        <tr><td class='l'>Name</td><td>{_e((ee['first_name'] or '') + ' ' + (ee['last_name'] or ''))}</td></tr>
        <tr><td class='l'>Social Security Number</td><td>{_e(ssn_disp)}</td></tr>
        <tr><td class='l'>Home address</td><td>{_e(ee_addr)}</td></tr>
        <tr><td class='l'>First day of work (start date)</td><td>{_e(start.isoformat() if start else '')}</td></tr>
      </table>
      <p class='sub'>File with the EDD within 20 days of the start date (e-Services for Business).</p>
    </body></html>"""
    from app.services.contracts.pdf_renderer import render_contract_pdf
    pdf = await render_contract_pdf(html)
    name = f"{ee['first_name']}_{ee['last_name']}".replace(" ", "_")
    return pdf, f"DE34_{name}.pdf"
