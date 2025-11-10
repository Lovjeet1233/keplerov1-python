import os
import json
import asyncio
import logging
import sys
from datetime import datetime
from livekit import api
from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions
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
    TTS_MODEL, TTS_VOICE,STT_MODEL, STT_LANGUAGE, LLM_MODEL, TRANSCRIPT_DIR
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

async def hangup_call():
    """Hang up the current call"""
    from livekit.agents import get_job_context
    ctx = get_job_context()
    if ctx is None:
        # Not running in a job context
        return
    
    await ctx.api.room.delete_room(
        api.DeleteRoomRequest(
            room=ctx.room.name,
        )
    )

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
    logger.info("✓ Shutdown callback added")
    
    # Connect to the room
    logger.info("Connecting to room...")
    await ctx.connect()
    logger.info("✓ Connected to room successfully")

    # Initialize session components with error handling
    try:
        logger.info("Initializing session components...")
        
        logger.info("Step 1: Initializing STT (Deepgram)...")
        stt_instance = deepgram.STT(model=STT_MODEL, language=STT_LANGUAGE)
        logger.info("✓ STT initialized successfully")
        
        logger.info("Step 2: Initializing LLM (OpenAI)...")
        llm_instance = openai.LLM(model=LLM_MODEL)
        logger.info("✓ LLM initialized successfully")
        
        logger.info("Step 3: Initializing TTS (Google)...")
        # tts_instance = google.TTS()
        tts_instance = cartesia.TTS(
            model=TTS_MODEL, 
            emotion=emotion,
            language=language,
        
        )
        logger.info("✓ TTS initialized successfully")
        
        logger.info("Step 4: Creating AgentSession...")
        session = AgentSession(
            stt=stt_instance,
            llm=llm_instance,
            tts=tts_instance,
        )
        logger.info("✓ Session components initialized successfully")
        
    except Exception as e:
        logger.error(f"✗ Error initializing session: {e}", exc_info=True)
        raise

    # Track SIP participant
    sip_participant_identity = "sip-caller"
    greeting_sent = False

    # Handle participant connection
    async def handle_participant_connected(participant):
        nonlocal greeting_sent
        logger.info(f"Participant connected: {participant.identity}")
        
        # Send greeting only once and only for actual participants (not the agent)
        if not greeting_sent and participant.identity != "agent":
            greeting_sent = True
            await asyncio.sleep(2)  # Wait for connection to stabilize
            
            try:
                logger.info("Sending initial greeting...")
                # Build personalized greeting instruction
                greeting_instruction = "Greet the caller warmly, introduce yourself as an assistant from Island AI"
                if caller_name:
                    greeting_instruction += f", address them by name ({caller_name})"
                greeting_instruction += ", and ask how you can help them today."
                
                await session.generate_reply(instructions=greeting_instruction)
                logger.info("Initial greeting sent successfully")
            except Exception as e:
                logger.error(f"Error sending greeting: {e}")

    # Handle participant disconnection
    async def handle_disconnect(participant):
        logger.info(f"Participant disconnected: {participant.identity}")
        if participant.identity == sip_participant_identity:
            logger.info(f"SIP caller '{participant.identity}' disconnected — session will end")
            # Let the session handle cleanup naturally

    # Register event handlers
    def on_participant_connected(participant):
        asyncio.create_task(handle_participant_connected(participant))
    
    def on_disconnect(participant):
        asyncio.create_task(handle_disconnect(participant))

    ctx.room.on("participant_connected", on_participant_connected)
    ctx.room.on("participant_disconnected", on_disconnect)

    # Start the agent session
    try:
        logger.info("Starting agent session...")
        logger.info("Creating Assistant instance...")
        
        # Use dynamic instruction from environment variable
        assistant = Assistant(instructions=dynamic_instruction)
        logger.info("✓ Assistant instance created")
        logger.info(f"Using instructions: {dynamic_instruction[:100]}...")
        
        logger.info("Creating RoomInputOptions with BVC noise cancellation...")
        room_options = RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        )
        logger.info("✓ RoomInputOptions created")
        
        logger.info("Calling session.start()...")
        await session.start(
            room=ctx.room,
            agent=assistant,
            room_input_options=room_options,
        )
        logger.info("✓ Agent session started successfully")
        
        # Keep the session alive
        logger.info("Session running, keeping alive...")
        while True:
            await asyncio.sleep(0)
            
    except Exception as e:
        logger.error(f"✗ Error in agent session: {e}", exc_info=True)
        raise

def run_agent():
    """Run the agent with CLI interface"""
    logger.info("=" * 60)
    logger.info("RUN_AGENT CALLED - Starting LiveKit Agent CLI")
    logger.info("=" * 60)
    try:
        agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
    except Exception as e:
        logger.error(f"✗ Fatal error in run_agent: {e}", exc_info=True)
        raise 