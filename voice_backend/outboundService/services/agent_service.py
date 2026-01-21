import os
import json
import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

import aiohttp
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
    google,
    elevenlabs
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

# Import ecommerce tools
try:
    from voice_backend.outboundService.services.tool import EcommerceClient, set_ecommerce_client, get_ecommerce_client
except ImportError:
    # Placeholder for compatibility
    class EcommerceClient:
        def __init__(self, **kwargs): pass
        async def get_products(self, limit=5): return "Ecommerce tools not available"
        async def get_orders(self, limit=5): return "Ecommerce tools not available"
    def set_ecommerce_client(client): pass
    def get_ecommerce_client(): return None

# --- Configuration ---
LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DATABASE = "IslandAI"
MONGODB_COLLECTION = "outbound-call-config"

# Gmail API Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "https://keplerov1-python-2.onrender.com")
GMAIL_USER_EMAIL = os.getenv("GMAIL_USER_EMAIL", "")  # Authorized Gmail address

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
# Create logs directory if it doesn't exist
logs_dir = project_root / "logs"
logs_dir.mkdir(exist_ok=True)

# Setup logging with both file and console output
log_filename = logs_dir / f"outbound-call-log_{datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_filename, mode='a', encoding='utf-8')
    ]
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

async def send_gmail_email_async(
    to: str, 
    subject: str, 
    body: str, 
    cc: Optional[str] = None,
    user_email: Optional[str] = None
) -> bool:
    """Send email via Gmail API endpoint."""
    sender_email = user_email or GMAIL_USER_EMAIL
    
    if not sender_email:
        logger.error("Gmail user email not configured. Set GMAIL_USER_EMAIL env var or authorize at /email/authorize")
        return False
    
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "to": to,
                "subject": subject,
                "body": body
            }
            if cc:
                payload["cc"] = [cc] if isinstance(cc, str) else cc
            
            headers = {
                "Content-Type": "application/json",
                "X-User-Email": sender_email
            }
            
            async with session.post(
                f"{API_BASE_URL}/email/send",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"Email sent successfully via Gmail API: {result.get('message_id')}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Gmail API error ({response.status}): {error_text}")
                    return False
    except Exception as e:
        logger.error(f"Email failed: {e}")
        return False

# --- Assistant Class ---

class Assistant(Agent):
    def __init__(self, instructions: str = None, collection_names: List[str] = None) -> None:
        self.collection_names = collection_names
        self._agent_session = None  # Will be set when session starts
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
    async def send_email_tool(self, ctx: RunContext, tool_name: str, to: Optional[str] = None, subject: Optional[str] = None, body: Optional[str] = None, cc: Optional[str] = None) -> str:
        """Send email via Gmail API in background."""
        tools = await load_registered_tools_async()
        tool = next((t for tid, t in tools.items() if t.get("tool_name") == tool_name), None)
        if not tool or tool.get("tool_type") != "email": 
            return "error: tool not found or not an email tool"
        
        # Get config for owner_email and recipient email
        config = await load_dynamic_config_async()
        
        props = tool.get("schema", {}).get("properties", {})
        # Priority: function param > config email > tool schema default
        final_to = to or config.get("email","")
        final_subject = subject or props.get("subject", {}).get("value", "")
        final_body = body or props.get("body", {}).get("value", "")
        final_cc = cc or props.get("cc", {}).get("value", "")
        
        # Get owner_email (authorized Gmail) from config
        gmail_user = config.get("owner_email")
        
        if not gmail_user:
            return "error: Gmail not configured. Set owner_email in /calls/outbound request or authorize at /email/authorize"
        
        if not final_to:
            return "error: No recipient email provided. Set 'email' in /calls/outbound request or provide 'to' parameter"
        
        asyncio.create_task(send_gmail_email_async(final_to, final_subject, final_body, final_cc, gmail_user))
        return "success: email queued"

    @function_tool
    async def get_products(self, ctx: RunContext, limit: Optional[int] = 5) -> str:
        """
        Fetch products from the connected ecommerce store.
        Use this tool to get product information, pricing, and availability.
        
        Args:
            limit: Number of products to fetch (default: 5, max: 20)
        
        Returns:
            Formatted product information
        """
        # Provide immediate feedback to the caller
        if self._agent_session:
            await self._agent_session.say("Let me check our products for you, just a moment.")
        
        client = get_ecommerce_client()
        if not client:
            return "No ecommerce platform is connected. Please configure ecommerce credentials."
        
        # Limit to max 20 products
        limit = min(limit or 5, 20)
        
        try:
            result = await client.get_products(limit=limit)
            logger.info(f"✓ Products fetched successfully (limit: {limit})")
            return result
        except Exception as e:
            logger.error(f"Error fetching products: {e}")
            return f"Error fetching products: {str(e)}"

    @function_tool
    async def get_orders(self, ctx: RunContext, limit: Optional[int] = 5) -> str:
        """
        Fetch recent orders from the connected ecommerce store.
        Use this tool to check order status, history, and details.
        
        Args:
            limit: Number of orders to fetch (default: 5, max: 20)
        
        Returns:
            Formatted order information
        """
        # Provide immediate feedback to the caller
        if self._agent_session:
            await self._agent_session.say("Let me look up the order information, one moment please.")
        
        client = get_ecommerce_client()
        if not client:
            return "No ecommerce platform is connected. Please configure ecommerce credentials."
        
        # Limit to max 20 orders
        limit = min(limit or 5, 20)
        
        try:
            result = await client.get_orders(limit=limit)
            logger.info(f"✓ Orders fetched successfully (limit: {limit})")
            return result
        except Exception as e:
            logger.error(f"Error fetching orders: {e}")
            return f"Error fetching orders: {str(e)}"

# --- Main Entrypoint ---

async def entrypoint(ctx: agents.JobContext):
    logger.info(f"Starting entrypoint for room: {ctx.room.name}")
    
    # State variables for recording
    egress_id = None
    gcs_bucket = os.getenv("GCS_BUCKET") or os.getenv("GCS_BUCKET_NAME")
    session_start_time = datetime.utcnow()
    
    # 1. Parallelize Config & Tools Loading
    config_task = asyncio.create_task(load_dynamic_config_async())
    tools_task = asyncio.create_task(load_registered_tools_async())

    # 5. Wait for Config
    dynamic_config = await config_task
    await tools_task
    
    # Extract config parameters from MongoDB
    tts_language = dynamic_config.get("tts_language", "it")
    voice_id = dynamic_config.get("voice_id", "21m00Tcm4TlvDq8ikWAM")  # Default: Rachel
    escalation_condition = dynamic_config.get("escalation_condition", "")
    collection_names = dynamic_config.get("collection_names", [])
    greeting_message = dynamic_config.get("greeting_message", "")
    agent_instructions = dynamic_config.get("agent_instructions", "You are a helpful assistant.")
    
    logger.info(f"Config loaded - TTS Language: {tts_language}, Voice ID: {voice_id}")
    logger.info(f"Escalation Condition: {escalation_condition}")
    logger.info(f"Collection Names: {collection_names}")
    
    # Initialize ecommerce client if credentials are provided
    ecommerce_creds = dynamic_config.get("ecommerce_credentials")
    if ecommerce_creds:
        try:
            ecommerce_client = EcommerceClient(
                platform=ecommerce_creds.get("platform", "woocommerce"),
                base_url=ecommerce_creds.get("base_url"),
                api_key=ecommerce_creds.get("api_key"),
                api_secret=ecommerce_creds.get("api_secret"),
                access_token=ecommerce_creds.get("access_token")
            )
            set_ecommerce_client(ecommerce_client)
            logger.info(f"✓ Ecommerce client initialized: {ecommerce_creds.get('platform')}")
            logger.info(f"  Store URL: {ecommerce_creds.get('base_url')}")
        except Exception as e:
            logger.error(f"Failed to initialize ecommerce client: {e}")
            set_ecommerce_client(None)
    else:
        set_ecommerce_client(None)
        logger.info("No ecommerce credentials configured")
    
    # 2. Initialize STT (Deepgram Nova-2) - use language from config
    stt_instance = deepgram.STT(model="nova-3", language=tts_language, interim_results=True)
    
    # 3. Initialize TTS (ElevenLabs - optimized for low latency) - use voice_id and language from config
    tts_instance = elevenlabs.TTS(
        base_url="https://api.eu.residency.elevenlabs.io/v1",
        api_key=os.getenv("ELEVEN_API_KEY"),
        model="eleven_flash_v2_5",  # Flash model = fastest (~150ms vs turbo ~250ms)
        voice_id=voice_id,
        language=tts_language,
        streaming_latency=3,  # 0 = lowest latency (was 1)
    )

    # # 4. Initialize LLM (GPT-4o-mini)
    # llm_instance = google.LLM(model="gemini-2.5-flash")
    # 4. Initialize LLM (GPT-4o-mini - more reliable)

    # 4. Initialize LLM (GPT-4o-mini - more reliable)
    # llm_instance = openai.LLM(model="gpt-4o-mini", temperature=0.3)
    llm_instance = google.LLM(model="gemini-2.5-flash", temperature=0.3)
    
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
    recording_started = asyncio.Event()  # Signal when recording is ready
    
    async def start_recording():
        nonlocal egress_id
        try:
            gcs_credentials_json_raw = os.getenv("GCP_CREDENTIALS_JSON")
            if not gcs_bucket or not gcs_credentials_json_raw:
                logger.warning("GCS configuration missing - skipping recording")
                recording_started.set()  # Signal even if not started
                return

            # Fix escaped newlines in private_key (common issue with env vars)
            try:
                creds_dict = json.loads(gcs_credentials_json_raw)
                if "private_key" in creds_dict:
                    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
                gcs_credentials_json = json.dumps(creds_dict)
            except json.JSONDecodeError:
                logger.error("Failed to parse GCP_CREDENTIALS_JSON")
                recording_started.set()
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
        finally:
            recording_started.set()  # Always signal completion

    async def stop_recording():
        """
        Stop the egress recording while the connection is still active.
        This runs BEFORE the main cleanup to ensure API is still available.
        """
        nonlocal egress_id
        
        # Wait for recording to be initialized (with timeout)
        try:
            await asyncio.wait_for(recording_started.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for recording to start")
        
        if not egress_id:
            logger.warning("stop_recording called but egress_id is None - recording may not have started")
            return
        
        logger.info(f"Attempting to stop recording with egress_id: {egress_id}")
            
        try:
            # Fetch the current status first to avoid stopping a failed egress
            egress_info = await ctx.api.egress.list_egress(api.ListEgressRequest(egress_id=egress_id))
            if not egress_info or len(egress_info.items) == 0:
                logger.warning(f"No egress info found for egress_id: {egress_id}")
                return

            status = egress_info.items[0].status
            logger.info(f"Egress {egress_id} current status: {status}")
            
            # Only attempt to stop if it's active or starting
            if status in [api.EgressStatus.EGRESS_STARTING, api.EgressStatus.EGRESS_ACTIVE]:
                await ctx.api.egress.stop_egress(api.StopEgressRequest(egress_id=egress_id))
                logger.info(f"Recording stopped successfully: {egress_id}")
                
                # Wait a moment for upload to complete
                await asyncio.sleep(1.0)
            else:
                logger.warning(f"Egress {egress_id} is in state {status}, skipping stop request.")
                
        except Exception as e:
            logger.error(f"Error during egress cleanup for egress_id {egress_id}: {e}")

    
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

    # Register shutdown callbacks - pass async functions directly (they will be awaited)
    # Order matters: stop_recording first while API is still connected, then cleanup
    ctx.add_shutdown_callback(stop_recording)
    ctx.add_shutdown_callback(cleanup_and_save)

    # 8. Connect and Start
    await ctx.connect()
    
    # Build full instructions with escalation condition if provided
    full_instructions = agent_instructions
    if escalation_condition:
        full_instructions += f"\n\nEscalation Condition: {escalation_condition}. When this condition is met, use the transfer_to_human tool to transfer the call."
    
    # Load registered tools and add their descriptions to instructions
    registered_tools = await load_registered_tools_async()
    if registered_tools:
        tool_descriptions = []
        for tool_id, tool_config in registered_tools.items():
            tool_name = tool_config.get("tool_name", "unknown")
            tool_type = tool_config.get("tool_type", "unknown")
            tool_desc = tool_config.get("description", "No description")
            props = tool_config.get("schema", {}).get("properties", {})
            
            # Build parameter info
            param_info = []
            for prop_name, prop_config in props.items():
                default_val = prop_config.get("value", "")
                if default_val:
                    param_info.append(f"{prop_name}='{default_val[:30]}...' (default)" if len(str(default_val)) > 30 else f"{prop_name}='{default_val}' (default)")
                else:
                    param_info.append(f"{prop_name} (required)")
            
            tool_descriptions.append(f"- {tool_name} ({tool_type}): {tool_desc}")
            if param_info:
                tool_descriptions.append(f"  Parameters: {', '.join(param_info)}")
        
        if tool_descriptions:
            full_instructions += "\n\n## Available Tools:\n" + "\n".join(tool_descriptions)
            full_instructions += "\n\nWhen you need to use a tool, call send_email_tool with the tool_name parameter matching the tool you want to use."
            logger.info(f"Added {len(registered_tools)} tool descriptions to instructions")
    
    logger.info(f"Agent Instructions: {full_instructions[:200]}...")
    
    assistant = Assistant(
        instructions=full_instructions,
        collection_names=collection_names
    )
    
    # Set the session reference in the assistant for tool access
    assistant._agent_session = session
    
    await session.start(room=ctx.room, agent=assistant, room_input_options=RoomInputOptions(noise_cancellation=noise_cancellation.BVC()))
    
    # Start recording in background
    asyncio.create_task(start_recording())
    
    # 9. Immediate Greeting - use greeting from config
    final_greeting = greeting_message if greeting_message else "Hi, this is Sarah from Islands AI. I'd like to share a few of our services with you - do you have a few minutes?"
    await session.generate_reply(instructions=final_greeting)

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
