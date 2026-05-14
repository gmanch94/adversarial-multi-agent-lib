"""P&C workflow implementations.

Foundational (mainstream commercial):
- ClaimsReserveWorkflow            — veto + triple-flag (RESERVE / PRECEDENT / LITIGATION)
- CoverageDecisionWorkflow         — veto + dual-flag (WORDING / CASE-LAW)
- CommercialUnderwritingWorkflow   — triple-flag (LOSS-COST / EXCLUSION / CAPACITY)
- CyberUnderwritingWorkflow        — triple-flag (CONTROL-GAP / SUB-LIMIT / AGGREGATION)

Specialty lines (D-PC-6):
- EnvironmentalImpairmentWorkflow  — veto + triple-flag (KNOWN-CONDITION / TAIL / REGULATORY-OVERLAP)
- ParametricCropWorkflow           — triple-flag (PERIL-MATCH / BASIS / ATTACHMENT)
- GigPlatformLiabilityWorkflow     — veto + triple-flag (CLASSIFICATION / COVERAGE-GAP / REGULATORY-PATCHWORK)
"""

from .claims_reserve import ClaimsReserveRequest, ClaimsReserveWorkflow
from .commercial_underwriting import (
    CommercialUnderwritingRequest,
    CommercialUnderwritingWorkflow,
)
from .coverage_decision import CoverageDecisionRequest, CoverageDecisionWorkflow
from .cyber_underwriting import CyberUnderwritingRequest, CyberUnderwritingWorkflow
from .environmental_impairment import (
    EnvironmentalImpairmentRequest,
    EnvironmentalImpairmentWorkflow,
)
from .gig_platform_liability import (
    GigPlatformLiabilityRequest,
    GigPlatformLiabilityWorkflow,
)
from .parametric_crop import ParametricCropRequest, ParametricCropWorkflow

__all__ = [
    "ClaimsReserveRequest",
    "ClaimsReserveWorkflow",
    "CommercialUnderwritingRequest",
    "CommercialUnderwritingWorkflow",
    "CoverageDecisionRequest",
    "CoverageDecisionWorkflow",
    "CyberUnderwritingRequest",
    "CyberUnderwritingWorkflow",
    "EnvironmentalImpairmentRequest",
    "EnvironmentalImpairmentWorkflow",
    "GigPlatformLiabilityRequest",
    "GigPlatformLiabilityWorkflow",
    "ParametricCropRequest",
    "ParametricCropWorkflow",
]
