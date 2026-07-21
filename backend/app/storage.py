from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import boto3

from .config import get_settings


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    sha256: str


class ObjectStorage:
    def __init__(self) -> None:
        self.settings = get_settings()
        if self.settings.storage_backend == "local":
            self.settings.local_storage_root.mkdir(parents=True, exist_ok=True)
            self.client = None
        elif self.settings.storage_backend == "s3":
            if not self.settings.s3_bucket:
                raise RuntimeError("S3_BUCKET is required when STORAGE_BACKEND=s3")
            self.client = boto3.client(
                "s3",
                endpoint_url=self.settings.s3_endpoint_url,
                region_name=self.settings.s3_region,
                aws_access_key_id=self.settings.s3_access_key_id,
                aws_secret_access_key=self.settings.s3_secret_access_key,
            )
        else:
            raise RuntimeError(f"Unsupported storage backend: {self.settings.storage_backend}")

    def _local_path(self, key: str) -> Path:
        target = (self.settings.local_storage_root / key).resolve()
        root = self.settings.local_storage_root
        if target != root and root not in target.parents:
            raise ValueError("Unsafe object-storage key")
        return target

    def put(self, *, key: str, data: bytes, content_type: str, metadata: dict[str, str] | None = None) -> StoredObject:
        digest = hashlib.sha256(data).hexdigest()
        if self.settings.storage_backend == "local":
            target = self._local_path(key)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.with_suffix(target.suffix + ".meta").write_text(
                f"content_type={content_type}\nsha256={digest}\n", encoding="utf-8"
            )
        else:
            encryption = {"ServerSideEncryption": "AES256"}
            if self.settings.s3_kms_key_id:
                encryption = {
                    "ServerSideEncryption": "aws:kms",
                    "SSEKMSKeyId": self.settings.s3_kms_key_id,
                    "BucketKeyEnabled": True,
                }
            self.client.put_object(
                Bucket=self.settings.s3_bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                Metadata={**(metadata or {}), "sha256": digest},
                **encryption,
            )
        return StoredObject(key=key, size=len(data), sha256=digest)

    def get(self, key: str) -> bytes:
        if self.settings.storage_backend == "local":
            return self._local_path(key).read_bytes()
        response = self.client.get_object(Bucket=self.settings.s3_bucket, Key=key)
        return response["Body"].read()

    def delete(self, key: str) -> None:
        if self.settings.storage_backend == "local":
            path = self._local_path(key)
            if path.exists():
                path.unlink()
            return
        self.client.delete_object(Bucket=self.settings.s3_bucket, Key=key)


storage = ObjectStorage()
