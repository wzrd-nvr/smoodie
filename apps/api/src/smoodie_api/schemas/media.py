import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from smoodie_api.services.storage import ALLOWED_IMAGE_TYPES, MAX_UPLOAD_BYTES


class UploadRequest(BaseModel):
    content_type: str = Field(description="MIME type of the image about to be uploaded")
    # Advisory: the real size is measured from the stored object at completion,
    # but rejecting here saves the user a doomed upload.
    size_bytes: int | None = Field(default=None, gt=0)

    @field_validator("content_type")
    @classmethod
    def _supported_type(cls, value: str) -> str:
        normalized = value.split(";")[0].strip().lower()
        if normalized not in ALLOWED_IMAGE_TYPES:
            supported = ", ".join(sorted(ALLOWED_IMAGE_TYPES))
            raise ValueError(f"That file type isn't supported. Try one of: {supported}.")
        return normalized

    @field_validator("size_bytes")
    @classmethod
    def _within_limit(cls, value: int | None) -> int | None:
        if value is not None and value > MAX_UPLOAD_BYTES:
            mb = MAX_UPLOAD_BYTES // (1024 * 1024)
            raise ValueError(f"Images need to be under {mb} MB.")
        return value


class UploadTicket(BaseModel):
    """Everything the browser needs to PUT the file itself."""

    media_id: uuid.UUID
    upload_url: str
    content_type: str
    max_bytes: int = MAX_UPLOAD_BYTES


class MediaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    content_type: str
    bytes: int | None
    url: str | None = None
    created_at: datetime
