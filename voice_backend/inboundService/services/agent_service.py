import os
import logging
import sys
import asyncio
from livekit import api
from livekit import agents
from livekit.agents import (
    AgentSession, 
    Agent, 
    RoomInputOptions, 
    function_tool, 
    RunContext, 
    get_job_context, 
    JobProcess,
    JobRequest,
    AutoSubscribe
)
from livekit.plugins import openai, deepgram, noise_cancellation, silero, elevenlabs
from dotenv import load_dotenv
from RAGService import RAGService

load_dotenv()

# ------------------------------------------------------------
# Environment variables
# ------------------------------------------------------------
LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

# Agent configuration
AGENT_INSTRUCTIONS = os.getenv("AGENT_INSTRUCTIONS", "You are a helpful voice AI assistant of Aistein.")
TRANSFER_NUMBER = os.getenv("TRANSFER_NUMBER", "+919911062767")

# ------------------------------------------------------------
# Logging setup
# ------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("agent_debug.log")
    ]
)
logger = logging.getLogger("services.agent_service")

logger.info("=" * 60)
logger.info("Inbound Agent Service Module Loading")
logger.info(f"LIVEKIT_URL: {LIVEKIT_URL or 'NOT SET'}")
logger.info(f"LIVEKIT_API_KEY: {'SET' if LIVEKIT_API_KEY else 'NOT SET'}")
logger.info(f"LIVEKIT_API_SECRET: {'SET' if LIVEKIT_API_SECRET else 'NOT SET'}")
logger.info(f"OPENAI_API_KEY: {'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}")
logger.info(f"DEEPGRAM_API_KEY: {'SET' if os.getenv('DEEPGRAM_API_KEY') else 'NOT SET'}")
logger.info(f"ELEVENLABS_API_KEY: {'SET' if os.getenv('ELEVEN_API_KEY') else 'NOT SET'}")
logger.info(f"TRANSFER_NUMBER: {TRANSFER_NUMBER}")
logger.info("=" * 60)

# Validate required environment variables
if not LIVEKIT_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
    logger.error("ERROR: Missing required LiveKit credentials!")
    logger.error("Please set LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET in .env file")
    sys.exit(1)


# ------------------------------------------------------------
# Simple Assistant class
# ------------------------------------------------------------
class Assistant(Agent):
    def __init__(self, instructions: str = None) -> None:
        if instructions is None:
            instructions = AGENT_INSTRUCTIONS or "You are a helpful voice AI assistant of Aistein."
        logger.info(f"Agent initialized with instructions: {instructions[:100]}...")
        self.rag_service = RAGService()
        super().__init__(instructions=instructions)

    @function_tool
    async def transfer_to_human(self, ctx: RunContext) -> str:
        """Transfer active SIP caller to a human number."""
        job_ctx = get_job_context()
        if job_ctx is None:
            logger.error("Job context not found")
            return "error"
        
        # Format transfer number
        transfer_to = TRANSFER_NUMBER if TRANSFER_NUMBER.startswith("tel:") else f"tel:{TRANSFER_NUMBER}"
        logger.info(f"Transfer requested to: {transfer_to}")

        # Find SIP participant
        sip_participant = None
        for participant in job_ctx.room.remote_participants.values():
            if participant.identity == "sip-caller":
                sip_participant = participant
                break

        if sip_participant is None:
            logger.error("No SIP participant found to transfer")
            return "error"

        try:
            await job_ctx.api.sip.transfer_sip_participant(
                api.TransferSIPParticipantRequest(
                    room_name=job_ctx.room.name,
                    participant_identity=sip_participant.identity,
                    transfer_to=transfer_to,
                    play_dialtone=True
                )
            )
            logger.info(f"Transferred participant to {transfer_to}")
            return "transferred"
        except Exception as e:
            logger.error(f"Failed to transfer call: {e}", exc_info=True)
            return "error"

    @function_tool
    async def end_call(self, ctx: RunContext) -> str:
        """End call gracefully."""
        job_ctx = get_job_context()
        if job_ctx is None:
            logger.error("Failed to get job context")
            return "error"

        try:
            await job_ctx.api.room.delete_room(api.DeleteRoomRequest(room=job_ctx.room.name))
            logger.info(f"Successfully ended call for room {job_ctx.room.name}")
            return "ended"
        except Exception as e:
            logger.error(f"Failed to end call: {e}", exc_info=True)
            return "error"

    @function_tool
    async def knowledge_base_search(self, query: str) -> str:
        """Search the knowledge base for the query."""
        logger.info(f"Knowledge base search requested for query: {query}")
        
        answer = self.rag_service.search_knowledge_base(query)
        return answer

# ------------------------------------------------------------
# Request handler - CRITICAL FOR AUTO-ACCEPT
# ------------------------------------------------------------
async def request_fnc(req: JobRequest) -> None:
    """
    Job request handler - accepts ALL incoming job requests.
    This is CRITICAL for SIP calls to work properly.
    """
    logger.info("=" * 60)
    logger.info(f"JOB REQUEST RECEIVED!")
    logger.info(f"Room: {req.room.name}")
    logger.info(f"Job ID: {req.id}")
    logger.info(f"Accepting job automatically...")
    logger.info("=" * 60)
    
    # Always accept the job
    await req.accept(entrypoint_fnc=entrypoint)


# ------------------------------------------------------------
# Inbound Agent entrypoint
# ------------------------------------------------------------
async def entrypoint(ctx: agents.JobContext):
    """Entrypoint for inbound SIP voice calls."""
    logger.info("=" * 60)
    logger.info(f"🔥 ENTRYPOINT TRIGGERED - Room: {ctx.room.name}")
    logger.info(f"Participants: {len(ctx.room.remote_participants)}")
    logger.info("=" * 60)

    # --------------------------------------------------------
    # Step 1: Connect to room
    # --------------------------------------------------------
    try:
        logger.info("Connecting to room...")
        await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
        logger.info("[OK] Connected to room successfully")
    except Exception as e:
        logger.error(f"[ERROR] Failed to connect to room: {e}", exc_info=True)
        raise

    # Log SIP participant info
    for participant in ctx.room.remote_participants.values():
        logger.info(f"Participant: {participant.identity} - {participant.name}")

    # --------------------------------------------------------
    # Step 2: Initialize AI components (STT, LLM, TTS, VAD)
    # --------------------------------------------------------
    try:
        logger.info("Initializing AI components...")
        
        # Initialize STT (Deepgram)
        stt_instance = deepgram.STT(
            model="nova-2-general",
            language="en"
        )
        logger.info("[OK] STT initialized (Deepgram nova-2-general)")
        
        # Initialize LLM (OpenAI)
        llm_instance = openai.LLM(model="gpt-4o-mini")
        logger.info("[OK] LLM initialized (gpt-4o-mini)")
        
        # Initialize TTS (ElevenLabs)
        tts_instance = elevenlabs.TTS(
            base_url="https://api.eu.residency.elevenlabs.io/v1",
            voice_id="bIHbv24MWmeRgasZH58o",
            language="en",
        )
        logger.info("[OK] TTS initialized (ElevenLabs)")
        
        # Initialize VAD (Silero)
        vad_instance = silero.VAD.load()
        logger.info("[OK] VAD initialized (Silero)")
        
        # Create session
        logger.info("Creating AgentSession...")
        session = AgentSession(
            vad=vad_instance,
            stt=stt_instance,
            llm=llm_instance,
            tts=tts_instance
        )
        logger.info("[OK] AgentSession created successfully")
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to initialize AI components: {e}", exc_info=True)
        raise

    # --------------------------------------------------------
    # Step 3: Create assistant and start session
    # --------------------------------------------------------
    try:
        logger.info("Creating Assistant instance...")
        assistant = Assistant()
        
        logger.info("Configuring room input options...")
        room_options = RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC()
        )
        
        logger.info("Starting agent session...")
        await session.start(
            room=ctx.room,
            agent=assistant,
            room_input_options=room_options
        )
        logger.info("[OK] Agent session started successfully")
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to start agent session: {e}", exc_info=True)
        raise

    # --------------------------------------------------------
    # Step 4: Send greeting
    # --------------------------------------------------------
    try:
        greeting_message = "Hello, I'm your AI assistant. How can I help you today?"
        logger.info(f"Sending greeting: '{greeting_message}'")
        
        await session.say(greeting_message, allow_interruptions=True)
        logger.info("[OK] Greeting sent successfully")
            
    except Exception as e:
        logger.error(f"[ERROR] Failed to send greeting: {e}", exc_info=True)

    # --------------------------------------------------------
    # Step 5: Keep session alive
    # --------------------------------------------------------
    logger.info("Session running - waiting for call to end...")
    logger.info("=" * 60)




# ------------------------------------------------------------
# CLI entrypoint
# ------------------------------------------------------------
def run_agent():
    """Run the inbound agent worker."""
    logger.info("=" * 60)
    logger.info("🚀 RUN_AGENT CALLED - Starting LiveKit Inbound Agent CLI")
    logger.info("=" * 60)
    
    logger.info("Mode: AUTO-ACCEPT all incoming SIP calls")
    logger.info("Agent will run CONTINUOUSLY - press Ctrl+C to stop")
    logger.info("=" * 60)
    
    try:
        # CRITICAL: Use request_fnc for auto-accepting jobs
        # This allows the agent to accept ANY incoming job request
        worker_options = agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            # request_fnc=request_fnc,  # Auto-accept handler
            agent_name="inbound-agent"  # Must match dispatch rule "Agents" field
        )
        
        logger.info("✓ Worker configured with AUTO-ACCEPT mode")
        logger.info("✓ Ready to receive calls...")
        agents.cli.run_app(worker_options)
        logger.info("Agent CLI exited normally")
    except KeyboardInterrupt:
        logger.info("\n👋 Agent stopped by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"[ERROR] Fatal error in run_agent: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    run_agent()