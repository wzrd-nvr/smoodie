"""Object storage, behind a protocol.

Uploads go browser -> GCS directly via a signed URL, so image bytes never pass
through the API. The protocol exists so the routers can be tested against an
in-memory fake rather than a live bucket or an emulator subprocess; the GCS
implementation holds no logic beyond translating calls.
"""

import datetime as dt
from dataclasses import dataclass
from typing import Any, Protocol

# Deliberately narrow. Every entry is something browsers render natively and
# Cloud CDN can serve; SVG is excluded on purpose because it can carry script.
ALLOWED_IMAGE_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/avif": "avif",
    "image/gif": "gif",
}

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


class StorageError(Exception):
    """Raised when the object store cannot satisfy a request."""


@dataclass(frozen=True)
class StoredObject:
    name: str
    size: int
    content_type: str


class ObjectStore(Protocol):
    def signed_upload_url(self, name: str, content_type: str, expires_in: dt.timedelta) -> str: ...

    def stat(self, name: str) -> StoredObject | None: ...

    def delete(self, name: str) -> None: ...

    def public_url(self, name: str) -> str: ...


class GcsObjectStore:  # pragma: no cover - thin adapter, exercised via FakeObjectStore
    """Google Cloud Storage.

    Signing is the subtle part: on Cloud Run the runtime account has a token and
    no private key, so signing must go through the IAM SignBlob API. Passing
    service_account_email plus an access token makes google-cloud-storage take
    that path instead of looking for a key it will never find.
    """

    def __init__(self, bucket_name: str) -> None:
        self._bucket_name = bucket_name
        self._client: Any = None  # built lazily so imports stay cheap in tests

    def _bucket(self) -> Any:
        if self._client is None:
            from google.cloud import storage

            self._client = storage.Client()
        return self._client.bucket(self._bucket_name)

    def _signing_credentials(self) -> tuple[str, str]:
        import google.auth
        import google.auth.transport.requests

        credentials, _ = google.auth.default()
        # google-auth ships no type information for this path.
        creds: Any = credentials
        creds.refresh(google.auth.transport.requests.Request())
        email = getattr(creds, "service_account_email", None)
        token = getattr(creds, "token", None)
        if not email or not token:
            raise StorageError("no service account available to sign upload URLs")
        return str(email), str(token)

    def signed_upload_url(self, name: str, content_type: str, expires_in: dt.timedelta) -> str:
        email, token = self._signing_credentials()
        try:
            url = (
                self._bucket()
                .blob(name)
                .generate_signed_url(
                    version="v4",
                    expiration=expires_in,
                    method="PUT",
                    content_type=content_type,
                    service_account_email=email,
                    access_token=token,
                )
            )
        except Exception as exc:
            raise StorageError(str(exc)) from exc
        return str(url)

    def stat(self, name: str) -> StoredObject | None:
        blob = self._bucket().get_blob(name)
        if blob is None:
            return None
        return StoredObject(
            name=name,
            size=blob.size or 0,
            content_type=blob.content_type or "",
        )

    def delete(self, name: str) -> None:
        blob = self._bucket().get_blob(name)
        if blob is not None:
            blob.delete()

    def public_url(self, name: str) -> str:
        return f"https://storage.googleapis.com/{self._bucket_name}/{name}"
