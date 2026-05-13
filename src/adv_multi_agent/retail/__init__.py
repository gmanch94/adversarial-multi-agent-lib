"""
retail — adversarial multi-agent workflows for retail decision support.
"""
from .workflows.demand_forecasting import DemandForecastWorkflow, ForecastRequest
from .workflows.labor_scheduling import LaborSchedulingWorkflow, SchedulingRequest

__all__ = [
    "DemandForecastWorkflow",
    "ForecastRequest",
    "LaborSchedulingWorkflow",
    "SchedulingRequest",
]
