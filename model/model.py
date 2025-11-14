"""
Pydantic models for the RAG Service API
All request and response models are centralized here for better organization and reusability.
"""

from pydantic import BaseModel
from typing import Optional


# ============================================================================
# COMMON MODELS
# ============================================================================

class StatusResponse(BaseModel):
    """Generic status response model used across multiple endpoints."""
    status: str
    message: str
    details: Optional[dict] = None
    transcript: Optional[dict] = None  # Added for call transcripts


# ============================================================================
# RAG MODELS
# ============================================================================

class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    query: str
    collection_name: str
    top_k: Optional[int] = 5
    thread_id: Optional[str] = None
    system_prompt: Optional[str] = None


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    query: str
    answer: str
    retrieved_docs: list
    context: Optional[str] = None
    thread_id: Optional[str] = None


class DataIngestionRequest(BaseModel):
    """Request model for data ingestion endpoint."""
    collection_name: str
    url_link: Optional[str] = None
    source_type: str  # 'url', 'pdf', or 'excel'


class CreateCollectionRequest(BaseModel):
    """Request model for creating a collection."""
    collection_name: str


class DeleteCollectionRequest(BaseModel):
    """Request model for deleting a collection."""
    collection_name: str


# ============================================================================
# CALLS MODELS
# ============================================================================

class OutboundCallRequest(BaseModel):
    """Request model for initiating an outbound call."""
    phone_number: str
    name: Optional[str] = None
    dynamic_instruction: Optional[str] = None
    language: Optional[str] = "en"  # TTS language (e.g., "en", "es", "fr")
    voice_id: Optional[str] = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs voice ID (default: Rachel)
    sip_trunk_id: Optional[str] = None  # SIP trunk ID (uses env variable if not provided)
    transfer_to: Optional[str] = None  # Phone number to transfer to (e.g., +1234567890)
    escalation_condition: Optional[str] = None  # Condition when to escalate/transfer the call


# ============================================================================
# LLM MODELS
# ============================================================================

class ElaboratePromptRequest(BaseModel):
    """Request model for prompt elaboration."""
    prompt: str


class ElaboratePromptResponse(BaseModel):
    """Response model for prompt elaboration."""
    original_prompt: str
    elaborated_prompt: str


# ============================================================================
# SMS MODELS
# ============================================================================

class SMSRequest(BaseModel):
    """Request model for sending SMS."""
    body: str
    number: str


class SMSResponse(BaseModel):
    """Response model for SMS sending."""
    status: str
    message: str
    message_sid: str
    to_number: str


# ============================================================================
# EMAIL MODELS
# ============================================================================

class EmailRequest(BaseModel):
    """Request model for sending email."""
    receiver_email: str
    subject: str
    body: str
    is_html: Optional[bool] = False


class EmailResponse(BaseModel):
    """Response model for email sending."""
    status: str
    message: str
    receiver_email: str


# ============================================================================
# BULK COMMUNICATION MODELS
# ============================================================================

class Contact(BaseModel):
    """Model for a single contact."""
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None


class SMSBody(BaseModel):
    """Model for SMS body configuration."""
    message: str


class EmailBody(BaseModel):
    """Model for Email body configuration."""
    subject: str
    body: str
    is_html: Optional[bool] = False


class BulkCommunicationRequest(BaseModel):
    """Request model for bulk communication endpoint."""
    contacts: list[Contact]  # List of contacts or single contact in a list
    communication_types: list[str]  # e.g., ["call", "sms", "email"]
    sms_body: Optional[SMSBody] = None  # Required if "sms" in communication_types
    email_body: Optional[EmailBody] = None  # Required if "email" in communication_types
    # Call-related parameters
    dynamic_instruction: Optional[str] = None
    language: Optional[str] = "en"
    voice_id: Optional[str] = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs voice ID
    sip_trunk_id: Optional[str] = None  # SIP trunk ID (uses env variable if not provided)
    transfer_to: Optional[str] = None  # Phone number to transfer to (e.g., +1234567890)
    escalation_condition: Optional[str] = None  # Condition when to escalate/transfer the call


class ContactResult(BaseModel):
    """Result for a single contact's communication."""
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    call_status: Optional[str] = None
    transcript: Optional[dict] = None
    sms_status: Optional[str] = None
    email_status: Optional[str] = None
    created_at: str
    ended_at: str
    errors: Optional[dict] = None  # Store any errors that occurred


class BulkCommunicationResponse(BaseModel):
    """Response model for bulk communication endpoint."""
    status: str
    message: str
    total_contacts: int
    results: list[ContactResult]


# ============================================================================
# TOOL REGISTRATION MODELS
# ============================================================================

class ToolProperty(BaseModel):
    """Model for tool property definition."""
    name: str
    type: str  # e.g., "string", "number", "boolean", "array"
    description: Optional[str] = None
    required: Optional[bool] = False
    value: Optional[str] = ""  # Default value for the property


class RegisterToolRequest(BaseModel):
    """Request model for registering a tool."""
    tool_name: str
    tool_type: str  # e.g., "email", "sms", "api_call", "database"
    description: str
    properties: list[ToolProperty]


class RegisterToolResponse(BaseModel):
    """Response model for tool registration."""
    status: str
    message: str
    tool_id: str
    tool: dict


class DeleteToolRequest(BaseModel):
    """Request model for deleting a tool."""
    tool_id: str


class DeleteToolResponse(BaseModel):
    """Response model for tool deletion."""
    status: str
    message: str
    tool_id: str