"""T-204 (SPEC-204 AC5): "Artifacts of org A are unreadable with org B credentials
(storage ACL test)." A real, throwaway MinIO container (declared in docker-compose.yml
since before this ticket, disclosed unused until now) — the denial proved here is
MinIO's own STS/policy engine, not a hand-rolled check."""

import time
from collections.abc import Iterator

import boto3
import botocore.exceptions
import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

from api.artifact_storage import ArtifactStorageConfig, mint_scoped_credential

MINIO_ROOT_USER = "agent_factory_test"
MINIO_ROOT_PASSWORD = "change-me-too-test"


@pytest.fixture(scope="module")
def minio_config() -> Iterator[ArtifactStorageConfig]:
    container = (
        DockerContainer("minio/minio:latest")
        .with_env("MINIO_ROOT_USER", MINIO_ROOT_USER)
        .with_env("MINIO_ROOT_PASSWORD", MINIO_ROOT_PASSWORD)
        .with_command("server /data")
        .with_exposed_ports(9000)
    )
    with container:
        wait_for_logs(container, r"API:", timeout=30)
        endpoint = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(9000)}"
        config = ArtifactStorageConfig(
            endpoint_url=endpoint, access_key=MINIO_ROOT_USER, secret_key=MINIO_ROOT_PASSWORD
        )
        _wait_for_minio_ready(config)
        yield config


def _wait_for_minio_ready(config: ArtifactStorageConfig, timeout_s: float = 20.0) -> None:
    s3 = boto3.client(
        "s3",
        endpoint_url=config.endpoint_url,
        aws_access_key_id=config.access_key,
        aws_secret_access_key=config.secret_key,
        region_name="us-east-1",
    )
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            s3.list_buckets()
            return
        except Exception as exc:  # noqa: BLE001 - polling for readiness, retry any error
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"MinIO never became ready: {last_error}")


def test_mint_scoped_credential_can_write_and_read_its_own_prefix(
    minio_config: ArtifactStorageConfig,
) -> None:
    credential = mint_scoped_credential(minio_config, org_id="org-artifact-a")
    s3 = boto3.client(
        "s3",
        endpoint_url=minio_config.endpoint_url,
        aws_access_key_id=credential.access_key,
        aws_secret_access_key=credential.secret_key,
        aws_session_token=credential.session_token,
        region_name="us-east-1",
    )

    key = f"{credential.prefix}result.txt"
    s3.put_object(Bucket=credential.bucket, Key=key, Body=b"hello from org A")
    body = s3.get_object(Bucket=credential.bucket, Key=key)["Body"].read()
    assert body == b"hello from org A"


def test_org_a_credential_cannot_read_org_b_prefix(minio_config: ArtifactStorageConfig) -> None:
    cred_b = mint_scoped_credential(minio_config, org_id="org-artifact-b")
    s3_b = boto3.client(
        "s3",
        endpoint_url=minio_config.endpoint_url,
        aws_access_key_id=cred_b.access_key,
        aws_secret_access_key=cred_b.secret_key,
        aws_session_token=cred_b.session_token,
        region_name="us-east-1",
    )
    key_b = f"{cred_b.prefix}secret.txt"
    s3_b.put_object(Bucket=cred_b.bucket, Key=key_b, Body=b"org B's secret")

    cred_a = mint_scoped_credential(minio_config, org_id="org-artifact-c")
    s3_a = boto3.client(
        "s3",
        endpoint_url=minio_config.endpoint_url,
        aws_access_key_id=cred_a.access_key,
        aws_secret_access_key=cred_a.secret_key,
        aws_session_token=cred_a.session_token,
        region_name="us-east-1",
    )

    with pytest.raises(botocore.exceptions.ClientError) as exc_info:
        s3_a.get_object(Bucket=cred_a.bucket, Key=key_b)
    assert exc_info.value.response["Error"]["Code"] in {"AccessDenied", "403"}

    with pytest.raises(botocore.exceptions.ClientError):
        s3_a.put_object(Bucket=cred_a.bucket, Key=key_b, Body=b"overwritten by org C")
