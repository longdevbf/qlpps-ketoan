"""Kế Toán V2 — FastAPI app (port 8005).

Endpoints:
    HTML:
        GET  /                       -- redirect /login hoặc /app
        GET  /app                    -- main SPA (index.html)
        GET  /login                  -- login page
        GET  /logout

    API (JWT required, app=ketoan, role ∈ {admin,ceo,manager}):
        /api/doanh-thu               (CRUD)
        /api/chi-phi                 (CRUD)
        /api/co-dinh                 (CRUD)
        /api/cong-no                 (CRUD + POST /{id}/tra)
        /api/so-quy                  (CRUD)
        /api/loai-chi-phi            (CRUD danh mục)
        /api/tai-khoan               (CRUD tài khoản NH/tiền mặt)
        /api/bao-cao/tong-hop        (P&L)
        /api/bao-cao/doanh-thu
        /api/bao-cao/chi-phi
        /api/bao-cao/cong-no
        /api/external/luong          (read hcns.payroll)
        /api/external/don-hang       (read muahang.purchase_orders)
        /api/external/ads            (read marketing.ads_cost)
"""
from contextlib import asynccontextmanager
from pathlib import Path
import json
import os

import sentry_sdk
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

try:
    import redis as _redis_mod  # type: ignore
except Exception:  # pragma: no cover - redis là optional dependency
    _redis_mod = None  # type: ignore

from shared.config import settings
from shared.middleware import register_error_handlers, install_sliding_session


# ─── Redis cache helper (singleton lazy init) ─────────────────────────────
# Dùng chung cho mọi hot endpoint ketoan. Key prefix "ketoan:" để tách với
# các app khác chia sẻ cùng Redis instance.
_redis = None  # type: ignore


def _get_redis():
    """Lazy singleton kết nối Redis. Fail-soft trả None nếu lỗi."""
    global _redis
    if _redis is not None:
        return _redis
    if _redis_mod is None:
        return None
    try:
        url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
        _redis = _redis_mod.Redis.from_url(  # type: ignore[attr-defined]
            url,
            socket_timeout=2,
            socket_connect_timeout=2,
            decode_responses=True,
        )
        # Ping nhẹ để chắc chắn (vẫn fail-soft nếu lỗi).
        try:
            _redis.ping()
        except Exception:
            pass
    except Exception:
        _redis = None
    return _redis


def cache_get_or_set(key: str, ttl: int, compute_fn):
    """Get JSON từ Redis hoặc compute + setex. Redis lỗi → fallback compute.

    Args:
        key: cache key (đã prefix "ketoan:").
        ttl: TTL giây.
        compute_fn: callable không tham số trả JSON-serializable.
    """
    r = _get_redis()
    if r is not None:
        try:
            raw = r.get(key)
            if raw is not None:
                try:
                    return json.loads(raw)
                except Exception:
                    pass
        except Exception:
            pass
    value = compute_fn()
    if r is not None:
        try:
            r.setex(key, int(ttl), json.dumps(value, default=str, ensure_ascii=False))
        except Exception:
            pass
    return value

# Eager-import cross-app models để tránh SQLAlchemy mapper init race (đã xảy ra
# 30/05 muahang Quote/QuoteItem + 01/06 saleadmin JournalEntry/JournalLine).
import baogia.app.models  # noqa: F401
import ketoan.app.models  # noqa: F401
from shared.routers.xin_nghi import router as xin_nghi_router
from shared.routers.duyet_chi import router as duyet_chi_router
from shared.routers.de_xuat import router as de_xuat_router
from shared.routers.tai_lieu import router as tai_lieu_router
from shared.routers.thu_vien import router as thu_vien_router
from shared.routers.giao_viec import router as giao_viec_router
from shared.routers.calendar import router as calendar_router
from hcns.app.routers.cham_cong import router as cham_cong_router
from hcns.app.routers.lenh_di_do import router as lenh_di_do_router
from hcns.app.routers.cong_trinh import router as cong_trinh_router
from hcns.app.routers.ip_config import router as ip_config_router_hcns
from hcns.app.routers.bao_cao_cong import router as bao_cao_cong_router
from hcns.app.routers.profile_avatar import router as profile_avatar_router
from hcns.app.routers.profile_workflow import router as profile_workflow_router
from hcns.app.routers.chat import router as chat_router
from shared.services.product_files import router as product_files_router

# Pre-register cross-app mappers — ketoan đọc PurchaseOrder/Supplier nhiều chỗ.
# Nếu không import full muahang.app.models, SQLAlchemy mapper sẽ fail khi
# resolve relationship `PurchaseOrder.items → POItem` (POItem chưa register).
import muahang.app.models  # noqa: F401, E402
import baogia.app.models   # noqa: F401, E402  (bridge revenue từ quote)
import marketing.app.models  # noqa: F401, E402  (bridge ads cost)
import hcns.app.models  # noqa: F401, E402  (bridge lương)
import saleadmin.app.models  # noqa: F401, E402  (cross-app DNTT phê duyệt)

from .routers import (
    doanh_thu, chi_phi, co_dinh, cong_no, so_quy,
    loai_chi_phi, tai_khoan_nh, bao_cao, external, pages,
    revenue_from_order, so_du_dau_ky, meta, cong_no_ncc, cong_no_vc,
    cong_no_from_order, uploads, products, product_attributes,
    bao_cao_can_doi, bao_cao_pnl, bao_cao_cashflow,
    khoan_vay, chi_phi_bridges, dao_tao,
    # M1 — Sản phẩm + Tồn kho
    product_category, inv_products, inventory,
    # M4 — VCSH + TK NH giao dịch
    von_csh, tai_khoan_nh_giao_dich,
    # M5 — Đóng kỳ
    ky_ke_toan,
    # M2 — BOM giá vốn
    bom,
    # Phase 2 — Double-entry journal
    journal,
    # Phase 3 — TSCĐ + Khấu hao
    tai_san,
    # Phase 6 — Phân bổ Ads + CPA
    ads_phan_bo, bao_cao_cpa,
    # Quản lý quỹ doanh nghiệp (cây)
    quy_dn,
    # Profile + đổi mật khẩu
    profile,
    # KT xác nhận cọc
    kt_duyet,
    # KT duyệt cọc BỔ SUNG (lần 2,3…) từ baogia.quote_deposits
    coc_bo_sung,
    # Báo cáo Duyệt Chi (page dashboard)
    bao_cao_duyet_chi,
    # KT phê duyệt cấp 1 Đề Nghị Thanh Toán từ saleadmin
    de_nghi_tt,
    # KT duyệt cấp 1 Đề Xuất Trả NCC từ muahang.congno
    ncc_de_xuat,
    # SePay webhook — thu tiền auto qua QR CK
    sepay,
)


_BASE_DIR = Path(__file__).resolve().parent.parent


if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=0.1,
        send_default_pii=False,
        environment=settings.app_env,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Anh Quang 2026-06-06: Auto-migrate cột so_quy.ma_don để link giao dịch
    # tới đơn báo giá (multi-cọc SUM theo ma_don).
    try:
        from sqlalchemy import text as _sa_text
        from shared.db import engine as _engine
        with _engine.begin() as _c:
            _c.execute(_sa_text(
                "ALTER TABLE ketoan.so_quy "
                "ADD COLUMN IF NOT EXISTS ma_don VARCHAR(64)"
            ))
            _c.execute(_sa_text(
                "CREATE INDEX IF NOT EXISTS ix_sq_ma_don "
                "ON ketoan.so_quy (ma_don) WHERE ma_don IS NOT NULL"
            ))
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning("auto-migrate so_quy.ma_don failed: %s", _e)

    # Anh Quang 2026-06-13: 2-cấp duyệt cho muahang.congno de_xuat_tra
    # (KT cấp 1 → CEO cấp 2). Thêm 2 cột kt_duyet_boi/kt_duyet_luc.
    try:
        from sqlalchemy import text as _sa_text
        from shared.db import engine as _engine
        with _engine.begin() as _c:
            _c.execute(_sa_text(
                "ALTER TABLE muahang.congno "
                "ADD COLUMN IF NOT EXISTS kt_duyet_boi VARCHAR(128)"
            ))
            _c.execute(_sa_text(
                "ALTER TABLE muahang.congno "
                "ADD COLUMN IF NOT EXISTS kt_duyet_luc TIMESTAMPTZ"
            ))
            _c.execute(_sa_text(
                "ALTER TABLE muahang.congno "
                "ADD COLUMN IF NOT EXISTS kt_ghi_chu TEXT"
            ))
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning("auto-migrate congno.kt_duyet failed: %s", _e)
    yield


app = FastAPI(
    title="QLPPS Kế Toán",
    version="0.1.0",
    lifespan=lifespan,
    # TẮT Swagger/OpenAPI ở prod — tránh phơi toàn bộ sơ đồ API (mọi endpoint, field
    # nội bộ) cho kẻ chưa đăng nhập. (anh Quang 2026-08-31)
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


# ── Support module (shared) ─────────────────────────────────────────
from shared.routers.support import router as support_router
app.state.app_name = 'ketoan'
app.include_router(support_router, tags=["support"])
register_error_handlers(app)
install_sliding_session(app)

# Static files (CSS/JS/fonts/icon)
_STATIC_DIR = _BASE_DIR / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


# templates/index.html:10 tro toi /manifest.webmanifest tu truoc, nhung ketoan
# chua bao gio co route nay -> production tra 404, nen "them vao man hinh chinh"
# tren iOS khong bao gio chay. File da co san la static/manifest.json; chi thieu
# dia chi va dung media_type. Doi ten file se lam hong cac tham chieu cu, nen
# phuc vu no duoi ca hai ten. (khoi phuc sau khi merge 01/09 lo tay xoa mat.)
@app.get("/manifest.webmanifest", include_in_schema=False)
def _manifest():
    return FileResponse(
        str(_STATIC_DIR / "manifest.json"),
        media_type="application/manifest+json",
    )

# HTML pages
app.include_router(pages.router, tags=["pages"])
# Anh Quang 2026-06-06: NV xem chấm công + lương cá nhân tại app ketoan
from shared.routers.payroll_me import router as payroll_me_router
app.include_router(payroll_me_router, prefix="/api/payroll", tags=["payroll_me"])
app.include_router(kt_duyet.router, tags=["kt_duyet"])
app.include_router(coc_bo_sung.router, tags=["coc_bo_sung"])
app.include_router(bao_cao_duyet_chi.router, tags=["bao_cao_duyet_chi"])
app.include_router(de_nghi_tt.router, tags=["de_nghi_tt"])
app.include_router(ncc_de_xuat.router, tags=["ncc_de_xuat"])

# API routers
app.include_router(doanh_thu.router, prefix="/api/doanh-thu", tags=["doanh_thu"])
# Bridge muahang -> ketoan (PO 'Đã giao'/'Hoàn Thành' -> ghi doanh thu)
app.include_router(
    revenue_from_order.pending_router, prefix="/api/orders", tags=["revenue_bridge"]
)
app.include_router(
    revenue_from_order.create_router, prefix="/api/doanh-thu", tags=["revenue_bridge"]
)
app.include_router(chi_phi.router, prefix="/api/chi-phi", tags=["chi_phi"])
app.include_router(chi_phi_bridges.router, prefix="/api/chi-phi", tags=["chi_phi_bridges"])
# Bridge saleadmin VC -> ketoan (VC 'da_giao'/'hoan_thanh' -> ghi chi phí + thu COD)
app.include_router(
    cong_no_vc.pending_router, prefix="/api/vc", tags=["vc_bridge"]
)
app.include_router(
    cong_no_vc.create_router, prefix="/api/chi-phi", tags=["vc_bridge"]
)
app.include_router(co_dinh.router, prefix="/api/co-dinh", tags=["co_dinh"])
# Bridge read-only: tổng hợp công nợ NCC từ muahang.congno
# QUAN TRỌNG: phải đăng ký TRƯỚC `cong_no.router` để route `/ncc-summary`
# và `/ncc/{supplier_id}/detail` không bị `/api/cong-no/{cid}` bắt nhầm.
app.include_router(cong_no_ncc.router, prefix="/api/cong-no", tags=["cong_no_ncc"])
# Bridge muahang PO → ketoan cong_no phai_tra (đăng ký TRƯỚC cong_no.router
# để /pending-payable + /from-order/{id} không bị /{cid} catch-all)
app.include_router(
    cong_no_from_order.pending_router, prefix="/api/cong-no", tags=["cong_no_bridge"]
)
app.include_router(
    cong_no_from_order.create_router, prefix="/api/cong-no", tags=["cong_no_bridge"]
)
app.include_router(cong_no.router, prefix="/api/cong-no", tags=["cong_no"])
app.include_router(so_quy.router, prefix="/api/so-quy", tags=["so_quy"])
# SePay webhook — path đầy đủ `/api/sepay/webhook` đã set trong router.
app.include_router(sepay.router, tags=["sepay"])
app.include_router(loai_chi_phi.router, prefix="/api/loai-chi-phi", tags=["loai_chi_phi"])
app.include_router(tai_khoan_nh.router, prefix="/api/tai-khoan", tags=["tai_khoan_nh"])
app.include_router(bao_cao.router, prefix="/api/bao-cao", tags=["bao_cao"])
app.include_router(bao_cao_can_doi.router, prefix="/api/bao-cao", tags=["bao_cao_can_doi"])
app.include_router(bao_cao_pnl.router, prefix="/api/bao-cao", tags=["bao_cao_pnl"])
app.include_router(bao_cao_cashflow.router, prefix="/api/bao-cao", tags=["bao_cao_cashflow"])
app.include_router(khoan_vay.router, prefix="/api/khoan-vay", tags=["khoan_vay"])
app.include_router(
    so_du_dau_ky.router, prefix="/api/so-du-dau-ky", tags=["so_du_dau_ky"]
)
app.include_router(meta.router, prefix="/api/meta", tags=["meta"])
app.include_router(products.router, prefix="/api/products", tags=["products"])
app.include_router(
    product_attributes.router,
    prefix="/api/product-attributes",
    tags=["product_attributes"],
)
app.include_router(external.router, prefix="/api/external", tags=["external"])

# ─── M1: Sản phẩm + Tồn kho ───────────────────────────────────────────────
app.include_router(product_category.router, prefix="/api/product-category", tags=["product_category"])
app.include_router(inv_products.router, prefix="/api/product", tags=["inv_products"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["inventory"])

# ─── M4: VCSH + Quỹ DN + TK NH giao dịch ──────────────────────────────────
app.include_router(von_csh.router, prefix="/api/von-csh", tags=["von_csh"])
app.include_router(von_csh.quy_router, prefix="/api/quy-dn", tags=["quy_dn"])
# QUAN TRỌNG: đăng ký TRƯỚC khi xét lại tai_khoan_nh để các route /{tk_id}/giao-dich
# và /giao-dich/{gd_id} không bị /{rid} (PUT/DELETE TK) catch-all.
# (tai_khoan_nh.router đã đăng ký phía trên — giao_dich đăng ký SAU vì FastAPI
# match theo thứ tự nhưng paths của giao_dich đặc thù hơn (`/{tk_id}/giao-dich`),
# không trùng pattern PUT /{rid} của tai_khoan_nh.)
app.include_router(tai_khoan_nh_giao_dich.router, prefix="/api/tai-khoan", tags=["tai_khoan_nh_gd"])

# ─── M5: Đóng kỳ kế toán ──────────────────────────────────────────────────
app.include_router(ky_ke_toan.router, prefix="/api/ky-ke-toan", tags=["ky_ke_toan"])

# ─── M2: BOM giá vốn ──────────────────────────────────────────────────────
app.include_router(bom.router, prefix="/api/bom", tags=["bom"])

# ─── Phase 2: Double-entry journal ────────────────────────────────────────
app.include_router(journal.router, prefix="/api/journal", tags=["journal"])

# ─── Phase 3: TSCĐ + Khấu hao ─────────────────────────────────────────────
app.include_router(tai_san.router, prefix="/api/tai-san", tags=["tai_san"])

# ─── Phase 6: Phân bổ Ads + CPA report ───────────────────────────────────
app.include_router(ads_phan_bo.router, prefix="/api/ads-phan-bo", tags=["ads_phan_bo"])
app.include_router(bao_cao_cpa.router, prefix="/api/bao-cao", tags=["bao_cao_cpa"])

# ─── Quản lý quỹ doanh nghiệp ────────────────────────────────────────────
app.include_router(quy_dn.router, prefix="/api/quy", tags=["quy"])
# Giao dịch quỹ (thu/chi audit trail) — mount cùng prefix với von_csh.quy_router
app.include_router(quy_dn.giao_dich_router, prefix="/api/quy-dn", tags=["quy_dn_gd"])

# Profile + đổi mật khẩu (FE topbar mở modal)
app.include_router(profile.router, tags=["profile"])

# Đào tạo (cross-schema marketing.dao_tao_sessions)
app.include_router(dao_tao.router, prefix="/api/dao-tao", tags=["dao-tao"])
# Local file uploads (hóa đơn / chứng từ) — routes có full path tự khai báo
app.include_router(uploads.router, tags=["uploads"])
# Serve ảnh sản phẩm cross-app
app.include_router(product_files_router, tags=["product_files"])
# Xin Nghỉ — cross-app leave request system
app.include_router(xin_nghi_router, prefix="/api/xin-nghi", tags=["xin-nghi"])
# Duyệt Chi — cross-app expense request system
app.include_router(duyet_chi_router, prefix="/api/duyet-chi", tags=["duyet-chi"])
app.include_router(de_xuat_router, prefix="/api/de-xuat", tags=["de-xuat"])
app.include_router(tai_lieu_router, prefix="/api/tai-lieu", tags=["tai-lieu"])  # van ban cong ty dung chung 8 app (12/09/2026)
app.include_router(thu_vien_router, prefix="/api/thu-vien", tags=["thu-vien"])  # thu vien dao tao dung chung 8 app (12/09/2026)
# Giao Việc — cross-app
app.include_router(giao_viec_router, prefix="/api/giao-viec", tags=["giao-viec"])
# Lịch Làm Việc — cross-app calendar
app.include_router(calendar_router, prefix="/api/calendar", tags=["calendar"])
app.include_router(cham_cong_router,      prefix="/api/cham-cong",    tags=["cham_cong"])
app.include_router(profile_workflow_router, prefix="/api/profile-workflow", tags=["profile_workflow"])
app.include_router(lenh_di_do_router,     prefix="/api/lenh-di-do",   tags=["lenh_di_do"])
app.include_router(cong_trinh_router,     prefix="/api/cong-trinh",   tags=["cong_trinh"])
app.include_router(ip_config_router_hcns, prefix="/api/ip-config",    tags=["ip_config"])
app.include_router(bao_cao_cong_router,   prefix="/api/bao-cao-cong", tags=["bao_cao_cong"])
app.include_router(profile_avatar_router, prefix="/api/profile",      tags=["profile"])
app.include_router(chat_router,           prefix="/api/chat",          tags=["chat"])


@app.get("/health")
def health():
    return {"status": "ok"}  # KHÔNG lộ service/env cho endpoint public (2026-08-31)





# ── Demo masking (che chỉ số kinh doanh cho tài khoản demo) — gắn NGOÀI CÙNG ──
from shared.middleware.demo_mask import install_demo_masking as _install_demo_masking  # noqa: E402
_install_demo_masking(app)
