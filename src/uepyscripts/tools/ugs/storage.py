"""
Key/value storage underneath the Publish store.

The Publish store only ever needs these seven operations, so anything that
provides them can sit behind it: S3 in production, a logging pass-through for
dry runs, and an in-memory dictionary in the tests.
"""

import builtins
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from gamedevtools.s3 import S3Client

from uepyscripts import logger


@dataclass(frozen=True)
class StoredObject:
    key: str
    last_modified: datetime


class Storage(Protocol):
    def read(self, key: str) -> bytes | None:
        """The object's content, or None when the key doesn't exist."""
        ...

    def write(self, key: str, data: bytes) -> None: ...

    def upload_file(self, key: str, path: Path) -> None:
        """Streams a local file to `key` without loading it in memory."""
        ...

    def download_file(self, key: str, path: Path) -> None:
        """Streams `key` to a local file. Raises when the key doesn't exist."""
        ...

    def exists(self, key: str) -> bool: ...

    def list(self, prefix: str) -> builtins.list[StoredObject]: ...

    def delete(self, keys: builtins.list[str]) -> None:
        """Deletes every key. Missing keys are ignored."""
        ...


class S3Storage:
    def __init__(self, client: S3Client, bucket_name: str) -> None:
        self._client = client
        self._bucket = bucket_name

    def read(self, key: str) -> bytes | None:
        try:
            return self._client.download_bytes(self._bucket, key)
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
                return None
            raise

    def write(self, key: str, data: bytes) -> None:
        self._client.upload_bytes(self._bucket, key, data)

    def upload_file(self, key: str, path: Path) -> None:
        self._client.upload_file(self._bucket, key, path)

    def download_file(self, key: str, path: Path) -> None:
        self._client.s3.download_file(self._bucket, key, str(path))

    def exists(self, key: str) -> bool:
        return self._client.object_exists(self._bucket, key)

    def list(self, prefix: str) -> builtins.list[StoredObject]:
        paginator = self._client.s3.get_paginator("list_objects_v2")
        objects: builtins.list[StoredObject] = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                objects.append(StoredObject(obj["Key"], obj["LastModified"]))
        return objects

    def delete(self, keys: builtins.list[str]) -> None:
        self._client.delete_keys(self._bucket, keys)


class DryRunStorage:
    """Reads from the wrapped storage, but only logs the writes and deletes it
    would have made."""

    def __init__(self, inner: Storage) -> None:
        self._inner = inner

    def read(self, key: str) -> bytes | None:
        return self._inner.read(key)

    def write(self, key: str, data: bytes) -> None:
        logger.info(f"[dry-run] Would write {key} ({len(data)} bytes)")

    def upload_file(self, key: str, path: Path) -> None:
        logger.info(f"[dry-run] Would upload {path} to {key}")

    def download_file(self, key: str, path: Path) -> None:
        self._inner.download_file(key, path)

    def exists(self, key: str) -> bool:
        return self._inner.exists(key)

    def list(self, prefix: str) -> builtins.list[StoredObject]:
        return self._inner.list(prefix)

    def delete(self, keys: builtins.list[str]) -> None:
        for key in keys:
            logger.info(f"[dry-run] Would delete {key}")
