"""
CRM Integration Module for Kepler v1
Provides CRM tool registration and execution capabilities.
"""

from .crm_client import CRMClient
from .crm_tools import (
    build_crm_search_tool,
    build_crm_create_tool,
    build_crm_update_tool,
)
from .schemas import (
    CRMFieldSchema,
    RegisterCRMSearchToolRequest,
    RegisterCRMCreateToolRequest,
    RegisterCRMUpdateToolRequest,
)

__all__ = [
    "CRMClient",
    "build_crm_search_tool",
    "build_crm_create_tool",
    "build_crm_update_tool",
    "CRMFieldSchema",
    "RegisterCRMSearchToolRequest",
    "RegisterCRMCreateToolRequest",
    "RegisterCRMUpdateToolRequest",
]
