"""AuraFlow — AI Feature Endpoints

Content generation, churn analysis, schedule optimization, marketing drafts,
milestone tracking, churn risk management, waitlist triage, dynamic pricing,
and review management powered by Claude.
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.services.ai.ai_service import AIService
from app.services.ai.churn_service import ChurnService
from app.services.ai.milestone_service import MilestoneService
from app.services.ai.video_generation_service import VideoGenerationService
from app.services.ai.waitlist_triage_service import WaitlistTriageService
from app.services.ai.dynamic_pricing_service import DynamicPricingService
from app.services.ai.review_service import ReviewService
from app.services.ai.retention_model import RetentionModel
from app.services.ai.smart_scheduling_service import SmartSchedulingService
from app.services.ai.member_insights_service import MemberInsightsService

router = APIRouter()
ai_svc = AIService()
churn_svc = ChurnService()
milestone_svc = MilestoneService()
video_svc = VideoGenerationService()
waitlist_svc = WaitlistTriageService()
pricing_svc = DynamicPricingService()
review_svc = ReviewService()
retention_model = RetentionModel()
smart_scheduling_svc = SmartSchedulingService()
member_insights_svc = MemberInsightsService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class ClassDescriptionRequest(BaseModel):
    class_name: str
    class_type: str
    level: str = "all levels"
    duration_minutes: int = 60
    studio_name: str = ""
    tone: str = "warm and inviting"

class MarketingEmailRequest(BaseModel):
    subject_context: str
    audience: str = "all members"
    tone: str = "friendly and professional"
    studio_name: str = ""

class SocialPostRequest(BaseModel):
    topic: str
    platform: str = "instagram"
    studio_name: str = ""

class ChurnAnalysisRequest(BaseModel):
    total_visits: int = 0
    last_visit_at: Optional[str] = None
    membership_status: str = "none"
    joined_at: Optional[str] = None
    lifetime_revenue_cents: int = 0
    recent_cancellations: int = 0
    days_since_visit: Optional[int] = None

class ScheduleSuggestionRequest(BaseModel):
    current_schedule_summary: str
    attendance_data: str
    studio_context: str = ""

class GenerateVideoRequest(BaseModel):
    member_id: str
    milestone_type: str
    studio_name: str = "the studio"


class DraftCreateRequest(BaseModel):
    prompt_context: str
    draft_type: str = "email"
    tone: str = "friendly and professional"
    studio_name: str = ""

class DraftUpdateRequest(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None


# ── Content Generation ───────────────────────────────────────────────────────

@router.post("/generate/class-description")
async def generate_class_description(
    body: ClassDescriptionRequest,
    rbac=Depends(require_permission("ai.generate_class_description")),
):
    """Generate an AI-powered class description."""
    return {"data": await ai_svc.generate_class_description(**body.model_dump())}


@router.post("/generate/marketing-email")
async def generate_marketing_email(
    body: MarketingEmailRequest,
    rbac=Depends(require_permission("ai.generate_marketing")),
):
    """Generate marketing email content."""
    return {"data": await ai_svc.generate_marketing_email(**body.model_dump())}


@router.post("/generate/social-post")
async def generate_social_post(
    body: SocialPostRequest,
    rbac=Depends(require_permission("ai.generate_marketing")),
):
    """Generate a social media post."""
    return {"data": await ai_svc.generate_social_post(**body.model_dump())}


# ── Analysis ─────────────────────────────────────────────────────────────────

@router.post("/analyze/churn-risk")
async def analyze_churn_risk(
    body: ChurnAnalysisRequest,
    rbac=Depends(require_permission("ai.analyze_retention")),
):
    """Analyze churn risk for a member (AI-powered, on-demand)."""
    return {"data": await ai_svc.analyze_churn_risk(body.model_dump())}


@router.post("/analyze/schedule")
async def suggest_schedule(
    body: ScheduleSuggestionRequest,
    rbac=Depends(require_permission("ai.analyze_schedule")),
):
    """Get AI-powered schedule optimization suggestions."""
    return {"data": await ai_svc.suggest_class_schedule(**body.model_dump())}


# ── Churn Risk Management ───────────────────────────────────────────────────

@router.post("/churn-scan")
async def trigger_churn_scan(
    user=Depends(get_current_user),
    _=Depends(require_permission("ai.analyze_retention")),
):
    """Manually trigger a churn risk scan for this tenant."""
    result = await churn_svc.scan_tenant_churn()
    return {"data": result}


@router.get("/churn-risk")
async def list_at_risk_members(
    user=Depends(get_current_user),
    _=Depends(require_permission("ai.view_retention")),
):
    """List members currently flagged as churn risk."""
    members = await churn_svc.get_at_risk_members()
    return {"data": members}


@router.post("/churn-risk/{member_id}/outreach")
async def send_winback(
    member_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("ai.outreach_retention")),
):
    """Send a 'we miss you' outreach to a flagged member."""
    try:
        result = await churn_svc.send_winback_outreach(member_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"data": result}


@router.post("/churn-risk/{member_id}/dismiss")
async def dismiss_churn_flag(
    member_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("ai.manage_retention")),
):
    """Clear the churn risk flag for a member."""
    dismissed = await churn_svc.dismiss_churn_flag(member_id)
    if not dismissed:
        raise HTTPException(status_code=404, detail="Member not found")
    return {"data": {"member_id": member_id, "status": "dismissed"}}


# ── ML-Enhanced Retention ──────────────────────────────────────────────────

@router.post("/ml-churn-scan")
async def trigger_ml_churn_scan(
    user=Depends(get_current_user),
    _=Depends(require_permission("ai.analyze_retention")),
):
    """Trigger an ML-enhanced churn scan using the 12-feature retention model.

    Scores every active member with a logistic regression model and flags
    those with churn probability > 0.4.  Returns risk distribution, newly
    flagged members, and per-member top risk factors.
    """
    result = await churn_svc.ml_scan_tenant_churn()
    return {"data": result}


@router.get("/churn-risk/{member_id}/score")
async def get_member_risk_score(
    member_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("ai.view_retention")),
):
    """Get the detailed ML risk score for a single member.

    Returns churn probability, risk level, the full 12-feature vector,
    and the top contributing factors.
    """
    try:
        score = await churn_svc.get_member_risk_score(member_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"data": score}


@router.get("/retention/dashboard")
async def retention_dashboard(
    user=Depends(get_current_user),
    _=Depends(require_permission("ai.view_retention")),
):
    """Retention dashboard: risk distribution, top churn factors, at-risk list.

    Provides a tenant-wide overview of member retention health including
    aggregate statistics, the most impactful churn factors across all
    members, and the top 25 highest-risk members.
    """
    dashboard = await retention_model.get_dashboard_stats()
    return {"data": dashboard}


# ── Milestones ───────────────────────────────────────────────────────────────

@router.get("/milestones/{member_id}")
async def get_member_milestones(
    member_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("ai.view_milestones")),
):
    """Get all milestones for a member."""
    milestones = await milestone_svc.get_member_milestones(member_id)
    return {"data": milestones}


@router.get("/milestones/{member_id}/{milestone_id}/video-status")
async def get_milestone_video_status(
    member_id: str,
    milestone_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("ai.view_milestones")),
):
    """Check video generation status for a milestone."""
    from app.db.session import get_tenant_db

    async with get_tenant_db() as db:
        row = await db.fetchrow(
            """
            SELECT id, video_url, video_provider, video_id, video_status
            FROM member_milestones
            WHERE id = $1 AND member_id = $2
            """,
            milestone_id, member_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Milestone not found")

    provider = row.get("video_provider")
    video_id = row.get("video_id")

    # If no video was ever triggered, return current DB state
    if not provider or not video_id:
        return {"data": {
            "milestone_id": milestone_id,
            "video_url": row.get("video_url"),
            "video_status": row.get("video_status") or "not_started",
            "provider": None,
            "video_id": None,
        }}

    # If already completed, return cached result
    if row.get("video_status") == "completed" and row.get("video_url"):
        return {"data": {
            "milestone_id": milestone_id,
            "video_url": row["video_url"],
            "video_status": "completed",
            "provider": provider,
            "video_id": video_id,
        }}

    # Poll the provider for current status
    status_result = await video_svc.check_video_status(provider, video_id)

    # Update DB if status changed
    if status_result.get("status") in ("completed", "failed"):
        async with get_tenant_db() as db:
            await db.execute(
                """
                UPDATE member_milestones
                SET video_status = $2, video_url = $3
                WHERE id = $1
                """,
                milestone_id,
                status_result["status"],
                status_result.get("video_url"),
            )

    return {"data": {
        "milestone_id": milestone_id,
        "video_url": status_result.get("video_url"),
        "video_status": status_result.get("status", "processing"),
        "provider": provider,
        "video_id": video_id,
    }}


@router.post("/milestones/generate-video")
async def generate_milestone_video(
    body: GenerateVideoRequest,
    user=Depends(get_current_user),
    _=Depends(require_permission("ai.generate_milestones_video")),
):
    """Manually trigger video generation for a milestone."""
    from app.db.session import get_tenant_db

    # Look up member info
    async with get_tenant_db() as db:
        member = await db.fetchrow(
            """
            SELECT id, first_name, last_name, total_visits
            FROM members WHERE id = $1
            """,
            body.member_id,
        )

    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    member_name = f"{member['first_name']} {member.get('last_name', '')}".strip()

    result = await video_svc.generate_milestone_video(
        member_name=member_name,
        milestone_type=body.milestone_type,
        total_visits=member["total_visits"],
        studio_name=body.studio_name,
    )

    # Try to find and update the existing milestone record
    if result.get("video_id"):
        async with get_tenant_db() as db:
            await db.execute(
                """
                UPDATE member_milestones
                SET video_url = $2,
                    video_provider = $3,
                    video_id = $4,
                    video_status = $5
                WHERE member_id = $1
                  AND milestone_type = $6
                """,
                body.member_id,
                result.get("video_url"),
                result.get("provider"),
                result.get("video_id"),
                result.get("status", "processing"),
                body.milestone_type,
            )

    return {"data": result}


# ── Marketing Drafts ────────────────────────────────────────────────────────

@router.post("/drafts", status_code=201)
async def create_draft(
    body: DraftCreateRequest,
    user=Depends(get_current_user),
    _=Depends(require_permission("ai.create_draft")),
):
    """Generate AI content and save as a draft for review."""
    draft = await ai_svc.generate_and_save_draft(
        prompt_context=body.prompt_context,
        draft_type=body.draft_type,
        tone=body.tone,
        studio_name=body.studio_name,
        created_by=user["sub"],
    )
    return {"data": draft}


@router.get("/drafts")
async def list_drafts(
    status: Optional[str] = Query(None),
    user=Depends(get_current_user),
    _=Depends(require_permission("ai.view_draft")),
):
    """List marketing drafts, optionally filtered by status."""
    drafts = await ai_svc.list_drafts(status)
    return {"data": drafts}


@router.get("/drafts/{draft_id}")
async def get_draft(
    draft_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("ai.view_draft")),
):
    """Get a single draft."""
    draft = await ai_svc.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"data": draft}


@router.put("/drafts/{draft_id}")
async def update_draft(
    draft_id: str,
    body: DraftUpdateRequest,
    user=Depends(get_current_user),
    _=Depends(require_permission("ai.edit_draft")),
):
    """Edit a draft's subject or body."""
    draft = await ai_svc.update_draft(draft_id, body.model_dump(exclude_unset=True))
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"data": draft}


@router.post("/drafts/{draft_id}/approve")
async def approve_draft(
    draft_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("ai.approve_draft")),
):
    """Approve a draft (owner only)."""
    draft = await ai_svc.approve_draft(draft_id, user["sub"])
    if not draft:
        raise HTTPException(status_code=400, detail="Draft not found or not in draft status")
    return {"data": draft}


@router.post("/drafts/{draft_id}/reject")
async def reject_draft(
    draft_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("ai.approve_draft")),
):
    """Reject a draft (owner only)."""
    draft = await ai_svc.reject_draft(draft_id, user["sub"])
    if not draft:
        raise HTTPException(status_code=400, detail="Draft not found or not in draft status")
    return {"data": draft}


# ── Waitlist Triage ─────────────────────────────────────────────────────────

class WaitlistModeRequest(BaseModel):
    studio_id: str
    mode: str


@router.get("/waitlist-triage/sessions")
async def get_sessions_with_waitlist(
    _=Depends(require_permission("ai.view_waitlist")),
):
    """List upcoming sessions that have waitlisted bookings."""
    sessions = await waitlist_svc.get_sessions_with_waitlist()
    return {"data": sessions}


@router.get("/waitlist-triage/{session_id}")
async def get_session_waitlist_scores(
    session_id: str,
    _=Depends(require_permission("ai.view_waitlist")),
):
    """Get scored waitlist for a session, ranked by AI priority."""
    scores = await waitlist_svc.get_session_waitlist_with_scores(session_id)
    return {"data": scores}


@router.post("/waitlist-triage/{session_id}/rerank")
async def rerank_waitlist(
    session_id: str,
    _=Depends(require_permission("ai.manage_waitlist")),
):
    """Re-order waitlist positions by AI priority score."""
    result = await waitlist_svc.rerank_waitlist(session_id)
    return {"data": result}


@router.put("/waitlist-triage/mode")
async def set_waitlist_mode(
    body: WaitlistModeRequest,
    _=Depends(require_permission("ai.manage_waitlist")),
):
    """Toggle waitlist mode (fifo or ai_priority) for a studio."""
    try:
        result = await waitlist_svc.set_waitlist_mode(body.studio_id, body.mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": result}


# ── Dynamic Pricing ─────────────────────────────────────────────────────────

class PricingRuleCreate(BaseModel):
    studio_id: str
    name: str
    rule_type: str
    config: dict = {}
    is_active: bool = True


class PricingRuleUpdate(BaseModel):
    name: Optional[str] = None
    rule_type: Optional[str] = None
    config: Optional[dict] = None
    is_active: Optional[bool] = None


@router.get("/pricing/rules/{studio_id}")
async def get_pricing_rules(
    studio_id: str,
    _=Depends(require_permission("ai.view_pricing")),
):
    """List pricing rules for a studio."""
    rules = await pricing_svc.get_pricing_rules(studio_id)
    return {"data": rules}


@router.post("/pricing/rules", status_code=201)
async def create_pricing_rule(
    body: PricingRuleCreate,
    _=Depends(require_permission("ai.create_pricing_rule")),
):
    """Create a new pricing rule."""
    rule = await pricing_svc.create_pricing_rule(body.model_dump())
    return {"data": rule}


@router.put("/pricing/rules/{rule_id}")
async def update_pricing_rule(
    rule_id: str,
    body: PricingRuleUpdate,
    _=Depends(require_permission("ai.edit_pricing_rule")),
):
    """Update a pricing rule."""
    rule = await pricing_svc.update_pricing_rule(
        rule_id, body.model_dump(exclude_unset=True),
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"data": rule}


@router.delete("/pricing/rules/{rule_id}", status_code=204)
async def delete_pricing_rule(
    rule_id: str,
    _=Depends(require_permission("ai.delete_pricing_rule")),
):
    """Delete a pricing rule."""
    deleted = await pricing_svc.delete_pricing_rule(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule not found")


@router.post("/pricing/suggest/{studio_id}")
async def trigger_price_suggestions(
    studio_id: str,
    _=Depends(require_permission("ai.suggest_pricing")),
):
    """Trigger AI price suggestion generation for upcoming sessions."""
    suggestions = await pricing_svc.ai_suggest_prices(studio_id)
    return {"data": suggestions}


@router.get("/pricing/suggestions/{studio_id}")
async def get_price_suggestions(
    studio_id: str,
    status: str = Query("suggested"),
    _=Depends(require_permission("ai.view_pricing")),
):
    """List pending price suggestions for a studio."""
    suggestions = await pricing_svc.get_suggestions(studio_id, status)
    return {"data": suggestions}


@router.post("/pricing/suggestions/{adjustment_id}/approve")
async def approve_price_suggestion(
    adjustment_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("ai.approve_pricing")),
):
    """Approve a price suggestion and apply it to the session."""
    result = await pricing_svc.approve_price_suggestion(
        adjustment_id, user["sub"],
    )
    if not result:
        raise HTTPException(status_code=404, detail="Suggestion not found or already processed")
    return {"data": result}


@router.post("/pricing/suggestions/{adjustment_id}/reject")
async def reject_price_suggestion(
    adjustment_id: str,
    _=Depends(require_permission("ai.approve_pricing")),
):
    """Reject a price suggestion."""
    result = await pricing_svc.reject_price_suggestion(adjustment_id)
    if not result:
        raise HTTPException(status_code=404, detail="Suggestion not found or already processed")
    return {"data": result}


# ── Reviews (Staff Management) ─────────────────────────────────────────────

class ReviewResponseRequest(BaseModel):
    response_text: str


class ReviewFlagRequest(BaseModel):
    reason: str


@router.get("/reviews")
async def list_reviews(
    sentiment: Optional[str] = Query(None),
    min_rating: Optional[int] = Query(None),
    _=Depends(require_permission("ai.view_reviews")),
):
    """List all reviews with optional filters."""
    reviews = await review_svc.list_reviews(
        sentiment=sentiment, min_rating=min_rating,
    )
    return {"data": reviews}


@router.get("/reviews/stats")
async def get_review_stats(
    _=Depends(require_permission("ai.view_reviews")),
):
    """Get aggregate review statistics."""
    stats = await review_svc.get_review_stats()
    return {"data": stats}


@router.get("/reviews/{review_id}")
async def get_review(
    review_id: str,
    _=Depends(require_permission("ai.view_reviews")),
):
    """Get a single review with details."""
    review = await review_svc.get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return {"data": review}


@router.post("/reviews/{review_id}/respond")
async def respond_to_review(
    review_id: str,
    body: ReviewResponseRequest,
    user=Depends(get_current_user),
    _=Depends(require_permission("ai.respond_reviews")),
):
    """Submit a staff response to a review."""
    result = await review_svc.respond_to_review(
        review_id, body.response_text, user["sub"],
    )
    if not result:
        raise HTTPException(status_code=404, detail="Review not found")
    return {"data": result}


@router.post("/reviews/{review_id}/flag")
async def flag_review(
    review_id: str,
    body: ReviewFlagRequest,
    _=Depends(require_permission("ai.moderate_reviews")),
):
    """Flag a review for moderation."""
    result = await review_svc.flag_review(review_id, body.reason)
    if not result:
        raise HTTPException(status_code=404, detail="Review not found")
    return {"data": result}


# ── Smart Schedule Analysis ────────────────────────────────────────────────

@router.post("/schedule-analysis")
async def schedule_analysis(
    _=Depends(require_permission("ai.analyze_schedule")),
):
    """AI-powered schedule analysis using 90-day attendance data.

    Analyzes attendance patterns by day/time, instructor-class pairings,
    and fill rates to suggest schedule optimizations.
    """
    try:
        result = await smart_scheduling_svc.analyze_schedule()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Schedule analysis failed: {str(e)}")
    return {"data": result}


# ── Member Insights ────────────────────────────────────────────────────────

@router.get("/member-insight/{member_id}")
async def member_insight(
    member_id: str,
    _=Depends(require_permission("ai.view_member_insight")),
):
    """AI-powered member profile insight.

    Aggregates booking history, membership, payments, milestones, and
    churn risk into a natural language summary with recommendations.
    """
    result = await member_insights_svc.get_insight(member_id)
    if not result:
        raise HTTPException(status_code=404, detail="Member not found")
    return {"data": result}
