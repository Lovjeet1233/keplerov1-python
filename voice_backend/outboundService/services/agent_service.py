import os
import json
import asyncio
import logging
import sys
from datetime import datetime
from livekit import api
from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, function_tool, RunContext,get_job_context
from livekit.plugins import (
    openai,
    cartesia,
    deepgram,
    noise_cancellation,
    silero,
    google
)
from dotenv import load_dotenv
load_dotenv()
# Commented out to avoid inference executor timeout on Windows
# from livekit.plugins.turn_detector.multilingual import MultilingualModel
from common.config.settings import (
    TTS_MODEL, TTS_VOICE,STT_MODEL, STT_LANGUAGE, LLM_MODEL, TRANSCRIPT_DIR, PARTICIPANT_IDENTITY
)

# Configure logging with more detail
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('agent_debug.log')
    ]
)
logger = logging.getLogger(__name__)

# Log environment check at module load
logger.info("=" * 60)
logger.info("Agent Service Module Loading")
logger.info(f"LIVEKIT_URL: {os.getenv('LIVEKIT_URL', 'NOT SET')}")
logger.info(f"LIVEKIT_API_KEY: {'SET' if os.getenv('LIVEKIT_API_KEY') else 'NOT SET'}")
logger.info(f"LIVEKIT_API_SECRET: {'SET' if os.getenv('LIVEKIT_API_SECRET') else 'NOT SET'}")
logger.info(f"OPENAI_API_KEY: {'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}")
logger.info(f"STT_MODEL: {STT_MODEL}")
logger.info(f"LLM_MODEL: {LLM_MODEL}")
logger.info("=" * 60)

class Assistant(Agent):
    def __init__(self, instructions: str = None) -> None:
        if instructions is None:
            instructions = os.getenv("AGENT_INSTRUCTIONS", "You are a helpful voice AI assistant.")
        logger.info(f"Agent initialized with instructions: {instructions}")
        super().__init__(instructions=instructions)
    
    @function_tool
    async def transfer_to_human(self, ctx: RunContext) -> str:
        job_ctx = get_job_context()
        for p in job_ctx.room.remote_participants.values():
            logger.info(f"Participant identity: {p.identity}")
        if job_ctx is None:
            logger.error("Job context not found")
            return "error"

        transfer_to = "tel:+919911062767"

        # find sip participant
        sip_participant = None
        for participant in job_ctx.room.remote_participants.values():
            # if participant.identity.startswith("sip:"):
            if participant.identity == "sip-caller":
                sip_participant = participant
                break

        if sip_participant is None:
            logger.error("No SIP participant found")
            return "error"

        logger.info(f"Transferring call for participant {sip_participant.identity} to {transfer_to}")

        try:
            await job_ctx.api.sip.transfer_sip_participant(
                api.TransferSIPParticipantRequest(
                    room_name=job_ctx.room.name,
                    participant_identity=sip_participant.identity,
                    transfer_to=transfer_to,
                    play_dialtone=True
                )
            )
            logger.info(f"Successfully transferred participant {sip_participant.identity} to {transfer_to}")
            return "transferred"
        except Exception as e:
            logger.error(f"Failed to transfer call: {e}", exc_info=True)
            return "error"

    @function_tool
    async def end_call(ctx: RunContext) -> str:
        """End call. If the user isn't interested, expresses general disinterest or wants to end the call"""
        logger = logging.getLogger("phone-assistant")

        job_ctx = get_job_context()
        if job_ctx is None:
            logger.error("Failed to get job context")
            return "error"

        logger.info(f"Ending call for room {job_ctx.room.name}")

        try:
            await job_ctx.api.room.delete_room(
                api.DeleteRoomRequest(
                    room=job_ctx.room.name,
                )
            )
            logger.info(f"Successfully ended call for room {job_ctx.room.name}")
            return "ended"
        except Exception as e:
            logger.error(f"Failed to end call: {e}", exc_info=True)
            return "error"


async def entrypoint(ctx: agents.JobContext):
    """Main entrypoint for the agent service"""
    logger.info("=" * 60)
    logger.info(f"ENTRYPOINT CALLED - Room: {ctx.room.name}")
    logger.info("=" * 60)
    
    # Read dynamic parameters from environment variables
    caller_name = os.getenv("CALLER_NAME", None)
    dynamic_instruction = os.getenv("AGENT_INSTRUCTIONS", "You are a helpful voice AI assistant.")
    language=os.getenv("TTS_LANGUAGE", "en")
    emotion=os.getenv("TTS_EMOTION", "Calm")
    logger.info(f"Caller Name: {caller_name if caller_name else 'Not set'}")
    logger.info(f"Agent Instructions: {dynamic_instruction[:100]}...")
    
    # Transcript cleanup function
    async def cleanup_and_save():
        try:
            logger.info("Cleanup started...")
            # Save transcript
            os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
            filename = f"{TRANSCRIPT_DIR}/transcript.json"
            
            with open(filename, 'w') as f:
                json.dump(session.history.to_dict(), f, indent=2)
                
            logger.info(f"Transcript for {ctx.room.name} saved to {filename}")
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)

    logger.info("Adding shutdown callback...")
    ctx.add_shutdown_callback(cleanup_and_save)
    logger.info("[OK] Shutdown callback added")
    
    # Initialize session components with error handling BEFORE connecting
    try:
        logger.info("Initializing session components...")
        
        logger.info("Step 1: Initializing STT (Deepgram)...")
        stt_instance = deepgram.STT(model=STT_MODEL, language=STT_LANGUAGE)
        logger.info("[OK] STT initialized successfully")
        
        logger.info("Step 2: Initializing LLM (OpenAI)...")
        from livekit.plugins import openai as openai_plugin
        
        # Create AssistantLLM with function calling support
        llm_instance = openai_plugin.LLM(model=LLM_MODEL)
        logger.info("[OK] LLM initialized successfully")
        
        logger.info("Step 3: Initializing TTS (Google)...")
        # tts_instance = google.TTS()
        tts_instance = cartesia.TTS(
            model=TTS_MODEL, 
            emotion=emotion,
            language=language,
        
        )
        logger.info("[OK] TTS initialized successfully")
        
        logger.info("Step 4: Creating AgentSession...")
        session = AgentSession(
            stt=stt_instance,
            llm=llm_instance,
            tts=tts_instance,
        )
        logger.info("[OK] Session components initialized successfully")
        
    except Exception as e:
        logger.error(f"[ERROR] Error initializing session: {e}", exc_info=True)
        raise

    # Track SIP participant
    sip_participant_identity = "sip-caller"
    greeting_sent = False

    # Handle participant connection
    async def handle_participant_connected(participant):
        nonlocal greeting_sent
        logger.info(f"Participant connected - Identity: '{participant.identity}', Kind: {participant.kind}")
        
        # Check if this is a SIP participant (could be "sip-caller" or start with "sip:")
        is_sip = participant.identity == sip_participant_identity or participant.identity.startswith("sip:")
        logger.info(f"Is SIP participant: {is_sip}")
        
        # Send greeting only once and only for actual participants (not the agent)
        if not greeting_sent and participant.identity not in ["agent", "agent-worker"]:
            greeting_sent = True
            logger.info("Waiting for connection to stabilize before greeting...")
            await asyncio.sleep(2)  # Wait for connection to stabilize
            
            try:
                logger.info("Sending initial greeting...")
                # Build personalized greeting instruction
                greeting_instruction = "Greet the caller warmly, introduce yourself as an assistant from Island AI"
                if caller_name:
                    greeting_instruction += f", address them by name ({caller_name})"
                greeting_instruction += ", and ask how you can help them today."
                
                await session.generate_reply(instructions=greeting_instruction)
                logger.info("[OK] Initial greeting sent successfully")
            except Exception as e:
                logger.error(f"[ERROR] Error sending greeting: {e}", exc_info=True)

    # Handle participant disconnection
    async def handle_disconnect(participant):
        nonlocal greeting_sent
        logger.info(f"Participant disconnected: {participant.identity}")
        if participant.identity == sip_participant_identity or participant.identity.startswith("sip:"):
            logger.info(f"SIP caller '{participant.identity}' disconnected — ending session")
            try:
                # End the room to properly cleanup
                await ctx.api.room.delete_room(
                    api.DeleteRoomRequest(room=ctx.room.name)
                )
                logger.info(f"Room {ctx.room.name} deleted successfully")
                logger.info("Shutting down agent to allow new calls...")
                # Exit the session gracefully - this allows the worker to handle new rooms
                await ctx.shutdown()
            except Exception as e:
                logger.error(f"Error deleting room: {e}", exc_info=True)
        else:
            # Reset greeting flag if a non-SIP participant leaves (to support reconnection)
            logger.info("Resetting greeting flag for potential reconnection")
            greeting_sent = False

    # Register event handlers BEFORE starting session
    def on_participant_connected(participant):
        asyncio.create_task(handle_participant_connected(participant))
    
    def on_disconnect(participant):
        asyncio.create_task(handle_disconnect(participant))

    logger.info("Registering event handlers...")
    ctx.room.on("participant_connected", on_participant_connected)
    ctx.room.on("participant_disconnected", on_disconnect)
    logger.info("[OK] Event handlers registered")

    # Connect to the room NOW (after everything is ready)
    logger.info("Connecting to room...")
    await ctx.connect()
    logger.info("[OK] Connected to room successfully - agent is ready for participants")
    
    # Log existing participants in the room
    logger.info(f"Checking for existing participants in room...")
    logger.info(f"Remote participants: {len(ctx.room.remote_participants)}")
    for identity, participant in ctx.room.remote_participants.items():
        logger.info(f"  - Existing participant: '{identity}' (Kind: {participant.kind})")
        # Trigger greeting for existing participants
        await handle_participant_connected(participant)

    # Start the agent session
    try:
        logger.info("Starting agent session...")
        logger.info("Creating Assistant instance...")
        
        # Use dynamic instruction from environment variable
        assistant = Assistant(instructions=dynamic_instruction)
        logger.info("[OK] Assistant instance created")
        logger.info(f"Using instructions: {dynamic_instruction[:100]}...")
        logger.info("[OK] Transfer tool registered via @function_tool decorator")
        
        logger.info("Creating RoomInputOptions with BVC noise cancellation...")
        room_options = RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        )
        logger.info("[OK] RoomInputOptions created")
        
        logger.info("Calling session.start()...")
        await session.start(
            room=ctx.room,
            agent=assistant,
            room_input_options=room_options,
        )
        logger.info("[OK] Agent session started successfully")
        
        # Keep the session alive - wait for shutdown
        logger.info("Session running, waiting for shutdown...")
        await ctx.wait_for_shutdown()
        logger.info("Agent shutdown completed - ready for next call")
            
    except Exception as e:
        logger.error(f"[ERROR] Error in agent session: {e}", exc_info=True)
        raise
    finally:
        logger.info("=" * 60)
        logger.info(f"ENTRYPOINT FINISHED - Room: {ctx.room.name}")
        logger.info("=" * 60)

def run_agent():
    """Run the agent with CLI interface"""
    logger.info("=" * 60)
    logger.info("RUN_AGENT CALLED - Starting LiveKit Agent CLI")
    logger.info("=" * 60)
    try:
        agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
    except Exception as e:
        logger.error(f"[ERROR] Fatal error in run_agent: {e}", exc_info=True)
        raise 