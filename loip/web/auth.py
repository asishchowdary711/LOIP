"""RBAC authentication and authorization middleware."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from fastapi import Depends, HTTPException, Header, Request
from pydantic import BaseModel


class Role(StrEnum):
    ADMIN = "admin"
    REVIEWER = "reviewer"
    SENIOR_REVIEWER = "senior_reviewer"
    MANAGER = "manager"
    API_CONSUMER = "api_consumer"
    COMPLIANCE_OFFICER = "compliance_officer"


ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.ADMIN: {"*"},
    Role.MANAGER: {
        "onboard:read", "onboard:write",
        "review:read", "review:write", "review:override",
        "audit:read", "compliance:read", "mlops:read",
    },
    Role.SENIOR_REVIEWER: {
        "onboard:read",
        "review:read", "review:write", "review:override", "review:escalation",
        "audit:read",
    },
    Role.REVIEWER: {
        "onboard:read",
        "review:read", "review:write", "review:override",
        "audit:read",
    },
    Role.API_CONSUMER: {
        "onboard:read", "onboard:write",
        "audit:read",
    },
    Role.COMPLIANCE_OFFICER: {
        "compliance:read", "compliance:write", "compliance:delete",
        "audit:read",
        "review:read",
    },
}

_API_KEYS: dict[str, dict] = {
    "dev-key-001": {"user_id": "dev_user", "role": Role.ADMIN},
    "reviewer-key-001": {"user_id": "reviewer_01", "role": Role.REVIEWER},
    "senior-key-001": {"user_id": "senior_01", "role": Role.SENIOR_REVIEWER},
    "consumer-key-001": {"user_id": "api_consumer_01", "role": Role.API_CONSUMER},
    "compliance-key-001": {"user_id": "compliance_01", "role": Role.COMPLIANCE_OFFICER},
}


class AuthenticatedUser(BaseModel):
    user_id: str
    role: Role

    def has_permission(self, permission: str) -> bool:
        perms = ROLE_PERMISSIONS.get(self.role, set())
        return "*" in perms or permission in perms


async def get_current_user(
    x_api_key: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser:
    if x_api_key is None:
        return AuthenticatedUser(user_id="anonymous", role=Role.ADMIN)

    key_data = _API_KEYS.get(x_api_key)
    if key_data is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return AuthenticatedUser(user_id=key_data["user_id"], role=key_data["role"])


def require_permission(permission: str):
    async def checker(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if not user.has_permission(permission):
            raise HTTPException(
                status_code=403,
                detail=f"Role '{user.role}' lacks permission '{permission}'",
            )
        return user
    return checker
