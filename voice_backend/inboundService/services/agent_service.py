import os
import logging
import sys
import asyncio
from datetime import datetime
from pathlib import Path

# Add project root to Python path to import RAGService
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

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

# Add database imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))
from database.mongo import get_mongodb_manager

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
logger.info(f"QDRANT_URL: {'SET' if os.getenv('QDRANT_URL') else 'NOT SET'}")
logger.info(f"QDRANT_API_KEY: {'SET' if os.getenv('QDRANT_API_KEY') else 'NOT SET'}")
logger.info(f"TRANSFER_NUMBER: {TRANSFER_NUMBER}")
logger.info(f"RAG Mode: Search ALL documents in main_collection (no collection filter)")
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
        
        # Initialize RAG service with required credentials
        qdrant_url = os.getenv("QDRANT_URL")
        qdrant_api_key = os.getenv("QDRANT_API_KEY")
        openai_api_key = os.getenv("OPENAI_API_KEY")
        
        if qdrant_url and qdrant_api_key and openai_api_key:
            self.rag_service = RAGService(
                qdrant_url=qdrant_url,
                qdrant_api_key=qdrant_api_key,
                openai_api_key=openai_api_key
            )
            logger.info("RAG service initialized successfully")
        else:
            self.rag_service = None
            logger.warning("RAG service not initialized - missing credentials")
        
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
        """
        Search in the entire knowledge base for information. Use this when user asks specific questions.
        This searches ALL documents in main_collection without filtering by specific collections.
        The agent will say 'Let me check' before calling this.
        
        Args:
            query: The user's question to search for
        """
        logger.info(f"Knowledge base search requested for query: {query}")
        
        # Acknowledgment message that agent will speak
        acknowledgment = "Let me check that for you. "
        
        # Check if RAG service is available
        if not self.rag_service:
            logger.error("RAG service not initialized")
            return acknowledgment + "I'm sorry, the knowledge base is not available right now."
        
        try:
            logger.info("Searching across ALL documents in main_collection (no collection filter)")
            
            # Perform search without collection filter (searches all documents)
            search_results = self.rag_service.retrieval_based_search(
                query=query,
                collections=None,  # No filter = search all documents
                top_k=3
            )
            
            # Format results into a readable answer
            if not search_results:
                return acknowledgment + "I couldn't find any relevant information in the knowledge base."
            
            # Extract and combine text from top results
            relevant_texts = [result['text'] for result in search_results]
            combined_context = " ".join(relevant_texts[:2])  # Use top 2 results
            
            logger.info(f"Found {len(search_results)} results from collections: {[r.get('collection') for r in search_results]}")
            
            # Return acknowledgment + context for the agent to synthesize an answer
            return acknowledgment + f"Based on the knowledge base: {combined_context}"
            
        except Exception as e:
            logger.error(f"Error in knowledge base search: {e}", exc_info=True)
            return acknowledgment + "I'm sorry, I encountered an error while searching the knowledge base."

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
    # Track session variables for cleanup
    # --------------------------------------------------------
    session_start_time = None
    egress_id = None
    gcs_bucket = None

    # --------------------------------------------------------
    # Step 1.5: Recording and cleanup functions
    # --------------------------------------------------------
    async def start_recording():
        """Start recording the room audio to Google Cloud Storage."""
        nonlocal egress_id, gcs_bucket
        try:
            logger.info("Starting GCS recording...")
            
            # Validate GCS configuration
            gcs_bucket = os.getenv("GCS_BUCKET_NAME")
            gcs_credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            gcs_credentials_json = os.getenv("GCP_CREDENTIALS_JSON")
            
            if not gcs_bucket:
                logger.warning("GCS_BUCKET_NAME not set - skipping recording")
                return
            
            # Get credentials from either file path or environment variable
            credentials_json = None
            
            # Option 1: Direct JSON from environment variable (recommended for cloud)
            if gcs_credentials_json:
                logger.info("Using GCP credentials from GCP_CREDENTIALS_JSON environment variable")
                credentials_json = gcs_credentials_json
            
            # Option 2: Read from file path (for local development)
            elif gcs_credentials_path:
                logger.info(f"Using GCP credentials from file: {gcs_credentials_path}")
                try:
                    with open(gcs_credentials_path, 'r') as f:
                        credentials_json = f.read()
                except FileNotFoundError:
                    logger.error(f"Credentials file not found: {gcs_credentials_path}")
                    return
                except Exception as e:
                    logger.error(f"Failed to read credentials file: {e}")
                    return
            else:
                logger.warning("No GCP credentials provided (set GCP_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS) - skipping recording")
                return
            
            if not credentials_json:
                logger.error("Failed to load GCP credentials")
                return
            
            # Start room composite egress using the job context API
            egress_info = await ctx.api.egress.start_room_composite_egress(
                api.RoomCompositeEgressRequest(
                    room_name=ctx.room.name,
                    audio_only=True,
                    file_outputs=[
                        api.EncodedFileOutput(
                            file_type=api.EncodedFileType.OGG,
                            filepath=f"calls/{ctx.room.name}.ogg",
                            gcp=api.GCPUpload(
                                bucket=gcs_bucket,
                                credentials=credentials_json,
                            ),
                        )
                    ],
                )
            )
            
            # Store egress ID for cleanup
            egress_id = egress_info.egress_id
            
            logger.info(f"Recording started successfully - Egress ID: {egress_id}")
            logger.info(f"Recording will be saved to: gs://{gcs_bucket}/calls/{ctx.room.name}.ogg")
            
        except Exception as e:
            logger.error(f"Failed to start recording: {e}", exc_info=True)
            logger.warning("Call will continue without recording")
    
    async def stop_recording():
        """
        Stop the egress recording while the connection is still active.
        This runs BEFORE the main cleanup to ensure API is still available.
        """
        nonlocal egress_id, gcs_bucket
        if not egress_id:
            logger.info("No active recording to stop (egress_id not set)")
            return
            
        try:
            logger.info(f"Stopping egress recording: {egress_id}")
            
            # Try to use existing ctx.api first
            try:
                await ctx.api.egress.stop_egress(
                    api.StopEgressRequest(egress_id=egress_id)
                )
                logger.info(f"✓ Recording stopped successfully - Egress ID: {egress_id}")
                if gcs_bucket:
                    logger.info(f"✓ Recording saved to: gs://{gcs_bucket}/calls/{ctx.room.name}.ogg")
                return
            except Exception as ctx_error:
                logger.warning(f"Failed to stop egress via ctx.api: {ctx_error}")
                logger.info("Attempting with fresh API client...")
                
                # Fallback: Create a fresh API client if ctx.api is unavailable
                if LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET:
                    try:
                        fresh_api = api.LiveKitAPI(
                            url=LIVEKIT_URL,
                            api_key=LIVEKIT_API_KEY,
                            api_secret=LIVEKIT_API_SECRET
                        )
                        await fresh_api.egress.stop_egress(
                            api.StopEgressRequest(egress_id=egress_id)
                        )
                        await fresh_api.aclose()
                        logger.info(f"✓ Recording stopped successfully (fresh client) - Egress ID: {egress_id}")
                        if gcs_bucket:
                            logger.info(f"✓ Recording saved to: gs://{gcs_bucket}/calls/{ctx.room.name}.ogg")
                        return
                    except Exception as fresh_error:
                        logger.error(f"Failed to stop egress with fresh client: {fresh_error}")
                        raise
                else:
                    logger.error("Cannot create fresh API client - credentials not available")
                    raise ctx_error
                    
        except Exception as egress_error:
            logger.error(f"All attempts to stop egress failed: {egress_error}", exc_info=True)
            logger.info("Note: Recording will still finalize automatically when room closes")
            logger.info(f"Check GCS bucket for: gs://{gcs_bucket}/calls/{ctx.room.name}.ogg" if gcs_bucket else "Check GCS bucket for recording")
    
    async def cleanup_and_save():
        """
        Non-blocking cleanup that runs in background.
        This ensures participant disconnect doesn't block the server.
        """
        nonlocal egress_id, gcs_bucket, session_start_time
        try:
            logger.info("Cleanup started (non-blocking)...")
            
            # --------------------------------------------------------
            # Save transcript to MongoDB
            # --------------------------------------------------------
            if "session" in locals() and session is not None and hasattr(session, "history"):
                transcript_data = session.history.to_dict()
                
                try:
                    logger.info("Saving transcript to MongoDB...")
                    
                    # Generate caller_id from room name
                    caller_id = ctx.room.name if ctx.room else f"inbound_call_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    
                    # Calculate call duration
                    duration_seconds = None
                    if session_start_time is not None:
                        end_time = datetime.utcnow()
                        duration_delta = end_time - session_start_time
                        duration_seconds = int(duration_delta.total_seconds())
                        logger.info(f"Call duration: {duration_seconds} seconds ({duration_delta})")
                    
                    # Get MongoDB manager
                    mongodb_uri = os.getenv("MONGODB_URI")
                    if mongodb_uri:
                        mongo_manager = get_mongodb_manager(mongodb_uri)
                        
                        # Build metadata with duration and recording URL
                        metadata = {
                            "room_name": ctx.room.name if ctx.room else None,
                            "timestamp": datetime.utcnow().isoformat(),
                            "call_type": "inbound"
                        }
                        if duration_seconds is not None:
                            metadata["duration_seconds"] = duration_seconds
                            metadata["duration_formatted"] = f"{duration_seconds // 60}m {duration_seconds % 60}s"
                        
                        # Add recording URL if available
                        if gcs_bucket and ctx.room:
                            recording_url = f"https://storage.googleapis.com/{gcs_bucket}/calls/{ctx.room.name}.ogg"
                            metadata["recording_url"] = recording_url
                            logger.info(f"Recording URL added to metadata: {recording_url}")
                        
                        transcript_id = mongo_manager.save_transcript(
                            transcript=transcript_data,
                            caller_id=caller_id,
                            name="Inbound Caller",
                            contact_number=None,
                            metadata=metadata
                        )
                        logger.info(f"Transcript saved to MongoDB with ID: {transcript_id}")
                    else:
                        logger.warning("MONGODB_URI not set, skipping MongoDB transcript save")
                except Exception as mongo_error:
                    logger.error(f"Failed to save transcript to MongoDB: {mongo_error}", exc_info=True)
            else:
                logger.warning("No session history to save (session not created or no history).")
            
            logger.info("Cleanup completed successfully")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)

    async def cleanup_wrapper():
        """Non-blocking wrapper that schedules cleanup as background task"""
        asyncio.create_task(cleanup_and_save())
        logger.info("[OK] Cleanup task scheduled (non-blocking)")
    
    async def recording_stop_wrapper():
        """Stop recording BEFORE main cleanup while API is still available"""
        try:
            await stop_recording()
            logger.info("[OK] Recording stop completed")
        except Exception as e:
            logger.error(f"Error stopping recording: {e}", exc_info=True)
    
    # Add shutdown callbacks
    ctx.add_shutdown_callback(recording_stop_wrapper)
    logger.info("[OK] Recording stop callback added (runs first)")
    
    ctx.add_shutdown_callback(cleanup_wrapper)
    logger.info("[OK] Cleanup callback added (runs second)")

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
        
        # Track session start time for duration calculation
        session_start_time = datetime.utcnow()
        logger.info(f"Session start time recorded: {session_start_time.isoformat()}")
        
        await session.start(
            room=ctx.room,
            agent=assistant,
            room_input_options=room_options
        )
        logger.info("[OK] Agent session started successfully")
        
        # Start recording after session is started
        logger.info("Initiating call recording...")
        asyncio.create_task(start_recording())
        
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
    logger.info("RUN_AGENT CALLED - Starting LiveKit Inbound Agent CLI")
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
        logger.info("\nAgent stopped by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"[ERROR] Fatal error in run_agent: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    run_agent()