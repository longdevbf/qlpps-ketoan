"""Pydantic schemas — InvProductCategory (M1 cây danh mục SP)."""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field


class InvProductCategoryBase(BaseModel):
    ma_nhom: str = Field(..., max_length=32)
    ten_nhom: str = Field(..., max_length=128)
    parent_id: Optional[int] = None
    display_order: int = 0
    active: bool = True


class InvProductCategoryCreate(InvProductCategoryBase):
    pass


class InvProductCategoryUpdate(BaseModel):
    ma_nhom: Optional[str] = None
    ten_nhom: Optional[str] = None
    parent_id: Optional[int] = None
    display_order: Optional[int] = None
    active: Optional[bool] = None


class InvProductCategoryOut(InvProductCategoryBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class InvProductCategoryNode(InvProductCategoryOut):
    """Tree node — embed children recursively."""
    children: List["InvProductCategoryNode"] = Field(default_factory=list)
    product_count: int = 0


InvProductCategoryNode.model_rebuild()
