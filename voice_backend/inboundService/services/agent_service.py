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
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

from livekit import api
from livekit import agents
from livekit.agents import (
    AgentSession, 
    Agent, 
    RoomInputOptions, 
    function_tool, 
    RunContext, 
    get_job_context, 
    JobRequest,
    AutoSubscribe
)
from livekit.plugins import (
    openai,
    deepgram,
    noise_cancellation,
    silero,
    elevenlabs,
    google,
    cartesia
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
INBOUND_CONFIG_COLLECTION = "inbound-agent-config"

# SMTP Configuration
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("EMAIL_ADDRESS", "")
SMTP_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("EMAIL_ADDRESS", SMTP_USERNAME)

# Global Caches
_TOOLS_CACHE = None

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
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("optimized_inbound_agent")

# --- Utilities ---

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
    def __init__(self, instructions: str = None, agent_config: Dict[str, Any] = None) -> None:
        self.agent_config = agent_config or {}
        openai_api_key = os.getenv("OPENAI_API_KEY")
        self.rag_service = RAGService(openai_api_key=openai_api_key) if openai_api_key else None
        super().__init__(instructions=instructions)

    async def before_llm_inference(self, ctx: RunContext):
        """Optimized RAG search with timeout."""
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
                    collections=self.agent_config.get('collections'),
                    top_k=1
                ),
                timeout=0.85
            )
            
            if search_results:
                context = search_results[0].get('text', '').strip()
                if context:
                    chat_ctx.append(role="system", text=f"Context: {context}")
                    logger.info(f"RAG Context injected: {context[:50]}...")
        except (asyncio.TimeoutError, Exception) as e:
            logger.error(f"RAG search error: {e}")

    @function_tool
    async def transfer_to_human(self, ctx: RunContext) -> str:
        """Transfer active SIP caller to a human number."""
        job_ctx = get_job_context()
        if not job_ctx: return "error"
        
        transfer_to = self.agent_config.get("transfer_to", os.getenv("TRANSFER_NUMBER", "+919911062767"))
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
        except Exception as e:
            logger.error(f"Transfer failed: {e}")
            return "error"

    @function_tool
    async def end_call(self, ctx: RunContext) -> str:
        """End call gracefully."""
        job_ctx = get_job_context()
        if not job_ctx: return "error"
        try:
            await job_ctx.api.room.delete_room(api.DeleteRoomRequest(room=job_ctx.room.name))
            return "ended"
        except Exception as e:
            logger.error(f"End call failed: {e}")
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

async def request_fnc(req: JobRequest) -> None:
    """Auto-accept job requests."""
    logger.info(f"Accepting job for room: {req.room.name}")
    await req.accept(entrypoint_fnc=entrypoint)

async def entrypoint(ctx: agents.JobContext):
    logger.info(f"Starting inbound entrypoint for room: {ctx.room.name}")
    
    # 1. Connect to room
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    
    # 2. Extract SIP Info & Load Multi-tenant Config
    called_number = None
    caller_number = None
    
    # Wait briefly for participant attributes
    for _ in range(10):
        if ctx.room.remote_participants:
            p = next(iter(ctx.room.remote_participants.values()))
            if hasattr(p, 'attributes'):
                called_number = p.attributes.get('sip.callTo') or p.attributes.get('sip.toNumber')
                caller_number = p.attributes.get('sip.callFrom') or p.attributes.get('sip.fromNumber')
                if called_number: break
        await asyncio.sleep(0.5)
    
    if called_number:
        called_number = called_number.replace('tel:', '').replace('+', '')
    
    # Load Config from MongoDB
    agent_config = {}
    client = get_async_mongo_client()
    if client and called_number:
        db = client[MONGODB_DATABASE]
        col = db[INBOUND_CONFIG_COLLECTION]
        agent_config = await col.find_one({"calledNumber": f"+{called_number}"}) or {}
    
    # 3. Initialize AI Components
    stt_instance = deepgram.STT(model="nova-2-phonecall", language=agent_config.get('language', 'en'))
    
    # tts_instance = elevenlabs.TTS(
    #     base_url="https://api.eu.residency.elevenlabs.io/v1",
    #     voice_id=agent_config.get('voice_id', "2EiwWnXFnvU5JabPnv8n"),
    #     api_key=os.getenv("ELEVEN_API_KEY"),
    #     language=agent_config.get('language', 'en'),
    #     model="eleven_flash_v2_5",
    #     streaming_latency=4,
    # )
    # 3. Initialize TTS (Cartesia Sonic-3)
    tts_instance = cartesia.TTS(
        api_key="sk_car_5TjKemDoHphETZp64Tpv1Z",
        model='sonic-3',
        language=agent_config.get('language', 'en'),
        voice=agent_config.get('voice_id', "f786b574-daa5-4673-aa0c-cbe3e8534c02"),
        speed=1.1
    )

    llm_instance = google.LLM(model="gemini-2.5-flash")

    # 4. Configure Session with Aggressive VAD
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

    # 5. Recording & Cleanup Logic
    egress_id = None
    gcs_bucket = os.getenv("GCS_BUCKET_NAME")
    session_start_time = datetime.utcnow()

    async def start_recording():
        nonlocal egress_id
        try:
            creds_json = os.getenv("GCP_CREDENTIALS_JSON")
            if not gcs_bucket or not creds_json: 
                logger.warning("Recording skipped: GCS_BUCKET_NAME or GCP_CREDENTIALS_JSON missing")
                return
            
            egress_info = await ctx.api.egress.start_room_composite_egress(
                api.RoomCompositeEgressRequest(
                    room_name=ctx.room.name,
                    audio_only=True,
                    file_outputs=[
                        api.EncodedFileOutput(
                            file_type=api.EncodedFileType.OGG,
                            filepath=f"calls/{ctx.room.name}.ogg",
                            gcp=api.GCPUpload(bucket=gcs_bucket, credentials=creds_json),
                        )
                    ],
                )
            )
            egress_id = egress_info.egress_id
            logger.info(f"Recording started: {egress_id}")
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")

    async def stop_recording():
        """Explicitly stop the egress recording."""
        nonlocal egress_id
        if not egress_id:
            return
        try:
            logger.info(f"Stopping recording: {egress_id}")
            await ctx.api.egress.stop_egress(api.StopEgressRequest(egress_id=egress_id))
            logger.info(f"Recording stopped successfully: {egress_id}")
        except Exception as e:
            logger.error(f"Failed to stop recording: {e}")

    async def cleanup_and_save():
        """Final cleanup: Stop recording and save transcript."""
        try:
            # 1. Stop recording first while API is still available
            await stop_recording()
            
            # 2. Save transcript and metadata
            if hasattr(session, "history"):
                transcript_data = session.history.to_dict()
                duration = int((datetime.utcnow() - session_start_time).total_seconds())
                
                metadata = {
                    "room_name": ctx.room.name,
                    "duration_seconds": duration,
                    "timestamp": datetime.utcnow().isoformat(),
                    "call_type": "inbound",
                    "called_number": f"+{called_number}" if called_number else None,
                    "caller_number": f"+{caller_number}" if caller_number else None
                }
                if gcs_bucket:
                    metadata["recording_url"] = f"https://storage.googleapis.com/{gcs_bucket}/calls/{ctx.room.name}.ogg"

                mongo_manager = get_mongodb_manager(MONGODB_URI)
                if mongo_manager:
                    mongo_manager.save_transcript(
                        transcript=transcript_data,
                        caller_id=ctx.room.name,
                        name="Inbound Caller",
                        contact_number=f"+{caller_number}" if caller_number else None,
                        organisation_id=agent_config.get("organisation_id"),
                        metadata=metadata
                    )
                    logger.info("Transcript and metadata saved to MongoDB")
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")

    # Register shutdown callbacks
    ctx.add_shutdown_callback(lambda: asyncio.create_task(cleanup_and_save()))

    # 6. Start Session
    assistant = Assistant(
        instructions=agent_config.get("agent_instruction", "You are a helpful assistant."),
        agent_config=agent_config
    )
    
    await session.start(room=ctx.room, agent=assistant, room_input_options=RoomInputOptions(noise_cancellation=noise_cancellation.BVC()))
    
    # Start recording in background
    asyncio.create_task(start_recording())
    
    # 7. Greeting
    greeting = agent_config.get("greeting_message", "Hello, how can I help you today?")
    await session.say(greeting, allow_interruptions=True)

def run_agent():
    worker_options = agents.WorkerOptions(
        entrypoint_fnc=entrypoint,
        request_fnc=request_fnc,
        agent_name="inbound-agent"
    )
    agents.cli.run_app(worker_options)

if __name__ == "__main__":
    run_agent()