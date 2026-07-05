"""AuraFlow — Staff management request/response schemas."""
from typing import Optional, List, Dict
from datetime import date

from pydantic import BaseModel, field_validator


class StaffMemberResponse(BaseModel):
    user_id: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str
    title: Optional[str] = None
    department: Optional[str] = None
    hire_date: Optional[date] = None
    is_active: bool
    permissions: List[str] = []


class UpdateStaffProfileRequest(BaseModel):
    title: Optional[str] = None
    department: Optional[str] = None
    hire_date: Optional[date] = None
    notes: Optional[str] = None


class UpdateRoleRequest(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v not in ("admin", "instructor", "front_desk"):
            raise ValueError(
                "Invalid role. Must be admin, instructor, or front_desk. "
                "Cannot assign owner or member roles via this endpoint."
            )
        return v


class UpdatePermissionsRequest(BaseModel):
    permissions: Dict[str, bool]

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, v):
        from app.services.permissions import ALL_PERMISSIONS
        invalid = [k for k in v if k not in ALL_PERMISSIONS]
        if invalid:
            raise ValueError(f"Invalid permission keys: {', '.join(invalid)}")
        return v


class UserPermissionsResponse(BaseModel):
    role: str
    permissions: List[str]
