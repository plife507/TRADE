"""
Risk management modules for global portfolio and account-level risk analysis.

This package provides:
- GlobalRiskView: Centralized risk analysis service
- RiskDecision: Pre-trade risk check results
- Risk threshold configuration

Usage:
    from src.risk import GlobalRiskView, get_global_risk_view
    
    risk_view = get_global_risk_view()
    snapshot = risk_view.build_snapshot()
    decision = risk_view.check_pre_trade(signal)
"""

from .global_risk import (
    GlobalRiskView,
    RiskDecision,
    get_global_risk_view,
)

__all__ = [
    "GlobalRiskView",
    "RiskDecision",
    "get_global_risk_view",
]

