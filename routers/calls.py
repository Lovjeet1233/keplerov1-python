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
from model import OutboundCallRequest, StatusResponse

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
    escalation_condition: str = None
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


async def wait_for_transcript(timeout: int = 300, check_interval: int = 10) -> Optional[dict]:
    """
    Wait for transcript file to appear in the transcripts folder.
    
    Args:
        timeout: Maximum time to wait in seconds (default: 300s = 5 minutes)
        check_interval: Time between checks in seconds (default: 10s)
        
    Returns:
        Transcript data as dict or None if timeout
    """
    elapsed_time = 0
    
    log_info(f"Starting to monitor for transcript file: {TRANSCRIPT_FILE}")
    
    while elapsed_time < timeout:
        # Check if transcript file exists
        if TRANSCRIPT_FILE.exists():
            try:
                log_info(f"Transcript file found after {elapsed_time} seconds")
                
                # Read the transcript
                with open(TRANSCRIPT_FILE, 'r', encoding='utf-8') as f:
                    transcript_data = json.load(f)
                
                log_info(f"Successfully read transcript file")
                
                # Delete the file after reading
                TRANSCRIPT_FILE.unlink()
                log_info(f"Transcript file deleted successfully")
                
                return transcript_data
                
            except Exception as e:
                log_error(f"Error reading/deleting transcript file: {str(e)}")
                # Try to delete the file even if reading failed
                try:
                    if TRANSCRIPT_FILE.exists():
                        TRANSCRIPT_FILE.unlink()
                except:
                    pass
                return None
        
        # Wait before next check
        await asyncio.sleep(check_interval)
        elapsed_time += check_interval
        
        if elapsed_time % 30 == 0:  # Log every 30 seconds
            log_info(f"Still waiting for transcript... ({elapsed_time}s elapsed)")
    
    log_warning(f"Transcript not received within {timeout} seconds timeout")
    return None


@router.post("/outbound", response_model=StatusResponse)
async def outbound_call(request: OutboundCallRequest):
    """
    Initiate an outbound call to the specified phone number and wait for transcript.
    
    This endpoint:
    1. Validates and initiates the outbound call
    2. Waits for the call to complete and transcript to be saved
    3. Polls transcripts/transcript.json every 10 seconds (max 5 minutes)
    4. Returns the transcript and deletes the file
    
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
        
    Returns:
        StatusResponse with call status and transcript (if available)
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
            escalation_condition=request.escalation_condition
        )
        log_info("✓ config.json updated successfully")
        
        log_info(f"Initiating call to formatted number: '{formatted_number}'")
        
        # Clear any existing transcript file before making new call
        if TRANSCRIPT_FILE.exists():
            try:
                TRANSCRIPT_FILE.unlink()
                log_info("Cleared existing transcript file before new call")
            except Exception as e:
                log_warning(f"Could not clear existing transcript: {str(e)}")
        
        # Make the outbound call
        await make_outbound_call(
            phone_number=formatted_number,
            sip_trunk_id=request.sip_trunk_id
        )
        
        log_info(f"Successfully initiated call to '{formatted_number}' for {request.name or 'caller'}")
        
        # Wait for transcript to be generated
        log_info("Waiting for call transcript...")
        transcript = await wait_for_transcript(timeout=300, check_interval=10)
        
        if transcript:
            log_info("Transcript received and will be included in response")
        else:
            log_warning("No transcript received within timeout period")
        
        return StatusResponse(
            status="success",
            message=f"Outbound call completed to {formatted_number}" + (f" for {request.name}" if request.name else ""),
            details={
                "phone_number": formatted_number,
                "original_input": request.phone_number,
                "name": request.name,
                "has_dynamic_instruction": bool(request.dynamic_instruction),
                "language": request.language,
                "voice_id": request.voice_id,
                "sip_trunk_id": request.sip_trunk_id,
                "transfer_to": request.transfer_to,
                "escalation_condition": request.escalation_condition,
                "transcript_received": transcript is not None
            },
            transcript=transcript
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
            escalation_condition=request.escalation_condition
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

