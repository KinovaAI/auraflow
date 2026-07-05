"""Guest Workshop Services Agreement — template v1.

Source-of-truth for the legal text + the field schema. When the contract
text changes, BUMP the version (v1 → v2) and add a new module; never edit
this file in place. Old signed contracts always render at the version they
were signed under (workshop_contracts.template_version column).

Studio identity is configured by the self-hosting operator. Replace the
placeholder constants below — and the default governing-law jurisdiction in
Section 17 — with your studio's own legal name, address, and signatory
before putting this template into use.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

VERSION = "guest_workshop_v1"

STUDIO_LEGAL_NAME = "Example Wellness LLC"
STUDIO_DBA = "Example Wellness Studio"
STUDIO_ADDRESS = "123 Example Street, Your City, Your State"
STUDIO_SIGNATORY_NAME = "Studio Owner"
STUDIO_SIGNATORY_TITLE = "Owner"


# ── Instructor field schema (rendered as form on your-domain.com) ──────
INSTRUCTOR_FIELDS = [
    # ── Section 0: Workshop Marketing Details (instructor-supplied) ──
    {"name": "workshop_description",  "label": "Workshop description (this becomes the public-facing marketing copy)",
        "type": "textarea", "required": True, "section": "marketing",
        "help_text": "What is the workshop about? What will participants learn or experience? Write in your own voice; this goes on the website."},
    {"name": "advertising_details",   "label": "Anything else for our marketing team (style, vibe, target audience, what NOT to say, etc.)",
        "type": "textarea", "required": False, "section": "marketing"},
    {"name": "intake_form_link",      "label": "Pre-workshop intake form link (URL, optional)",
        "type": "url",      "required": False, "section": "marketing",
        "help_text": "If you have a Typeform/Google Form/etc. you want participants to fill before class."},
    {"name": "waiver_link",           "label": "Additional waiver link (URL, optional — beyond the studio's standard liability waiver)",
        "type": "url",      "required": False, "section": "marketing"},
    {"name": "pre_workshop_docs",     "label": "Anything participants should read or do before they arrive",
        "type": "textarea", "required": False, "section": "marketing"},
    {"name": "instructor_photo",      "label": "Photo of yourself (used on the workshop listing + website)",
        "type": "image",    "required": True,  "section": "marketing", "sensitive": False,
        "help_text": "Headshot or action shot. JPG/PNG, max 5 MB."},
    {"name": "workshop_flyer",        "label": "Workshop flyer image (used as the cover on the AuraFlow workshop page + flyers)",
        "type": "image",    "required": True,  "section": "marketing",
        "help_text": "Main marketing image for the workshop. JPG/PNG, max 5 MB. Square or landscape works best."},

    # ── Existing identity + signature fields ──
    {"name": "legal_name",        "label": "Instructor Legal Name",            "type": "text",     "required": True},
    {"name": "entity_dba",        "label": "Instructor Entity / DBA (if any)", "type": "text",     "required": False},
    {"name": "address",           "label": "Instructor Address (mailing — used for 1099)", "type": "textarea", "required": True},
    {"name": "email",             "label": "Email",                            "type": "email",    "required": True},
    {"name": "phone",             "label": "Phone",                            "type": "tel",      "required": True},
    {"name": "tax_id_type",       "label": "Tax ID type",                      "type": "select",
        "options": [{"value": "ssn", "label": "Social Security Number (SSN)"},
                    {"value": "ein", "label": "Employer Identification Number (EIN)"}],
        "required": True},
    {"name": "tax_id",            "label": "Tax ID (SSN or EIN — encrypted at rest, used for 1099 only)",
        "type": "ssn_or_ein", "required": True, "sensitive": True,
        "help_text": "Format SSN as XXX-XX-XXXX or EIN as XX-XXXXXXX. Stored encrypted."},
    {"name": "printed_name",      "label": "Printed Name (for signature block)", "type": "text",   "required": True},
    {"name": "title",             "label": "Title (e.g. Owner, Sole Proprietor, Instructor)", "type": "text", "required": True},
    {"name": "esign_consent",     "label": "I agree to sign this Agreement electronically and affirm that this electronic signature has the same legal effect as a wet-ink signature.",
        "type": "checkbox", "required": True},
]


def prefill(course: dict, sessions: list[dict], guest: dict, comp: dict) -> dict:
    """Build the prefilled_data JSONB for a workshop_contracts row.

    `course`   — courses row (id, title, description, location, capacity,
                 min_enrollment, price_cents, starts_at, ends_at, etc.)
    `sessions` — list of course_sessions for this workshop
    `guest`    — guest_instructors row (any pre-known contact info)
    `comp`     — studio admin's compensation entry (option, amount, etc.)
    """
    fmt_date = lambda dt: dt.isoformat() if dt else None
    return {
        "studio": {
            "legal_name": STUDIO_LEGAL_NAME,
            "dba": STUDIO_DBA,
            "address": STUDIO_ADDRESS,
        },
        "workshop": {
            "title": course.get("title"),
            "description": course.get("description"),
            "format": "In-studio" if not course.get("is_virtual") else "Virtual",
            "num_sessions": len(sessions),
            "length_per_session_min": (
                int((sessions[0]["ends_at"] - sessions[0]["starts_at"]).total_seconds() // 60)
                if sessions and sessions[0].get("ends_at") and sessions[0].get("starts_at")
                else None
            ),
            "location": course.get("location") or STUDIO_ADDRESS,
            "max_participants": course.get("capacity"),
            "min_enrollment": course.get("min_enrollment") or 0,
            "participant_fee_cents": course.get("price_cents") or 0,
            "sessions": [
                {
                    "n": i + 1,
                    "date": fmt_date(s.get("starts_at")),
                    "starts_at": fmt_date(s.get("starts_at")),
                    "ends_at": fmt_date(s.get("ends_at")),
                }
                for i, s in enumerate(sessions)
            ],
            "instructor_supplied_materials": comp.get("instructor_supplied_materials") or "",
            "studio_supplied_materials": comp.get("studio_supplied_materials") or "Workshop space, sound system, standard studio props (mats, blocks, straps, bolsters), cleaning and preparation of the space.",
            "prerequisites": course.get("prerequisites") or "None",
        },
        "compensation": {
            "option": comp.get("option"),                        # flat_fee | per_participant | revenue_share | hybrid
            "flat_fee_cents": comp.get("flat_fee_cents"),
            "flat_fee_payable_per": comp.get("flat_fee_payable_per"),  # e.g. "session" or "workshop"
            "per_participant_cents": comp.get("per_participant_cents"),
            "revenue_share_percent_to_instructor": comp.get("revenue_share_percent_to_instructor"),
            "hybrid_description": comp.get("hybrid_description") or "",
            "expense_reimbursements": comp.get("expense_reimbursements") or "None",
            "payment_method": comp.get("payment_method") or "Stripe Connect (direct deposit)",
            "payment_timing_business_days": comp.get("payment_timing_business_days") or 15,
        },
        "guest_known_contact": {
            "name": guest.get("name"),
            "email": guest.get("email"),
            "phone": guest.get("phone"),
            "address_line1": guest.get("address_line1"),
            "city": guest.get("city"),
            "state": guest.get("state"),
            "postal_code": guest.get("postal_code"),
        },
    }


# ── Studio acknowledgment text (Option B from Don's design call) ─────────────
def studio_acknowledgment(prepared_at: datetime) -> str:
    """No drawn studio signature; affixed by electronic preparation per §18.7."""
    when = prepared_at.astimezone(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
    return (
        f"/s/ {STUDIO_SIGNATORY_NAME}, {STUDIO_SIGNATORY_TITLE}, {STUDIO_LEGAL_NAME} "
        f"— affixed by electronic preparation on {when}"
    )


# ── HTML rendering (used both for the sign page payload + final PDF) ────────


def _marketing_section_html(inst: dict, photo_url: str | None, flyer_url: str | None) -> str:
    """Renders Section 0 — the instructor-supplied marketing block. If signing
    isn't done yet, photo_url/flyer_url are None and we show placeholders."""
    desc = (inst.get("workshop_description") or "").strip()
    adv = (inst.get("advertising_details") or "").strip()
    intake = (inst.get("intake_form_link") or "").strip()
    waiver = (inst.get("waiver_link") or "").strip()
    pre = (inst.get("pre_workshop_docs") or "").strip()
    rows = []
    if desc:
        rows.append(f"<h3>Workshop Description</h3><p>{desc.replace(chr(10), '<br>')}</p>")
    if adv:
        rows.append(f"<h3>Marketing Notes</h3><p>{adv.replace(chr(10), '<br>')}</p>")
    if intake:
        rows.append(f"<h3>Pre-Workshop Intake Form</h3><p><a href='{intake}'>{intake}</a></p>")
    if waiver:
        rows.append(f"<h3>Additional Waiver</h3><p><a href='{waiver}'>{waiver}</a></p>")
    if pre:
        rows.append(f"<h3>Pre-Workshop Reading / Tasks</h3><p>{pre.replace(chr(10), '<br>')}</p>")

    img_block = ""
    if photo_url or flyer_url:
        img_block = '<div class="img-row">'
        if photo_url:
            img_block += f'<div class="img-col"><div class="img-cap">Instructor Photo</div><img src="{photo_url}" class="marketing-img"></div>'
        if flyer_url:
            img_block += f'<div class="img-col"><div class="img-cap">Workshop Flyer</div><img src="{flyer_url}" class="marketing-img"></div>'
        img_block += '</div>'
    if not rows and not img_block:
        return ""
    return f"""
    <h2>SECTION 0 — WORKSHOP MARKETING DETAILS (Instructor-Supplied)</h2>
    <p style="font-size:9pt;color:#666;font-style:italic;">
      The following details were supplied by the Instructor at signing for use
      in advertising and on-site materials. They form part of the agreement
      between the Parties as to the public-facing scope of the Workshop.
    </p>
    {''.join(rows)}
    {img_block}
    """


def render_html(
    *,
    prefilled: dict,
    instructor_data: dict | None = None,
    signature_image_data_url: str | None = None,
    signed_at: datetime | None = None,
    signed_ip: str | None = None,
    studio_ack: str | None = None,
    effective_date: date | None = None,
    instructor_photo_data_url: str | None = None,
    workshop_flyer_data_url: str | None = None,
) -> str:
    """Render the full agreement as a single HTML document.

    When called for SIGNING (instructor hasn't signed yet), pass only
    `prefilled`. Instructor-side fields render as visible blanks/inputs.

    When called for PDF (instructor has signed), pass everything; output
    is fully filled in and ready for weasyprint.
    """
    w = prefilled["workshop"]
    s = prefilled["studio"]
    c = prefilled["compensation"]
    inst = instructor_data or {}
    eff = effective_date.strftime("%B %d, %Y") if effective_date else "____________________"

    # Compensation block render
    comp_html = _comp_html(c)
    sessions_html = _sessions_html(w["sessions"])
    sig_block_html = _signature_block_html(s, inst, signature_image_data_url, signed_at, signed_ip, studio_ack)

    return _PAGE_SHELL.format(
        title="Guest Instructor Workshop Services Agreement",
        body=f"""
        <h1>GUEST INSTRUCTOR WORKSHOP SERVICES AGREEMENT</h1>
        <p class="subtitle">{s['dba']} / {s['legal_name']}</p>

        {_marketing_section_html(inst, instructor_photo_data_url, workshop_flyer_data_url)}

        <h2>PARTIES AND EFFECTIVE DATE</h2>
        <p>This Guest Instructor Workshop Services Agreement (the &ldquo;Agreement&rdquo;) is entered into as of the Effective Date set forth below, by and between <strong>{s['legal_name']}</strong>, a limited liability company doing business as <strong>{s['dba']}</strong>, with its principal place of business at {s['address']} (the &ldquo;Studio&rdquo;), and the Instructor identified below. The Studio and the Instructor are referred to individually as a &ldquo;Party&rdquo; and collectively as the &ldquo;Parties.&rdquo;</p>

        <table class="parties">
            <tr><td class="lbl">Effective Date:</td><td>{eff}</td></tr>
            <tr><td class="lbl">Instructor Legal Name:</td><td>{_inst_field(inst, 'legal_name')}</td></tr>
            <tr><td class="lbl">Instructor Entity / DBA:</td><td>{_inst_field(inst, 'entity_dba') or '<i>(none)</i>'}</td></tr>
            <tr><td class="lbl">Instructor Address:</td><td>{_inst_field(inst, 'address')}</td></tr>
            <tr><td class="lbl">Email:</td><td>{_inst_field(inst, 'email')}</td></tr>
            <tr><td class="lbl">Phone:</td><td>{_inst_field(inst, 'phone')}</td></tr>
        </table>

        <h2>RECITALS</h2>
        <p>WHEREAS, the Studio operates a yoga and wellness studio and from time to time engages qualified independent professionals to present workshops, special events, and educational programs for its participants and members;</p>
        <p>WHEREAS, the Instructor is a qualified professional engaged in the independent practice of delivering workshops in the Instructor&rsquo;s area of expertise and has represented to the Studio that the Instructor possesses the training, credentials, experience, and business infrastructure necessary to deliver the Workshop (as defined below);</p>
        <p>WHEREAS, the Parties desire to set forth the terms and conditions under which the Instructor will present a workshop series at the Studio&rsquo;s facility;</p>
        <p>NOW, THEREFORE, in consideration of the mutual promises and covenants contained herein, and for other good and valuable consideration, the receipt and sufficiency of which are hereby acknowledged, the Parties agree as follows:</p>

        <h2>1. THE WORKSHOP</h2>
        <p><strong>1.1 Workshop Description.</strong> The Instructor shall plan, prepare for, and present a workshop or series of workshops (the &ldquo;Workshop&rdquo;) as described in <strong>Exhibit A</strong> attached hereto and incorporated herein by reference. Exhibit A sets forth the title, subject matter, format, learning objectives, session dates, session start and end times, session duration, maximum number of participants per session, and any special equipment, props, or setup requirements.</p>
        <p><strong>1.2 Location.</strong> The Workshop shall be held at the Studio&rsquo;s facility located at {s['address']}, or such other location as the Parties may mutually agree in writing.</p>
        <p><strong>1.3 Scope of Services.</strong> The Instructor shall deliver the Workshop substantially as described in Exhibit A. The Instructor shall arrive at least thirty (30) minutes before each scheduled session to set up and shall remain reasonably available after each session for participant questions. The Instructor shall not substantially modify the Workshop content, format, or schedule without the Studio&rsquo;s prior written consent.</p>
        <p><strong>1.4 Substitutes.</strong> The Workshop shall be delivered personally by the Instructor. The Instructor shall not delegate delivery of the Workshop to any substitute, assistant, or other third party without the Studio&rsquo;s prior written consent. In the event of illness, injury, or emergency, the Instructor shall promptly notify the Studio so that the Parties may jointly determine whether to reschedule, cancel, or engage an approved substitute.</p>

        <h2>2. STUDIO OBLIGATIONS</h2>
        <p><strong>2.1 Facility and Equipment.</strong> The Studio shall provide the Workshop space, sound system, standard studio props (mats, blocks, straps, bolsters), cleaning and preparation of the space, and such other equipment as is customary for the Studio&rsquo;s operations. Any specialized equipment, materials, or handouts required by the Instructor shall be the Instructor&rsquo;s sole responsibility unless otherwise set forth in Exhibit A.</p>
        <p><strong>2.2 Registration Platform.</strong> The Studio shall make available its online registration system and intake workflow for the Workshop and shall be responsible for collecting participant registrations, participant payments, and executed Liability Waivers (as defined in Section 3 below) through that system.</p>
        <p><strong>2.3 Marketing Support.</strong> The Studio shall include the Workshop in its ordinary promotional channels, which may include the Studio website, email newsletters, in-studio signage, and social media. Nothing in this Agreement obligates the Studio to incur specific advertising expenditures on behalf of the Workshop unless expressly stated in Exhibit A.</p>

        <h2>3. PARTICIPANT REGISTRATION AND LIABILITY WAIVER</h2>
        <p><strong>3.1 Mandatory Registration.</strong> As a material condition of this Agreement, no person shall be permitted to participate in, attend, observe, or otherwise access any session of the Workshop unless and until such person has (a) completed registration for the Workshop through the official {s['dba']} website or Studio-approved registration system (the &ldquo;Registration Portal&rdquo;); and (b) electronically executed, acknowledged, and agreed to the Studio&rsquo;s then-current participant release, waiver of liability, assumption of risk, and informed-consent agreement (the &ldquo;Liability Waiver&rdquo;).</p>
        <p><strong>3.2 No Exceptions.</strong> The registration and Liability Waiver requirement set forth in Section 3.1 is non-negotiable and shall not be waived, suspended, or relaxed by the Instructor for any person under any circumstance, including without limitation friends, family members, personal guests of the Instructor, media, photographers, videographers, observers, industry peers, substitute participants, or walk-ins. Any person wishing to attend must complete the Registration Portal process and execute the Liability Waiver before being admitted to the Workshop space.</p>
        <p><strong>3.3 Verification.</strong> The Studio shall maintain a roster of registered participants for each session who have completed the Liability Waiver. The Instructor shall cooperate with the Studio&rsquo;s staff in verifying that each person present has completed registration and executed the Liability Waiver prior to the commencement of each session. The Instructor shall not knowingly permit an unregistered person to remain in the Workshop space and shall promptly notify Studio staff of any person whose status cannot be confirmed.</p>
        <p><strong>3.4 Instructor Materials Consistent with Waiver.</strong> The Instructor shall not require, request, or encourage any participant to perform any activity, technique, posture, or practice that falls outside the scope of activities and risks disclosed in the Liability Waiver without first obtaining the Studio&rsquo;s prior written approval and, if the Studio so requires, a supplemental participant acknowledgment.</p>
        <p><strong>3.5 Breach.</strong> The Instructor acknowledges that any breach of this Section 3 constitutes a material breach of this Agreement, entitles the Studio to terminate this Agreement immediately for cause under Section 15.2, and may result in the Instructor bearing sole responsibility, including under Section 9 (Indemnification), for any resulting claims, injuries, or losses.</p>

        <h2>4. COMPENSATION AND PAYMENT</h2>
        <p><strong>4.1 Compensation.</strong> In consideration for the services provided by the Instructor under this Agreement, the Studio shall pay the Instructor the compensation set forth in <strong>Exhibit B</strong> attached hereto. Exhibit B specifies the compensation structure (flat fee, per-participant fee, revenue share, or other), the amount(s), the basis of calculation, and the payment schedule.</p>
        <p><strong>4.2 Payment Timing.</strong> Unless otherwise stated in Exhibit B, the Studio shall remit payment to the Instructor within fifteen (15) business days after the conclusion of the Workshop (or, for a series, within fifteen (15) business days after the final session), subject to the Studio having received all participant payments and any required tax documentation from the Instructor.</p>
        <p><strong>4.3 Tax Documentation.</strong> Before the first payment is made, the Instructor shall deliver to the Studio a completed IRS Form W-9 (or Form W-8, as applicable). The Instructor acknowledges that the Studio will issue an IRS Form 1099-NEC or other required tax reporting form if total compensation meets applicable thresholds. The Instructor is solely responsible for the payment of all federal, state, and local taxes, including self-employment taxes, attributable to compensation received under this Agreement.</p>
        <p><strong>4.4 Expenses.</strong> Except as expressly set forth in Exhibit B, the Instructor shall bear all of the Instructor&rsquo;s own expenses, including without limitation travel, lodging, meals, materials, equipment, insurance premiums, licensing, and continuing education.</p>
        <p><strong>4.5 Refunds and Chargebacks.</strong> The Studio shall handle all participant-facing refunds, cancellations, and payment processing in accordance with its standard policies. Where the Instructor&rsquo;s compensation is based on a per-participant or revenue-share basis, participant refunds and payment-processor chargebacks shall reduce the Instructor&rsquo;s compensation on a pro rata basis, calculated on net collected revenue after payment processing fees.</p>

        <h2>5. MINIMUM ENROLLMENT; CANCELLATION; RESCHEDULING</h2>
        <p><strong>5.1 Minimum Enrollment.</strong> The Studio reserves the right, in its sole discretion, to cancel or reschedule a Workshop session if enrollment falls below the minimum enrollment threshold stated in Exhibit A (or, if no threshold is stated, if enrollment is in the Studio&rsquo;s reasonable business judgment insufficient to proceed). In the event of a Studio-initiated cancellation due to low enrollment communicated at least seventy-two (72) hours before the session, neither Party shall owe the other Party any compensation or damages for the cancelled session.</p>
        <p><strong>5.2 Instructor Cancellation.</strong> If the Instructor cancels or fails to appear for any scheduled session for reasons other than a Force Majeure Event (as defined in Section 11), the Instructor shall (a) forfeit all compensation for the cancelled session, and (b) reimburse the Studio for any participant refunds the Studio elects to issue on account of the cancellation and any reasonable, documented out-of-pocket expenses the Studio incurs as a direct result of the cancellation, up to a cap equal to the compensation the Instructor would otherwise have earned for the cancelled session.</p>
        <p><strong>5.3 Rescheduling.</strong> The Parties shall use good-faith efforts to reschedule any session cancelled for any reason before exercising any remedy under Sections 5.1 or 5.2.</p>
        <p><strong>5.4 Participant-Facing Communications.</strong> All participant-facing communications regarding cancellation, rescheduling, or refunds shall be issued by the Studio.</p>

        <h2>6. MARKETING, NAME AND LIKENESS</h2>
        <p><strong>6.1 License to Use Name and Likeness.</strong> The Instructor grants the Studio a non-exclusive, royalty-free, worldwide license to use the Instructor&rsquo;s name, biography, professional photographs, voice, and likeness (collectively, &ldquo;Instructor Materials&rdquo;) for the purpose of marketing, advertising, and promoting the Workshop and the Studio&rsquo;s related offerings. This license extends to the Studio&rsquo;s website, email, social media, print materials, and in-studio signage.</p>
        <p><strong>6.2 Duration of License.</strong> The license granted in Section 6.1 is effective as of the Effective Date and continues for twelve (12) months following the final session of the Workshop, after which the Studio shall make reasonable efforts to remove Workshop-specific promotional content featuring the Instructor from channels under the Studio&rsquo;s direct control upon the Instructor&rsquo;s written request.</p>
        <p><strong>6.3 Instructor Promotion.</strong> The Instructor may promote the Workshop through the Instructor&rsquo;s own channels. All such promotion shall accurately reflect the Workshop details set forth in Exhibit A, identify the Studio as the host venue, and direct prospective participants to the Registration Portal for enrollment. The Instructor shall not accept registrations, payments, or waivers outside the Registration Portal.</p>

        <h2>7. INTELLECTUAL PROPERTY; RECORDINGS</h2>
        <p><strong>7.1 Instructor Content.</strong> As between the Parties, the Instructor retains all right, title, and interest in and to the Instructor&rsquo;s pre-existing curriculum, teaching methodology, handouts, and other materials that the Instructor brings to the Workshop (the &ldquo;Instructor Content&rdquo;). The Instructor grants the Studio a limited, non-exclusive, royalty-free license to use the Instructor Content solely as reasonably necessary to deliver and administer the Workshop.</p>
        <p><strong>7.2 Studio Content.</strong> As between the Parties, the Studio retains all right, title, and interest in and to the Studio&rsquo;s brand, logos, website, Registration Portal, participant data, and all other Studio-generated content and systems.</p>
        <p><strong>7.3 Recording.</strong> Neither Party shall audio-record, video-record, livestream, or otherwise capture any Workshop session without the other Party&rsquo;s prior written consent. If the Parties agree in writing that a session will be recorded, they shall separately agree in writing on ownership of, and permitted uses of, the resulting recordings. The Instructor shall be responsible for ensuring that any participant appearing in a recording has signed an appropriate media release provided or approved by the Studio.</p>
        <p><strong>7.4 Participant Recording.</strong> The Instructor shall not permit participants to record any Workshop session without the Studio&rsquo;s prior written consent.</p>

        <h2>8. INSURANCE</h2>
        <p><strong>8.1 Instructor Insurance.</strong> Throughout the term of this Agreement, the Instructor shall procure and maintain, at the Instructor&rsquo;s sole expense, the following insurance coverage:</p>
        <p style="margin-left:24px;">(a) Commercial General Liability insurance with limits of not less than $1,000,000 per occurrence and $2,000,000 aggregate, covering bodily injury, property damage, personal injury, and advertising injury;</p>
        <p style="margin-left:24px;">(b) Professional Liability (Errors &amp; Omissions) insurance appropriate to the Instructor&rsquo;s modality, with limits of not less than $1,000,000 per occurrence and $2,000,000 aggregate; and</p>
        <p style="margin-left:24px;">(c) Such additional coverage as is customary for the Instructor&rsquo;s professional practice, which may include workers&rsquo; compensation if the Instructor has employees.</p>
        <p><strong>8.2 Additional Insured; Certificate.</strong> The Instructor shall name {s['legal_name']} dba {s['dba']} as an additional insured under the Commercial General Liability policy for the term of this Agreement. Before the first Workshop session, the Instructor shall deliver to the Studio a certificate of insurance evidencing the coverage required under Section 8.1 and the additional-insured endorsement required under this Section 8.2. The Instructor shall provide the Studio with at least thirty (30) days&rsquo; prior written notice of any cancellation, non-renewal, or material reduction in coverage.</p>
        <p><strong>8.3 Studio Insurance.</strong> The Studio shall maintain, at its expense, commercial general liability insurance appropriate to its operations.</p>

        <h2>9. INDEMNIFICATION</h2>
        <p><strong>9.1 By the Instructor.</strong> The Instructor shall indemnify, defend, and hold harmless the Studio, its members, managers, officers, employees, agents, successors, and assigns (collectively, the &ldquo;Studio Indemnitees&rdquo;) from and against any and all third-party claims, demands, suits, actions, losses, damages, fines, penalties, costs, and expenses, including reasonable attorneys&rsquo; fees (collectively, &ldquo;Losses&rdquo;), arising out of or relating to: (a) the Instructor&rsquo;s acts, omissions, errors, or negligence in connection with the Workshop; (b) any bodily injury, death, or property damage alleged to arise from the Workshop content, instruction, cueing, adjustments, or physical assists delivered by the Instructor; (c) any breach by the Instructor of this Agreement, including any breach of the representations and warranties in Section 12; (d) any breach by the Instructor of Section 3 (Participant Registration and Liability Waiver); (e) any claim by any taxing authority, worker&rsquo;s compensation board, or other governmental agency that the Instructor is or was an employee of the Studio for purposes of taxes, benefits, or insurance; and (f) any claim that the Instructor Content infringes or misappropriates a third party&rsquo;s intellectual property rights.</p>
        <p><strong>9.2 By the Studio.</strong> The Studio shall indemnify, defend, and hold harmless the Instructor from and against any and all Losses arising out of or relating to (a) the Studio&rsquo;s gross negligence or willful misconduct in the maintenance of the Workshop facility; or (b) any breach by the Studio of this Agreement.</p>
        <p><strong>9.3 Procedure.</strong> The indemnified Party shall give the indemnifying Party prompt written notice of any claim for which indemnification is sought, shall reasonably cooperate in the defense of the claim, and shall not settle or compromise any claim without the indemnifying Party&rsquo;s prior written consent, not to be unreasonably withheld.</p>

        <h2>10. LIMITATION OF LIABILITY</h2>
        <p>EXCEPT FOR EACH PARTY&rsquo;S INDEMNIFICATION OBLIGATIONS UNDER SECTION 9, EACH PARTY&rsquo;S OBLIGATIONS OF CONFIDENTIALITY UNDER SECTION 13, AND LIABILITY ARISING FROM A PARTY&rsquo;S GROSS NEGLIGENCE OR WILLFUL MISCONDUCT, IN NO EVENT SHALL EITHER PARTY BE LIABLE TO THE OTHER PARTY FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, EXEMPLARY, OR PUNITIVE DAMAGES, INCLUDING LOST PROFITS, ARISING OUT OF OR RELATING TO THIS AGREEMENT, EVEN IF SUCH PARTY HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGES. EXCEPT FOR THE EXCLUDED MATTERS ABOVE, EACH PARTY&rsquo;S TOTAL AGGREGATE LIABILITY UNDER THIS AGREEMENT SHALL NOT EXCEED THE TOTAL COMPENSATION PAID OR PAYABLE TO THE INSTRUCTOR UNDER THIS AGREEMENT.</p>

        <h2>11. FORCE MAJEURE</h2>
        <p>Neither Party shall be liable for any failure or delay in performance under this Agreement (except for payment obligations for services already rendered) arising from causes beyond its reasonable control, including without limitation acts of God, natural disasters, fire, flood, earthquake, severe weather, epidemic, pandemic, quarantine, government order, civil unrest, war, terrorism, or failure of utilities or telecommunications (a &ldquo;Force Majeure Event&rdquo;). The affected Party shall promptly notify the other Party of the Force Majeure Event and use reasonable efforts to mitigate its effects. If a Force Majeure Event continues for more than thirty (30) days, either Party may terminate this Agreement on written notice without further liability other than for services already rendered and expenses already incurred.</p>

        <h2>12. INSTRUCTOR REPRESENTATIONS AND WARRANTIES</h2>
        <p>The Instructor represents and warrants to the Studio that, as of the Effective Date and throughout the term of this Agreement:</p>
        <p style="margin-left:24px;">(a) the Instructor holds all certifications, registrations, licenses, and qualifications reasonably required to deliver the Workshop, and all such credentials are current and in good standing;</p>
        <p style="margin-left:24px;">(b) the Instructor has no physical or mental condition that would impair the Instructor&rsquo;s ability to deliver the Workshop safely;</p>
        <p style="margin-left:24px;">(c) the Instructor has not been the subject of any criminal conviction, civil judgment, professional disciplinary action, restraining order, or accusation of misconduct (including sexual, physical, or emotional misconduct) that would reasonably be expected to affect the Instructor&rsquo;s fitness to deliver the Workshop or reflect adversely on the Studio;</p>
        <p style="margin-left:24px;">(d) the Instructor&rsquo;s performance under this Agreement will not breach any agreement with any third party, including any non-compete, non-solicit, confidentiality, or exclusivity obligation;</p>
        <p style="margin-left:24px;">(e) the Instructor Content and the Workshop, as delivered, will not infringe, misappropriate, or violate any third party&rsquo;s intellectual property rights, privacy rights, or publicity rights;</p>
        <p style="margin-left:24px;">(f) the Instructor will deliver the Workshop in a professional manner consistent with the standards of care applicable to the Instructor&rsquo;s profession and will comply with all applicable federal, state, and local laws, regulations, and codes of professional conduct; and</p>
        <p style="margin-left:24px;">(g) the Instructor is engaged in an independently established trade, occupation, or business of the same nature as the services being performed under this Agreement, customarily performs such services for other clients, and holds itself out to the public as available to perform such services.</p>

        <h2>13. CONFIDENTIALITY</h2>
        <p><strong>13.1 Confidential Information.</strong> Each Party may disclose to the other Party non-public information concerning its business, participants, pricing, marketing, financial results, and operations (&ldquo;Confidential Information&rdquo;). Without limiting the foregoing, all personally identifiable information of Studio participants constitutes the Studio&rsquo;s Confidential Information. Each Party shall (a) use Confidential Information only as necessary to perform its obligations under this Agreement; (b) protect Confidential Information with the same degree of care it uses to protect its own confidential information, and in no event less than reasonable care; and (c) not disclose Confidential Information to any third party without the other Party&rsquo;s prior written consent, except as required by law.</p>
        <p><strong>13.2 Participant Data.</strong> The Instructor shall not collect, retain, copy, export, or use participant contact information, health information, registration data, or payment information for any purpose other than delivering the Workshop, and shall not use such information to solicit, market to, or otherwise contact participants outside the scope of the Workshop without the Studio&rsquo;s prior written consent.</p>

        <h2>14. NON-SOLICITATION</h2>
        <p>During the term of this Agreement and for a period of twelve (12) months after its expiration or termination, the Instructor shall not, directly or indirectly, use the Studio&rsquo;s participant lists, Confidential Information, or information learned in connection with the Workshop to solicit Studio participants to attend any program, class, workshop, or service that is offered outside the Studio and is competitive with the Studio&rsquo;s offerings. Nothing in this Section 14 prohibits the Instructor from general advertising not targeted at Studio participants, or from continuing to serve persons with whom the Instructor had a pre-existing professional relationship prior to the Effective Date.</p>

        <h2>15. TERM AND TERMINATION</h2>
        <p><strong>15.1 Term.</strong> This Agreement commences on the Effective Date and continues until the completion of the Workshop as set forth in Exhibit A, unless earlier terminated in accordance with this Section 15.</p>
        <p><strong>15.2 Termination for Cause.</strong> Either Party may terminate this Agreement immediately upon written notice if the other Party: (a) materially breaches this Agreement and fails to cure such breach within five (5) business days after written notice of the breach (or, in the case of a breach that by its nature cannot be cured, immediately upon written notice); (b) becomes insolvent or makes a general assignment for the benefit of creditors; or (c) engages in conduct that, in the reasonable judgment of the non-breaching Party, threatens the safety or wellbeing of Workshop participants or reflects materially adversely on the non-breaching Party&rsquo;s reputation. The Studio may additionally terminate this Agreement immediately for cause upon any breach of Section 3 (Participant Registration and Liability Waiver).</p>
        <p><strong>15.3 Termination for Convenience.</strong> Either Party may terminate this Agreement for any reason upon fourteen (14) days&rsquo; prior written notice. If the Studio terminates for convenience after the Workshop has been publicly promoted and enrollments have been accepted, the Studio shall pay the Instructor a pro rata portion of the agreed compensation for any session that has already occurred, plus a reasonable cancellation fee not to exceed twenty-five percent (25%) of the compensation that would have been earned for the remaining scheduled sessions.</p>
        <p><strong>15.4 Effect of Termination.</strong> Upon termination or expiration of this Agreement, the Instructor shall promptly return or destroy all Studio Confidential Information in the Instructor&rsquo;s possession. Sections 3.5, 4.3, 6.2, 7, 9, 10, 12, 13, 14, 15.4, 16, and 17 shall survive termination.</p>

        <h2>16. INDEPENDENT CONTRACTOR RELATIONSHIP</h2>
        <p><strong>16.1 Status.</strong> The Parties intend that the Instructor perform services under this Agreement as an independent contractor and not as an employee, agent, partner, or joint venturer of the Studio. Nothing in this Agreement creates an employer-employee relationship between the Parties.</p>
        <p><strong>16.2 Control.</strong> Subject to the scheduling, facility, safety, registration, and branding requirements expressly set forth in this Agreement, the Instructor retains sole control over the manner and means by which the Workshop is delivered, including the selection of methodology, curriculum, pacing, cueing, and adjustments.</p>
        <p><strong>16.3 No Employee Benefits.</strong> The Instructor is not entitled to participate in any benefit plans of the Studio, including health insurance, retirement plans, paid time off, workers&rsquo; compensation (except to the extent required by law), unemployment insurance, or disability insurance. The Instructor acknowledges responsibility for its own taxes, benefits, and expenses.</p>
        <p><strong>16.4 Own Business.</strong> The Instructor represents that the Instructor operates an independently established trade, occupation, or business, holds itself out to the public as performing services of the type contemplated by this Agreement for other clients, and is not financially dependent on the Studio.</p>

        <h2>17. GOVERNING LAW; VENUE; DISPUTE RESOLUTION</h2>
        <p><strong>17.1 Governing Law.</strong> This Agreement is governed by and construed in accordance with the laws of the State in which the Studio is located, without regard to its conflict-of-laws principles.</p>
        <p><strong>17.2 Venue.</strong> Subject to Section 17.3, any action or proceeding arising out of or relating to this Agreement shall be brought exclusively in the state or federal courts located in the county in which the Studio is located, and each Party consents to the personal jurisdiction of such courts.</p>
        <p><strong>17.3 Informal Resolution; Mediation.</strong> Before initiating any formal legal proceeding, the Parties shall first attempt in good faith to resolve any dispute through informal negotiation. If the dispute is not resolved within thirty (30) days, the Parties shall attempt to resolve the dispute through non-binding mediation administered by a mutually agreeable mediator in the county in which the Studio is located, with each Party bearing its own costs and the Parties equally splitting the mediator&rsquo;s fees. This Section 17.3 shall not prevent either Party from seeking immediate injunctive or other equitable relief in court to protect its intellectual property, Confidential Information, or the safety of its participants.</p>
        <p><strong>17.4 Attorneys&rsquo; Fees.</strong> In any action to enforce or interpret this Agreement, the prevailing Party shall be entitled to recover its reasonable attorneys&rsquo; fees and costs from the non-prevailing Party.</p>

        <h2>18. GENERAL PROVISIONS</h2>
        <p><strong>18.1 Notices.</strong> All notices under this Agreement shall be in writing and shall be deemed given upon personal delivery, upon delivery by nationally recognized overnight courier, or upon confirmation of receipt by email, in each case addressed to the Parties at the addresses set forth in this Agreement or at such other address as a Party may designate in writing.</p>
        <p><strong>18.2 Entire Agreement.</strong> This Agreement, together with its Exhibits, constitutes the entire agreement between the Parties regarding its subject matter and supersedes all prior and contemporaneous understandings, agreements, representations, and warranties, whether written or oral.</p>
        <p><strong>18.3 Amendments.</strong> No amendment, modification, or waiver of any provision of this Agreement shall be effective unless in writing and signed by both Parties.</p>
        <p><strong>18.4 Assignment.</strong> The Instructor shall not assign or delegate this Agreement, in whole or in part, without the Studio&rsquo;s prior written consent. The Studio may assign this Agreement to an affiliate or to a successor in connection with a merger, reorganization, or sale of substantially all of its assets.</p>
        <p><strong>18.5 Severability.</strong> If any provision of this Agreement is held to be invalid or unenforceable, the remaining provisions shall continue in full force and effect, and the invalid or unenforceable provision shall be reformed to the minimum extent necessary to render it valid and enforceable.</p>
        <p><strong>18.6 No Waiver.</strong> No waiver of any breach or default under this Agreement shall constitute a waiver of any subsequent breach or default.</p>
        <p><strong>18.7 Counterparts; Electronic Signatures.</strong> This Agreement may be executed in counterparts, each of which shall be deemed an original and all of which together shall constitute one instrument. The Parties agree that electronic signatures, PDFs of signed documents, and signatures delivered through recognized electronic signature platforms (such as LibreSign, Documenso, DocuSign, or Dropbox Sign) have the same legal effect as original ink signatures.</p>
        <p><strong>18.8 Headings.</strong> Section headings are for convenience only and do not affect the interpretation of this Agreement.</p>

        {sig_block_html}

        <h2 class="page-break">EXHIBIT A — WORKSHOP DETAILS</h2>
        <table class="exhibit">
            <tr><td class="lbl">Workshop Title:</td><td>{w['title']}</td></tr>
            <tr><td class="lbl">Description / Learning Objectives:</td><td>{(w.get('description') or '').replace(chr(10), '<br>')}</td></tr>
            <tr><td class="lbl">Format:</td><td>{w['format']}</td></tr>
            <tr><td class="lbl">Number of Sessions:</td><td>{w['num_sessions']}</td></tr>
            <tr><td class="lbl">Length per Session (min):</td><td>{w.get('length_per_session_min') or 'See schedule below'}</td></tr>
            <tr><td class="lbl">Location:</td><td>{w['location']}</td></tr>
            <tr><td class="lbl">Maximum Participants per Session:</td><td>{w.get('max_participants') or 'N/A'}</td></tr>
            <tr><td class="lbl">Minimum Enrollment Threshold:</td><td>{w.get('min_enrollment') or 'N/A'}</td></tr>
            <tr><td class="lbl">Participant Fee (collected by Studio):</td><td>${(w.get('participant_fee_cents') or 0)/100:.2f}</td></tr>
        </table>
        <h3>Session Schedule</h3>
        {sessions_html}
        <h3>Instructor-Supplied Materials / Props / Equipment</h3>
        <p>{w['instructor_supplied_materials'] or '<i>(none)</i>'}</p>
        <h3>Studio-Supplied Materials / Props / Equipment</h3>
        <p>{w['studio_supplied_materials']}</p>
        <h3>Prerequisites or Participant Restrictions</h3>
        <p>{w['prerequisites']}</p>

        <h2 class="page-break">EXHIBIT B — COMPENSATION SCHEDULE</h2>
        {comp_html}
        """,
    )


def _inst_field(inst: dict, name: str) -> str:
    v = inst.get(name) if inst else None
    if v is None or v == "":
        return '<span class="blank">________________________________</span>'
    if name == "address":
        # textarea — preserve newlines
        return str(v).replace("\n", "<br>")
    return str(v)


def _sessions_html(sessions: list[dict]) -> str:
    if not sessions:
        return '<p><i>(see workshop record)</i></p>'
    rows = []
    for s in sessions:
        d = s.get("date", "")
        st = s.get("starts_at", "")
        et = s.get("ends_at", "")
        # Display ISO timestamps in a friendlier format if possible
        try:
            dt_s = datetime.fromisoformat(st.replace("Z", "+00:00"))
            dt_e = datetime.fromisoformat(et.replace("Z", "+00:00"))
            disp = f'{dt_s.strftime("%a %b %d, %Y")} &mdash; {dt_s.strftime("%-I:%M %p")} to {dt_e.strftime("%-I:%M %p")}'
        except Exception:
            disp = f'{d} {st} &ndash; {et}'
        rows.append(f'<tr><td class="lbl">Session {s["n"]}:</td><td>{disp}</td></tr>')
    return '<table class="exhibit">' + ''.join(rows) + '</table>'


def _comp_html(c: dict) -> str:
    opt = (c.get("option") or "").lower()
    parts = []
    if opt == "flat_fee":
        parts.append('<p><strong>Compensation Structure: Flat Fee</strong></p>')
        amt = (c.get("flat_fee_cents") or 0) / 100
        parts.append(f'<p>Amount: <strong>${amt:,.2f}</strong> &mdash; payable per: <strong>{c.get("flat_fee_payable_per") or "workshop"}</strong></p>')
    elif opt == "per_participant":
        parts.append('<p><strong>Compensation Structure: Per-Participant Fee</strong></p>')
        amt = (c.get("per_participant_cents") or 0) / 100
        parts.append(f'<p>Amount per paying participant per session: <strong>${amt:,.2f}</strong></p>')
    elif opt == "revenue_share":
        parts.append('<p><strong>Compensation Structure: Revenue Share</strong></p>')
        pct = c.get("revenue_share_percent_to_instructor") or 0
        parts.append(f'<p>Percentage of net collected Workshop revenue (gross collections minus payment-processing fees, refunds, and chargebacks) payable to the Instructor: <strong>{pct}%</strong>; remainder to the Studio.</p>')
    elif opt == "hybrid":
        parts.append('<p><strong>Compensation Structure: Hybrid / Other</strong></p>')
        parts.append(f'<p>{(c.get("hybrid_description") or "").replace(chr(10), "<br>")}</p>')
    else:
        parts.append('<p><i>(compensation structure to be determined)</i></p>')
    parts.append(f'<p><strong>Expense Reimbursements payable by Studio:</strong> {c.get("expense_reimbursements") or "None"}</p>')
    parts.append(f'<p><strong>Payment Method:</strong> {c.get("payment_method") or "Stripe Connect (direct deposit)"} &nbsp;&nbsp; <strong>Payment Timing:</strong> {c.get("payment_timing_business_days") or 15} business days after final session</p>')
    return ''.join(parts)


def _signature_block_html(s, inst, sig_url, signed_at, signed_ip, studio_ack):
    studio_line = studio_ack or '<span class="blank">________________________________</span>'
    if sig_url and signed_at:
        sig_img = f'<img src="{sig_url}" class="sig-img" alt="signature">'
        signed_when = signed_at.astimezone(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
        attribution = f'<p class="audit">Electronically signed by {inst.get("legal_name","")} on {signed_when} from IP {signed_ip}. Signed under US ESIGN Act + UETA.</p>'
    else:
        sig_img = '<div class="sig-blank">[ instructor signature ]</div>'
        attribution = ''

    return f"""
    <h2 class="page-break">SIGNATURES</h2>
    <p>IN WITNESS WHEREOF, the Parties have executed this Agreement as of the Effective Date.</p>

    <div class="sig-block">
        <h3>STUDIO</h3>
        <p>{s['legal_name']}, d/b/a {s['dba']}</p>
        <p>Signature: {studio_line}</p>
        <p>Printed Name: <strong>{STUDIO_SIGNATORY_NAME}</strong> &nbsp;&nbsp; Title: <strong>{STUDIO_SIGNATORY_TITLE}</strong></p>
    </div>

    <div class="sig-block">
        <h3>INSTRUCTOR</h3>
        <p>Signature:</p>
        {sig_img}
        <p>Printed Name: <strong>{_inst_field(inst, 'printed_name')}</strong> &nbsp;&nbsp; Title: <strong>{_inst_field(inst, 'title')}</strong></p>
        <p>Date: <strong>{signed_at.astimezone(timezone.utc).strftime('%B %d, %Y') if signed_at else _inst_field(inst, 'signed_date_display') or '________________'}</strong></p>
        {attribution}
    </div>
    """


_PAGE_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  @page {{ size: letter; margin: 0.75in 0.75in 1in 0.75in;
    @top-right {{ content: "{title}"; font-style: italic; font-size: 9pt; color: #666; }}
    @bottom-center {{ content: "Page " counter(page); font-size: 9pt; color: #666; }}
  }}
  body {{ font-family: -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 11pt; line-height: 1.45; color: #1f2937; }}
  h1 {{ font-size: 18pt; text-align: center; margin: 0 0 4pt; }}
  .subtitle {{ text-align: center; color: #555; margin: 0 0 24pt; }}
  h2 {{ font-size: 13pt; margin: 24pt 0 8pt; padding-bottom: 4pt; border-bottom: 1px solid #ddd; }}
  h2.page-break {{ page-break-before: always; }}
  h3 {{ font-size: 11pt; margin: 16pt 0 6pt; }}
  p {{ margin: 0 0 8pt; text-align: justify; }}
  table.parties, table.exhibit {{ border-collapse: collapse; width: 100%; margin: 8pt 0; }}
  table.parties td, table.exhibit td {{ padding: 4pt 8pt; vertical-align: top; }}
  td.lbl {{ width: 35%; color: #555; font-weight: 600; }}
  .blank {{ color: #999; font-family: monospace; }}
  .sig-block {{ margin: 18pt 0; padding: 12pt; border: 1px solid #ddd; border-radius: 4pt; }}
  .sig-img {{ display: block; max-width: 280pt; max-height: 80pt; margin: 8pt 0; border-bottom: 1px solid #444; }}
  .sig-blank {{ height: 60pt; border-bottom: 1px solid #ccc; color: #aaa; font-style: italic; padding-top: 30pt; }}
  .audit {{ font-size: 9pt; color: #666; margin-top: 8pt; font-style: italic; }}
  .img-row {{ display: flex; gap: 16pt; margin: 12pt 0; }}
  .img-col {{ flex: 1; text-align: center; }}
  .img-cap {{ font-size: 9pt; color: #666; margin-bottom: 4pt; font-weight: 600; text-transform: uppercase; letter-spacing: .5px; }}
  .marketing-img {{ max-width: 100%; max-height: 240pt; border: 1px solid #ddd; border-radius: 4pt; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""
