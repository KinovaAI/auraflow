"""AuraFlow — New-hire onboarding form catalog (California).

System-shipped form definitions + HTML renderers. Every form auto-fills from
the tenant's employer_profile + the employee's data, so any studio is turnkey
once they fill their Employer Profile. Forms render to PDF via weasyprint.

Each catalog entry:
  doc_type, title, kind ('form_fillable' | 'acknowledgment'),
  collects_ssn (bool), sort_order, render(ctx) -> html

`ctx` = {employer: dict|None, employee: dict, form: dict} where `form` is the
employee-entered field data for fillable forms (filing status, elections,
acknowledgment, etc.).
"""
import html as _html
from datetime import datetime, timezone


def _e(v) -> str:
    return _html.escape("" if v is None else str(v))


def _cents(v) -> str:
    return f"${(v or 0) / 100:,.2f}"


def _mask_ssn(ssn) -> str:
    if not ssn:
        return ""
    d = "".join(c for c in str(ssn) if c.isdigit())
    return f"***-**-{d[-4:]}" if len(d) >= 4 else "***-**-****"


def _employer_lines(emp: dict | None) -> str:
    if not emp:
        return '<div class="muted">Employer information not yet configured.</div>'
    name = emp.get("legal_name") or emp.get("dba_name") or ""
    addr = ", ".join(x for x in [
        emp.get("address_line1"), emp.get("address_line2"),
        " ".join(x for x in [emp.get("city"), emp.get("state"), emp.get("postal_code")] if x),
    ] if x)
    return (
        f"<div><strong>{_e(name)}</strong></div>"
        f"<div>{_e(addr)}</div>"
        f"<div>{_e(emp.get('phone'))}</div>"
    )


_CSS = """
  body { font-family: Helvetica, Arial, sans-serif; color:#1a1a1a; font-size:12px; padding:34px; }
  h1 { font-size:17px; margin:0 0 2px; } .sub { color:#555; margin-bottom:14px; }
  h2 { font-size:13px; margin:16px 0 6px; border-bottom:1px solid #ccc; padding-bottom:3px; }
  table { width:100%; border-collapse:collapse; margin:6px 0 12px; }
  td { padding:6px 8px; border:1px solid #ccc; vertical-align:top; }
  td.l { width:40%; background:#f6f6f4; font-weight:600; }
  .muted { color:#888; font-style:italic; }
  .notice { white-space:pre-wrap; line-height:1.45; }
  .sig { margin-top:22px; padding-top:10px; border-top:2px solid #333; }
  .sig .name { font-size:20px; font-family:'Brush Script MT',cursive; }
"""


def _doc(title: str, subtitle: str, body: str, signature: str) -> str:
    signed_on = datetime.now(timezone.utc).strftime("%B %d, %Y %H:%M UTC")
    sig = (
        f'<div class="sig"><div class="name">{_e(signature)}</div>'
        f'<div class="sub">Electronically signed — {_e(signed_on)}</div></div>'
    ) if signature else ""
    return (
        f"<!doctype html><html><head><meta charset='utf-8'><style>{_CSS}</style></head><body>"
        f"<h1>{_e(title)}</h1><div class='sub'>{_e(subtitle)}</div>{body}{sig}</body></html>"
    )


def _employee_name(ee: dict) -> str:
    return f"{ee.get('first_name','')} {ee.get('last_name','')}".strip()


def _employee_address(ee: dict) -> str:
    return ", ".join(x for x in [
        ee.get("address_line1"), ee.get("address_line2"),
        " ".join(x for x in [ee.get("city"), ee.get("state"), ee.get("postal_code")] if x),
    ] if x)


# ── Renderers ────────────────────────────────────────────────────────────────

def _render_w4(ctx):
    ee, f = ctx["employee"], ctx["form"]
    filing = {
        "single": "Single or Married filing separately",
        "married_jointly": "Married filing jointly or Qualifying surviving spouse",
        "head_of_household": "Head of household",
    }.get(f.get("filing_status"), f.get("filing_status"))
    body = f"""
      <h2>Step 1 — Personal Information</h2>
      <table>
        <tr><td class="l">Name</td><td>{_e(_employee_name(ee))}</td></tr>
        <tr><td class="l">Address</td><td>{_e(_employee_address(ee))}</td></tr>
        <tr><td class="l">Social Security Number</td><td>{_e(_mask_ssn(f.get('ssn')))}</td></tr>
        <tr><td class="l">Filing status</td><td>{_e(filing)}</td></tr>
      </table>
      <h2>Steps 2–4 — Adjustments</h2>
      <table>
        <tr><td class="l">Multiple jobs / spouse works</td><td>{'Yes' if f.get('multiple_jobs') else 'No'}</td></tr>
        <tr><td class="l">Claim dependents (annual)</td><td>{_cents(f.get('dependents_amount_cents'))}</td></tr>
        <tr><td class="l">Other income (annual)</td><td>{_cents(f.get('other_income_cents'))}</td></tr>
        <tr><td class="l">Deductions (annual)</td><td>{_cents(f.get('deductions_cents'))}</td></tr>
        <tr><td class="l">Extra withholding (per pay period)</td><td>{_cents(f.get('extra_withholding_cents'))}</td></tr>
        <tr><td class="l">Exempt</td><td>{'Yes' if f.get('exempt') else 'No'}</td></tr>
      </table>
      <p class="sub">Under penalties of perjury, I declare this certificate is true, correct, and complete.</p>
    """
    return _doc("Form W-4 — Employee's Withholding Certificate",
                f"Employer: {_e((ctx['employer'] or {}).get('legal_name') or '')}",
                body, f.get("signature_text", ""))


def _render_de4(ctx):
    ee, f = ctx["employee"], ctx["form"]
    filing = {
        "single": "Single or Married (with two or more incomes)",
        "married": "Married (one income)",
        "head_of_household": "Head of household",
    }.get(f.get("filing_status"), f.get("filing_status"))
    body = f"""
      <h2>Employee</h2>
      <table>
        <tr><td class="l">Name</td><td>{_e(_employee_name(ee))}</td></tr>
        <tr><td class="l">Address</td><td>{_e(_employee_address(ee))}</td></tr>
        <tr><td class="l">Social Security Number</td><td>{_e(_mask_ssn(f.get('ssn')))}</td></tr>
      </table>
      <h2>California Withholding</h2>
      <table>
        <tr><td class="l">Filing status</td><td>{_e(filing)}</td></tr>
        <tr><td class="l">Regular withholding allowances (Worksheet A)</td><td>{_e(f.get('allowances_regular', 0))}</td></tr>
        <tr><td class="l">Additional allowances (Worksheet B)</td><td>{_e(f.get('allowances_additional', 0))}</td></tr>
        <tr><td class="l">Additional amount withheld per pay period</td><td>{_cents(f.get('additional_withholding_cents'))}</td></tr>
        <tr><td class="l">Exempt</td><td>{'Yes' if f.get('exempt') else 'No'}</td></tr>
      </table>
      <p class="sub">Under penalties of perjury, I certify the number of withholding allowances claimed
      on this certificate does not exceed the number to which I am entitled.</p>
    """
    return _doc("Form DE 4 — Employee's Withholding Allowance Certificate (California)",
                f"Employer: {_e((ctx['employer'] or {}).get('legal_name') or '')}",
                body, f.get("signature_text", ""))


def _render_i9(ctx):
    ee, f = ctx["employee"], ctx["form"]
    status = {
        "citizen": "A citizen of the United States",
        "noncitizen_national": "A noncitizen national of the United States",
        "lpr": "A lawful permanent resident",
        "authorized_alien": "An alien authorized to work",
    }.get(f.get("citizenship_status"), f.get("citizenship_status"))
    body = f"""
      <h2>Section 1 — Employee Information and Attestation</h2>
      <table>
        <tr><td class="l">Name</td><td>{_e(_employee_name(ee))}</td></tr>
        <tr><td class="l">Address</td><td>{_e(_employee_address(ee))}</td></tr>
        <tr><td class="l">Date of birth</td><td>{_e(f.get('date_of_birth'))}</td></tr>
        <tr><td class="l">Social Security Number</td><td>{_e(_mask_ssn(f.get('ssn')))}</td></tr>
        <tr><td class="l">Email</td><td>{_e(ee.get('email'))}</td></tr>
        <tr><td class="l">Citizenship / immigration status</td><td>{_e(status)}</td></tr>
        <tr><td class="l">USCIS / A-Number or document #</td><td>{_e(f.get('document_number'))}</td></tr>
        <tr><td class="l">Work authorization expiration</td><td>{_e(f.get('work_auth_expiration') or 'N/A')}</td></tr>
      </table>
      <p class="sub">I am aware that federal law provides for imprisonment and/or fines for false statements,
      or the use of false documents, in connection with the completion of this form. I attest, under
      penalty of perjury, that the information above is true and correct.</p>
      <p class="muted">Section 2 (employer document verification) is completed by the employer within
      3 business days of the start date.</p>
    """
    return _doc("Form I-9 — Employment Eligibility Verification (Section 1)",
                "U.S. Citizenship and Immigration Services", body, f.get("signature_text", ""))


def _render_dlse_nte(ctx):
    emp, ee, f = ctx["employer"] or {}, ctx["employee"], ctx["form"]
    pay = {
        "weekly": "Weekly", "biweekly": "Every two weeks (biweekly)",
        "semimonthly": "Twice monthly (semimonthly)", "monthly": "Monthly",
    }.get(emp.get("pay_schedule"), emp.get("pay_schedule") or "")
    rate = ctx.get("hire", {}).get("rate_text") or f.get("rate_text") or ""
    body = f"""
      <h2>Employee</h2>
      <table><tr><td class="l">Name</td><td>{_e(_employee_name(ee))}</td></tr></table>
      <h2>Employer</h2>
      <table>
        <tr><td class="l">Legal name</td><td>{_e(emp.get('legal_name'))}</td></tr>
        <tr><td class="l">Doing business as</td><td>{_e(emp.get('dba_name'))}</td></tr>
        <tr><td class="l">Address</td><td>{_e(", ".join(x for x in [emp.get('address_line1'), emp.get('city'), emp.get('state'), emp.get('postal_code')] if x))}</td></tr>
        <tr><td class="l">Phone</td><td>{_e(emp.get('phone'))}</td></tr>
      </table>
      <h2>Pay</h2>
      <table>
        <tr><td class="l">Rate(s) of pay</td><td>{_e(rate)}</td></tr>
        <tr><td class="l">Regular payday</td><td>{_e(emp.get('regular_payday'))}</td></tr>
        <tr><td class="l">Pay schedule</td><td>{_e(pay)}</td></tr>
        <tr><td class="l">Overtime basis</td><td>{_e(emp.get('overtime_basis') or 'Per California law: 1.5× after 8 hrs/day or 40 hrs/week; 2× after 12 hrs/day')}</td></tr>
      </table>
      <h2>Workers' Compensation</h2>
      <table>
        <tr><td class="l">Carrier</td><td>{_e(emp.get('wc_carrier_name'))}</td></tr>
        <tr><td class="l">Policy number</td><td>{_e(emp.get('wc_policy_number'))}</td></tr>
        <tr><td class="l">Carrier phone</td><td>{_e(emp.get('wc_carrier_phone'))}</td></tr>
      </table>
      <p class="sub">Notice to Employee under Labor Code section 2810.5. I acknowledge receipt of this notice.</p>
    """
    return _doc("Notice to Employee (DLSE-NTE) — Labor Code § 2810.5",
                "Wage Theft Prevention Act", body, f.get("signature_text", ""))


def _render_acknowledgment(title, notice_text):
    def _r(ctx):
        ee, f = ctx["employee"], ctx["form"]
        body = (
            f'<div class="notice">{_e(notice_text)}</div>'
            f'<p class="sub">Employee: {_e(_employee_name(ee))}. '
            f'I acknowledge that I received and reviewed this notice.</p>'
        )
        return _doc(title, "California new-hire notice", body, f.get("signature_text", ""))
    return _r


# Standard CA notice text (system-shipped; same for every employer). These are
# the acknowledgment cover notices; studios also post/provide the full official
# pamphlets per state requirements.
_DWC7_TEXT = (
    "DWC 7 — Notice to Employees: Injuries Caused By Work.\n\n"
    "If you are injured or become ill because of your job, you may be entitled to "
    "workers' compensation benefits. Report any injury to your employer immediately. "
    "Your employer's workers' compensation carrier is shown on your Notice to Employee "
    "(DLSE-NTE). You have the right to receive medical care, temporary disability "
    "benefits, and other benefits as provided by California law. For more information, "
    "contact the Division of Workers' Compensation (DWC) or your employer's claims "
    "administrator."
)
_SICK_LEAVE_TEXT = (
    "Paid Sick Leave — Notice to Employee (Healthy Workplaces, Healthy Families Act).\n\n"
    "You may accrue and use paid sick leave under California law. You cannot be "
    "terminated or retaliated against for using or requesting paid sick leave. You may "
    "file a complaint with the Labor Commissioner against an employer who retaliates."
)
_SB294_TEXT = (
    "Know Your Rights (SB 294, eff. Feb 2026).\n\n"
    "California workers have important rights, including: protection from discrimination "
    "and harassment; the right to a safe workplace and workers' compensation if injured; "
    "protections regardless of immigration status; the right to organize; and protection "
    "from retaliation for exercising these rights."
)
_DFEH_TEXT = (
    "Sexual Harassment Pamphlet (CRD/DFEH-185P).\n\n"
    "Sexual harassment is prohibited by law. It includes unwanted sexual advances, "
    "requests for sexual favors, and other verbal or physical conduct of a sexual nature. "
    "You have the right to a workplace free of harassment and to file a complaint with "
    "the California Civil Rights Department (CRD). Retaliation for reporting harassment "
    "is illegal."
)
_DE2511_TEXT = (
    "Paid Family Leave (DE 2511).\n\n"
    "California Paid Family Leave (PFL) provides partial wage replacement when you take "
    "time off work to care for a seriously ill family member, to bond with a new child, "
    "or for a qualifying military event. Benefits are administered by the EDD."
)
_DE2515_TEXT = (
    "State Disability Insurance (DE 2515).\n\n"
    "California State Disability Insurance (SDI) provides short-term wage replacement to "
    "eligible workers who are unable to work due to a non-work-related illness, injury, "
    "or pregnancy. Benefits are administered by the EDD."
)


# ── Catalog ──────────────────────────────────────────────────────────────────

# Order matters — this is the order the employee completes them in the packet.
CATALOG = [
    {"doc_type": "w4", "title": "Form W-4 (Federal Withholding)", "kind": "form_fillable",
     "collects_ssn": True, "render": _render_w4},
    {"doc_type": "de4", "title": "Form DE 4 (California Withholding)", "kind": "form_fillable",
     "collects_ssn": True, "render": _render_de4},
    {"doc_type": "i9_section1", "title": "Form I-9 (Section 1)", "kind": "form_fillable",
     "collects_ssn": True, "render": _render_i9},
    {"doc_type": "dlse_nte", "title": "Notice to Employee (Wage Theft / DLSE-NTE)", "kind": "form_fillable",
     "collects_ssn": False, "render": _render_dlse_nte},
    {"doc_type": "dwc7", "title": "Workers' Compensation Notice (DWC 7)", "kind": "acknowledgment",
     "collects_ssn": False, "body_text": _DWC7_TEXT,
     "render": _render_acknowledgment("Workers' Compensation Notice (DWC 7)", _DWC7_TEXT)},
    {"doc_type": "notice_sick_leave", "title": "Paid Sick Leave Notice", "kind": "acknowledgment",
     "collects_ssn": False, "body_text": _SICK_LEAVE_TEXT,
     "render": _render_acknowledgment("Paid Sick Leave Notice", _SICK_LEAVE_TEXT)},
    {"doc_type": "notice_sb294", "title": "Know Your Rights (SB 294)", "kind": "acknowledgment",
     "collects_ssn": False, "body_text": _SB294_TEXT,
     "render": _render_acknowledgment("Know Your Rights (SB 294)", _SB294_TEXT)},
    {"doc_type": "pamphlet_dfeh185p", "title": "Sexual Harassment Pamphlet (DFEH-185P)", "kind": "acknowledgment",
     "collects_ssn": False, "body_text": _DFEH_TEXT,
     "render": _render_acknowledgment("Sexual Harassment Pamphlet (DFEH-185P)", _DFEH_TEXT)},
    {"doc_type": "pamphlet_de2511", "title": "Paid Family Leave (DE 2511)", "kind": "acknowledgment",
     "collects_ssn": False, "body_text": _DE2511_TEXT,
     "render": _render_acknowledgment("Paid Family Leave (DE 2511)", _DE2511_TEXT)},
    {"doc_type": "pamphlet_de2515", "title": "State Disability Insurance (DE 2515)", "kind": "acknowledgment",
     "collects_ssn": False, "body_text": _DE2515_TEXT,
     "render": _render_acknowledgment("State Disability Insurance (DE 2515)", _DE2515_TEXT)},
]

CATALOG_BY_TYPE = {d["doc_type"]: d for d in CATALOG}


async def render_pdf(doc_type: str, ctx: dict) -> bytes:
    spec = CATALOG_BY_TYPE[doc_type]
    html = spec["render"](ctx)
    from app.services.contracts.pdf_renderer import render_contract_pdf
    return await render_contract_pdf(html)
