import os
import logging
import sys
import asyncio
from datetime import datetime
from pathlib import Path
from pymongo import MongoClient

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
from livekit.plugins import openai, deepgram, noise_cancellation, silero, elevenlabs,google
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
# Get absolute path for log file
log_file_path = os.path.join(os.path.dirname(__file__), "..", "..", "inbound_agent_debug.log")
log_file_path = os.path.abspath(log_file_path)

logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG for more detailed logs
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file_path, mode='a', encoding='utf-8')
    ]
)
logger = logging.getLogger("services.agent_service")

logger.info(f"Log file location: {log_file_path}")

logger.info("=" * 60)
logger.info("Inbound Agent Service Module Loading")
logger.info(f"LIVEKIT_URL: {LIVEKIT_URL or 'NOT SET'}")
logger.info(f"LIVEKIT_API_KEY: {'SET' if LIVEKIT_API_KEY else 'NOT SET'}")
logger.info(f"LIVEKIT_API_SECRET: {'SET' if LIVEKIT_API_SECRET else 'NOT SET'}")
logger.info(f"OPENAI_API_KEY: {'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}")
logger.info(f"DEEPGRAM_API_KEY: {'SET' if os.getenv('DEEPGRAM_API_KEY') else 'NOT SET'}")
logger.info(f"ELEVENLABS_API_KEY: {'SET' if os.getenv('ELEVEN_API_KEY') else 'NOT SET'}")
logger.info(f"RAG Storage: FAISS (local vector database)")
logger.info(f"TRANSFER_NUMBER: {TRANSFER_NUMBER}")
logger.info(f"MONGODB_URI: {'SET' if os.getenv('MONGODB_URI') else 'NOT SET'}")
logger.info("Multi-Tenant Mode: Agent config loaded per called number from MongoDB")
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
    def __init__(self, instructions: str = None, agent_config: dict = None) -> None:
        if instructions is None:
            instructions = AGENT_INSTRUCTIONS or "You are a helpful voice AI assistant of Aistein."
        logger.info(f"Agent initialized with instructions: {instructions[:100]}...")
        
        # Store agent config for use in tools
        self.agent_config = agent_config or {}
        
        # Initialize RAG service with required credentials (FAISS-based)
        openai_api_key = os.getenv("OPENAI_API_KEY")
        
        if openai_api_key:
            self.rag_service = RAGService(
                openai_api_key=openai_api_key
            )
            logger.info("RAG service initialized successfully (FAISS-based)")
        else:
            self.rag_service = None
            logger.warning("RAG service not initialized - missing OpenAI API key")
        
        super().__init__(instructions=instructions)

    async def before_llm_inference(self, ctx: RunContext):
        """
        Hook that runs BEFORE the LLM is called. We inject RAG context here
        so the agent can speak immediately without tool call delays.
        """
        # Get the user's last message
        chat_ctx = ctx.chat_context
        if not chat_ctx or not chat_ctx.messages:
            return
        
        last_message = chat_ctx.messages[-1]
        if last_message.role != "user":
            return
        
        user_query = last_message.content
        logger.info(f"🔍 Proactive RAG search for: {user_query}")
        
        if not self.rag_service:
            return
        
        try:
            # Quick RAG search with timeout to prevent blocking
            search_results = await asyncio.wait_for(
                asyncio.to_thread(
                    self.rag_service.retrieval_based_search,
                    query=user_query,
                    collections=self.agent_config.get('collections', None),
                    top_k=1
                ),
                timeout=1.0  # 1 second max - adjust based on your needs
            )
            
            if search_results and len(search_results) > 0:
                context = search_results[0].get('text', '').strip()
                if context:
                    # Inject context into the chat as a system message
                    chat_ctx.append(
                        role="system",
                        text=f"Relevant context from knowledge base: {context}"
                    )
                    logger.info("✓ RAG context injected into chat")
            else:
                logger.info("No RAG results found")
                
        except asyncio.TimeoutError:
            logger.warning("⚠️ RAG search timed out - continuing without context")
        except Exception as e:
            logger.error(f"RAG search error: {e}")

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
    # Step 0: Initialize variables for call tracking
    # --------------------------------------------------------
    called_number = None  # The inbound number that was dialed
    caller_number = None  # Who is calling
    organisation_id = None  # Organization ID for multi-tenant tracking

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

    # --------------------------------------------------------
    # Step 1.5: Wait for participant and extract SIP call information
    # --------------------------------------------------------
    logger.info("Waiting for participant to join...")
    max_wait_seconds = 10
    wait_interval = 0.5
    elapsed = 0
    
    while elapsed < max_wait_seconds:
        if len(ctx.room.remote_participants) > 0:
            logger.info(f"✓ Participant joined after {elapsed:.1f}s")
            break
        await asyncio.sleep(wait_interval)
        elapsed += wait_interval
        logger.debug(f"Waiting for participant... {elapsed:.1f}s")
    
    if len(ctx.room.remote_participants) == 0:
        logger.error("❌ No participants joined after waiting")
    
    logger.info(f"Extracting SIP call information from {len(ctx.room.remote_participants)} participant(s)...")
    
    for participant in ctx.room.remote_participants.values():
        logger.info(f"Participant found: identity='{participant.identity}', name='{participant.name}'")
        logger.debug(f"Participant has attributes: {hasattr(participant, 'attributes')}")
        
        # Extract SIP attributes if available
        if hasattr(participant, 'attributes') and participant.attributes:
            logger.info(f"✓ Participant attributes found: {dict(participant.attributes)}")
            
            # Log all available attribute keys for debugging
            all_keys = list(participant.attributes.keys())
            logger.debug(f"All available attribute keys: {all_keys}")
            
            # Extract the called number (the inbound number that was dialed)
            # Try multiple possible attribute keys
            called_number_keys = [
                'sip.callTo', 'sip.trunkPhoneNumber', 'sip.toNumber', 
                'sip.toUri', 'sip.to', 'sip.toUser', 'sip.phoneNumber'
            ]
            called_number = None
            for key in called_number_keys:
                if key in participant.attributes:
                    called_number = participant.attributes.get(key)
                    logger.debug(f"Found called_number in key '{key}': {called_number}")
                    break
            
            # Extract the caller's number (who is calling)
            # Try multiple possible attribute keys
            caller_number_keys = [
                'sip.callFrom', 'sip.fromNumber', 'sip.callerNumber',
                'sip.fromUri', 'sip.from', 'sip.fromUser'
            ]
            caller_number = None
            for key in caller_number_keys:
                if key in participant.attributes:
                    caller_number = participant.attributes.get(key)
                    logger.debug(f"Found caller_number in key '{key}': {caller_number}")
                    break
            
            logger.debug(f"Raw called_number extracted: {called_number}")
            logger.debug(f"Raw caller_number extracted: {caller_number}")
            
            # Clean up phone numbers (remove tel: prefix if present)
            if called_number:
                called_number = called_number.replace('tel:', '').replace('+', '')
                logger.info(f"Called Number (Inbound): +{called_number}")
            else:
                logger.error(f"Could not extract called number!")
                logger.error(f"   Tried keys: {called_number_keys}")
                logger.error(f"   Available keys: {all_keys}")
                logger.error(f"   Attributes: {dict(participant.attributes)}")
            
            if caller_number:
                caller_number = caller_number.replace('tel:', '').replace('+', '')
                logger.info(f"Caller Number: +{caller_number}")
            else:
                logger.warning(f"Could not extract caller number")
                logger.debug(f"   Tried keys: {caller_number_keys}")
        else:
            logger.warning(f"No attributes found on participant '{participant.identity}'")
    
    # --------------------------------------------------------
    # Step 1.5.5: Fetch agent configuration from MongoDB based on called number (Multi-tenant)
    # --------------------------------------------------------
    agent_config = {}
    try:
        mongodb_uri = os.getenv("MONGODB_URI")
        logger.debug(f"MONGODB_URI present: {bool(mongodb_uri)}")
        logger.debug(f"called_number present: {bool(called_number)}, value: {called_number if called_number else 'None'}")
        
        if mongodb_uri and called_number:
            logger.info("=" * 60)
            logger.info(f"🔍 Fetching agent configuration for called number: +{called_number}")
            logger.debug(f"Connecting to MongoDB: {mongodb_uri[:20]}...")  # Log partial URI for security
            
            mongo_client = MongoClient(mongodb_uri)
            db = mongo_client["IslandAI"]
            collection = db["inbound-agent-config"]
            
            logger.debug(f"Connected to database: IslandAI, collection: inbound-agent-config")
            
            # Query for config matching the called number (multi-tenant lookup)
            # Format: search for documents where calledNumber matches (with or without + prefix)
            called_number_formatted = f"+{called_number}"
            query = {"calledNumber": called_number_formatted}
            logger.info(f"MongoDB Query: {query}")
            agent_config = collection.find_one(query)
            
            if agent_config:
                # Remove MongoDB _id for cleaner logging
                config_for_logging = {k: v for k, v in agent_config.items() if k != '_id'}
                logger.info(f"✓✓✓ MULTI-TENANT CONFIG FOUND for called number: {called_number_formatted}")
                logger.debug(f"Full agent config: {config_for_logging}")
                logger.info(f"  - calledNumber: {agent_config.get('calledNumber', 'N/A')}")
                logger.info(f"  - voice_id: {agent_config.get('voice_id', 'N/A')}")
                logger.info(f"  - language: {agent_config.get('language', 'N/A')}")
                logger.info(f"  - collections: {agent_config.get('collections', 'N/A')}")
                logger.info(f"  - agent_instruction length: {len(agent_config.get('agent_instruction', ''))} chars")
                logger.info(f"  - agent_instruction preview: {agent_config.get('agent_instruction', 'N/A')[:100]}...")
            else:
                logger.warning(f"No agent config found for called number {called_number_formatted}")
                logger.info(f"💡 TIP: Create a document in 'inbound-agent-config' collection with:")
                logger.info(f'    {{"calledNumber": "{called_number_formatted}", "voice_id": "...", "language": "en", ...}}')
                logger.info("📋 Using default configuration")
            
            mongo_client.close()
            logger.debug("MongoDB connection closed")
            logger.info("=" * 60)
        elif not mongodb_uri:
            logger.warning("MONGODB_URI not set, using default agent configuration")
        elif not called_number:
            logger.warning("Called number NOT AVAILABLE - cannot fetch tenant-specific config")
            logger.warning("📋 Using default agent configuration")
            logger.info("TIP: Check SIP trunk configuration to ensure phone number is passed in attributes")
    except Exception as config_error:
        logger.error(f"Error loading agent config from MongoDB: {config_error}", exc_info=True)
        logger.info("Continuing with default configuration...")
        logger.debug(f"agent_config state after error: {agent_config}")
    
    # --------------------------------------------------------
    # Step 1.6: Map called number to organization
    # --------------------------------------------------------
    if called_number:
        try:
            # Load phone-to-organization mapping from environment
            phone_org_map_str = os.getenv("PHONE_ORG_MAP")
            if phone_org_map_str:
                import json
                phone_org_map = json.loads(phone_org_map_str)
                organisation_id = phone_org_map.get(called_number)
                
                if organisation_id:
                    logger.info(f"✓ Organisation identified: {organisation_id} (from called number: +{called_number})")
                else:
                    logger.warning(f"⚠️ No organisation mapping found for called number: +{called_number}")
                    logger.warning(f"Available mappings: {list(phone_org_map.keys())}")
            else:
                logger.warning("PHONE_ORG_MAP not configured - cannot identify organisation")
                logger.info("Set PHONE_ORG_MAP environment variable like: {'14789002879':'org_company1','12025551234':'org_company2'}")
        except Exception as map_error:
            logger.error(f"Error mapping phone to organisation: {map_error}", exc_info=True)
    
    # Final check - log overall extraction status
    if not called_number:
        logger.error("=" * 60)
        logger.error("CRITICAL: Could not extract called number from SIP attributes")
        logger.error("This prevents multi-tenant configuration lookup!")
        logger.error("Possible causes:")
        logger.error("  1. SIP trunk not configured to pass phone number in attributes")
        logger.error("  2. LiveKit version uses different attribute keys")
        logger.error("  3. Call attributes not yet available (timing issue)")
        logger.error(f"Participant count: {len(ctx.room.remote_participants)}")
        logger.error("=" * 60)

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
        nonlocal egress_id, gcs_bucket, session_start_time, called_number, caller_number, organisation_id
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
                        
                        # Add called number (inbound number that was dialed)
                        if called_number:
                            metadata["called_number"] = f"+{called_number}"
                            logger.info(f"Called number (inbound): +{called_number}")
                        
                        # Add caller number (who called)
                        if caller_number:
                            metadata["caller_number"] = f"+{caller_number}"
                            logger.info(f"Caller number: +{caller_number}")
                        
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
                            contact_number=f"+{caller_number}" if caller_number else None,
                            organisation_id=organisation_id,
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
        logger.info("=" * 60)
        logger.info("Initializing AI components...")
        logger.debug(f"Using agent_config keys: {list(agent_config.keys())}")
        
        # Initialize STT (Deepgram) with language from MongoDB config
        stt_language = agent_config.get('language', "en")
        logger.debug(f"Initializing STT with language: {stt_language}")
        stt_instance = deepgram.STT(
            model="nova-2-general",
            language=stt_language
        )
        logger.info(f"✓ STT initialized (Deepgram nova-2-general) - Language: {stt_language}")
        
        # Initialize LLM (OpenAI)
        logger.debug("Initializing LLM (Google Gemini 2.5 Flash Lite)")
        # llm_instance = openai.LLM(model="gpt-4o-mini")
        llm_instance = google.LLM(
        model="gemini-2.5-flash-lite",
        api_key=os.getenv("GOOGLE_API_KEY"),
    )
        logger.info("✓ LLM initialized (Google Gemini 2.5 Flash Lite)")
        
        # Initialize TTS (ElevenLabs) with config from MongoDB
        tts_voice_id = agent_config.get('voice_id', "bIHbv24MWmeRgasZH58o")
        tts_language = agent_config.get('language', "en")
        logger.debug(f"Initializing TTS with voice_id: {tts_voice_id}, language: {tts_language}")
        tts_instance = elevenlabs.TTS(
            base_url="https://api.eu.residency.elevenlabs.io/v1",
            voice_id=tts_voice_id,
            api_key=os.getenv("ELEVEN_API_KEY"),
            language=tts_language,
            model="eleven_flash_v2_5",
            streaming_latency=4
        )
        logger.info(f"✓ TTS initialized (ElevenLabs) - Voice: {tts_voice_id}, Language: {tts_language}")
        
        # Initialize VAD (Silero)
        logger.debug("Initializing VAD (Silero)")
        vad_instance = silero.VAD.load()
        logger.info("✓ VAD initialized (Silero)")
        
        # Create session
        logger.info("Creating AgentSession...")
        session = AgentSession(
            vad=vad_instance,
            stt=stt_instance,
            llm=llm_instance,
            tts=tts_instance
        )
        logger.info("✓ AgentSession created successfully")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize AI components: {e}", exc_info=True)
        raise

    # --------------------------------------------------------
    # Step 3: Create assistant and start session
    # --------------------------------------------------------
    try:
        logger.info("Creating Assistant instance...")
        # Use agent_instruction from MongoDB config if available
        agent_instructions = agent_config.get('agent_instruction', AGENT_INSTRUCTIONS)
        assistant = Assistant(instructions=agent_instructions, agent_config=agent_config)
        
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
        # Get caller name (if available from future enhancements, for now it's "there")
        caller_name = "there"
        if caller_number:
            # You could look up the caller name from database here if needed
            caller_name = "there"
        
        # Get language from config
        greeting_language = agent_config.get('language', 'en')
        
        # Multi-language greeting support
        default_greetings = {
            "en": f"Hello there, I'm your AI assistant from Aistein. How can I help you today?",
            "it": f"Ciao , sono il tuo assistente AI di Aistein. Come posso aiutarti oggi?",
            "es": f"Hola , soy tu asistente de IA de Aistein. ¿Cómo puedo ayudarte hoy?",
            "ar": f"مرحبا , أنا مساعدك الذكي من Aistein. كيف يمكنني مساعدتك اليوم؟",
            "tr": f"Merhaba , ben Aistein'dan yapay zeka asistanınızım. Bugün size nasıl yardımcı olabilirim?",
            "hi": f"नमस्ते , मैं Aistein से आपका एआई सहायक हूँ। मैं आज आपकी कैसे मदद कर सकता हूँ?",
            "fr": f"Bonjour , je suis votre assistant IA d'Aistein. Comment puis-je vous aider aujourd'hui?",
            "de": f"Hallo , ich bin Ihr KI-Assistent von Aistein. Wie kann ich Ihnen heute helfen?",
            "pt": f"Olá , sou seu assistente de IA da Aistein. Como posso ajudá-lo hoje?"
        }
        
        # Check if custom greeting is provided in config, otherwise use language-specific default
        if agent_config.get('greeting_message'):
            greeting_message = agent_config.get('greeting_message')
            logger.info(f"Using custom greeting from config")
        else:
            greeting_message = default_greetings.get(greeting_language, default_greetings['en'])
            logger.info(f"Using default greeting for language: {greeting_language}")
        
        logger.info(f"Greeting language: {greeting_language}")
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