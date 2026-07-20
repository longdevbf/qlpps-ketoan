"""LoaiChiPhi — danh mục loại chi phí (port từ `loai_chi_phi.json`)."""
from typing import Optional

from sqlalchemy import String, Boolean, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


class LoaiChiPhi(Base):
    __tablename__ = "loai_chi_phi"
    __table_args__ = ({"schema": "ketoan"},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ten: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    mo_ta: Mapped[Optional[str]] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    # Mặc định nhóm chức năng cho P&L — FE auto-fill khi tạo CP
    # Values: 'ban_hang' | 'quan_ly' | 'tai_chinh' | 'khac'
    nhom_default: Mapped[Optional[str]] = mapped_column(
        String(20), server_default="khac", nullable=True
    )

    def __repr__(self) -> str:
        return f"<LoaiChiPhi {self.id} {self.ten!r}>"
