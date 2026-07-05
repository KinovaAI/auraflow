"""
AuraFlow — Security Utility Tests
"""
import os
os.environ.setdefault("DATABASE_URL", "postgresql://auraflow:1d50a904518d74c94260bc57c66a7ca5dffc58359c4b4b6653605241bf043fed@localhost:5432/auraflow")
os.environ.setdefault("APP_SECRET", "test-secret-not-for-production-use-only")

import pytest
from app.core.security import hash_password, verify_password, create_access_token, decode_token


class TestPasswordHashing:
    def test_hash_and_verify(self):
        password = "SecurePassword123!"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed) is True

    def test_wrong_password(self):
        hashed = hash_password("CorrectPassword")
        assert verify_password("WrongPassword", hashed) is False

    def test_different_hashes_same_password(self):
        p = "SamePassword"
        h1 = hash_password(p)
        h2 = hash_password(p)
        assert h1 != h2  # bcrypt uses random salt
        assert verify_password(p, h1) is True
        assert verify_password(p, h2) is True


class TestJWT:
    def test_create_and_decode(self):
        data = {"sub": "user-123", "email": "test@example.com"}
        token = create_access_token(data)
        decoded = decode_token(token)
        assert decoded["sub"] == "user-123"
        assert decoded["email"] == "test@example.com"
        assert "exp" in decoded

    def test_token_with_org_slug(self):
        data = {"sub": "user-123", "org_slug": "test-studio", "org_role": "owner"}
        token = create_access_token(data)
        decoded = decode_token(token)
        assert decoded["org_slug"] == "test-studio"
        assert decoded["org_role"] == "owner"

    def test_invalid_token(self):
        from app.core.security import JWTError
        with pytest.raises(JWTError):
            decode_token("not.a.valid.token")


class TestRBACHierarchy:
    def test_role_levels(self):
        from app.api.v1.dependencies.rbac import _role_level, ROLE_HIERARCHY
        assert _role_level("owner") > _role_level("admin")
        assert _role_level("admin") > _role_level("instructor")
        assert _role_level("instructor") > _role_level("front_desk")
        assert _role_level("front_desk") > _role_level("member")
        assert _role_level("unknown_role") == -1
