"""SePay webhook endpoint — nhận notify giao dịch bank.

Endpoint KHÔNG dùng JWT: SePay là 3rd party gọi từ server ngoài. Xác thực
qua shared secret `SEPAY_WEBHOOK_SECRET` trong header `Authorization: Apikey ...`.

Design idempotent — SePay retry được (nếu server timeout / trả != 200) sẽ tự
gọi lại tối đa 7 lần theo config Console SePay. `sepay_id` UNIQUE chống double credit.
"""
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from shared.db import get_db

from ..services.sepay_webhook import handle_webhook, verify_api_key


router = APIRouter()


@router.post("/api/sepay/webhook", status_code=status.HTTP_200_OK)
async def sepay_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[Optional[str], Header(alias="Authorization")] = None,
) -> dict[str, Any]:
    if not verify_api_key(authorization):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key")

    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid JSON: {e}")

    if not isinstance(payload, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payload must be a JSON object")

    try:
        result = handle_webhook(db, payload)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except Exception as e:
        # Log ở service. Trả 500 để SePay retry (payload đúng, nội bộ lỗi).
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Internal: {e}")

    return result


@router.get("/api/sepay/webhook/ping")
def sepay_webhook_ping() -> dict[str, str]:
    """Health check — SePay không dùng. Chỉ để dev test URL."""
    return {"status": "ok", "endpoint": "/api/sepay/webhook"}
