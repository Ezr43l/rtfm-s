from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    actor: str = Field(min_length=1, max_length=200)
    credential: str = Field(min_length=1, max_length=1000)
    otp: str | None = Field(default=None, max_length=64)


class ProfileUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=64)
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    current_password: str | None = Field(default=None, max_length=256)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)
    otp: str | None = Field(default=None, max_length=64)


class TwoFactorSetup(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)


class TwoFactorEnable(BaseModel):
    code: str = Field(min_length=1, max_length=64)


class TwoFactorDisable(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=1, max_length=64)


class RecoveryCodesRegenerate(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=1, max_length=64)


class AdminConfirmation(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    otp: str | None = Field(default=None, max_length=64)


class UserCreate(AdminConfirmation):
    username: str = Field(min_length=3, max_length=64)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)
    role: str = Field(default="reader", max_length=40)


class UserAccessUpdate(AdminConfirmation):
    username: str | None = Field(default=None, min_length=3, max_length=64)
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = Field(default=None, max_length=40)
    status: str | None = Field(default=None, max_length=40)


class UserPasswordReset(AdminConfirmation):
    new_password: str = Field(min_length=1, max_length=256)


class ApiClientCreate(AdminConfirmation):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    role: str = Field(default="reader", max_length=40)
    expires_at: datetime | None = None


class ApiClientUpdate(AdminConfirmation):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    role: str | None = Field(default=None, max_length=40)
    status: str | None = Field(default=None, max_length=40)
    expires_at: datetime | None = None


class ApiClientTokenAction(AdminConfirmation):
    pass


class LibraryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=1000)
    icon: str = Field(default="library", max_length=40)
    color: str = Field(default="indigo", max_length=40)


class LibraryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    icon: str | None = Field(default=None, max_length=40)
    color: str | None = Field(default=None, max_length=40)
    position: int | None = Field(default=None, ge=0)
    category_sort: Literal["manual", "alphabetical"] | None = None


class LibraryPermissionGrant(BaseModel):
    subject_type: Literal["user", "api_client"]
    subject_id: str = Field(min_length=1, max_length=80)
    role: Literal["reader", "operator", "full_control"]


class LibraryPermissionsUpdate(AdminConfirmation):
    mode: Literal["open", "restricted"]
    grants: list[LibraryPermissionGrant] = Field(default_factory=list, max_length=500)


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    parent_id: str | None = None
    description: str = Field(default="", max_length=1000)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    parent_id: str | None = None
    position: int | None = Field(default=None, ge=0)


class CategoryOrderUpdate(BaseModel):
    parent_id: str | None = None
    category_ids: list[str] = Field(min_length=1, max_length=1000)


class DocumentCreate(BaseModel):
    library_id: str
    category_id: str | None = None
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(default="", max_length=1200)
    content: str = ""
    tags: list[str] = Field(default_factory=list, max_length=100)


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    summary: str | None = Field(default=None, max_length=1200)
    content: str | None = None
    tags: list[str] | None = Field(default=None, max_length=100)


class DocumentImageCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=100)
    data: str = Field(min_length=1, max_length=140_000_000)


class DocumentMove(BaseModel):
    library_id: str
    category_id: str | None = None
    position: int | None = Field(default=None, ge=0)
