"""AuraFlow — Auth request/response schemas."""
from typing import Optional, List
from pydantic import BaseModel, EmailStr, field_validator

from app.core.config import settings


# ── Token Responses ──────────────────────────────────────────────────────────
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    force_password_reset: bool = False
    # True when an admin (or initial provisioning) wants the user
    # forced into the in-app /change-password screen on next login —
    # distinct from `force_password_reset` which is the email-link
    # path. The frontend MUST route to /change-password when either
    # flag is true; previously only the _reset flag triggered the
    # redirect and Mira Dick's force-change flag was silently ignored.
    force_password_change: bool = False


# ── Auth Requests ────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 10:
            raise ValueError("Password must be at least 10 characters")
        if not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    organization_name: Optional[str] = None
    organization_slug: Optional[str] = None
    invite_token: Optional[str] = None
    # UTM / ad attribution fields
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    gclid: Optional[str] = None
    fbclid: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 10:
            raise ValueError("Password must be at least 10 characters")
        if not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v

    @field_validator("organization_slug")
    @classmethod
    def validate_slug(cls, v):
        if v is not None:
            import re
            if not re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", v):
                raise ValueError("Slug must be lowercase alphanumeric with hyphens")
        return v


# ── User Profile ─────────────────────────────────────────────────────────────
class UserOrganization(BaseModel):
    id: str
    slug: str
    name: str
    role: str
    status: str
    trial_ends_at: Optional[str] = None


class UserStudioRole(BaseModel):
    studio_id: str
    studio_name: str
    studio_slug: str
    role: str
    is_primary: bool = False


class UserProfile(BaseModel):
    id: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    is_platform_admin: bool = False
    email_verified: bool = False
    organizations: List[UserOrganization] = []
    permissions: List[str] = []
    active_org_slug: Optional[str] = None
    active_org_role: Optional[str] = None
    has_video_access: bool = False
    studios: List[UserStudioRole] = []


class MemberRegisterRequest(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    org_slug: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 10:
            raise ValueError("Password must be at least 10 characters")
        if not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v


class UpdateProfileRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None


# ── MFA / TOTP ──────────────────────────────────────────────────────────────
class MFASetupResponse(BaseModel):
    provisioning_uri: str
    secret: str  # returned so frontend can display manual-entry key


class MFAVerifySetupRequest(BaseModel):
    code: str


class MFAVerifySetupResponse(BaseModel):
    backup_codes: List[str]
    message: str = "MFA enabled successfully"


class MFADisableRequest(BaseModel):
    password: str
    code: str


class MFALoginPendingResponse(BaseModel):
    requires_mfa: bool = True
    mfa_token: str


class MFAVerifyRequest(BaseModel):
    mfa_token: str
    code: str
