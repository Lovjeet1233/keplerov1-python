"""
Centralized Pydantic models for the RAG Service API
"""

from .model import (
    # Common models
    StatusResponse,
    
    # RAG models
    ChatRequest,
    ChatResponse,
    DataIngestionRequest,
    CreateCollectionRequest,
    DeleteCollectionRequest,
    
    # Calls models
    OutboundCallRequest,
    
    # LLM models
    ElaboratePromptRequest,
    ElaboratePromptResponse,
    
    # SMS models
    SMSRequest,
    SMSResponse,
    
    # Email models
    EmailRequest,
    EmailResponse,
    
    # Bulk Communication models
    Contact,
    SMSBody,
    EmailBody,
    BulkCommunicationRequest,
    ContactResult,
    BulkCommunicationResponse,
    
    # Tool Registration models
    ToolProperty,
    RegisterToolRequest,
    RegisterToolResponse,
    DeleteToolRequest,
    DeleteToolResponse,
)

__all__ = [
    # Common
    "StatusResponse",
    
    # RAG
    "ChatRequest",
    "ChatResponse",
    "DataIngestionRequest",
    "CreateCollectionRequest",
    "DeleteCollectionRequest",
    
    # Calls
    "OutboundCallRequest",
    
    # LLM
    "ElaboratePromptRequest",
    "ElaboratePromptResponse",
    
    # SMS
    "SMSRequest",
    "SMSResponse",
    
    # Email
    "EmailRequest",
    "EmailResponse",
    
    # Bulk Communication
    "Contact",
    "SMSBody",
    "EmailBody",
    "BulkCommunicationRequest",
    "ContactResult",
    "BulkCommunicationResponse",
    
    # Tool Registration
    "ToolProperty",
    "RegisterToolRequest",
    "RegisterToolResponse",
    "DeleteToolRequest",
    "DeleteToolResponse",
]

