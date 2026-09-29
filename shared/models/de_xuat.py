"""DeXuat — nhân viên đề xuất công việc lên cấp trên.

Khác `ExpenseRequest` (Duyệt Chi) ở chỗ: đề xuất KHÔNG phải xin tiền mà xin
làm một việc. Nên chuỗi duyệt ngắn hơn (Manager → CEO thay vì Manager → Kế
Toán → CEO) và duyệt xong thì **sinh ra một `Directive` thật** để việc có
người theo dõi tới lúc xong — xem `shared/routers/de_xuat.py`.

`directive_id` là chỗ khép vòng đó. Không có nó thì đề xuất được duyệt cũng
chỉ nằm im trong bảng, không ai biết có làm hay không.

Chuỗi cấp duyệt (anh Quang chốt 28/08/2026):
    manager → ceo → done          (ceo CHỈ khi cần, xem `_can_ceo()`)
    bất kỳ cấp nào reject         → rejected

Vì sao chỉ lên CEO khi cần: bắt mọi đề xuất qua CEO thì hộp thư CEO ngập và
việc nhỏ chạy chậm. Ba dấu hiệu đẩy lên CEO — có ngân sách, ảnh hưởng nhiều
phòng, hoặc người gửi chủ động xin ý kiến.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class DeXuat(Base):
    __tablename__ = "de_xuat"
    __table_args__ = (
        Index("ix_de_xuat_username", "username"),
        Index("ix_de_xuat_trang_thai", "trang_thai"),
        Index("ix_de_xuat_approval_level", "approval_level"),
        Index("ix_de_xuat_phong_ban", "phong_ban"),
        Index("ix_de_xuat_created", "created_at"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # ── Người gửi + bối cảnh: quyết định AI là người duyệt ────────────────
    # Hệ không có cây tổ chức (không cột manager_username ở đâu cả), nên cấp
    # trên được suy từ role + phong_ban + apps y hệt Duyệt Chi. Chép lại 3
    # trường này lúc tạo để về sau đổi phòng không làm lệch lịch sử duyệt.
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    ho_ten: Mapped[str] = mapped_column(String(128), nullable=False)
    phong_ban: Mapped[Optional[str]] = mapped_column(String(128))
    app_name: Mapped[str] = mapped_column(String(32), nullable=False)

    # ── Nội dung đề xuất ──────────────────────────────────────────────────
    tieu_de: Mapped[str] = mapped_column(String(256), nullable=False)
    loai: Mapped[str] = mapped_column(String(32), nullable=False)  # xem _LOAI_LABELS
    noi_dung: Mapped[str] = mapped_column(Text, nullable=False)
    # Bắt buộc: "duyệt xong thì đạt được gì, đo bằng gì". Ép người gửi nghĩ
    # trước, và cho người duyệt căn cứ để quyết trong 30 giây.
    ket_qua_ky_vong: Mapped[str] = mapped_column(Text, nullable=False)

    muc_do: Mapped[str] = mapped_column(String(8), server_default="trung", nullable=False)
    han_mong_muon: Mapped[Optional[date]] = mapped_column(Date)

    # ── Ba dấu hiệu đẩy lên CEO ───────────────────────────────────────────
    # NULL/0 = không tốn tiền. Có số > 0 → bắt buộc CEO chốt.
    ngan_sach_du_kien: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 0))
    lien_phong_ban: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )
    xin_y_kien_ceo: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )

    # List[str] URL. "[]" thuần — SQLAlchemy tự bọc nháy khi sinh DDL; viết
    # "'[]'" sẽ thành '''[]''' (JSON hỏng) lúc create_all.
    tep_dinh_kem: Mapped[list] = mapped_column(
        JSONB, server_default="[]", nullable=False
    )

    # ── Trạng thái duyệt ──────────────────────────────────────────────────
    trang_thai: Mapped[str] = mapped_column(
        String(32), server_default="cho_duyet", nullable=False
    )  # cho_duyet | da_duyet | tu_choi | huy
    approval_level: Mapped[str] = mapped_column(
        String(16), server_default="manager", nullable=False
    )  # manager | ceo | done | rejected
    approval_history: Mapped[list] = mapped_column(
        JSONB, server_default="[]", nullable=False
    )

    # Người duyệt GẦN NHẤT — tiện cho danh sách khỏi phải bới approval_history
    nguoi_duyet: Mapped[Optional[str]] = mapped_column(String(64))
    ho_ten_nguoi_duyet: Mapped[Optional[str]] = mapped_column(String(128))
    nhan_xet_duyet: Mapped[Optional[str]] = mapped_column(Text)
    ngay_duyet: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # ── Khép vòng ─────────────────────────────────────────────────────────
    # id của shared.directives sinh ra khi duyệt xong. Cố ý KHÔNG đặt
    # ForeignKey: xoá một task cũ không được phép làm hỏng lịch sử đề xuất.
    directive_id: Mapped[Optional[int]] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<DeXuat {self.id} {self.username!r} {self.trang_thai} @{self.approval_level}>"
