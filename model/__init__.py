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
    EcommerceCredentials,
    EmailToolCredentials,
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
    
    # SIP Trunk Setup models
    CreateSIPTrunkRequest,
    CreateSIPTrunkResponse,
    CreateLiveKitTrunkRequest,
    CreateLiveKitTrunkResponse,
    CreateGenericSIPTrunkRequest,
    CreateGenericSIPTrunkResponse,
    CreateInboundTrunkRequest,
    CreateInboundTrunkResponse,
    AgentConfig,
    RoomConfig,
    CreateDispatchRuleRequest,
    CreateDispatchRuleResponse,
    SetupInboundSIPRequest,
    SetupInboundSIPResponse,
)

from .tool_assignment_models import (
    AssignToolRequest,
    UpdateAssignmentRequest,
    AssignToolResponse,
    DeleteAssignmentRequest,
    DeleteAssignmentResponse,
    BulkEnableToolsRequest,
    BulkEnableToolsResponse,
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
    "EcommerceCredentials",
    "EmailToolCredentials",
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
    
    # SIP Trunk Setup
    "CreateSIPTrunkRequest",
    "CreateSIPTrunkResponse",
    "CreateLiveKitTrunkRequest",
    "CreateLiveKitTrunkResponse",
    "CreateGenericSIPTrunkRequest",
    "CreateGenericSIPTrunkResponse",
    "CreateInboundTrunkRequest",
    "CreateInboundTrunkResponse",
    "AgentConfig",
    "RoomConfig",
    "CreateDispatchRuleRequest",
    "CreateDispatchRuleResponse",
    "SetupInboundSIPRequest",
    "SetupInboundSIPResponse",
    
    # Tool Assignments
    "AssignToolRequest",
    "UpdateAssignmentRequest",
    "AssignToolResponse",
    "DeleteAssignmentRequest",
    "DeleteAssignmentResponse",
    "BulkEnableToolsRequest",
    "BulkEnableToolsResponse",
]

