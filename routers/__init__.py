"""
API Routers for the RAG Service
"""

from .rag import router as rag_router
from .llm import router as llm_router
from .sms import router as sms_router
from .crm import router as crm_router

__all__ = [
    "rag_router",
    "llm_router",
    "sms_router",
    "crm_router",
]
