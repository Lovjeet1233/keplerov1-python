"""
Outbound call-related API endpoints
"""

import os
import asyncio
import json
from fastapi import APIRouter, HTTPException
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv
from livekit import api, rtc
from utils.logger import log_info, log_error, log_warning, log_exception
from voice_backend.outboundService.services.call_service import make_outbound_call
from voice_backend.outboundService.common.utils import validate_phone_number, format_phone_number
from voice_backend.outboundService.common.update_config import update_config_async
from model import (
    OutboundCallRequest, 
    StatusResponse, 
    CreateSIPTrunkRequest, 
    CreateSIPTrunkResponse, 
    CreateLiveKitTrunkRequest, 
    CreateLiveKitTrunkResponse,
    CreateInboundTrunkRequest,
    CreateInboundTrunkResponse,
    CreateDispatchRuleRequest,
    CreateDispatchRuleResponse,
    SetupInboundSIPRequest,
    SetupInboundSIPResponse
)

load_dotenv()

router = APIRouter(prefix="/calls", tags=["Calls"])

# Transcript folder path
TRANSCRIPT_FOLDER = Path("transcripts")
TRANSCRIPT_FILE = TRANSCRIPT_FOLDER / "transcript.json"


async def update_dynamic_config(
    dynamic_instruction: str = None,
    caller_name: str = None,
    language: str = "en",
    voice_id: str = "21m00Tcm4TlvDq8ikWAM",
    transfer_to: str = None,
    escalation_condition: str = None,
    provider: str = "openai",
    api_key: str = None
):
    """
    Update the dynamic configuration (config.json) with agent parameters.
    
    This replaces the old .env file update approach. The config.json file
    is read by the agent service on each new call/room connection.
    
    Args:
        dynamic_instruction: Custom instructions for the AI agent
        caller_name: Name of the person being called
        language: TTS language (e.g., "en", "es", "fr")
        voice_id: ElevenLabs voice ID (default: Rachel)
        transfer_to: Phone number to transfer to (e.g., +1234567890)
        escalation_condition: Condition when to escalate/transfer the call
        provider: LLM provider ("openai" or "gemini", default: "openai")
        api_key: Custom API key for the provider (optional)
    """
    # Build the full instruction
    if dynamic_instruction:
        if caller_name:
            full_instruction = f"{dynamic_instruction} The caller's name is {caller_name}, address them by name."
        else:
            full_instruction = dynamic_instruction
    else:
        if caller_name:
            full_instruction = f"You are a helpful voice AI assistant. The caller's name is {caller_name}, address them by name."
        else:
            full_instruction = "You are a helpful voice AI assistant."
    
    # Build additional parameters for config
    additional_params = {}
    if transfer_to:
        additional_params["transfer_to"] = transfer_to
    if escalation_condition:
        additional_params["escalation_condition"] = escalation_condition
    if provider:
        additional_params["provider"] = provider
    if api_key:
        additional_params["api_key"] = api_key
    
    # Update config.json using the async function
    await update_config_async(
        caller_name=caller_name or "Guest",
        agent_instructions=full_instruction,
        tts_language=language,
        voice_id=voice_id,
        additional_params=additional_params if additional_params else None
    )
    
    log_info(f"Updated config.json with dynamic parameters:")
    log_info(f"  - Agent Instructions: {full_instruction[:100]}...")
    if caller_name:
        log_info(f"  - Caller Name: {caller_name}")
    log_info(f"  - TTS Language: {language}")
    log_info(f"  - Voice ID: {voice_id}")
    if transfer_to:
        log_info(f"  - Transfer To: {transfer_to}")
    if escalation_condition:
        log_info(f"  - Escalation Condition: {escalation_condition}")
    if provider:
        log_info(f"  - LLM Provider: {provider}")
    if api_key:
        log_info(f"  - Custom API Key: {'***' + api_key[-4:] if len(api_key) > 4 else '***'}")


@router.post("/outbound", response_model=StatusResponse)
async def outbound_call(request: OutboundCallRequest):
    """
    Initiate an outbound call to the specified phone number.
    
    This endpoint:
    1. Validates and initiates the outbound call
    2. Returns immediately with status and caller_id (room name)
    
    Args:
        request: OutboundCallRequest containing:
            - phone_number: Phone number with country code (e.g., +1234567890)
            - name: Caller's name for personalization (optional)
            - dynamic_instruction: Custom instructions for the AI agent (optional)
            - language: TTS language code (default: "en")
            - voice_id: ElevenLabs voice ID (default: Rachel)
            - sip_trunk_id: SIP trunk ID (optional, uses env variable if not provided)
            - transfer_to: Phone number to transfer to (optional)
            - escalation_condition: Condition when to escalate/transfer (optional)
            - provider: LLM provider ("openai" or "gemini", default: "openai")
            - api_key: Custom API key for the provider (optional)
        
    Returns:
        StatusResponse with call status and caller_id (room name)
    
    Example:
        {
            "phone_number": "+1234567890",
            "name": "John Doe",
            "dynamic_instruction": "Ask about appointment",
            "provider": "gemini",
            "api_key": "your-gemini-api-key"
        }
    """
    try:
        log_info(f"Outbound call request to: '{request.phone_number}'")
        
        # Format and validate phone number
        formatted_number = format_phone_number(request.phone_number)
        
        if not validate_phone_number(formatted_number):
            log_error(f"Invalid phone number format: '{request.phone_number}'")
            raise HTTPException(
                status_code=400,
                detail="Invalid phone number format. Phone number must start with '+' followed by country code and number (e.g., +1234567890)"
            )
        
        # Update config.json with dynamic parameters
        log_info("Updating config.json with dynamic parameters...")
        await update_dynamic_config(
            dynamic_instruction=request.dynamic_instruction,
            caller_name=request.name,
            language=request.language,
            voice_id=request.voice_id,
            transfer_to=request.transfer_to,
            escalation_condition=request.escalation_condition,
            provider=request.provider,
            api_key=request.api_key
        )
        log_info("✓ config.json updated successfully")
        
        log_info(f"Initiating call to formatted number: '{formatted_number}'")
        
        # Make the outbound call and get room name
        participant, room_name = await make_outbound_call(
            phone_number=formatted_number,
            sip_trunk_id=request.sip_trunk_id
        )
        
        log_info(f"Successfully initiated call to '{formatted_number}' for {request.name or 'caller'}")
        log_info(f"Room name (caller_id): {room_name}")
        
        return StatusResponse(
            status="success",
            message=f"Outbound call initiated to {formatted_number}" + (f" for {request.name}" if request.name else ""),
            details={
                "caller_id": room_name,
                "phone_number": formatted_number,
                "original_input": request.phone_number,
                "name": request.name
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error initiating outbound call: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Outbound call error: {str(e)}")


@router.post("/outbound-with-escalation", response_model=StatusResponse)
async def outbound_call_with_escalation(request: OutboundCallRequest):
    """
    Initiate an outbound call with AI agent that can escalate to a human supervisor.
    
    This endpoint creates a LiveKit room and calls the customer. The outbound.py agent worker
    (which must be running) will automatically join the room and handle the conversation.
    
    Prerequisites:
    - outbound.py agent worker must be running (python outbound.py)
    - Agent worker uses the "sip-inbound" agent name to dispatch
    
    Flow (as implemented in outbound.py):
    1. Room is created
    2. Customer joins room via SIP call
    3. Agent worker (outbound.py) automatically dispatches to the room
    4. SupportAgent starts conversation with customer
    5. If customer requests escalation, agent calls supervisor
    6. Agent provides conversation summary to supervisor
    7. Supervisor confirms, calls are merged, agent disconnects
    
    Args:
        request: OutboundCallRequest containing:
            - phone_number: Customer phone number with country code (e.g., +1234567890)
            - name: Customer's name for personalization (optional)
            - dynamic_instruction: Custom instructions for the AI agent (optional)
            - language: TTS language code (default: "en")
            - voice_id: ElevenLabs voice ID (default: Rachel)
            - sip_trunk_id: SIP trunk ID (optional, uses env variable if not provided)
            - transfer_to: Phone number to transfer to (optional)
            - escalation_condition: Condition when to escalate/transfer (optional)
            - provider: LLM provider ("openai" or "gemini", default: "openai")
            - api_key: Custom API key for the provider (optional)
        
    Returns:
        StatusResponse with call initiation status
    
    Environment variables required:
        - LIVEKIT_API_KEY: Your LiveKit API key
        - LIVEKIT_API_SECRET: Your LiveKit API secret
        - LIVEKIT_URL: Your LiveKit server URL
        - LIVEKIT_SIP_OUTBOUND_TRUNK: Your SIP trunk ID (e.g., ST_vEtSehKXAp4d)
        - LIVEKIT_SUPERVISOR_PHONE_NUMBER: Supervisor's phone number (e.g., +919911062767)
    """
    try:
        log_info(f"Outbound call with escalation request to: '{request.phone_number}'")
        
        # Format and validate phone number
        formatted_number = format_phone_number(request.phone_number)
        
        if not validate_phone_number(formatted_number):
            log_error(f"Invalid phone number format: '{request.phone_number}'")
            raise HTTPException(
                status_code=400,
                detail="Invalid phone number format. Phone number must start with '+' followed by country code and number (e.g., +1234567890)"
            )
        
        # Get LiveKit credentials from environment
        livekit_url = os.getenv("LIVEKIT_URL")
        livekit_api_key = os.getenv("LIVEKIT_API_KEY")
        livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")
        sip_trunk_id = os.getenv("LIVEKIT_SIP_OUTBOUND_TRUNK")
        supervisor_phone = os.getenv("LIVEKIT_SUPERVISOR_PHONE_NUMBER")
        
        # Validate required credentials
        if not all([livekit_url, livekit_api_key, livekit_api_secret, sip_trunk_id]):
            log_error("Missing LiveKit credentials in environment variables")
            raise HTTPException(
                status_code=500,
                detail="LiveKit credentials not configured. Please set LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, and LIVEKIT_SIP_OUTBOUND_TRUNK"
            )
        
        if not supervisor_phone:
            log_warning("LIVEKIT_SUPERVISOR_PHONE_NUMBER not set - escalation will fail if requested")
        
        # Update config.json with dynamic parameters for the agent
        # The agent worker will read these values from config.json
        log_info("Updating config.json with dynamic parameters for agent...")
        await update_dynamic_config(
            dynamic_instruction=request.dynamic_instruction,
            caller_name=request.name,
            language=request.language,
            voice_id=request.voice_id,
            transfer_to=request.transfer_to,
            escalation_condition=request.escalation_condition,
            provider=request.provider,
            api_key=request.api_key
        )
        log_info("✓ config.json updated successfully")
        
        # Create unique room name for this call
        # Pattern matches what outbound.py expects
        import uuid
        import time
        room_name = f"outbound-escalation-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        log_info(f"Creating room: {room_name}")
        
        # Initialize LiveKit API
        lkapi = api.LiveKitAPI(
            url=livekit_url,
            api_key=livekit_api_key,
            api_secret=livekit_api_secret
        )
        
        try:
            # Step 1: Create the room with metadata for agent dispatch
            # Setting metadata to signal the agent worker to join
            await lkapi.room.create_room(
                api.CreateRoomRequest(
                    name=room_name,
                    metadata=json.dumps({"agent_name": "sip-inbound"})  # Signal which agent should join
                )
            )
            log_info(f"✓ Room created: {room_name}")
            
            # Step 2: Agent will auto-dispatch to the room
            # The outbound.py worker is configured to automatically join any room
            log_info(f"Agent worker will auto-dispatch when participant joins...")
            
            # Step 3: Initiate SIP call to customer
            # Customer joins the room as "customer-sip" participant
            # This triggers the outbound.py entrypoint which:
            # - Creates AgentSession with SupportAgent
            # - Sets up SessionManager with escalation capabilities  
            # - Starts the agent conversation
            log_info(f"Initiating SIP call to customer: {formatted_number}")
            log_info(f"  Customer will join room as participant")
            log_info(f"  Agent will handle conversation with escalation support")
            
            participant = await lkapi.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    sip_trunk_id=sip_trunk_id,
                    sip_call_to=formatted_number,
                    room_name=room_name,
                    participant_identity="customer-sip",
                    participant_name=request.name or "Customer",
                    krisp_enabled=True,  # Enable noise cancellation as in outbound.py
                    wait_until_answered=True
                )
            )
            
            log_info(f"✓ Call initiated successfully")
            log_info(f"  - Room: {room_name}")
            log_info(f"  - Customer Participant ID: {participant.participant_id}")
            log_info(f"  - SIP Call ID: {participant.sip_call_id}")
            log_info(f"  - Agent dispatched and ready to handle conversation")
            log_info(f"  - Escalation available to: {supervisor_phone or 'Not configured'}")
            
            return StatusResponse(
                status="success",
                message=f"Outbound call with escalation initiated to {formatted_number}" + (f" for {request.name}" if request.name else ""),
                details={
                    "phone_number": formatted_number,
                    "original_input": request.phone_number,
                    "name": request.name,
                    "room_name": room_name,
                    "dispatch_method": "Auto-dispatch (agent joins automatically)",
                    "participant_id": participant.participant_id,
                    "sip_call_id": participant.sip_call_id,
                    "has_dynamic_instruction": bool(request.dynamic_instruction),
                    "language": request.language,
                    "voice_id": request.voice_id,
                    "sip_trunk_id": request.sip_trunk_id,
                    "transfer_to": request.transfer_to,
                    "escalation_condition": request.escalation_condition,
                    "provider": request.provider,
                    "has_custom_api_key": bool(request.api_key),
                    "escalation_enabled": bool(supervisor_phone),
                    "supervisor_phone": supervisor_phone if supervisor_phone else "Not configured",
                    "flow": "Room created → Customer joins → Agent auto-dispatches → Conversation starts → Escalation available"
                }
            )
            
        finally:
            await lkapi.aclose()
    
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error initiating outbound call with escalation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Outbound call error: {str(e)}")


@router.post("/setup-sip-trunk", response_model=CreateSIPTrunkResponse)
async def setup_sip_trunk(request: CreateSIPTrunkRequest):
    """
    Create and configure a complete SIP trunk setup with Twilio and LiveKit.
    
    This endpoint orchestrates the full SIP trunk creation process:
    1. Creates a Twilio SIP Trunk with credentials
    2. Creates a LiveKit SIP Trunk linked to the Twilio trunk
    
    Args:
        request: CreateSIPTrunkRequest containing:
            - label: Friendly name/label for the trunk
            - phone_number: Associated phone number (for reference)
            - twilio_sid: Twilio Account SID
            - twilio_auth_token: Twilio Auth Token
    
    Returns:
        CreateSIPTrunkResponse with:
            - twilio_trunk_sid: Created Twilio trunk SID
            - livekit_trunk_id: Created LiveKit trunk ID
            - credential_list_sid: Twilio credential list SID
            - username: SIP username for authentication
    """
    try:
        log_info(f"======================================")
        log_info(f"  SIP TRUNK SETUP STARTED")
        log_info(f"======================================")
        log_info(request)
        log_info(f"======================================")
        log_info(f"Starting SIP trunk setup with label: '{request.label}'")
        log_info(f"Phone number: {request.phone_number}")
        
        # Import the functions from twilio_setup
        from twilio_setup import create_twilio_sip_trunk, create_livekit_trunk
        
        # Step 1: Create Twilio SIP Trunk
        log_info("Step 1: Creating Twilio SIP Trunk...")
        twilio_data = await create_twilio_sip_trunk(
            account_sid=request.twilio_sid,
            auth_token=request.twilio_auth_token,
            friendly_name=request.label,
            username=f"agent_{request.label.lower().replace(' ', '_')}",
            password="StrongPass123!"  # You might want to make this configurable or generate it
        )
        log_info(f"✓ Twilio Trunk created: {twilio_data['trunk_sid']}")
        
        # Step 2: Create LiveKit SIP Trunk
        log_info("Step 2: Creating LiveKit SIP Trunk...")
        livekit_trunk_id = await create_livekit_trunk(
            twilio_trunk_sid=twilio_data["trunk_sid"],
            username=twilio_data["username"],
            password=twilio_data["password"],
            phone_number=request.phone_number,
            trunk_name=request.label
        )
        log_info(f"✓ LiveKit Trunk created: {livekit_trunk_id}")
        
        log_info("✓ SIP trunk setup completed successfully")
        
        # Log summary
        log_info(f"")
        log_info(f"======================================")
        log_info(f"  SIP TRUNK SETUP COMPLETED")
        log_info(f"======================================")
        log_info(f"Label:           {request.label}")
        log_info(f"Phone Number:    {request.phone_number}")
        log_info(f"--------------------------------------")
        log_info(f"Twilio Trunk:    {twilio_data['trunk_name']}")
        log_info(f"  └─ SID:        {twilio_data['trunk_sid']}")
        log_info(f"--------------------------------------")
        log_info(f"LiveKit Trunk:   {livekit_trunk_id}")
        log_info(f"--------------------------------------")
        log_info(f"Termination URI: {twilio_data.get('termination_uri', 'N/A')}")
        log_info(f"  (Use this in LiveKit configuration)")
        log_info(f"--------------------------------------")
        log_info(f"Credentials:")
        log_info(f"  └─ List:       {twilio_data['credential_list_name']}")
        log_info(f"  └─ List SID:   {twilio_data['credential_list_sid']}")
        log_info(f"  └─ Username:   {twilio_data['username']}")
        log_info(f"--------------------------------------")
        log_info(f"IP Access Control:")
        log_info(f"  └─ IP ACL SID: {twilio_data.get('ip_acl_sid', 'N/A')}")
        log_info(f"--------------------------------------")
        log_info(f"Origination URI: {twilio_data.get('origination_uri', 'N/A')}")
        log_info(f"  └─ URI SID:    {twilio_data.get('origination_uri_sid', 'N/A')}")
        log_info(f"======================================")
        
        return CreateSIPTrunkResponse(
            status="success",
            message=f"SIP trunk '{request.label}' created successfully. Twilio: {twilio_data['trunk_name']}, LiveKit: {livekit_trunk_id}. Termination URI: {twilio_data.get('termination_uri')}",
            twilio_trunk_sid=twilio_data["trunk_sid"],
            livekit_trunk_id=livekit_trunk_id,
            termination_uri=twilio_data.get("termination_uri", ""),
            credential_list_sid=twilio_data["credential_list_sid"],
            ip_acl_sid=twilio_data.get("ip_acl_sid", ""),
            username=twilio_data["username"],
            origination_uri=twilio_data.get("origination_uri"),
            origination_uri_sid=twilio_data.get("origination_uri_sid")
        )
        
    except Exception as e:
        log_exception(f"Error setting up SIP trunk: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"SIP trunk setup error: {str(e)}"
        )


@router.post("/create-livekit-trunk", response_model=CreateLiveKitTrunkResponse)
async def create_livekit_trunk_endpoint(request: CreateLiveKitTrunkRequest):
    """
    Create a LiveKit SIP trunk from an existing Twilio SIP address.
    
    Use this endpoint when you already have a Twilio trunk configured and just 
    want to create the LiveKit side of the connection.
    
    Args:
        request: CreateLiveKitTrunkRequest containing:
            - label: Friendly name/label for the trunk
            - phone_number: Phone number with country code (e.g., +1234567890)
            - sip_address: Twilio SIP address (e.g., example.pstn.twilio.com)
            - username: SIP username for authentication
            - password: SIP password for authentication
    
    Returns:
        CreateLiveKitTrunkResponse with:
            - livekit_trunk_id: Created LiveKit trunk ID
            - sip_address: The SIP address used
            - phone_number: The phone number associated
    
    Example:
        POST /calls/create-livekit-trunk
        {
            "label": "My Trunk",
            "phone_number": "+12625925656",
            "sip_address": "example.pstn.twilio.com",
            "username": "my_username",
            "password": "my_password"
        }
    """
    try:
        log_info(f"Creating LiveKit trunk with label: '{request.label}'")
        log_info(f"Phone number: {request.phone_number}")
        log_info(f"SIP address: {request.sip_address}")
        
        # Import the function from twilio_setup
        from twilio_setup import create_livekit_trunk_from_address
        
        # Validate phone number format
        formatted_number = format_phone_number(request.phone_number)
        
        if not validate_phone_number(formatted_number):
            log_error(f"Invalid phone number format: '{request.phone_number}'")
            raise HTTPException(
                status_code=400,
                detail="Invalid phone number format. Phone number must start with '+' followed by country code and number (e.g., +1234567890)"
            )
        
        # Create LiveKit trunk
        log_info("Creating LiveKit SIP Trunk...")
        livekit_trunk_id = await create_livekit_trunk_from_address(
            sip_address=request.sip_address,
            username=request.username,
            password=request.password,
            phone_number=formatted_number,
            trunk_name=request.label
        )
        log_info(f"✓ LiveKit Trunk created: {livekit_trunk_id}")
        
        # Log summary
        log_info(f"")
        log_info(f"======================================")
        log_info(f"  LIVEKIT TRUNK CREATED")
        log_info(f"======================================")
        log_info(f"Label:           {request.label}")
        log_info(f"Phone Number:    {formatted_number}")
        log_info(f"SIP Address:     {request.sip_address}")
        log_info(f"--------------------------------------")
        log_info(f"LiveKit Trunk:   {livekit_trunk_id}")
        log_info(f"--------------------------------------")
        log_info(f"Authentication:")
        log_info(f"  └─ Username:   {request.username}")
        log_info(f"======================================")
        
        return CreateLiveKitTrunkResponse(
            status="success",
            message=f"LiveKit trunk '{request.label}' created successfully for {request.sip_address}",
            livekit_trunk_id=livekit_trunk_id,
            sip_address=request.sip_address,
            phone_number=formatted_number
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error creating LiveKit trunk: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"LiveKit trunk creation error: {str(e)}"
        )


@router.post("/create-inbound-trunk", response_model=CreateInboundTrunkResponse)
async def create_inbound_trunk(request: CreateInboundTrunkRequest):
    """
    Create a LiveKit inbound SIP trunk for receiving calls.
    
    This endpoint creates an inbound trunk that can receive calls from phone numbers.
    The trunk will be configured to route incoming calls to your LiveKit rooms.
    
    Args:
        request: CreateInboundTrunkRequest containing:
            - name: Friendly name for the trunk
            - phone_numbers: List of phone numbers (e.g., ["+1234567890"])
            - allowed_numbers: Optional whitelist of caller numbers
            - krisp_enabled: Enable noise cancellation (default: True)
    
    Returns:
        CreateInboundTrunkResponse with trunk details
    
    Example:
        {
            "name": "MyInboundTrunk",
            "phone_numbers": ["+1234567890", "+0987654321"],
            "allowed_numbers": ["+1111111111"],
            "krisp_enabled": true
        }
    """
    try:
        log_info(f"Creating inbound SIP trunk: '{request.name}'")
        log_info(f"Phone numbers: {', '.join(request.phone_numbers)}")
        
        # Get LiveKit credentials from environment
        livekit_url = os.getenv("LIVEKIT_URL")
        livekit_api_key = os.getenv("LIVEKIT_API_KEY")
        livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")
        
        if not all([livekit_url, livekit_api_key, livekit_api_secret]):
            log_error("Missing LiveKit credentials")
            raise HTTPException(
                status_code=500,
                detail="LiveKit credentials not configured"
            )
        
        # Initialize LiveKit API
        lk = api.LiveKitAPI(
            url=livekit_url,
            api_key=livekit_api_key,
            api_secret=livekit_api_secret
        )
        
        try:
            from livekit.protocol import sip
            
            # Create trunk info
            trunk_info = sip.SIPInboundTrunkInfo()
            trunk_info.name = request.name
            trunk_info.numbers.extend(request.phone_numbers)
            
            if request.allowed_numbers:
                trunk_info.allowed_numbers.extend(request.allowed_numbers)
            
            trunk_info.krisp_enabled = request.krisp_enabled
            
            # Create request
            create_request = sip.CreateSIPInboundTrunkRequest()
            create_request.trunk.CopyFrom(trunk_info)
            
            # Create trunk
            trunk = await lk.sip.create_inbound_trunk(create_request)
            
            await lk.aclose()
            
            log_info(f"✓ Inbound trunk created: {trunk.sip_trunk_id}")
            
            # Log summary
            log_info(f"")
            log_info(f"======================================")
            log_info(f"  INBOUND TRUNK CREATED")
            log_info(f"======================================")
            log_info(f"Trunk Name:      {request.name}")
            log_info(f"Trunk ID:        {trunk.sip_trunk_id}")
            log_info(f"Phone Numbers:   {', '.join(request.phone_numbers)}")
            if request.allowed_numbers:
                log_info(f"Allowed Numbers: {', '.join(request.allowed_numbers)}")
            log_info(f"Krisp Enabled:   {request.krisp_enabled}")
            log_info(f"======================================")
            
            return CreateInboundTrunkResponse(
                status="success",
                message=f"Inbound trunk '{request.name}' created successfully",
                trunk_id=trunk.sip_trunk_id,
                trunk_name=request.name,
                phone_numbers=request.phone_numbers
            )
            
        finally:
            await lk.aclose()
    
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error creating inbound trunk: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Inbound trunk creation error: {str(e)}"
        )


@router.post("/create-dispatch-rule", response_model=CreateDispatchRuleResponse)
async def create_dispatch_rule(request: CreateDispatchRuleRequest):
    """
    Create a dispatch rule to route incoming SIP calls to a LiveKit room.
    
    Dispatch rules determine how incoming calls are routed. Calls matching the
    trunk IDs will be directed to the specified room.
    
    Args:
        request: CreateDispatchRuleRequest containing:
            - name: Friendly name for the dispatch rule
            - trunk_ids: List of trunk IDs to attach this rule to
            - room_name: Room name to dispatch calls to
            - room_prefix: Optional room prefix for dynamic rooms
    
    Returns:
        CreateDispatchRuleResponse with dispatch rule details
    
    Example:
        {
            "name": "MyDispatchRule",
            "trunk_ids": ["ST_xxxxx", "ST_yyyyy"],
            "room_name": "call-center-room"
        }
    """
    try:
        log_info(f"Creating dispatch rule: '{request.name}'")
        log_info(f"Trunk IDs: {', '.join(request.trunk_ids)}")
        log_info(f"Target room: {request.room_name}")
        
        # Get LiveKit credentials
        livekit_url = os.getenv("LIVEKIT_URL")
        livekit_api_key = os.getenv("LIVEKIT_API_KEY")
        livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")
        
        if not all([livekit_url, livekit_api_key, livekit_api_secret]):
            log_error("Missing LiveKit credentials")
            raise HTTPException(
                status_code=500,
                detail="LiveKit credentials not configured"
            )
        
        # Initialize LiveKit API
        lk = api.LiveKitAPI(
            url=livekit_url,
            api_key=livekit_api_key,
            api_secret=livekit_api_secret
        )
        
        try:
            from livekit.protocol import sip
            
            # Create dispatch rule info
            rule_info = sip.SIPDispatchRuleInfo()
            rule_info.name = request.name
            rule_info.trunk_ids.extend(request.trunk_ids)
            
            # Set dispatch rule - direct to room
            rule_info.dispatch_rule_direct.room_name = request.room_name
            if request.room_prefix:
                rule_info.dispatch_rule_direct.room_prefix = request.room_prefix
            
            # Create request
            create_request = sip.CreateSIPDispatchRuleRequest()
            create_request.rule.CopyFrom(rule_info)
            
            # Create dispatch rule
            dispatch_rule = await lk.sip.create_dispatch_rule(create_request)
            
            await lk.aclose()
            
            log_info(f"✓ Dispatch rule created: {dispatch_rule.sip_dispatch_rule_id}")
            
            # Log summary
            log_info(f"")
            log_info(f"======================================")
            log_info(f"  DISPATCH RULE CREATED")
            log_info(f"======================================")
            log_info(f"Rule Name:       {request.name}")
            log_info(f"Rule ID:         {dispatch_rule.sip_dispatch_rule_id}")
            log_info(f"Trunk IDs:       {', '.join(request.trunk_ids)}")
            log_info(f"Target Room:     {request.room_name}")
            if request.room_prefix:
                log_info(f"Room Prefix:     {request.room_prefix}")
            log_info(f"======================================")
            
            return CreateDispatchRuleResponse(
                status="success",
                message=f"Dispatch rule '{request.name}' created successfully",
                dispatch_rule_id=dispatch_rule.sip_dispatch_rule_id,
                dispatch_rule_name=request.name
            )
            
        finally:
            await lk.aclose()
    
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error creating dispatch rule: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Dispatch rule creation error: {str(e)}"
        )


@router.post("/setup-inbound-sip", response_model=SetupInboundSIPResponse)
async def setup_inbound_sip(request: SetupInboundSIPRequest):
    """
    Complete inbound SIP setup: creates trunk and dispatch rule in one call.
    
    This endpoint orchestrates the complete setup for receiving inbound calls:
    1. Creates an inbound SIP trunk with your phone numbers
    2. Creates a dispatch rule to route calls to your room
    
    Args:
        request: SetupInboundSIPRequest containing:
            - name: Name for the trunk and dispatch rule
            - phone_numbers: List of phone numbers (e.g., ["+1234567890"])
            - room_name: Room name to dispatch calls to
            - allowed_numbers: Optional whitelist of caller numbers
            - krisp_enabled: Enable noise cancellation (default: True)
    
    Returns:
        SetupInboundSIPResponse with complete setup details
    
    Example:
        {
            "name": "CustomerSupport",
            "phone_numbers": ["+1234567890"],
            "room_name": "support-room",
            "allowed_numbers": ["+1111111111"],
            "krisp_enabled": true
        }
    """
    try:
        log_info(f"Setting up complete inbound SIP configuration: '{request.name}'")
        log_info(f"Phone numbers: {', '.join(request.phone_numbers)}")
        log_info(f"Target room: {request.room_name}")
        
        # Get LiveKit credentials
        livekit_url = os.getenv("LIVEKIT_URL")
        livekit_api_key = os.getenv("LIVEKIT_API_KEY")
        livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")
        
        if not all([livekit_url, livekit_api_key, livekit_api_secret]):
            log_error("Missing LiveKit credentials")
            raise HTTPException(
                status_code=500,
                detail="LiveKit credentials not configured"
            )
        
        # Initialize LiveKit API
        lk = api.LiveKitAPI(
            url=livekit_url,
            api_key=livekit_api_key,
            api_secret=livekit_api_secret
        )
        
        try:
            from livekit.protocol import sip
            
            # Step 1: Create inbound trunk
            log_info("Step 1: Creating inbound SIP trunk...")
            trunk_info = sip.SIPInboundTrunkInfo()
            trunk_info.name = request.name
            trunk_info.numbers.extend(request.phone_numbers)
            
            if request.allowed_numbers:
                trunk_info.allowed_numbers.extend(request.allowed_numbers)
            
            trunk_info.krisp_enabled = request.krisp_enabled
            
            create_trunk_request = sip.CreateSIPInboundTrunkRequest()
            create_trunk_request.trunk.CopyFrom(trunk_info)
            
            trunk = await lk.sip.create_inbound_trunk(create_trunk_request)
            log_info(f"✓ Trunk created: {trunk.sip_trunk_id}")
            
            # Step 2: Create dispatch rule
            log_info("Step 2: Creating dispatch rule...")
            rule_info = sip.SIPDispatchRuleInfo()
            rule_info.name = f"{request.name}_dispatch"
            rule_info.trunk_ids.append(trunk.sip_trunk_id)
            rule_info.dispatch_rule_direct.room_name = request.room_name
            
            create_rule_request = sip.CreateSIPDispatchRuleRequest()
            create_rule_request.rule.CopyFrom(rule_info)
            
            dispatch_rule = await lk.sip.create_dispatch_rule(create_rule_request)
            log_info(f"✓ Dispatch rule created: {dispatch_rule.sip_dispatch_rule_id}")
            
            await lk.aclose()
            
            # Log summary
            log_info(f"")
            log_info(f"======================================")
            log_info(f"  INBOUND SIP SETUP COMPLETED")
            log_info(f"======================================")
            log_info(f"Configuration:   {request.name}")
            log_info(f"--------------------------------------")
            log_info(f"Trunk ID:        {trunk.sip_trunk_id}")
            log_info(f"Phone Numbers:   {', '.join(request.phone_numbers)}")
            if request.allowed_numbers:
                log_info(f"Allowed Numbers: {', '.join(request.allowed_numbers)}")
            log_info(f"--------------------------------------")
            log_info(f"Dispatch Rule:   {dispatch_rule.sip_dispatch_rule_id}")
            log_info(f"Target Room:     {request.room_name}")
            log_info(f"--------------------------------------")
            log_info(f"Krisp Enabled:   {request.krisp_enabled}")
            log_info(f"======================================")
            log_info(f"")
            log_info(f"✓ Inbound calls to {', '.join(request.phone_numbers)} will route to room '{request.room_name}'")
            
            return SetupInboundSIPResponse(
                status="success",
                message=f"Inbound SIP setup '{request.name}' completed successfully. Calls to {', '.join(request.phone_numbers)} will route to room '{request.room_name}'",
                trunk_id=trunk.sip_trunk_id,
                dispatch_rule_id=dispatch_rule.sip_dispatch_rule_id,
                phone_numbers=request.phone_numbers,
                room_name=request.room_name
            )
            
        finally:
            await lk.aclose()
    
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error setting up inbound SIP: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Inbound SIP setup error: {str(e)}"
        )

