"""T-204 (SPEC-204 AC5): real per-org artifact storage ACLs via MinIO — declared in
`docker-compose.yml` since before this ticket but, per T-203's own disclosed note,
unused until now. Rather than a hand-rolled prefix check, this mints a short-lived
credential through MinIO's real STS `AssumeRole` API with an inline session policy
restricting S3 actions to `<bucket>/orgs/<org_id>/*` — the denial an org-A credential
hits reading org-B's prefix is MinIO's own policy engine, not our own code's opinion.

Dev-mode only: MinIO here has no real production topology (erasure coding, TLS,
external IAM) — same standing as this repo's Vault/Postgres dev-mode notes.
"""

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3

ARTIFACT_BUCKET = "agent-factory-artifacts"
_CREDENTIAL_TTL_S = 3600


@dataclass(frozen=True)
class ArtifactStorageConfig:
    endpoint_url: str
    access_key: str
    secret_key: str
    bucket: str = ARTIFACT_BUCKET


@dataclass(frozen=True)
class ScopedCredential:
    access_key: str
    secret_key: str
    session_token: str
    bucket: str
    prefix: str
    expires_at: datetime


def get_artifact_storage_config() -> ArtifactStorageConfig:
    """FastAPI dependency — reads S3_* env vars lazily per-request, matching
    vault_client.get_vault_client's lazy-read pattern."""
    return ArtifactStorageConfig(
        endpoint_url=os.environ.get("S3_ENDPOINT_URL", "http://localhost:9000"),
        access_key=os.environ.get("S3_ACCESS_KEY", "agent_factory"),
        secret_key=os.environ.get("S3_SECRET_KEY", "change-me-too"),
    )


def _s3_client(config: ArtifactStorageConfig) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=config.endpoint_url,
        aws_access_key_id=config.access_key,
        aws_secret_access_key=config.secret_key,
        region_name="us-east-1",
    )


def _sts_client(config: ArtifactStorageConfig) -> Any:
    return boto3.client(
        "sts",
        endpoint_url=config.endpoint_url,
        aws_access_key_id=config.access_key,
        aws_secret_access_key=config.secret_key,
        region_name="us-east-1",
    )


def ensure_bucket_exists(config: ArtifactStorageConfig) -> None:
    s3 = _s3_client(config)
    existing = {b["Name"] for b in s3.list_buckets().get("Buckets", [])}
    if config.bucket not in existing:
        s3.create_bucket(Bucket=config.bucket)


def _org_prefix(org_id: str) -> str:
    return f"orgs/{org_id}/"


def _scoped_policy(bucket: str, prefix: str) -> str:
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:DeleteObject"],
                    "Resource": [
                        f"arn:aws:s3:::{bucket}/{prefix}*",
                        f"arn:aws:s3:::{bucket}",
                    ],
                }
            ],
        }
    )


def mint_scoped_credential(config: ArtifactStorageConfig, *, org_id: str) -> ScopedCredential:
    """A short-lived, org-prefix-scoped MinIO credential — never persisted anywhere,
    same "mint on demand, hold in memory only" doctrine as BYOK keys / GitHub install
    tokens. MinIO's STS AssumeRole enforces this session policy can only ever narrow
    (never widen) the underlying root credential's own permissions."""
    ensure_bucket_exists(config)
    prefix = _org_prefix(org_id)
    sts = _sts_client(config)
    response = sts.assume_role(
        RoleArn="arn:aws:iam::minio:role/artifact-access",
        RoleSessionName=f"org-{org_id}",
        Policy=_scoped_policy(config.bucket, prefix),
        DurationSeconds=_CREDENTIAL_TTL_S,
    )
    credentials = response["Credentials"]
    expires_at = credentials.get("Expiration") or datetime.now(UTC) + timedelta(
        seconds=_CREDENTIAL_TTL_S
    )
    return ScopedCredential(
        access_key=credentials["AccessKeyId"],
        secret_key=credentials["SecretAccessKey"],
        session_token=credentials["SessionToken"],
        bucket=config.bucket,
        prefix=prefix,
        expires_at=expires_at,
    )
