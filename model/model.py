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
    collection_name: Optional[str] = None  # Deprecated: single collection (for backward compatibility)
    collection_names: Optional[list[str]] = None  # New: multiple collections support
    top_k: Optional[int] = 5
    thread_id: Optional[str] = None
    system_prompt: Optional[str] = None
    provider: Optional[str] = "openai"  # "openai" or "gemini"
    api_key: Optional[str] = None  # Custom API key for the provider
    
    def get_collections(self) -> list[str]:
        """Get list of collections, supporting both single and multiple collection names."""
        if self.collection_names:
            return self.collection_names
        elif self.collection_name:
            return [self.collection_name]
        else:
            return []


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
    provider: Optional[str] = "openai"  # LLM provider ("openai" or "gemini")
    api_key: Optional[str] = None  # Custom API key for the provider
    collection_name: Optional[str] = None  # RAG collection name for knowledge base queries


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


# ============================================================================
# SIP TRUNK SETUP MODELS
# ============================================================================

class CreateSIPTrunkRequest(BaseModel):
    """Request model for creating SIP trunk setup."""
    label: str
    phone_number: str
    twilio_sid: str
    twilio_auth_token: str


class CreateSIPTrunkResponse(BaseModel):
    """Response model for SIP trunk setup."""
    status: str
    message: str
    twilio_trunk_sid: str
    livekit_trunk_id: str
    termination_uri: str  # The SIP URI LiveKit connects to (e.g., tkxxxx.pstn.twilio.com)
    credential_list_sid: str
    ip_acl_sid: str
    username: str
    origination_uri: Optional[str] = None
    origination_uri_sid: Optional[str] = None


class CreateLiveKitTrunkRequest(BaseModel):
    """Request model for creating only LiveKit SIP trunk from existing Twilio trunk."""
    label: str
    phone_number: str
    sip_address: str  # e.g., example.pstn.twilio.com
    username: str
    password: str


class CreateLiveKitTrunkResponse(BaseModel):
    """Response model for LiveKit trunk creation."""
    status: str
    message: str
    livekit_trunk_id: str
    sip_address: str
    phone_number: str


class CreateGenericSIPTrunkRequest(BaseModel):
    """Request model for creating LiveKit SIP trunk from any generic SIP provider."""
    label: str
    phone_number: str  # e.g., +390110722580
    sip_address: str  # e.g., yes-group-2.fibrapro.it
    username: str
    password: str
    provider_name: Optional[str] = "generic"  # e.g., "fibrapro", "voip.ms", etc.
    transport: Optional[str] = "udp"  # "udp", "tcp", or "tls"
    port: Optional[int] = 5060  # Default SIP port


class CreateGenericSIPTrunkResponse(BaseModel):
    """Response model for generic SIP trunk creation."""
    status: str
    message: str
    livekit_trunk_id: str
    provider_name: str
    sip_address: str
    phone_number: str
    transport: str


class CreateInboundTrunkRequest(BaseModel):
    """Request model for creating inbound SIP trunk."""
    name: str
    phone_numbers: list[str]  # List of phone numbers (e.g., ["+1234567890"])
    krisp_enabled: Optional[bool] = True  # Enable noise cancellation


class CreateInboundTrunkResponse(BaseModel):
    """Response model for inbound trunk creation."""
    status: str
    message: str
    trunk_id: str
    trunk_name: str
    phone_numbers: list[str]


class AgentConfig(BaseModel):
    """Agent configuration for dispatch rule."""
    agent_name: Optional[str] = None  # e.g., "inbound-agent" (snake_case)
    agentName: Optional[str] = None  # e.g., "inbound-agent" (camelCase)
    metadata: Optional[str] = None  # Optional metadata for the agent
    
    def get_agent_name(self) -> str:
        """Return agent name, supporting both camelCase and snake_case."""
        return self.agent_name or self.agentName or ""


class RoomConfig(BaseModel):
    """Room configuration for dispatch rule."""
    agents: Optional[list[AgentConfig]] = None  # List of agents to dispatch


class DispatchRuleIndividual(BaseModel):
    """Individual dispatch rule configuration for dynamic room creation."""
    room_prefix: Optional[str] = None  # snake_case
    roomPrefix: Optional[str] = None  # camelCase
    
    def get_room_prefix(self) -> Optional[str]:
        """Return room prefix, supporting both camelCase and snake_case."""
        return self.room_prefix or self.roomPrefix


class DispatchRuleDirect(BaseModel):
    """Direct dispatch rule configuration for fixed room name."""
    room_name: Optional[str] = None  # snake_case
    roomName: Optional[str] = None  # camelCase
    
    def get_room_name(self) -> Optional[str]:
        """Return room name, supporting both camelCase and snake_case."""
        return self.room_name or self.roomName


class DispatchRuleUnion(BaseModel):
    """Union type for dispatch rules."""
    dispatchRuleIndividual: Optional[DispatchRuleIndividual] = None
    dispatchRuleDirect: Optional[DispatchRuleDirect] = None
    dispatch_rule_individual: Optional[DispatchRuleIndividual] = None
    dispatch_rule_direct: Optional[DispatchRuleDirect] = None
    
    def get_individual_rule(self) -> Optional[DispatchRuleIndividual]:
        """Get individual rule, supporting both camelCase and snake_case."""
        return self.dispatchRuleIndividual or self.dispatch_rule_individual
    
    def get_direct_rule(self) -> Optional[DispatchRuleDirect]:
        """Get direct rule, supporting both camelCase and snake_case."""
        return self.dispatchRuleDirect or self.dispatch_rule_direct


class DispatchRuleConfig(BaseModel):
    """Configuration for dispatch rule."""
    rule: DispatchRuleUnion
    name: str
    trunk_ids: Optional[list[str]] = None  # snake_case
    trunkIds: Optional[list[str]] = None  # camelCase
    room_config: Optional[RoomConfig] = None  # snake_case
    roomConfig: Optional[RoomConfig] = None  # camelCase
    
    def get_trunk_ids(self) -> list[str]:
        """Return trunk IDs, supporting both camelCase and snake_case."""
        return self.trunk_ids or self.trunkIds or []
    
    def get_room_config(self) -> Optional[RoomConfig]:
        """Return room config, supporting both camelCase and snake_case."""
        return self.room_config or self.roomConfig


class CreateDispatchRuleRequest(BaseModel):
    """Request model for creating dispatch rule with nested structure."""
    dispatch_rule: DispatchRuleConfig


class CreateDispatchRuleResponse(BaseModel):
    """Response model for dispatch rule creation."""
    status: str
    message: str
    dispatch_rule_id: str
    dispatch_rule_name: str


class SetupInboundSIPRequest(BaseModel):
    """Request model for complete inbound SIP setup."""
    name: str
    phone_numbers: list[str]
    room_name: str  # Room to dispatch calls to
    krisp_enabled: Optional[bool] = True


class SetupInboundSIPResponse(BaseModel):
    """Response model for complete inbound SIP setup."""
    status: str
    message: str
    trunk_id: str
    dispatch_rule_id: str
    phone_numbers: list[str]
    room_name: str