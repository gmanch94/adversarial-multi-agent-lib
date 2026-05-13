"""
retail — adversarial multi-agent workflows for retail decision support.
"""
from .workflows.demand_forecasting import DemandForecastWorkflow, ForecastRequest
from .workflows.inventory_replenishment import (
    InventoryReplenishmentRequest,
    InventoryReplenishmentWorkflow,
)
from .workflows.labor_scheduling import LaborSchedulingWorkflow, SchedulingRequest
from .workflows.loyalty_offer import LoyaltyOfferRequest, LoyaltyOfferWorkflow
from .workflows.private_label import PrivateLabelRequest, PrivateLabelWorkflow
from .workflows.promo_markdown import PromoMarkdownWorkflow, PromoRequest
from .workflows.recall_scope import RecallRequest, RecallScopeWorkflow
from .workflows.supplier_brief import SupplierBriefRequest, SupplierBriefWorkflow

__all__ = [
    "DemandForecastWorkflow",
    "ForecastRequest",
    "InventoryReplenishmentRequest",
    "InventoryReplenishmentWorkflow",
    "LaborSchedulingWorkflow",
    "LoyaltyOfferRequest",
    "LoyaltyOfferWorkflow",
    "PrivateLabelRequest",
    "PrivateLabelWorkflow",
    "PromoMarkdownWorkflow",
    "PromoRequest",
    "RecallRequest",
    "RecallScopeWorkflow",
    "SchedulingRequest",
    "SupplierBriefRequest",
    "SupplierBriefWorkflow",
]
