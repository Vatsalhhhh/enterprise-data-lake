"""Lands raw domain CSVs into the MinIO (S3-compatible) data lake.

This is the local substitute for an S3 landing-zone upload job you'd
otherwise run from a Glue job, a Lambda, or a plain boto3 script against
real AWS S3. The MinIO endpoint speaks the same S3 API, so this code would
work against AWS S3 with only endpoint/credential changes.

Uploads every CSV under generators/output/<domain>/ to:
    s3://<bucket>/raw/<domain>/<dataset>/dt=<ingestion_date>/<file>.csv

Partitioning by ingestion date (dt=YYYY-MM-DD) is the same convention Glue
crawlers/Athena partition projection expect, so this maps directly onto a
real AWS raw zone.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
BUCKET = os.getenv("MINIO_BUCKET", "data-lake")

GENERATORS_OUTPUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "generators", "output",
)

DOMAINS = ["sales", "hr", "finance", "inventory", "marketing"]


def get_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def ensure_bucket(client, bucket: str):
    try:
        client.head_bucket(Bucket=bucket)
        print(f"bucket '{bucket}' already exists")
    except ClientError:
        client.create_bucket(Bucket=bucket)
        print(f"created bucket '{bucket}'")


def land_domain(client, domain: str, ingest_date: str, bucket: str) -> int:
    domain_dir = os.path.join(GENERATORS_OUTPUT, domain)
    if not os.path.isdir(domain_dir):
        print(f"  [skip] no generated output for domain '{domain}' at {domain_dir}")
        return 0

    uploaded = 0
    for fname in sorted(os.listdir(domain_dir)):
        if not fname.endswith(".csv"):
            continue
        dataset = fname[:-4]
        local_path = os.path.join(domain_dir, fname)
        key = f"raw/{domain}/{dataset}/dt={ingest_date}/{fname}"

        # boto3's upload_file automatically uses multipart upload for large
        # files above the configured threshold -- this is "multipart-safe"
        # without any extra code on our part.
        client.upload_file(local_path, bucket, key)
        size = os.path.getsize(local_path)
        print(f"  uploaded {local_path} -> s3://{bucket}/{key} ({size:,} bytes)")
        uploaded += 1
    return uploaded


def list_raw_prefix(client, bucket: str, prefix: str = "raw/"):
    paginator = client.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def main():
    ingest_date = dt.date.today().isoformat()
    client = get_client()

    ensure_bucket(client, BUCKET)

    total = 0
    for domain in DOMAINS:
        print(f"landing domain: {domain}")
        total += land_domain(client, domain, ingest_date, BUCKET)

    print(f"\nlanded {total} files into s3://{BUCKET}/raw/ (partition dt={ingest_date})")

    keys = list_raw_prefix(client, BUCKET)
    print(f"verification: {len(keys)} objects now present under raw/ prefix")


if __name__ == "__main__":
    main()
