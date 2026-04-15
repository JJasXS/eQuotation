"""Customer management endpoints via SQL Accounting API (SigV4)."""
import logging
import os

import fdb
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Header, Query

from api.adapters import COMConnectionError
from api.clients import SqlAccountingApiError
from api.models import APIResponse, CustomerRequest
from api.services import COMOperationError, CustomerConfigurationError, CustomerService

router = APIRouter(prefix="/customers", tags=["Customers"])
compat_router = APIRouter(tags=["Customers"])
logger = logging.getLogger(__name__)

customer_service = CustomerService()

# Load DB settings for compatibility GET /customer list route.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../.env'))
DB_PATH = os.getenv('DB_PATH')
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

def verify_api_keys(
    x_access_key: str = Header(..., alias="X-Access-Key"),
    x_secret_key: str = Header(..., alias="X-Secret-Key"),
):
    """Dependency: reject requests with missing or invalid API keys."""
    # Accept either dedicated API keys or SQL API keys for local development convenience.
    api_access_key = (os.getenv("API_ACCESS_KEY") or "").strip()
    api_secret_key = (os.getenv("API_SECRET_KEY") or "").strip()
    sql_access_key = (os.getenv("SQL_API_ACCESS_KEY") or "").strip()
    sql_secret_key = (os.getenv("SQL_API_SECRET_KEY") or "").strip()
    provided_access_key = (x_access_key or "").strip()
    provided_secret_key = (x_secret_key or "").strip()

    valid_pairs = {
        (api_access_key, api_secret_key),
        (sql_access_key, sql_secret_key),
    }
    valid_pairs = {pair for pair in valid_pairs if pair[0] and pair[1]}

    if not valid_pairs:
        raise HTTPException(status_code=500, detail="API keys not configured on server.")
    if (provided_access_key, provided_secret_key) not in valid_pairs:
        raise HTTPException(status_code=401, detail="Invalid API credentials.")


def _create_customer_impl(
    customer_data: CustomerRequest,
    _: None = Depends(verify_api_keys),
    include_state: bool = Query(False, description="Run COM post-create state lookup before responding."),
):
    """Create customer via SQL Accounting REST API (AWS SigV4), not COM or direct SQL."""
    try:
        customer = customer_service.create_customer(customer_data)
        if customer.dry_run:
            state = {
                "skipped": True,
                "reason": "SQL_API_DRY_RUN: no remote create; post_create_state not read from COM.",
            }
        elif not include_state:
            state = {
                "skipped": True,
                "reason": "Post-create COM state lookup disabled. Pass include_state=true to enable it.",
            }
        else:
            try:
                state = customer_service.get_customer_state(customer.code)
            except (COMOperationError, COMConnectionError) as exc:
                logger.warning("Post-create COM state read failed: %s", exc)
                state = {"error": str(exc), "source": "com"}
        return APIResponse(
            success=True,
            message="Customer created successfully (dry-run preview)"
            if customer.dry_run
            else "Customer created successfully",
            data={
                "customer": customer.model_dump(),
                "post_create_state": state,
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except CustomerConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except SqlAccountingApiError as exc:
        sc = exc.status_code
        if sc is None:
            raise HTTPException(status_code=503, detail=str(exc))
        if 400 <= sc < 500:
            raise HTTPException(status_code=422, detail=str(exc))
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        logger.exception("Unhandled error while creating customer")
        raise HTTPException(status_code=500, detail=f"Failed to create customer: {str(exc)}")


@router.post("", response_model=APIResponse, status_code=201)
def create_customer(
    customer_data: CustomerRequest,
    _: None = Depends(verify_api_keys),
    include_state: bool = Query(False, description="Run COM post-create state lookup before responding."),
):
    return _create_customer_impl(customer_data, _, include_state)


@compat_router.post("/customer", status_code=201)
def create_customer_compat(
    customer_data: CustomerRequest,
    _: None = Depends(verify_api_keys),
    include_state: bool = Query(False, description="Run COM post-create state lookup before responding."),
):
    """Compatibility route for Postman collections that use singular /customer."""
    response = _create_customer_impl(customer_data, _, include_state)
    upstream = (((response.data or {}).get("customer") or {}).get("upstream_response") or {})
    return upstream or response


@compat_router.get("/customer")
def list_customers_compat(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    """Compatibility route matching /customer?offset=0 response shape for dashboard usage."""
    con = None
    cur = None
    try:
        con = fdb.connect(dsn=f"{DB_HOST}:{DB_PATH}", user=DB_USER, password=DB_PASSWORD, charset='UTF8')
        cur = con.cursor()

        cur.execute('SELECT COUNT(*) FROM AR_CUSTOMER')
        total = int((cur.fetchone() or [0])[0] or 0)

        cur.execute(
            """
            SELECT FIRST ? SKIP ? CODE, COMPANYNAME, STATUS
            FROM AR_CUSTOMER
            ORDER BY CODE ASC
            """,
            [limit, offset],
        )

        data = []
        for code, company_name, status in cur.fetchall() or []:
            code_str = str(code).strip() if code else ''
            company_str = str(company_name).strip() if company_name else ''
            status_str = (str(status).strip().upper() if status else '')[:1]
            data.append({
                'code': code_str,
                'companyname': company_str,
                'status': status_str,
            })

        return {
            'pagination': {
                'offset': offset,
                'limit': limit,
                'count': len(data),
                'total': total,
            },
            'data': data,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to list customers: {str(exc)}")
    finally:
        if cur is not None:
            cur.close()
        if con is not None:
            con.close()


@router.get("/{customer_code}/state", response_model=APIResponse)
def get_customer_state(customer_code: str):
    """Read STATUS and SUBMISSIONTYPE for a customer code (COM read helper)."""
    try:
        state = customer_service.get_customer_state(customer_code)
        return APIResponse(
            success=True,
            message="Customer state retrieved successfully",
            data=state,
        )
    except COMConnectionError as exc:
        raise HTTPException(status_code=503, detail=f"COM connection failed: {str(exc)}")
    except COMOperationError as exc:
        raise HTTPException(status_code=422, detail=f"Failed to read customer state: {str(exc)}")
    except Exception as exc:
        logger.exception("Unhandled error while reading customer state")
        raise HTTPException(status_code=500, detail=f"Failed to read customer state: {str(exc)}")
