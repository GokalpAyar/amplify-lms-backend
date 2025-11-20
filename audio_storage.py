from __future__ import annotations

"""
Supabase Storage helper focused on student audio uploads.

Encapsulates bucket provisioning, upload/download/delete helpers, and exposes a
singleton accessor the rest of the app can import without worrying about the
low-level Supabase client.
"""

import logging
import os
import posixpath
from dataclasses import dataclass
from typing import Any, Iterable
from uuid import uuid4

from supabase import Client, create_client

logger = logging.getLogger(__name__)


class AudioStorageError(RuntimeError):
    """Base error for storage failures."""


class AudioStorageConfigError(AudioStorageError):
    """Raised when Supabase Storage is not configured."""


class AudioStorageUploadError(AudioStorageError):
    """Raised when an upload to Supabase Storage fails."""


class AudioStorageDownloadError(AudioStorageError):
    """Raised when downloading audio fails."""


class AudioStorageDeleteError(AudioStorageError):
    """Raised when deleting audio fails."""


@dataclass(slots=True)
class StoredAudio:
    storage_path: str
    public_url: str


class SupabaseAudioStorage:
    """
    Thin wrapper around Supabase Storage for audio uploads.

    Uses the service role key so we can create buckets, upload private objects,
    and serve them via the backend without exposing the Supabase key to clients.
    """

    def __init__(
        self,
        *,
        url: str,
        service_role_key: str,
        bucket: str,
        folder: str = "",
        public_access: bool = False,
    ) -> None:
        if not url:
            raise AudioStorageConfigError(
                "SUPABASE_URL is required to use Supabase Storage.",
            )
        if not service_role_key:
            raise AudioStorageConfigError(
                "SUPABASE_SERVICE_ROLE_KEY is required to use Supabase Storage.",
            )

        self.url = url.rstrip("/")
        self.service_role_key = service_role_key
        self.bucket = bucket
        self.folder = folder.strip("/")
        self.public_access = public_access

        self._client: Client | None = None
        self._bucket_verified = False

    @classmethod
    def from_env(cls) -> SupabaseAudioStorage:
        bucket = os.getenv("SUPABASE_AUDIO_BUCKET", "response-audio")
        folder = os.getenv("SUPABASE_AUDIO_FOLDER", "responses")
        public_flag = os.getenv("SUPABASE_AUDIO_BUCKET_PUBLIC", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        return cls(
            url=os.getenv("SUPABASE_URL", ""),
            service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
            bucket=bucket,
            folder=folder,
            public_access=public_flag,
        )

    # ------------------------------------------------------------------ utils
    def _get_client(self) -> Client:
        if self._client is None:
            logger.info("Initializing Supabase client for audio storage.")
            self._client = create_client(self.url, self.service_role_key)
        return self._client

    def ensure_bucket(self) -> None:
        """Create the target bucket if it doesn't exist yet."""
        if self._bucket_verified:
            return

        client = self._get_client()
        try:
            buckets = client.storage.list_buckets()
        except Exception as exc:  # noqa: BLE001
            raise AudioStorageError("Failed to list Supabase buckets.") from exc

        bucket_names = {bucket.get("name") for bucket in _extract_bucket_rows(buckets)}
        if self.bucket not in bucket_names:
            logger.info("Creating Supabase bucket '%s' (public=%s)", self.bucket, self.public_access)
            try:
                client.storage.create_bucket(
                    self.bucket,
                    {"public": self.public_access},
                )
            except Exception as exc:  # noqa: BLE001
                raise AudioStorageError(
                    f"Unable to create Supabase bucket '{self.bucket}'.",
                ) from exc

        self._bucket_verified = True

    # ---------------------------------------------------------------- storage
    def upload_audio(
        self,
        *,
        data: bytes,
        content_type: str,
        extension: str | None = None,
    ) -> StoredAudio:
        """Upload content to Supabase Storage and return the stored metadata."""
        self.ensure_bucket()

        object_name = self._build_object_name(extension)
        storage = self._get_client().storage.from_(self.bucket)

        try:
            result = storage.upload(
                object_name,
                data,
                {
                    "content-type": content_type,
                    "cache-control": "3600",
                    "upsert": False,
                },
            )
        except Exception as exc:  # noqa: BLE001
            raise AudioStorageUploadError("Supabase upload failed.") from exc

        _raise_if_error(result, AudioStorageUploadError)

        public_url = self._build_public_url(object_name)

        return StoredAudio(storage_path=object_name, public_url=public_url)

    def download_audio(self, storage_path: str) -> bytes:
        """Download audio bytes from Supabase Storage."""
        self.ensure_bucket()
        storage = self._get_client().storage.from_(self.bucket)

        try:
            result = storage.download(storage_path)
        except Exception as exc:  # noqa: BLE001
            raise AudioStorageDownloadError("Failed to download audio file.") from exc

        if isinstance(result, dict):
            _raise_if_error(result, AudioStorageDownloadError)
            data = result.get("data")
            if isinstance(data, (bytes, bytearray)):
                return bytes(data)
            raise AudioStorageDownloadError("Unexpected response shape when downloading audio.")

        if not isinstance(result, (bytes, bytearray)):
            raise AudioStorageDownloadError("Unexpected response type from Supabase download.")

        return bytes(result)

    def delete_audio(self, storage_path: str) -> None:
        """Delete an audio object."""
        if not storage_path:
            return

        self.ensure_bucket()
        storage = self._get_client().storage.from_(self.bucket)

        try:
            result = storage.remove([storage_path])
        except Exception as exc:  # noqa: BLE001
            raise AudioStorageDeleteError("Failed to delete audio file.") from exc

        _raise_if_error(result, AudioStorageDeleteError)

    # ---------------------------------------------------------------- helpers
    def _build_object_name(self, extension: str | None) -> str:
        filename = uuid4().hex
        if extension:
            extension = extension.lower()
            if not extension.startswith("."):
                extension = f".{extension}"
            filename = f"{filename}{extension}"

        return posixpath.join(self.folder, filename) if self.folder else filename

    def _build_public_url(self, storage_path: str) -> str:
        """
        Use Supabase's helper to build a public URL. For private buckets this
        still produces an authenticated endpoint which the backend can access.
        """
        storage = self._get_client().storage.from_(self.bucket)
        # The SDK always returns {"data": {"publicUrl": "<url>"}, "error": None}
        response = storage.get_public_url(storage_path)
        if isinstance(response, dict):
            error = response.get("error")
            if error:
                raise AudioStorageUploadError(f"Failed to build public URL: {error}")
            data = response.get("data") or {}
            url = data.get("publicUrl")
            if url:
                return url

        # Fallback to predictable REST path.
        return f"{self.url}/storage/v1/object/{self.bucket}/{storage_path}"


def _extract_bucket_rows(payload: Any) -> Iterable[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return data
    return []


def _raise_if_error(response: Any, error_cls: type[AudioStorageError]) -> None:
    if response is None:
        return

    error = getattr(response, "error", None)
    if not error and isinstance(response, dict):
        error = response.get("error")

    if error:
        raise error_cls(str(error))


_CACHED_STORAGE: SupabaseAudioStorage | None = None


def get_audio_storage() -> SupabaseAudioStorage:
    global _CACHED_STORAGE
    if _CACHED_STORAGE is None:
        _CACHED_STORAGE = SupabaseAudioStorage.from_env()
    return _CACHED_STORAGE


def try_get_audio_storage() -> SupabaseAudioStorage | None:
    try:
        return get_audio_storage()
    except AudioStorageConfigError:
        logger.warning("Supabase audio storage is not configured.")
        return None

