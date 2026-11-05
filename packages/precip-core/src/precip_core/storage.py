"""Object storage behind one small interface.

The pipeline writes and the API reads through this. ``LocalStorage`` is for development and
tests. ``S3Storage`` speaks the S3 API, so it works with Cloudflare R2 (set ``endpoint_url``).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qs, urlparse

CACHE_IMMUTABLE = "public, max-age=31536000, immutable"
CACHE_MANIFEST = "public, max-age=60"


class NotFound(KeyError):
    """The requested key does not exist."""


class Storage(Protocol):
    def put(self, key: str, data: bytes, *, content_type: str, cache_control: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def list(self, prefix: str) -> list[str]: ...
    def delete_prefix(self, prefix: str) -> int: ...


class LocalStorage:
    def __init__(self, root: str | os.PathLike):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root != p and self.root not in p.parents:
            raise ValueError(f"key escapes storage root: {key!r}")
        return p

    def put(self, key: str, data: bytes, *, content_type: str, cache_control: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, p)  # atomic: readers never see a half-written file
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as e:
            raise NotFound(key) from e

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def list(self, prefix: str) -> list[str]:
        base = self._path(prefix) if prefix else self.root
        if not base.exists():
            return []
        files = [base] if base.is_file() else [p for p in base.rglob("*") if p.is_file()]
        return sorted(
            str(p.relative_to(self.root)) for p in files if not p.name.startswith(".tmp-")
        )

    def delete_prefix(self, prefix: str) -> int:
        keys = self.list(prefix)
        for k in keys:
            self._path(k).unlink()
        base = self._path(prefix)
        if base.is_dir():  # remove now-empty directories, deepest first
            for d in sorted((p for p in base.rglob("*") if p.is_dir()), reverse=True):
                d.rmdir()
            base.rmdir()
        return len(keys)


class S3Storage:
    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        *,
        endpoint_url: str | None = None,
        region: str = "auto",
        client=None,
    ):
        if client is None:
            import boto3  # optional dependency: precip-core[s3]

            client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region)
        self._c = client
        self.bucket = bucket
        self.prefix = prefix.strip("/")

    def _k(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def put(self, key: str, data: bytes, *, content_type: str, cache_control: str) -> None:
        self._c.put_object(
            Bucket=self.bucket,
            Key=self._k(key),
            Body=data,
            ContentType=content_type,
            CacheControl=cache_control,
        )

    def get(self, key: str) -> bytes:
        try:
            return self._c.get_object(Bucket=self.bucket, Key=self._k(key))["Body"].read()
        except self._c.exceptions.NoSuchKey as e:
            raise NotFound(key) from e

    def exists(self, key: str) -> bool:
        try:
            self._c.head_object(Bucket=self.bucket, Key=self._k(key))
            return True
        except self._c.exceptions.ClientError:
            return False

    def list(self, prefix: str) -> list[str]:
        full = self._k(prefix)
        strip = len(self.prefix) + 1 if self.prefix else 0
        keys: list[str] = []
        for page in self._c.get_paginator("list_objects_v2").paginate(
            Bucket=self.bucket, Prefix=full
        ):
            keys += [o["Key"][strip:] for o in page.get("Contents", [])]
        return sorted(keys)

    def delete_prefix(self, prefix: str) -> int:
        keys = self.list(prefix)
        for i in range(0, len(keys), 1000):
            batch = [{"Key": self._k(k)} for k in keys[i : i + 1000]]
            self._c.delete_objects(Bucket=self.bucket, Delete={"Objects": batch})
        return len(keys)


def storage_from_url(url: str) -> Storage:
    """``/path`` or ``file:///path`` for local; ``s3://bucket/prefix?endpoint_url=..`` for S3/R2."""
    if url.startswith("s3://"):
        u = urlparse(url)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        return S3Storage(
            u.netloc,
            u.path.lstrip("/"),
            endpoint_url=q.get("endpoint_url"),
            region=q.get("region", "auto"),
        )
    if url.startswith("file://"):
        url = urlparse(url).path
    return LocalStorage(url)
