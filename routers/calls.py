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
from model import OutboundCallRequest, StatusResponse

load_dotenv()

router = APIRouter(prefix="/calls", tags=["Calls"])

# Transcript folder path
TRANSCRIPT_FOLDER = Path("transcripts")
TRANSCRIPT_FILE = TRANSCRIPT_FOLDER / "transcript.json"


def update_env_file(
    dynamic_instruction: str = None,
    caller_name: str = None,
    language: str = "en",
    emotion: str = "Calm"
):
    """
    Update the .env file with dynamic agent instructions, caller name, language, and emotion.
    
    Args:
        dynamic_instruction: Custom instructions for the AI agent
        caller_name: Name of the person being called
        language: TTS language (e.g., "en", "es", "fr")
        emotion: TTS emotion (e.g., "Calm", "Excited", "Serious")
    """
    env_path = Path(".env")
    
    # Read existing .env content
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    else:
        lines = []
    
    # Build the new instruction
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
    
    # Check if environment variables exist and update them
    agent_instructions_found = False
    caller_name_found = False
    language_found = False
    emotion_found = False
    
    for i, line in enumerate(lines):
        if line.strip().startswith('AGENT_INSTRUCTIONS='):
            lines[i] = f'AGENT_INSTRUCTIONS="{full_instruction}"\n'
            agent_instructions_found = True
        elif line.strip().startswith('CALLER_NAME='):
            lines[i] = f'CALLER_NAME="{caller_name or ""}"\n'
            caller_name_found = True
        elif line.strip().startswith('TTS_LANGUAGE='):
            lines[i] = f'TTS_LANGUAGE="{language}"\n'
            language_found = True
        elif line.strip().startswith('TTS_EMOTION='):
            lines[i] = f'TTS_EMOTION="{emotion}"\n'
            emotion_found = True
    
    # If not found, append to the file
    if not agent_instructions_found:
        lines.append(f'AGENT_INSTRUCTIONS="{full_instruction}"\n')
    
    if not caller_name_found and caller_name:
        lines.append(f'CALLER_NAME="{caller_name}"\n')
    
    if not language_found:
        lines.append(f'TTS_LANGUAGE="{language}"\n')
    
    if not emotion_found:
        lines.append(f'TTS_EMOTION="{emotion}"\n')
    
    # Write back to .env
    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    # Update the current process environment
    os.environ['AGENT_INSTRUCTIONS'] = full_instruction
    if caller_name:
        os.environ['CALLER_NAME'] = caller_name
    os.environ['TTS_LANGUAGE'] = language
    os.environ['TTS_EMOTION'] = emotion
    
    log_info(f"Updated AGENT_INSTRUCTIONS: {full_instruction[:100]}...")
    if caller_name:
        log_info(f"Updated CALLER_NAME: {caller_name}")
    log_info(f"Updated TTS_LANGUAGE: {language}")
    log_info(f"Updated TTS_EMOTION: {emotion}")


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
            - emotion: TTS emotion (default: "Calm")
        
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
        
        # Update .env file with dynamic parameters
        log_info("Updating .env file with dynamic parameters...")
        update_env_file(
            dynamic_instruction=request.dynamic_instruction,
            caller_name=request.name,
            language=request.language,
            emotion=request.emotion
        )
        log_info("✓ .env file updated successfully")
        
        log_info(f"Initiating call to formatted number: '{formatted_number}'")
        
        # Clear any existing transcript file before making new call
        if TRANSCRIPT_FILE.exists():
            try:
                TRANSCRIPT_FILE.unlink()
                log_info("Cleared existing transcript file before new call")
            except Exception as e:
                log_warning(f"Could not clear existing transcript: {str(e)}")
        
        # Make the outbound call
        await make_outbound_call(phone_number=formatted_number)
        
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
                "emotion": request.emotion,
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
            - emotion: TTS emotion (default: "Calm")
        
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
        
        # Update .env file with dynamic parameters for the agent
        # The outbound.py agent worker will read these values
        log_info("Updating .env file with dynamic parameters for agent...")
        update_env_file(
            dynamic_instruction=request.dynamic_instruction,
            caller_name=request.name,
            language=request.language,
            emotion=request.emotion
        )
        log_info("✓ .env file updated successfully")
        
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
                    "emotion": request.emotion,
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

