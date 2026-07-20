"""Models schema `shared` — dùng chung mọi app.

Import all để Alembic autogenerate detect tất cả models của schema shared.
"""
from .user import User
from .audit_log import AuditLog
from .session import Session as SessionModel
from .app_config import AppConfig
from .approval import Approval
from .directive import Directive
from .ceo_comment import CeoComment
from .feedback import Feedback
from .opportunity import ProductOpportunity, OpportunityNote, OpportunityScorecard
from .product import Product, ProductAddon
from .product_attribute import ProductAttribute
from .notification import Notification
from .push_subscription import PushSubscription
from .mobile_device import MobileDevice
from .leave_request import LeaveRequest
from .expense_request import ExpenseRequest
from .calendar_event import CalendarEvent, EventParticipant, EventAttachment
from .morning_brief import MorningBrief
from .ai_chat_message import AIChatMessage
from .mai_target import MaiTarget
from .mai_preference import MaiPreference
from .mai_policy import MaiPolicy
from .mai_proposal import MaiProposal
from .mai_notified_item import MaiNotifiedItem
from .mai_interaction import MaiInteraction, NVActivity
from .mai_auto_decision import MaiAutoDecision
from .mai_kd import (  # noqa: F401  — đăng ký vào Base.metadata cho Alembic
    MaiFeatureConfig, MaiPersona, MaiCustomerExclude,
    MaiGeneratedMessage, MaiPromotionUsed, MaiActionLog,
)
from .zns_send_log import ZNSSendLog
from .zns_template_draft import ZNSTemplateDraft

__all__ = [
    "User", "AuditLog", "SessionModel", "AppConfig",
    "Approval", "Directive", "CeoComment", "Feedback",
    "ProductOpportunity", "OpportunityNote", "OpportunityScorecard",
    "Product", "ProductAddon", "ProductAttribute",
    "Notification", "PushSubscription", "MobileDevice",
    "LeaveRequest", "ExpenseRequest",
    "CalendarEvent", "EventParticipant", "EventAttachment",
    "MorningBrief", "AIChatMessage",
    "MaiTarget", "MaiPreference", "MaiPolicy", "MaiProposal", "MaiNotifiedItem",
    "MaiInteraction", "NVActivity", "MaiAutoDecision",
    "MaiFeatureConfig", "MaiPersona", "MaiCustomerExclude",
    "MaiGeneratedMessage", "MaiPromotionUsed", "MaiActionLog",
    "ZNSSendLog", "ZNSTemplateDraft",
]
