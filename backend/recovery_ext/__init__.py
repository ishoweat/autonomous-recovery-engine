"""
Recovery Extension Package for Autonomous Recovery Engine.
Provides additive persistence, durable event schemas, and phase feature flag control.
"""

from backend.recovery_ext.flags import get_flags, ExtFlags

__all__ = ["get_flags", "ExtFlags"]
