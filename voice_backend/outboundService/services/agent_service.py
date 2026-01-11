import os
import json
import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import aiohttp
import aiosmtplib
import pymongo
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

from livekit import api
from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, function_tool, RunContext, get_job_context
from livekit.plugins import (
    openai,
    cartesia,
    deepgram,
    noise_cancellation,
    silero,
    google
)

# --- Environment Setup ---
load_dotenv()

# Add project root to path for local imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from RAGService import RAGService
    from database.mongo import get_mongodb_manager
except ImportError:
    # Placeholders for environment compatibility
    class RAGService:
        def __init__(self, **kwargs): pass
        def retrieval_based_search(self, query, collections=None, top_k=1): return []
    def get_mongodb_manager(uri): return None

# --- Configuration ---
LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DATABASE = "IslandAI"
MONGODB_COLLECTION = "outbound-call-config"

# SMTP Configuration
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("EMAIL_ADDRESS", "")
SMTP_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("EMAIL_ADDRESS", SMTP_USERNAME)

# Global Caches
_DYNAMIC_CONFIG_CACHE = None
_TOOLS_CACHE = None
_CACHE_TIMESTAMP = 0
CACHE_TTL = 300  # 5 minutes

# Global Async MongoDB Client
_mongo_client = None

def get_async_mongo_client():
    global _mongo_client
    if _mongo_client is None and MONGODB_URI:
        _mongo_client = AsyncIOMotorClient(MONGODB_URI)
    return _mongo_client

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("optimized_agent")

# --- Optimized Utilities ---

async def load_dynamic_config_async() -> Dict[str, Any]:
    """Asynchronous and cached loading of config from MongoDB."""
    global _DYNAMIC_CONFIG_CACHE, _CACHE_TIMESTAMP
    current_time = time.time()
    
    if _DYNAMIC_CONFIG_CACHE is not None and (current_time - _CACHE_TIMESTAMP) < CACHE_TTL:
        return _DYNAMIC_CONFIG_CACHE
    
    client = get_async_mongo_client()
    if not client:
        return {}
        
    try:
        db = client[MONGODB_DATABASE]
        collection = db[MONGODB_COLLECTION]
        config_doc = await collection.find_one()
        
        if config_doc:
            config_doc.pop('_id', None)
            _DYNAMIC_CONFIG_CACHE = config_doc
            _CACHE_TIMESTAMP = current_time
            return config_doc
    except Exception as e:
        logger.error(f"Async config load error: {e}")
    
    return _DYNAMIC_CONFIG_CACHE or {}

async def load_registered_tools_async() -> Dict[str, Any]:
    """Asynchronous loading of tools.json."""
    global _TOOLS_CACHE
    if _TOOLS_CACHE is not None:
        return _TOOLS_CACHE
    
    tools_file = Path(__file__).parent.parent.parent.parent / "tools.json"
    try:
        if tools_file.exists():
            content = await asyncio.to_thread(tools_file.read_text, encoding='utf-8')
            _TOOLS_CACHE = json.loads(content)
            return _TOOLS_CACHE
    except Exception as e:
        logger.error(f"Error loading tools: {e}")
    return {}

async def send_smtp_email_async(to: str, subject: str, body: str, cc: Optional[str] = None):
    """Fully async SMTP sending."""
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_FROM_EMAIL
        msg['To'] = to
        msg['Subject'] = subject
        if cc: msg['Cc'] = cc
        msg.attach(MIMEText(body, 'plain'))
        
        recipients = [to]
        if cc: recipients.append(cc)
        
        smtp = aiosmtplib.SMTP(hostname=SMTP_SERVER, port=SMTP_PORT)
        await smtp.connect()
        await smtp.starttls()
        await smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
        await smtp.sendmail(SMTP_FROM_EMAIL, recipients, msg.as_string())
        await smtp.quit()
        return True
    except Exception as e:
        logger.error(f"Email failed: {e}")
        return False

# --- Assistant Class ---

class Assistant(Agent):
    def __init__(self, instructions: str = None, collection_names: List[str] = None) -> None:
        self.collection_names = collection_names
        openai_api_key = os.getenv("OPENAI_API_KEY")
        self.rag_service = RAGService(openai_api_key=openai_api_key) if openai_api_key else None
        super().__init__(instructions=instructions)

    async def before_llm_inference(self, ctx: RunContext):
        """Optimized RAG search with lower timeout."""
        logger.info(f"Before LLM inference: {ctx.chat_context}")
        chat_ctx = ctx.chat_context
        if not chat_ctx or not chat_ctx.messages or not self.rag_service:
            return
        
        last_message = chat_ctx.messages[-1]
        if last_message.role != "user":
            return
        
        user_query = last_message.content
        try:
            search_results = await asyncio.wait_for(
                asyncio.to_thread(
                    self.rag_service.retrieval_based_search,
                    query=user_query,
                    collections=self.collection_names,
                    top_k=1
                ),
                timeout=0.85
            )
            
            if search_results:
                context = search_results[0].get('text', '').strip()
                if context:
                    chat_ctx.append(role="system", text=f"Context: {context}")
                    logger.info(f"Context: {context}")
        except (asyncio.TimeoutError, Exception) as e:
            logger.error(f"Error in before LLM inference: {e}")
            pass

    @function_tool
    async def transfer_to_human(self, ctx: RunContext) -> str:
        """Transfer active SIP caller to a human number."""
        job_ctx = get_job_context()
        if not job_ctx: return "error"
        
        config = await load_dynamic_config_async()
        transfer_to = config.get("transfer_to", "+919911062767")
        if not transfer_to.startswith("tel:"): transfer_to = f"tel:{transfer_to}"
        
        sip_participant = next((p for p in job_ctx.room.remote_participants.values() if p.identity == "sip-caller"), None)
        if not sip_participant: return "error"

        try:
            await job_ctx.api.sip.transfer_sip_participant(
                api.TransferSIPParticipantRequest(
                    room_name=job_ctx.room.name,
                    participant_identity=sip_participant.identity,
                    transfer_to=transfer_to,
                    play_dialtone=True
                )
            )
            return "transferred"
        except Exception:
            return "error"

    @function_tool
    async def end_call(self, ctx: RunContext) -> str:
        """End call gracefully."""
        job_ctx = get_job_context()
        if not job_ctx: return "error"
        try:
            await job_ctx.api.room.delete_room(api.DeleteRoomRequest(room=job_ctx.room.name))
            return "ended"
        except Exception:
            return "error"

    @function_tool
    async def send_email_tool(self, ctx: RunContext, tool_name: str, to: str, subject: Optional[str] = None, body: Optional[str] = None, cc: Optional[str] = None) -> str:
        """Send email in background."""
        tools = await load_registered_tools_async()
        tool = next((t for tid, t in tools.items() if t.get("tool_name") == tool_name), None)
        if not tool or tool.get("tool_type") != "email": return "error"
        
        props = tool.get("schema", {}).get("properties", {})
        final_subject = subject or props.get("subject", {}).get("value", "")
        final_body = body or props.get("body", {}).get("value", "")
        final_cc = cc or props.get("cc", {}).get("value", "")
        
        asyncio.create_task(send_smtp_email_async(to, final_subject, final_body, final_cc))
        return "success: email queued"

# --- Main Entrypoint ---

async def entrypoint(ctx: agents.JobContext):
    logger.info(f"Starting entrypoint for room: {ctx.room.name}")
    
    # State variables for recording
    egress_id = None
    gcs_bucket = os.getenv("GCS_BUCKET_NAME")
    session_start_time = datetime.utcnow()
    
    # 1. Parallelize Config & Tools Loading
    config_task = asyncio.create_task(load_dynamic_config_async())
    tools_task = asyncio.create_task(load_registered_tools_async())

    # 5. Wait for Config
    dynamic_config = await config_task
    await tools_task
    
    # 2. Initialize STT (Deepgram Nova-2)
    stt_instance = deepgram.STT(model="nova-2-phonecall", language="en")
    
    # 3. Initialize TTS (Cartesia Sonic-3)
    tts_instance = cartesia.TTS(
        api_key="sk_car_5TjKemDoHphETZp64Tpv1Z",
        model='sonic-3',
        # language=dynamic_config.get('language', 'en'),
        # voice=dynamic_config.get('voice_id', "f786b574-daa5-4673-aa0c-cbe3e8534c02"),
        speed=1.1
    )

    # 4. Initialize LLM (GPT-4o-mini)
    llm_instance = google.LLM(model="gemini-2.5-flash")
    
    # 6. Configure Session with Aggressive VAD
    session = AgentSession(
        vad=silero.VAD.load(
            min_speech_duration=0.05,
            min_silence_duration=0.1,
            activation_threshold=0.4,
        ),
        stt=stt_instance, 
        llm=llm_instance, 
        tts=tts_instance
    )

    # 7. Recording Logic
    async def start_recording():
        nonlocal egress_id
        try:
            gcs_credentials_json = os.getenv("GCP_CREDENTIALS_JSON")
            if not gcs_bucket or not gcs_credentials_json:
                logger.warning("GCS configuration missing - skipping recording")
                return

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
                                credentials=gcs_credentials_json,
                            ),
                        )
                    ],
                )
            )
            egress_id = egress_info.egress_id
            logger.info(f"Recording started: {egress_id}")
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")

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
        """Save transcript and metadata to MongoDB."""
        try:
            if hasattr(session, "history"):
                transcript_data = session.history.to_dict()
                config = await load_dynamic_config_async()
                
                duration = int((datetime.utcnow() - session_start_time).total_seconds())
                metadata = {
                    "room_name": ctx.room.name,
                    "duration_seconds": duration,
                    "timestamp": datetime.utcnow().isoformat()
                }
                if gcs_bucket:
                    metadata["recording_url"] = f"https://storage.googleapis.com/{gcs_bucket}/calls/{ctx.room.name}.ogg"

                mongo_manager = get_mongodb_manager(MONGODB_URI)
                if mongo_manager:
                    mongo_manager.save_transcript(
                        transcript=transcript_data,
                        caller_id=ctx.room.name,
                        name=config.get("caller_name", "Guest"),
                        contact_number=config.get("contact_number"),
                        organisation_id=config.get("organisation_id"),
                        metadata=metadata
                    )
                    logger.info("Transcript saved successfully")
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")

    # Register callbacks
    ctx.add_shutdown_callback(lambda: asyncio.create_task(stop_recording()))
    ctx.add_shutdown_callback(lambda: asyncio.create_task(cleanup_and_save()))

    # 8. Connect and Start
    await ctx.connect()
    
    assistant = Assistant(
        instructions=dynamic_config.get("agent_instructions", "You are a helpful assistant."),
        collection_names=dynamic_config.get("collection_names")
    )
    
    await session.start(room=ctx.room, agent=assistant, room_input_options=RoomInputOptions(noise_cancellation=noise_cancellation.BVC()))
    
    # Start recording in background
    asyncio.create_task(start_recording())
    
    # 9. Immediate Greeting
    greeting = dynamic_config.get("greeting_message", "Hi, this is Sarah from Islands AI. I’d like to share a few of our services with you—do you have a few minutes?")
    await session.generate_reply(instructions=greeting)

def run_agent():
    """Run the agent CLI worker."""
    logger.info("=" * 60)
    logger.info("RUN_AGENT CALLED - Starting LiveKit Agent CLI")
    logger.info("=" * 60)
    
    # Get agent name from environment or use default
    # agent_name = "voice-assistant"
    # logger.info(f"Starting agent with name: {agent_name}")
    logger.info(f"Agent will listen for new rooms and auto-dispatch")
    logger.info(f"Agent will run CONTINUOUSLY - press Ctrl+C to stop")
    logger.info("=" * 60)
    try:
        # Configure worker to auto-join ALL new rooms
        # When only entrypoint_fnc is provided, it auto-accepts all job requests
        worker_options = agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
        )
        
        logger.info("Worker configured to auto-join ALL new rooms")
        agents.cli.run_app(worker_options)
        logger.info("Agent CLI exited normally")
    except KeyboardInterrupt:
        logger.info("Agent stopped by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"[ERROR] Fatal error in run_agent: {e}", exc_info=True)
        raise
if __name__ == "__main__":
    run_agent()