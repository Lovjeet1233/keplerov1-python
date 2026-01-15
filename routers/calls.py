"""
Outbound call-related API endpoints
"""

import os
import asyncio
import json
import httpx
from fastapi import APIRouter, HTTPException
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv
from livekit import api, rtc
import pymongo
from utils.logger import log_info, log_error, log_warning, log_exception
from voice_backend.outboundService.services.call_service import make_outbound_call
from voice_backend.outboundService.common.utils import validate_phone_number, format_phone_number
from model import (
    OutboundCallRequest, 
    StatusResponse, 
    CreateSIPTrunkRequest, 
    CreateSIPTrunkResponse, 
    CreateLiveKitTrunkRequest, 
    CreateLiveKitTrunkResponse,
    CreateGenericSIPTrunkRequest,
    CreateGenericSIPTrunkResponse,
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

# MongoDB configuration
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DATABASE = "IslandAI"
MONGODB_COLLECTION = "outbound-call-config"


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
            - collection_names: List of RAG collections to search (optional)
            - greeting_message: Custom greeting message for the call (optional)
        
    Returns:
        StatusResponse with call status and caller_id (room name)
    
    Examples:
        Basic call:
        {
            "phone_number": "+1234567890",
            "name": "John Doe",
            "dynamic_instruction": "Ask about appointment"
        }
        
        With custom greeting:
        {
            "phone_number": "+1234567890",
            "name": "John Doe",
            "dynamic_instruction": "Ask about appointment",
            "greeting_message": "Hello John, this is Sarah from ABC Clinic calling to confirm your appointment."
        }
        
        With RAG collections:
        {
            "phone_number": "+1234567890",
            "name": "John Doe",
            "dynamic_instruction": "Answer questions about our products",
            "collection_names": ["product_docs", "pricing_info"],
            "provider": "openai"
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
        
        # Update MongoDB configuration with dynamic parameters
        log_info("Updating MongoDB configuration with dynamic parameters...")
        
        # Handle collection_name for backward compatibility
        collection_names_param = None
        if hasattr(request, 'collection_names') and request.collection_names:
            collection_names_param = request.collection_names
        elif hasattr(request, 'collection_name') and request.collection_name:
            # Convert single collection_name to list for backward compatibility
            collection_names_param = [request.collection_name]
        
        # Build the full instruction
        if request.dynamic_instruction:
            if request.name:
                full_instruction = f"{request.dynamic_instruction} The caller's name is {request.name}, address them by name."
            else:
                full_instruction = request.dynamic_instruction
        else:
            if request.name:
                full_instruction = f"You are a helpful voice AI assistant. The caller's name is {request.name}, address them by name."
            else:
                full_instruction = "You are a helpful voice AI assistant."
        
        # Connect to MongoDB and update the single document
        try:
            if not MONGODB_URI:
                raise HTTPException(status_code=500, detail="MONGODB_URI not configured")
            
            client = pymongo.MongoClient(MONGODB_URI)
            db = client[MONGODB_DATABASE]
            collection = db[MONGODB_COLLECTION]
            
            # Build update document
            update_doc = {
                "caller_name": request.name or "Guest",
                "agent_instructions": full_instruction,
                "tts_language": request.language,
                "voice_id": request.voice_id,
                "contact_number": request.contact_number
            }
            
            # Add optional fields if provided
            if request.transfer_to:
                update_doc["transfer_to"] = request.transfer_to
            if request.escalation_condition:
                update_doc["escalation_condition"] = request.escalation_condition
            if request.provider:
                update_doc["provider"] = request.provider
            if request.api_key:
                update_doc["api_key"] = request.api_key
            if collection_names_param:
                update_doc["collection_names"] = collection_names_param
            if request.organisation_id:
                update_doc["organisation_id"] = request.organisation_id
            if request.greeting_message:
                update_doc["greeting_message"] = request.greeting_message
            
            # Update the single document (upsert if it doesn't exist)
            result = collection.update_one(
                {},  # Empty filter to match the single document
                {"$set": update_doc},
                upsert=True
            )
            
            client.close()
            
            log_info(f"✓ MongoDB configuration updated successfully")
            log_info(f"  - Agent Instructions: {full_instruction[:100]}...")
            if request.name:
                log_info(f"  - Caller Name: {request.name}")
            log_info(f"  - TTS Language: {request.language}")
            log_info(f"  - Voice ID: {request.voice_id}")
            if request.transfer_to:
                log_info(f"  - Transfer To: {request.transfer_to}")
            if request.escalation_condition:
                log_info(f"  - Escalation Condition: {request.escalation_condition}")
            if request.provider:
                log_info(f"  - LLM Provider: {request.provider}")
            if request.api_key:
                log_info(f"  - Custom API Key: {'***' + request.api_key[-4:] if len(request.api_key) > 4 else '***'}")
            if collection_names_param:
                log_info(f"  - RAG Collections: {collection_names_param}")
            if request.organisation_id:
                log_info(f"  - Organisation ID: {request.organisation_id}")
            if request.contact_number:
                log_info(f"  - Contact Number: {request.contact_number}")
            if request.greeting_message:
                log_info(f"  - Greeting Message: {request.greeting_message}")
                
        except Exception as e:
            log_error(f"Failed to update MongoDB configuration: {str(e)}")
            raise HTTPException(status_code=500, detail=f"MongoDB update error: {str(e)}")
        
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


@router.post("/create-generic-sip-trunk", response_model=CreateGenericSIPTrunkResponse)
async def create_generic_sip_trunk_endpoint(request: CreateGenericSIPTrunkRequest):
    """
    Create a LiveKit SIP trunk from ANY generic SIP provider (FibraPro, VoIP.ms, etc.).
    
    This endpoint works with any standard SIP provider that supports username/password 
    authentication. Unlike the Twilio-specific endpoint, this supports various transport 
    protocols and custom ports.
    
    Args:
        request: CreateGenericSIPTrunkRequest containing:
            - label: Friendly name/label for the trunk
            - phone_number: Phone number with country code (e.g., +390110722580)
            - sip_address: SIP domain/registrar (e.g., yes-group-2.fibrapro.it)
            - username: SIP username for authentication
            - password: SIP password for authentication
            - provider_name: Name of provider (e.g., "fibrapro", "voipms") - optional
            - transport: Protocol - "udp", "tcp", or "tls" (default: "udp")
            - port: SIP port (default: 5060)
    
    Returns:
        CreateGenericSIPTrunkResponse with:
            - livekit_trunk_id: Created LiveKit trunk ID
            - provider_name: The provider name
            - sip_address: The SIP address used
            - phone_number: The phone number associated
            - transport: Transport protocol used
    
    Example - FibraPro:
        POST /calls/create-generic-sip-trunk
        {
            "label": "FibraPro Italy",
            "phone_number": "+390110722580",
            "sip_address": "yes-group-2.fibrapro.it",
            "username": "abc",
            "password": "t15wf247",
            "provider_name": "fibrapro",
            "transport": "udp",
            "port": 5060
        }
    
    Example - VoIP.ms:
        {
            "label": "VoIP.ms Canada",
            "phone_number": "+14161234567",
            "sip_address": "toronto.voip.ms",
            "username": "123456_main",
            "password": "mypassword",
            "provider_name": "voipms",
            "transport": "udp"
        }
    """
    try:
        log_info(f"======================================")
        log_info(f"  GENERIC SIP TRUNK CREATION STARTED")
        log_info(f"======================================")
        log_info(f"Creating generic SIP trunk with label: '{request.label}'")
        log_info(f"Provider: {request.provider_name}")
        log_info(f"Phone number: {request.phone_number}")
        log_info(f"SIP address: {request.sip_address}")
        log_info(f"Transport: {request.transport.upper()}")
        log_info(f"Port: {request.port}")
        
        # Import the function from twilio_setup
        from twilio_setup import create_generic_livekit_trunk
        
        # Validate phone number format
        formatted_number = format_phone_number(request.phone_number)
        
        if not validate_phone_number(formatted_number):
            log_error(f"Invalid phone number format: '{request.phone_number}'")
            raise HTTPException(
                status_code=400,
                detail="Invalid phone number format. Phone number must start with '+' followed by country code and number (e.g., +390110722580)"
            )
        
        # Create LiveKit trunk for generic SIP provider
        log_info("Creating LiveKit SIP Trunk for generic provider...")
        livekit_trunk_id = await create_generic_livekit_trunk(
            sip_address=request.sip_address,
            username=request.username,
            password=request.password,
            phone_number=formatted_number,
            trunk_name=request.label,
            provider_name=request.provider_name,
            transport=request.transport,
            port=request.port
        )
        log_info(f"✓ LiveKit Trunk created: {livekit_trunk_id}")
        
        # Log summary
        log_info(f"")
        log_info(f"======================================")
        log_info(f"  GENERIC SIP TRUNK CREATED")
        log_info(f"======================================")
        log_info(f"Label:           {request.label}")
        log_info(f"Provider:        {request.provider_name}")
        log_info(f"Phone Number:    {formatted_number}")
        log_info(f"SIP Address:     {request.sip_address}")
        log_info(f"--------------------------------------")
        log_info(f"LiveKit Trunk:   {livekit_trunk_id}")
        log_info(f"--------------------------------------")
        log_info(f"Configuration:")
        log_info(f"  └─ Username:   {request.username}")
        log_info(f"  └─ Transport:  {request.transport.upper()}")
        log_info(f"  └─ Port:       {request.port}")
        log_info(f"======================================")
        log_info(f"")
        log_info(f"✓ You can now use this trunk for outbound calls!")
        log_info(f"  Use trunk ID: {livekit_trunk_id}")
        
        return CreateGenericSIPTrunkResponse(
            status="success",
            message=f"Generic SIP trunk '{request.label}' created successfully for {request.provider_name} provider",
            livekit_trunk_id=livekit_trunk_id,
            provider_name=request.provider_name,
            sip_address=request.sip_address,
            phone_number=formatted_number,
            transport=request.transport
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error creating generic SIP trunk: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Generic SIP trunk creation error: {str(e)}"
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
            - krisp_enabled: Enable noise cancellation (default: True)
    
    Returns:
        CreateInboundTrunkResponse with trunk details
    
    Example:
        {
            "name": "MyInboundTrunk",
            "phone_numbers": ["+1234567890", "+0987654321"],
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
async def create_dispatch_rule(sip_trunk_id: str, name: str, agent_name: str):
    """
    Create a dispatch rule to route incoming SIP calls to LiveKit rooms.
    
    Args:
        sip_trunk_id: The SIP trunk ID to attach this dispatch rule to
        name: Name for this dispatch rule
        agent_name: Name of the agent to dispatch calls to
    
    Returns:
        CreateDispatchRuleResponse with dispatch rule details
    """
    try:
        log_info(f"Creating dispatch rule: '{name}'")
        log_info(f"Trunk ID: {sip_trunk_id}")
        log_info(f"Agent Name: {agent_name}")
        
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
        lkapi = api.LiveKitAPI(
            url=livekit_url,
            api_key=livekit_api_key,
            api_secret=livekit_api_secret
        )
        
        try:
            # Create a dispatch rule to place each caller in a separate room
            rule = api.SIPDispatchRule(
                dispatch_rule_individual=api.SIPDispatchRuleIndividual(
                    room_prefix='call-',
                )
            )
            
            request = api.CreateSIPDispatchRuleRequest(
                dispatch_rule=api.SIPDispatchRuleInfo(
                    rule=rule,
                    name=name,
                    trunk_ids=[sip_trunk_id],
                    room_config=api.RoomConfiguration(
                        agents=[api.RoomAgentDispatch(
                            agent_name=agent_name,
                            metadata="job dispatch metadata",
                        )]
                    )
                )
            )
            
            dispatch = await lkapi.sip.create_sip_dispatch_rule(request)
            
            log_info(f"✓ Dispatch rule created: {dispatch.sip_dispatch_rule_id}")
            
            # Log summary
            log_info(f"")
            log_info(f"======================================")
            log_info(f"  DISPATCH RULE CREATED")
            log_info(f"======================================")
            log_info(f"Rule Name:       {name}")
            log_info(f"Rule ID:         {dispatch.sip_dispatch_rule_id}")
            log_info(f"Trunk ID:        {sip_trunk_id}")
            log_info(f"Agent Name:      {agent_name}")
            log_info(f"Room Prefix:     call-")
            log_info(f"======================================")
            
            return CreateDispatchRuleResponse(
                status="success",
                message=f"Dispatch rule '{name}' created successfully with room prefix 'call-'",
                dispatch_rule_id=dispatch.sip_dispatch_rule_id,
                dispatch_rule_name=name
            )
            
        finally:
            await lkapi.aclose()
    
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error creating dispatch rule: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Dispatch rule creation error: {str(e)}"
        )


@router.get("/list-sip-trunks")
async def list_sip_trunks():
    """
    List all SIP trunks (both outbound and inbound) from LiveKit.
    
    This endpoint retrieves all configured SIP trunks to help you manage your trunks
    and find trunk IDs for deletion or other operations.
    
    Returns:
        Dictionary with outbound and inbound trunk lists
    
    Example Response:
        {
            "status": "success",
            "outbound_trunks": [
                {
                    "trunk_id": "ST_xxxxx",
                    "name": "My Outbound Trunk",
                    "phone_number": "+1234567890"
                }
            ],
            "inbound_trunks": [
                {
                    "trunk_id": "ST_yyyyy",
                    "name": "My Inbound Trunk",
                    "phone_numbers": ["+0987654321"]
                }
            ]
        }
    """
    try:
        log_info("Fetching all SIP trunks from LiveKit...")
        
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
            
            outbound_trunks = []
            inbound_trunks = []
            
            # List outbound trunks
            try:
                outbound_list_request = sip.ListSIPOutboundTrunkRequest()
                outbound_response = await lk.sip.list_sip_outbound_trunk(outbound_list_request)
                
                for trunk in outbound_response.items:
                    outbound_trunks.append({
                        "trunk_id": trunk.sip_trunk_id,
                        "name": trunk.name if hasattr(trunk, 'name') else "N/A",
                        "outbound_number": trunk.numbers[0] if hasattr(trunk, 'numbers') and trunk.numbers else "N/A",
                        "outbound_address": trunk.address if hasattr(trunk, 'address') else "N/A"
                    })
                log_info(f"✓ Listed {len(outbound_trunks)} outbound trunk(s)")
            except Exception as e:
                log_warning(f"Could not list outbound trunks: {str(e)}")
            
            # List inbound trunks
            try:
                inbound_list_request = sip.ListSIPInboundTrunkRequest()
                inbound_response = await lk.sip.list_sip_inbound_trunk(inbound_list_request)
                
                for trunk in inbound_response.items:
                    inbound_trunks.append({
                        "trunk_id": trunk.sip_trunk_id,
                        "name": trunk.name if hasattr(trunk, 'name') else "N/A",
                        "phone_numbers": list(trunk.numbers) if hasattr(trunk, 'numbers') else []
                    })
                log_info(f"✓ Listed {len(inbound_trunks)} inbound trunk(s)")
            except Exception as e:
                log_warning(f"Could not list inbound trunks: {str(e)}")
            
            await lk.aclose()
            
            log_info(f"✓ Total: {len(outbound_trunks)} outbound trunk(s) and {len(inbound_trunks)} inbound trunk(s)")
            
            return {
                "status": "success",
                "message": f"Found {len(outbound_trunks)} outbound and {len(inbound_trunks)} inbound trunk(s)",
                "total_outbound": len(outbound_trunks),
                "total_inbound": len(inbound_trunks),
                "outbound_trunks": outbound_trunks,
                "inbound_trunks": inbound_trunks
            }
            
        finally:
            await lk.aclose()
    
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error listing SIP trunks: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"SIP trunk listing error: {str(e)}"
        )


@router.delete("/delete-sip-trunk", response_model=StatusResponse)
async def delete_sip_trunk(trunk_id: str, trunk_type: str = "outbound"):
    """
    Delete a SIP trunk from LiveKit.
    
    This endpoint removes a SIP trunk configuration from LiveKit. Use this to clean up
    unused trunks or remove outdated configurations.
    
    Args:
        trunk_id: The LiveKit SIP trunk ID to delete
        trunk_type: Type of trunk - "outbound" or "inbound" (default: "outbound")
    
    Returns:
        StatusResponse with deletion status
    
    Example:
        DELETE /calls/delete-sip-trunk?trunk_id=ST_xxxxx&trunk_type=outbound
    """
    try:
        log_info(f"======================================")
        log_info(f"  SIP TRUNK DELETION STARTED")
        log_info(f"======================================")
        log_info(f"Deleting {trunk_type} SIP trunk: {trunk_id}")
        
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
            from livekit.api.sip_service import DeleteSIPTrunkRequest
            from livekit.api import AccessToken
            
            # Try using SDK method first (works for both inbound and outbound in newer versions)
            log_info(f"Attempting to delete {trunk_type} trunk using SDK method...")
            try:
                delete_request = DeleteSIPTrunkRequest(sip_trunk_id=trunk_id)
                await lk.sip.delete_trunk(delete_request)
                log_info(f"✓ {trunk_type.capitalize()} trunk deleted via SDK: {trunk_id}")
            except Exception as sdk_error:
                log_warning(f"SDK deletion failed: {str(sdk_error)}")
                
                if trunk_type.lower() == "inbound":
                    # Fallback to REST API for inbound trunks
                    log_info(f"Trying REST API as fallback for inbound trunk...")
                    
                    token = AccessToken(livekit_api_key, livekit_api_secret)
                    token.with_grants(api.VideoGrants(room_admin=True))
                    jwt_token = token.to_jwt()
                    
                    base_url = livekit_url.replace("wss://", "https://").replace("ws://", "http://")
                    url = f"{base_url}/sip/inbound/{trunk_id}"
                    
                    headers = {
                        "Authorization": f"Bearer {jwt_token}",
                        "Content-Type": "application/json"
                    }
                    
                    async with httpx.AsyncClient() as client:
                        log_info(f"Sending DELETE request to: {url}")
                        response = await client.delete(url, headers=headers)
                        
                        log_info(f"Response status: {response.status_code}")
                        log_info(f"Response body: {response.text}")
                        
                        if response.status_code in [200, 204]:
                            log_info(f"✓ Inbound trunk deleted via REST API: {trunk_id}")
                        elif response.status_code == 404:
                            log_error(f"Trunk not found: {trunk_id}")
                            raise HTTPException(status_code=404, detail=f"Trunk '{trunk_id}' not found")
                        else:
                            log_error(f"Delete failed with status {response.status_code}: {response.text}")
                            raise HTTPException(
                                status_code=response.status_code,
                                detail=f"Failed to delete trunk: {response.text}"
                            )
                else:
                    # Re-raise the error for outbound trunks
                    raise
            
            await lk.aclose()
            
            # Log summary
            log_info(f"")
            log_info(f"======================================")
            log_info(f"  SIP TRUNK DELETED SUCCESSFULLY")
            log_info(f"======================================")
            log_info(f"Trunk ID:        {trunk_id}")
            log_info(f"Trunk Type:      {trunk_type}")
            log_info(f"======================================")
            
            return StatusResponse(
                status="success",
                message=f"{trunk_type.capitalize()} SIP trunk '{trunk_id}' deleted successfully",
                details={
                    "trunk_id": trunk_id,
                    "trunk_type": trunk_type
                }
            )
            
        finally:
            await lk.aclose()
    
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error deleting SIP trunk: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"SIP trunk deletion error: {str(e)}"
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
            - krisp_enabled: Enable noise cancellation (default: True)
    
    Returns:
        SetupInboundSIPResponse with complete setup details
    
    Example:
        {
            "name": "CustomerSupport",
            "phone_numbers": ["+1234567890"],
            "room_name": "support-room",
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
            
            # Create the direct dispatch rule object
            direct_rule = sip.SIPDispatchRuleDirect()
            direct_rule.room_name = request.room_name
            rule_info.rule.dispatch_rule_direct.CopyFrom(direct_rule)
            
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

