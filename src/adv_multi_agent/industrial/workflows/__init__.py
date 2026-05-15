"""Industrial workflow implementations (MVP-8 per D-IND-1).

Manufacturing Ops:
- MakeVsBuyWorkflow                — triple-flag (COST / CAPABILITY / IP-LEAK)
- SupplierQualificationWorkflow    — triple-flag (FINANCIAL / QUALITY / GEO-CONCENTRATION)
- EngineeringChangeOrderWorkflow   — triple-flag (SUPERSESSION / FMEA-DELTA / REGRESSION)
- QualityIncidentRootCauseWorkflow — triple-flag (CAUSAL-CHAIN / CONTAINMENT / SYSTEMIC)

Safety / Recall / Reserve:
- ProductLiabilityRootCauseWorkflow — veto + triple-flag
                                       (DESIGN-DEFECT / OPERATOR-ERROR / WARNING-ADEQUACY)
- RecallScopeManufacturingWorkflow — veto + triple-flag
                                       (TRIGGER-EVIDENCE / FLEET-SCOPE / REGULATORY-NOTIFY)

Strategic Capital:
- SupplyChainResilienceWorkflow    — triple-flag
                                       (SINGLE-SOURCE / GEO-CONCENTRATION / LEAD-TIME-FRAGILITY)

Industrial IoT:
- TelematicsAnomalyTriageWorkflow  — triple-flag
                                       (SIGNAL-EVIDENCE / FALSE-POSITIVE-COST / ACTIONABILITY)
"""

from .engineering_change_order import (
    EngineeringChangeOrderRequest,
    EngineeringChangeOrderWorkflow,
)
from .make_vs_buy import MakeVsBuyRequest, MakeVsBuyWorkflow
from .product_liability_root_cause import (
    ProductLiabilityRootCauseRequest,
    ProductLiabilityRootCauseWorkflow,
)
from .quality_incident_root_cause import (
    QualityIncidentRootCauseRequest,
    QualityIncidentRootCauseWorkflow,
)
from .recall_scope_manufacturing import (
    RecallScopeManufacturingRequest,
    RecallScopeManufacturingWorkflow,
)
from .supplier_qualification import (
    SupplierQualificationRequest,
    SupplierQualificationWorkflow,
)
from .supply_chain_resilience import (
    SupplyChainResilienceRequest,
    SupplyChainResilienceWorkflow,
)
from .telematics_anomaly_triage import (
    TelematicsAnomalyTriageRequest,
    TelematicsAnomalyTriageWorkflow,
)

__all__ = [
    "EngineeringChangeOrderRequest",
    "EngineeringChangeOrderWorkflow",
    "MakeVsBuyRequest",
    "MakeVsBuyWorkflow",
    "ProductLiabilityRootCauseRequest",
    "ProductLiabilityRootCauseWorkflow",
    "QualityIncidentRootCauseRequest",
    "QualityIncidentRootCauseWorkflow",
    "RecallScopeManufacturingRequest",
    "RecallScopeManufacturingWorkflow",
    "SupplierQualificationRequest",
    "SupplierQualificationWorkflow",
    "SupplyChainResilienceRequest",
    "SupplyChainResilienceWorkflow",
    "TelematicsAnomalyTriageRequest",
    "TelematicsAnomalyTriageWorkflow",
]
