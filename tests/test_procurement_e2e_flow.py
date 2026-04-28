import json
from datetime import date, timedelta

from utils.procurement_bidding import (
    apply_approved_bid_to_request,
    approve_bid,
    create_bid_invitations,
    ensure_bidding_schema,
    get_transfer_gate_state,
    list_bids_for_request,
    reject_bid,
    submit_supplier_bid,
    validate_transfer_against_approved_bid,
)
from utils.procurement_purchase_order_transfer import transfer_purchase_request_to_po
from utils.procurement_purchase_request import _connect_db, create_purchase_request


def _fetch_request_header_and_details(request_dockey: int) -> dict:
    con = _connect_db()
    try:
        cur = con.cursor()
        cur.execute("SELECT FIRST 1 * FROM PH_PQ WHERE DOCKEY = ?", (request_dockey,))
        header_row = cur.fetchone()
        if not header_row:
            raise RuntimeError(f"PH_PQ record not found for DOCKEY={request_dockey}")

        header_cols = [str(col[0] or "").strip().lower() for col in (cur.description or [])]
        header = {header_cols[i]: header_row[i] for i in range(min(len(header_cols), len(header_row)))}

        cur.execute("SELECT * FROM PH_PQDTL WHERE DOCKEY = ? ORDER BY SEQ", (request_dockey,))
        detail_rows = cur.fetchall() or []
        detail_cols = [str(col[0] or "").strip().lower() for col in (cur.description or [])]

        mapped_details = []
        for idx, row in enumerate(detail_rows, start=1):
            detail = {detail_cols[i]: row[i] for i in range(min(len(detail_cols), len(row)))}
            qty = float(detail.get("qty") or detail.get("quantity") or 0)
            unit_price = float(detail.get("unitprice") or 0)
            tax_amt = float(detail.get("taxamt") or detail.get("tax") or 0)
            mapped_details.append(
                {
                    "dtlkey": int(detail.get("dtlkey") or detail.get("pqdtlkey") or detail.get("id") or idx),
                    "seq": int(detail.get("seq") or detail.get("lineno") or detail.get("line_no") or idx),
                    "itemcode": str(detail.get("itemcode") or "").strip(),
                    "description": str(
                        detail.get("description")
                        or detail.get("description2")
                        or detail.get("itemname")
                        or ""
                    ).strip(),
                    "location": str(
                        detail.get("location")
                        or detail.get("loc")
                        or detail.get("stocklocation")
                        or detail.get("storelocation")
                        or ""
                    ).strip(),
                    "qty": qty,
                    "unitprice": unit_price,
                    "taxamt": tax_amt,
                    "amount": float((qty * unit_price) + tax_amt),
                    "udf_pqapproved": True,
                    "transferable": True,
                }
            )

        return {
            "dockey": int(header.get("dockey") or request_dockey),
            "docno": str(header.get("docno") or "").strip(),
            "code": str(header.get("code") or "").strip(),
            "companyname": str(header.get("companyname") or "").strip(),
            "currencycode": str(header.get("currencycode") or "MYR").strip(),
            "currencyrate": float(header.get("currencyrate") or 1),
            "project": str(header.get("project") or "----").strip(),
            "businessunit": str(header.get("businessunit") or "PROC").strip(),
            "shipper": str(header.get("shipper") or "----").strip(),
            "udf_status": "APPROVED",
            "sdsdocdetail": mapped_details,
        }
    finally:
        con.close()


def _build_bid_lines(details: list[dict], price_multiplier: float) -> list[dict]:
    lines = []
    for row in details:
        qty = float(row.get("qty") or 0)
        base_price = float(row.get("unitprice") or 0)
        lines.append(
            {
                "detailId": int(row["dtlkey"]),
                "itemCode": row.get("itemcode") or "",
                "description": row.get("description") or "",
                "quantity": qty,
                "unitPrice": round(base_price * price_multiplier, 2),
                "tax": round(float(row.get("taxamt") or 0), 2),
                "remarks": "E2E bid",
            }
        )
    return lines


def run_flow() -> dict:
    ensure_bidding_schema()

    today = date.today()
    payload = {
        "requestDate": today.isoformat(),
        "requiredDate": (today + timedelta(days=7)).isoformat(),
        "departmentId": "PROC",
        "requesterId": "AUTO-ADMIN",
        "currency": "MYR",
        "description": "E2E Procurement Flow",
        "status": "DRAFT",
        "lineItems": [
            {
                "itemCode": "E2E-ITEM-01",
                "itemName": "E2E Item 1",
                "description": "E2E item line 1",
                "locationCode": "MAIN",
                "quantity": 5,
                "unitPrice": 12.5,
                "tax": 0,
                "deliveryDate": (today + timedelta(days=7)).isoformat(),
            },
            {
                "itemCode": "E2E-ITEM-02",
                "itemName": "E2E Item 2",
                "description": "E2E item line 2",
                "locationCode": "MAIN",
                "quantity": 3,
                "unitPrice": 20,
                "tax": 0,
                "deliveryDate": (today + timedelta(days=7)).isoformat(),
            },
        ],
    }

    created = create_purchase_request(payload, created_by="e2e-admin")
    request_id = int(created["id"])
    request_no = str(created["requestNumber"])

    header = _fetch_request_header_and_details(request_id)
    details = header.get("sdsdocdetail") or []
    if not details:
        raise RuntimeError("No PH_PQDTL rows found for created PR")

    invited = create_bid_invitations(
        request_dockey=request_id,
        request_no=request_no,
        suppliers=[
            {"code": "E2E-SUP-A", "name": "E2E Supplier A"},
            {"code": "E2E-SUP-B", "name": "E2E Supplier B"},
        ],
        created_by="e2e-admin",
    )

    bid_a = submit_supplier_bid(
        request_dockey=request_id,
        request_no=request_no,
        supplier_code="E2E-SUP-A",
        supplier_name="E2E Supplier A",
        bid_lines=_build_bid_lines(details, 0.95),
        remarks="Supplier A quote",
        created_by="e2e-supplier-a",
    )

    bid_b = submit_supplier_bid(
        request_dockey=request_id,
        request_no=request_no,
        supplier_code="E2E-SUP-B",
        supplier_name="E2E Supplier B",
        bid_lines=_build_bid_lines(details, 1.05),
        remarks="Supplier B quote",
        created_by="e2e-supplier-b",
    )

    all_bids = list_bids_for_request(request_id)
    bid_id_a = next((int(row["bidId"]) for row in all_bids if row.get("supplierCode") == "E2E-SUP-A"), None)
    bid_id_b = next((int(row["bidId"]) for row in all_bids if row.get("supplierCode") == "E2E-SUP-B"), None)
    if not bid_id_a or not bid_id_b:
        raise RuntimeError("Failed to locate both supplier bids")

    rejected = reject_bid(request_id, bid_id_b, actor="e2e-admin", udf_reason="Cancelled in favor of better bid")
    approved = approve_bid(request_id, bid_id_a, actor="e2e-admin")

    gate = get_transfer_gate_state(request_id)
    approved_bid = validate_transfer_against_approved_bid(
        request_id,
        supplier_code="E2E-SUP-A",
        transfer_lines=[{"fromdtlkey": int(row["dtlkey"]), "qty": float(row["qty"])} for row in details],
    )

    request_for_transfer, approved_supplier = apply_approved_bid_to_request(header, approved_bid)

    transfer_result = transfer_purchase_request_to_po(
        purchase_request=request_for_transfer,
        transfer_lines=[{"fromdtlkey": int(row["dtlkey"]), "qty": float(row["qty"])} for row in details],
        supplier={
            "code": approved_supplier.get("code") or "E2E-SUP-A",
            "companyname": approved_supplier.get("companyname") or "E2E Supplier A",
            "currencycode": "MYR",
            "currencyrate": 1,
        },
        created_by="e2e-admin",
    )

    return {
        "created": created,
        "invited": invited,
        "bidA": bid_a,
        "bidB": bid_b,
        "rejected": rejected,
        "approved": approved,
        "gate": gate,
        "transfer": transfer_result,
    }


if __name__ == "__main__":
    summary = run_flow()
    print(json.dumps(summary, indent=2, default=str))
