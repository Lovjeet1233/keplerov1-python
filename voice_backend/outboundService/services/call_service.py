import asyncio
import time
from livekit import api
from livekit.protocol.sip import CreateSIPParticipantRequest
from voice_backend.outboundService.common.config.settings import (
    SIP_TRUNK_ID, ROOM_NAME, PARTICIPANT_IDENTITY, 
    PARTICIPANT_NAME, CALL_TIMEOUT
)

async def make_outbound_call(phone_number: str):
    """
    Make an outbound call to the specified phone number
    Agent instructions are read from .env AGENT_INSTRUCTIONS variable
    
    Args:
        phone_number: The phone number to call
    """
    print("Initiating outbound call...")
    print("Connecting to LiveKit API...")
    
    livekit_api = api.LiveKitAPI()
    
    request = CreateSIPParticipantRequest(
        sip_trunk_id=SIP_TRUNK_ID,
        sip_call_to=phone_number,
        room_name=ROOM_NAME,
        participant_identity=PARTICIPANT_IDENTITY,
        participant_name=PARTICIPANT_NAME,
        krisp_enabled=True,
        wait_until_answered=True
    )
    
    try:
        print(f"📱 Calling {phone_number}...")
        print(f"🏠 Room: {ROOM_NAME}")
        
        start_time = time.time()
        participant = await livekit_api.sip.create_sip_participant(request)
        connection_time = time.time() - start_time
        
        print(f"✓ Connection established in {connection_time:.2f} seconds")
        print(f"* Participant ID: {participant.participant_id}")
        print(f"* SIP Call ID: {participant.sip_call_id}")
        print(f"* Room: {participant.room_name}")
        print("-" * 50)
        print("✓ The AI assistant should now be speaking to the caller")
        print("* Metrics are being logged in real-time")
        
    except Exception as e:
        print(f"✗ Error creating SIP participant: {e}")
        print("⚠ Make sure:")
        print("   1. Your agent is running first")
        print("   2. SIP trunk ID is correct")
        print("   3. Phone number format is correct")
        print("   4. LiveKit credentials are set")
        raise
    finally:
        await livekit_api.aclose()

async def process_contacts_with_delay(contacts: list, delay_seconds: int):
    """
    Process multiple contacts with delay between calls
    
    Args:
        contacts: List of phone numbers
        delay_seconds: Delay between calls in seconds
    """
    for phone_number in contacts:
        await make_outbound_call(phone_number)
        await asyncio.sleep(delay_seconds) 