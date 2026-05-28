"""Lightweight audit of which AWS resources this tenant is using.

Reports:
  - Number of Secrets Manager secrets in the region (the main billable item)
  - Names + ARNs of secrets your tenant config references (so you can tell
    whether each one is needed)
  - DynamoDB tables in the region (free tier covers small usage)
  - Whether the tenant API Gateway is reachable

Cost lookups (Cost Explorer) are attempted last; they usually require explicit
permission, so we print a note if denied.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path


def _resolve_env() -> None:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    os.chdir(root)
    from dotenv import load_dotenv

    from utils.appsettings_env import apply_appsettings_to_environ
    from utils.tenant_bootstrap import apply_tenant_env_overrides

    apply_appsettings_to_environ(project_root=root)
    load_dotenv(root / ".env", override=False)
    # We need TENANT_CODE to know which secret names to inspect, but we will
    # try to skip the secret fetches themselves so this stays read-only.
    os.environ.setdefault("TENANT_BOOTSTRAP_SKIP_SECRETS", "1")
    try:
        apply_tenant_env_overrides()
    except Exception as exc:
        print(f"(tenant bootstrap warning: {exc})")


def _section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def _list_secrets(region: str) -> list[dict]:
    import boto3

    client = boto3.client("secretsmanager", region_name=region)
    paginator = client.get_paginator("list_secrets")
    out: list[dict] = []
    for page in paginator.paginate():
        out.extend(page.get("SecretList", []))
    return out


def _list_dynamo_tables(region: str) -> list[str]:
    import boto3

    client = boto3.client("dynamodb", region_name=region)
    paginator = client.get_paginator("list_tables")
    names: list[str] = []
    for page in paginator.paginate():
        names.extend(page.get("TableNames", []))
    return names


def _fetch_tenant_record(tenant_code: str) -> dict:
    import requests

    base = (
        os.getenv("TENANT_BOOTSTRAP_API_URL")
        or "https://v2wwsho311.execute-api.ap-southeast-1.amazonaws.com/default/proacc-tenant-config-api"
    ).rstrip("/")
    sep = "&" if "?" in base else "?"
    url = f"{base}{sep}tenantCode={tenant_code}"
    r = requests.get(url, timeout=20)
    return {"ok": r.ok, "status": r.status_code, "body_prefix": (r.text or "")[:200]}


def _cost_explorer(region: str) -> dict | None:
    """Try to read this month's cost. Most accounts deny this unless granted."""
    import boto3
    from botocore.exceptions import ClientError

    today = date.today()
    start = today.replace(day=1).isoformat()
    end = today.isoformat()
    if start == end:
        # First of the month: report yesterday too.
        end = (today + timedelta(days=1)).isoformat()
    client = boto3.client("ce", region_name="us-east-1")  # Cost Explorer is global
    try:
        resp = client.get_cost_and_usage(
            TimePeriod={"Start": start, "End": end},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )
        groups = resp["ResultsByTime"][0]["Groups"]
        out = []
        total = 0.0
        for g in groups:
            svc = g["Keys"][0]
            amt = float(g["Metrics"]["UnblendedCost"]["Amount"])
            unit = g["Metrics"]["UnblendedCost"]["Unit"]
            if amt > 0:
                out.append({"service": svc, "amount": amt, "unit": unit})
                total += amt
        return {"start": start, "end": end, "total": total, "items": sorted(out, key=lambda x: -x["amount"])}
    except ClientError as exc:
        return {"error": exc.response["Error"]["Code"] + ": " + exc.response["Error"].get("Message", "")}
    except Exception as exc:
        return {"error": str(exc)}


def main() -> int:
    _resolve_env()

    region = (os.getenv("AWS_REGION") or "ap-southeast-1").strip()
    tenant = (os.getenv("TENANT_CODE") or "").strip()

    _section("Identity")
    try:
        import boto3

        ident = boto3.client("sts").get_caller_identity()
        print(f"  Account ID : {ident.get('Account')}")
        print(f"  ARN        : {ident.get('Arn')}")
        print(f"  Region     : {region}")
        print(f"  Tenant code: {tenant or '(none)'}")
    except Exception as exc:
        print(f"  STS call failed: {exc}")
        return 1

    _section("Secrets Manager (the main paid item: ~$0.40 / secret / month)")
    try:
        secrets = _list_secrets(region)
        print(f"  Total secrets in {region}: {len(secrets)}")
        if secrets:
            print()
            print(f"  {'Name':45s} {'LastChanged':14s} {'Tags'}")
            print(f"  {'-'*45} {'-'*14} ----")
            for s in secrets:
                name = s.get("Name", "")[:45]
                changed = (s.get("LastChangedDate") or s.get("CreatedDate") or "")
                changed_str = str(changed)[:10] if changed else ""
                tags = ",".join(
                    f"{t.get('Key')}={t.get('Value')}" for t in (s.get("Tags") or [])
                )
                print(f"  {name:45s} {changed_str:14s} {tags}")
        sm_est = len(secrets) * 0.40
        print()
        print(f"  Estimated Secrets Manager fixed cost: ~${sm_est:.2f} / month")
        print("  (+ ~$0.05 per 10,000 GetSecretValue calls; tiny for this app.)")
    except Exception as exc:
        print(f"  list_secrets failed: {exc}")

    _section("DynamoDB (free tier: 25 GB + 25 WCU/RCU on-demand basically forever)")
    try:
        tables = _list_dynamo_tables(region)
        print(f"  Tables in {region}: {len(tables)}")
        for t in tables:
            print(f"    - {t}")
        print()
        print("  Likely free for this app (tenant config table is tiny).")
    except Exception as exc:
        print(f"  list_tables failed: {exc}")

    _section("Tenant config API Gateway (1M requests/month free for 12 months)")
    try:
        if tenant:
            info = _fetch_tenant_record(tenant)
            print(f"  GET tenant-config-api?tenantCode={tenant}: ok={info['ok']} status={info['status']}")
        else:
            print("  (TENANT_CODE not set; skipping)")
    except Exception as exc:
        print(f"  tenant API call failed: {exc}")

    _section("This month's bill (Cost Explorer)")
    ce = _cost_explorer(region)
    if not ce:
        print("  (skipped)")
    elif "error" in ce:
        print(f"  Cost Explorer denied / unavailable: {ce['error']}")
        print("  -> Open the AWS Console > Billing > Cost Explorer to see real numbers,")
        print("     or attach a policy with 'ce:GetCostAndUsage' to this IAM user.")
    else:
        print(f"  {ce['start']} -> {ce['end']}")
        print(f"  TOTAL: ${ce['total']:.4f}")
        for it in ce["items"]:
            print(f"    {it['service']:42s} ${it['amount']:.4f} {it['unit']}")
        if not ce["items"]:
            print("  (no billable usage so far this month)")

    print()
    print("Outside of AWS:")
    print("  - OpenAI: billed by OpenAI directly (per token of GPT calls).")
    print("  - SQL Accounting REST API (api.sql.my): billed by eStream/SQL Account.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
