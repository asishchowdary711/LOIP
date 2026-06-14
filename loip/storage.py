"""MinIO-backed document storage.

Stores onboarding documents (one bucket per document type, per the build
plan) and returns a self-describing ``document_id`` of the form
``"<bucket>/<uuid>.<ext>"``. That id is what gets written to
``SourceLocation.document_id`` on every document-derived evidence field, so
any figure can be traced back to the exact stored object.
"""

from __future__ import annotations

import io
import uuid

from minio import Minio

from loip.config import Settings, get_settings

# document_type (as classified by the pipeline / used in evidence) -> bucket
BUCKET_BY_DOC_TYPE: dict[str, str] = {
    "pan": "pan-cards",
    "aadhaar": "aadhaar-cards",
    "salary_slip": "salary-slips",
    "bank_statement": "bank-statements",
    "form16": "form16",
    "itr": "itr",
    "gst_return": "gst-returns",
    "offer_letter": "offer-letters",
}

EVIDENCE_BUCKET = "evidence"
ALL_BUCKETS = [*BUCKET_BY_DOC_TYPE.values(), EVIDENCE_BUCKET, "models", "annotations"]


class DocumentStore:
    """Thin wrapper over the MinIO client for document put/get/stat."""

    def __init__(self, settings: Settings | None = None, *, ensure_buckets: bool = True):
        self.settings = settings or get_settings()
        self.client = Minio(
            self.settings.minio_endpoint,
            access_key=self.settings.minio_access_key,
            secret_key=self.settings.minio_secret_key,
            secure=self.settings.minio_use_ssl,
        )
        if ensure_buckets:
            self.ensure_buckets()

    def ensure_buckets(self) -> None:
        for bucket in ALL_BUCKETS:
            if not self.client.bucket_exists(bucket):
                self.client.make_bucket(bucket)

    def bucket_for(self, document_type: str) -> str:
        return BUCKET_BY_DOC_TYPE.get(document_type, EVIDENCE_BUCKET)

    def store(self, document_type: str, data: bytes, *, ext: str = "png") -> str:
        """Upload ``data`` to the bucket for ``document_type``; return its id."""
        bucket = self.bucket_for(document_type)
        object_name = f"{uuid.uuid4().hex}.{ext}"
        self.client.put_object(
            bucket,
            object_name,
            io.BytesIO(data),
            length=len(data),
            content_type=_content_type(ext),
        )
        return f"{bucket}/{object_name}"

    def exists(self, document_id: str) -> bool:
        """True if ``document_id`` (``bucket/object``) resolves to a real object."""
        bucket, _, object_name = document_id.partition("/")
        if not bucket or not object_name:
            return False
        try:
            self.client.stat_object(bucket, object_name)
            return True
        except Exception:
            return False

    def get(self, document_id: str) -> bytes:
        bucket, _, object_name = document_id.partition("/")
        response = self.client.get_object(bucket, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()


def _content_type(ext: str) -> str:
    return {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "pdf": "application/pdf",
    }.get(ext.lower(), "application/octet-stream")
