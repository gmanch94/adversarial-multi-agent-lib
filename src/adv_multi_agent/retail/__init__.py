"""
retail — adversarial multi-agent workflows for retail decision support.
"""
from .workflows.demand_forecasting import DemandForecastWorkflow, ForecastRequest
from .workflows.labor_scheduling import LaborSchedulingWorkflow, SchedulingRequest
from .workflows.recall_scope import RecallRequest, RecallScopeWorkflow

__all__ = [
    "DemandForecastWorkflow",
    "ForecastRequest",
    "LaborSchedulingWorkflow",
    "SchedulingRequest",
    "RecallRequest",
    "RecallScopeWorkflow",
]
