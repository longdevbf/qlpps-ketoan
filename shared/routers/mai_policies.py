"""Mai Policies API — CEO set hạn mức/định mức cho Mai AI.

Hỗ trợ scope:
- 'company'    — áp toàn công ty (default).
- 'department' — scope_value = tên phòng ban (vd 'Marketing').
- 'employee'   — scope_value = username NV.

Priority khi check policy: employee > department > company.

Endpoints (yêu cầu CEO):
  GET    /policies                                — list tất cả policy
                                                    (filter optional: source, scope)
  POST   /policies        body MaiPolicyIn         — upsert theo
                                                    (source, rule_type, scope, scope_value)
  DELETE /policies/{id}                            — xoá theo id
  GET    /policies/check?source=X&value=Y
            [&rule=R][&department=D][&username=U]  — check policy theo priority

Mounted bởi orchestrator vào CEO main.py với prefix `/api/mai-policies`.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.auth import JWTPayload, require_ceo
from shared.db import get_db
from shared.models.mai_policy import MaiPolicy

router = APIRouter()

_AUTH_READ = Depends(require_ceo(write=False))
_AUTH_WRITE = Depends(require_ceo(write=True))


# Rule_type được coi là "ngưỡng tối đa" — value càng cao càng vượt.
_MAX_RULES = {"max_amount", "max_discount_pct", "max_percent", "max_days", "max_km"}

_VALID_SCOPES = {"company", "department", "employee"}


# ─── Schemas ─────────────────────────────────────────────────────────────
class MaiPolicyIn(BaseModel):
    source: str = Field(..., description="vd: baogia_quote, muahang_po, duyet_chi")
    rule_type: str = Field(..., description="vd: max_amount, max_discount_pct, enabled")
    value: Optional[Decimal] = Field(None, description="Threshold. 0/1 khi rule_type=enabled")
    unit: Optional[str] = Field(None, description="VND | % | ngày | km | bool")
    note: Optional[str] = None
    enabled: Optional[bool] = Field(True, description="Bật/tắt rule. Default True")
    scope: Optional[str] = Field(
        "company", description="'company' | 'department' | 'employee'"
    )
    scope_value: Optional[str] = Field(
        None, description="NULL khi company; phòng ban khi department; username khi employee"
    )


class MaiPolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source: str
    rule_type: str
    value: Optional[Decimal]
    unit: Optional[str]
    enabled: bool
    note: Optional[str]
    scope: str
    scope_value: Optional[str]
    updated_by: Optional[str]
    updated_at: datetime


class CheckResult(BaseModel):
    source: str
    rule_type: str
    within_budget: bool
    threshold: Optional[Decimal]
    gap: Optional[Decimal]
    enabled: bool
    note: Optional[str] = None
    scope_used: Optional[str] = None
    scope_value_used: Optional[str] = None


# ─── Helpers ─────────────────────────────────────────────────────────────
def _validate(body: MaiPolicyIn) -> None:
    if not (body.source or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "source không được trống")
    if not (body.rule_type or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "rule_type không được trống")
    scope = (body.scope or "company").strip()
    if scope not in _VALID_SCOPES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"scope không hợp lệ — phải thuộc {sorted(_VALID_SCOPES)}",
        )
    if scope == "company" and (body.scope_value or "").strip():
        # cho phép nhưng chuẩn hoá về NULL — không raise
        pass
    if scope in ("department", "employee") and not (body.scope_value or "").strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"scope_value bắt buộc khi scope='{scope}'",
        )


def _norm_scope(body: MaiPolicyIn) -> tuple[str, Optional[str]]:
    scope = (body.scope or "company").strip()
    sv = (body.scope_value or "").strip() or None
    if scope == "company":
        sv = None
    return scope, sv


# ─── Endpoints ───────────────────────────────────────────────────────────
@router.get("/policies", response_model=List[MaiPolicyOut])
def list_policies(
    _user: Annotated[JWTPayload, _AUTH_READ],
    db: Annotated[Session, Depends(get_db)],
    source: Optional[str] = None,
    scope: Optional[str] = None,
):
    stmt = select(MaiPolicy).order_by(
        MaiPolicy.source.asc(),
        MaiPolicy.rule_type.asc(),
        MaiPolicy.scope.asc(),
        MaiPolicy.scope_value.asc().nulls_first(),
    )
    if source:
        stmt = stmt.where(MaiPolicy.source == source)
    if scope:
        stmt = stmt.where(MaiPolicy.scope == scope)
    return db.execute(stmt).scalars().all()


@router.post("/policies", response_model=MaiPolicyOut, status_code=status.HTTP_200_OK)
def upsert_policy(
    body: MaiPolicyIn,
    user: Annotated[JWTPayload, _AUTH_WRITE],
    db: Annotated[Session, Depends(get_db)],
):
    _validate(body)
    src = body.source.strip()
    rule = body.rule_type.strip()
    scope, scope_value = _norm_scope(body)

    # Upsert theo (source, rule_type, scope, scope_value)
    q = (
        select(MaiPolicy)
        .where(MaiPolicy.source == src)
        .where(MaiPolicy.rule_type == rule)
        .where(MaiPolicy.scope == scope)
    )
    if scope_value is None:
        q = q.where(MaiPolicy.scope_value.is_(None))
    else:
        q = q.where(MaiPolicy.scope_value == scope_value)
    existing = db.execute(q.limit(1)).scalar_one_or_none()

    if existing:
        if body.value is not None:
            existing.value = body.value
        if body.unit is not None:
            existing.unit = body.unit
        if body.note is not None:
            existing.note = body.note
        if body.enabled is not None:
            existing.enabled = bool(body.enabled)
        existing.updated_by = user.username
        db.flush()
        db.commit()
        db.refresh(existing)
        return existing

    rec = MaiPolicy(
        source=src,
        rule_type=rule,
        value=body.value,
        unit=body.unit,
        note=body.note,
        enabled=bool(body.enabled) if body.enabled is not None else True,
        scope=scope,
        scope_value=scope_value,
        updated_by=user.username,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


@router.delete("/policies/{pid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_policy(
    pid: int,
    _user: Annotated[JWTPayload, _AUTH_WRITE],
    db: Annotated[Session, Depends(get_db)],
):
    rec = db.get(MaiPolicy, pid)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy policy")
    db.delete(rec)
    db.commit()


def _find_policy_by_scope(
    db: Session,
    source: str,
    rule: Optional[str],
    scope: str,
    scope_value: Optional[str],
) -> Optional[MaiPolicy]:
    """Tìm 1 policy match đúng (source, rule_type?, scope, scope_value)."""
    stmt = select(MaiPolicy).where(MaiPolicy.source == source).where(MaiPolicy.scope == scope)
    if scope_value is None:
        stmt = stmt.where(MaiPolicy.scope_value.is_(None))
    else:
        stmt = stmt.where(MaiPolicy.scope_value == scope_value)
    if rule:
        stmt = stmt.where(MaiPolicy.rule_type == rule)
    else:
        stmt = stmt.where(MaiPolicy.rule_type.in_(list(_MAX_RULES)))
    stmt = stmt.order_by(MaiPolicy.rule_type.asc()).limit(1)
    return db.execute(stmt).scalar_one_or_none()


@router.get("/policies/check", response_model=CheckResult)
def check_policy(
    _user: Annotated[JWTPayload, _AUTH_READ],
    db: Annotated[Session, Depends(get_db)],
    source: str = Query(..., description="vd: baogia_quote"),
    value: Decimal = Query(..., description="Giá trị cần check (số tiền/ngày/km/...)"),
    rule: Optional[str] = Query(
        None, description="Rule cụ thể (vd max_amount). Bỏ trống = tìm rule 'max_*' đầu tiên"
    ),
    department: Optional[str] = Query(
        None, description="Tên phòng ban — check policy scope=department trước"
    ),
    username: Optional[str] = Query(
        None, description="Username NV — check policy scope=employee đầu tiên (priority cao nhất)"
    ),
):
    """Trả {within_budget, threshold, gap, scope_used, scope_value_used}.

    Priority lookup: employee → department → company.
    - within_budget=True  → value <= threshold (Mai có thể auto-duyệt).
    - within_budget=False → vượt ngưỡng (Mai escalate CEO).
    - gap = threshold - value (âm khi vượt ngưỡng).
    - Nếu không tìm thấy policy nào (hoặc tất cả disabled) → within_budget=False
      (an toàn — escalate CEO).
    """
    rec: Optional[MaiPolicy] = None

    # 1) employee
    if username and (username or "").strip():
        rec = _find_policy_by_scope(db, source, rule, "employee", username.strip())
    # 2) department
    if rec is None and department and (department or "").strip():
        rec = _find_policy_by_scope(db, source, rule, "department", department.strip())
    # 3) company
    if rec is None:
        rec = _find_policy_by_scope(db, source, rule, "company", None)

    if rec is None:
        return CheckResult(
            source=source,
            rule_type=rule or "",
            within_budget=False,
            threshold=None,
            gap=None,
            enabled=False,
            note="Không tìm thấy policy — Mai phải escalate CEO.",
            scope_used=None,
            scope_value_used=None,
        )

    if not rec.enabled or rec.value is None:
        return CheckResult(
            source=rec.source,
            rule_type=rec.rule_type,
            within_budget=False,
            threshold=rec.value,
            gap=None,
            enabled=rec.enabled,
            note=rec.note or "Policy đang tắt — Mai escalate CEO.",
            scope_used=rec.scope,
            scope_value_used=rec.scope_value,
        )

    threshold = rec.value
    within = Decimal(value) <= threshold
    gap = threshold - Decimal(value)
    return CheckResult(
        source=rec.source,
        rule_type=rec.rule_type,
        within_budget=within,
        threshold=threshold,
        gap=gap,
        enabled=rec.enabled,
        note=rec.note,
        scope_used=rec.scope,
        scope_value_used=rec.scope_value,
    )
