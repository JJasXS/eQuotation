"""
Load repo .env and verify AWS credentials + Secrets Manager read.

Usage (from repo root):
  python scripts/verify_aws_dotenv.py
  python scripts/verify_aws_dotenv.py --secret-id proacc/tenant/TNT10004/sqlApiCredentials
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--secret-id",
        default="proacc/tenant/TNT10004/sqlApiCredentials",
        help="Secret id or ARN to fetch (only length printed, not value).",
    )
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    env_path = root / ".env"
    if not env_path.is_file():
        print("No .env at", env_path, flush=True)
        return 1

    os.chdir(root)
    sys.path.insert(0, str(root))

    from dotenv import load_dotenv

    load_dotenv(env_path, override=True)

    region = (os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "ap-southeast-1").strip()
    ak = (os.getenv("AWS_ACCESS_KEY_ID") or "").strip()
    sk = (os.getenv("AWS_SECRET_ACCESS_KEY") or "").strip()
    profile = (os.getenv("AWS_PROFILE") or "").strip()

    print(
        "After load_dotenv: AWS_PROFILE set=",
        bool(profile),
        " AWS_ACCESS_KEY_ID set=",
        bool(ak),
        " AWS_SECRET_ACCESS_KEY set=",
        bool(sk),
        " region=",
        region,
        flush=True,
    )

    if profile and not (ak and sk):
        print("Using AWS_PROFILE (SSO or shared credentials file); access keys in .env not required.", flush=True)
    elif not profile and (not ak or not sk):
        print(
            "FAIL: No AWS credentials found. In .env, either:\n"
            "  A) Uncomment and save:\n"
            "       AWS_ACCESS_KEY_ID=AKIA...\n"
            "       AWS_SECRET_ACCESS_KEY=...\n"
            "       AWS_REGION=ap-southeast-1\n"
            "  B) Or use SSO:\n"
            "       AWS_PROFILE=your-profile\n"
            "       AWS_REGION=ap-southeast-1\n"
            "     and run: aws sso login --profile your-profile",
            flush=True,
        )
        return 1

    from botocore.session import Session

    sess = Session()
    sts = sess.create_client("sts", region_name=region)
    ident = sts.get_caller_identity()
    print("STS OK  Account=", ident.get("Account"), flush=True)
    print("STS OK  Arn   =", ident.get("Arn"), flush=True)

    sm = sess.create_client("secretsmanager", region_name=region)
    try:
        r = sm.get_secret_value(SecretId=args.secret_id.strip())
        body = r.get("SecretString") or ""
        print("Secrets Manager OK  secret_id=", args.secret_id, " SecretString length=", len(body), flush=True)
    except Exception as exc:
        print("Secrets Manager FAIL", type(exc).__name__, str(exc)[:400], flush=True)
        return 1

    print("All checks passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
