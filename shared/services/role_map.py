"""Map phong_ban + chuc_vu → (role, apps[]) cho việc tự gán quyền khi sync user.

Dùng bởi:
- HCNS auto-sync khi tạo employee mới → tạo shared.users
- Admin UI khi tạo NV (gợi ý apps mặc định)

Logic:
- chuc_vu chứa "CEO" / "Giám Đốc" → role=ceo, apps=tất cả
- chuc_vu chứa "Manager" / "Quản Lý" → role=manager, apps=tất cả
- phong_ban quyết định role + apps cụ thể.
"""
from __future__ import annotations

ALL_APPS = ["baogia", "marketing", "muahang", "hcns", "ketoan", "saleadmin", "congnghe"]


# phong_ban (lowercase, không dấu) → (role, apps)
# Exact match ưu tiên. Nếu không match exact → substring match qua
# `_FUZZY_KEYS` (vd "Kinh Doanh Bán Lẻ Nhóm 1" → match "kinh doanh").
_PHONG_BAN_MAP: dict[str, tuple[str, list[str]]] = {
    # Chính sách (anh Quang 2026-07-15): NV chỉ vào app phòng MÌNH; app khác
    # chỉ khi tích KIÊM NHIỆM (phong_ban_phu). KD chỉ còn baogia (bỏ marketing).
    "kinh doanh":     ("kd",  ["baogia"]),
    "marketing":      ("mkt", ["marketing"]),
    "mua hang":       ("mh",  ["muahang"]),
    "ke toan":        ("kt",  ["ketoan"]),
    "sale admin":     ("sa",  ["saleadmin"]),
    # Kho Vận (giao vận) dùng app saleadmin để quản lý giao vận.
    "kho van":        ("nhan_vien", ["saleadmin"]),
    "hcns":           ("hr",  ["hcns"]),
    "nhan su":        ("hr",  ["hcns"]),
    # Hành Chính + Pháp Chế: cùng app HCNS (chính sách CEO chốt 2026-04-28)
    "hanh chinh":     ("nhan_vien", ["hcns"]),
    "phap che":       ("nhan_vien", ["hcns"]),
    "cong nghe":      ("nhan_vien", ["congnghe"]),
    "quan ly":        ("manager", ALL_APPS),
    "ban quan ly":    ("manager", ALL_APPS),
    "ban giam doc":   ("ceo", ALL_APPS),
}

# Substring keywords cho phòng con. Order quan trọng — key dài match trước.
_FUZZY_KEYS: list[tuple[str, str]] = [
    ("ban giam doc", "ban giam doc"),
    ("ban quan ly",  "ban quan ly"),
    ("kinh doanh",   "kinh doanh"),     # KD Bán Lẻ Nhóm X → kinh doanh
    ("quang cao",    "marketing"),      # Quảng Cáo Ads → marketing
    ("media",        "marketing"),      # Media / Designer → marketing
    ("tu van",       "marketing"),      # Tư Vấn - Lễ Tân → marketing
    ("le tan",       "marketing"),
    ("kien truc",    "marketing"),      # Kiến Trúc - Thiết Kế → marketing
    ("thiet ke",     "marketing"),
    ("marketing",    "marketing"),
    ("mua hang",     "mua hang"),
    ("ke toan",      "ke toan"),
    ("sale admin",   "sale admin"),
    ("kho van",      "kho van"),
    ("cong nghe",    "cong nghe"),
    ("hcns",         "hcns"),
    ("nhan su",      "nhan su"),
    ("hanh chinh",   "hanh chinh"),
    ("phap che",     "phap che"),
]


def _normalize(s: str) -> str:
    """Lowercase + bỏ dấu Việt cơ bản."""
    if not s:
        return ""
    s = s.lower().strip()
    table = str.maketrans(
        "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ",
        "aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd",
    )
    return s.translate(table)


def map_employee_to_role_apps(
    phong_ban: str | None,
    chuc_vu: str | None = None,
) -> tuple[str, list[str]]:
    """Trả (role, apps) cho 1 NV.

    Ưu tiên: chuc_vu CEO/Manager > phong_ban map > default ('nhan_vien', []).
    """
    cv = _normalize(chuc_vu or "")
    if any(k in cv for k in ("ceo", "giam doc", "tong giam doc")):
        return ("ceo", ALL_APPS)
    if any(k in cv for k in ("manager", "quan ly", "truong phong")):
        # Manager phòng ban — vẫn map theo phong_ban để xác định scope
        pb = _normalize(phong_ban or "")
        if pb in _PHONG_BAN_MAP:
            _, apps = _PHONG_BAN_MAP[pb]
            return ("manager", apps)
        # Manager phòng con (vd "KD Bán Lẻ Nhóm 1") → fuzzy match
        for kw, target_key in _FUZZY_KEYS:
            if kw in pb:
                _, apps = _PHONG_BAN_MAP[target_key]
                return ("manager", apps)
        return ("manager", ALL_APPS)

    pb = _normalize(phong_ban or "")
    if pb in _PHONG_BAN_MAP:
        return _PHONG_BAN_MAP[pb]
    # Fuzzy: phòng con như "Kinh Doanh Bán Lẻ Nhóm 1" → match "kinh doanh"
    for kw, target_key in _FUZZY_KEYS:
        if kw in pb:
            return _PHONG_BAN_MAP[target_key]
    # Fallback: NV không thuộc phòng nào rõ → role=nhan_vien, apps=[]
    return ("nhan_vien", [])


def parse_phong_ban_phu(value) -> list[str]:
    """`phong_ban_phu` lưu CSV 'Marketing, Kế Toán' (hoặc list) → list tên phòng."""
    if not value:
        return []
    items = value if isinstance(value, (list, tuple)) else str(value).split(",")
    return [str(s).strip() for s in items if s and str(s).strip()]


def apps_for_employee(
    phong_ban: str | None,
    chuc_vu: str | None = None,
    phong_ban_phu=None,
) -> tuple[str, list[str]]:
    """(role, apps) cho 1 NV — apps = HỢP của phòng CHÍNH + các phòng KIÊM NHIỆM.

    `role` giữ theo phòng chính (qua `map_employee_to_role_apps`). `apps` gộp
    thêm app của từng phòng trong `phong_ban_phu` để 1 NV vào được nhiều phòng ban.
    """
    role, apps = map_employee_to_role_apps(phong_ban, chuc_vu)
    merged = list(apps)
    for pb in parse_phong_ban_phu(phong_ban_phu):
        _, extra = map_employee_to_role_apps(pb, None)
        for a in extra:
            if a not in merged:
                merged.append(a)
    return role, merged


# Test self
if __name__ == "__main__":
    cases = [
        ("Kinh Doanh", "NV KD",        ("kd", ["baogia"])),
        ("Marketing",  "NV Marketing", ("mkt", ["marketing"])),
        ("Mua Hàng",   "NV Mua hàng",  ("mh", ["muahang"])),
        ("Kế Toán",    "Kế toán viên", ("kt", ["ketoan"])),
        ("Sale Admin", "NV SaleAdmin", ("sa", ["saleadmin"])),
        ("HCNS",       "Chuyên viên HCNS", ("hr", ["hcns"])),
        ("Quản Lý",    "Manager",      ("manager", ALL_APPS)),
        ("Ban Giám Đốc","CEO",         ("ceo", ALL_APPS)),
        ("Kinh Doanh", "Manager",      ("manager", ["baogia"])),
        ("",           "",             ("nhan_vien", [])),
    ]
    for pb, cv, expected in cases:
        got = map_employee_to_role_apps(pb, cv)
        status = "✓" if got == expected else "✗"
        print(f"  {status} {pb:15} / {cv:18} → {got}  (expected {expected})")
