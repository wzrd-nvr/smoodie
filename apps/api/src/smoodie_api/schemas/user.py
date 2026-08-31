import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from smoodie_api.services.usernames import InvalidUsername, validate_username


class SessionRequest(BaseModel):
    id_token: str = Field(min_length=1, description="Firebase ID token from the client")


class PublicProfile(BaseModel):
    """A profile as anyone can see it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str
    bio: str | None
    avatar_media_id: uuid.UUID | None
    created_at: datetime


class SessionResponse(BaseModel):
    user: PublicProfile
    created: bool = Field(description="True when this sign-in provisioned the account")


class ProfileUpdate(BaseModel):
    """Every field optional: PATCH semantics, only what's present is changed."""

    username: str | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    bio: str | None = Field(default=None, max_length=500)
    avatar_media_id: uuid.UUID | None = None

    @field_validator("username")
    @classmethod
    def _check_username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return validate_username(value)
        except InvalidUsername as exc:
            # Surfaces as a 422 with this exact message against the username
            # field, so the settings form can render it inline.
            raise ValueError(str(exc)) from exc

    @field_validator("display_name")
    @classmethod
    def _strip_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Display name can't be blank.")
        return cleaned
