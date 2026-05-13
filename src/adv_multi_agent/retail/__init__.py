"""
retail — adversarial multi-agent workflows for retail decision support.
"""
from .workflows.demand_forecasting import DemandForecastWorkflow, ForecastRequest

__all__ = [
    "DemandForecastWorkflow",
    "ForecastRequest",
]
