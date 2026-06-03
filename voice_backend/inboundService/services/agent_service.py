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
INBOUND_CONFIG_COLLECTION = "inbound-agent-config"

# Gmail API Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "https://keplerov1-python-2.onrender.com")
GMAIL_USER_EMAIL = os.getenv("GMAIL_USER_EMAIL", "")  # Authorized Gmail address

# Global Caches
_TOOLS_CACHE = {}

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

async def load_registered_tools_async(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Load registered tools for a user from MongoDB."""
    if not user_id:
        return {}

    if user_id in _TOOLS_CACHE:
        return _TOOLS_CACHE[user_id]

    try:
        from database.tool_store import get_tool_store
        tools = get_tool_store().get_tools_by_user_id(user_id)
        _TOOLS_CACHE[user_id] = tools
        return tools
    except Exception as e:
        logger.error(f"Error loading tools from MongoDB: {e}")
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
    def __init__(self, instructions: str = None, agent_config: Dict[str, Any] = None) -> None:
        self.agent_config = agent_config or {}
        self._agent_session = None  # Will be set when session starts
        openai_api_key = os.getenv("OPENAI_API_KEY")
        self.rag_service = RAGService(openai_api_key=openai_api_key) if openai_api_key else None
        super().__init__(instructions=instructions)

    async def llm_node(
        self,
        chat_ctx,
        tools,
        model_settings,
    ):
        """Override llm_node to inject RAG context before LLM inference.
        
        This is the correct hook for LiveKit Agents v1.x (pipeline nodes architecture).
        The before_llm_inference callback was removed in the v0.x to v1.x migration.
        """
        collections = self.agent_config.get('collections')
        
        # Inject RAG context as a system message
        # In v1.x, ChatContext uses 'items' instead of 'messages'
        items = chat_ctx.items if hasattr(chat_ctx, 'items') else []
        
        if items and self.rag_service and collections:
            # Find the last user message to get the query
            user_query = ""
            for i in range(len(items) - 1, -1, -1):
                item = items[i]
                if hasattr(item, 'role') and item.role == "user":
                    if hasattr(item, 'text_content'):
                        user_query = item.text_content or ""
                    elif hasattr(item, 'content'):
                        content = item.content
                        if isinstance(content, str):
                            user_query = content
                        elif isinstance(content, list) and content:
                            user_query = str(content[0])
                    break
            
            # Only search if we have a query and haven't already added context
            # Check if last system message already has RAG context
            has_rag_context = False
            for item in items:
                if hasattr(item, 'role') and item.role == "system":
                    text = getattr(item, 'text_content', '') or str(getattr(item, 'content', ''))
                    if "[RAG Context]" in text:
                        has_rag_context = True
                        break
            
            if user_query and not has_rag_context:
                try:
                    search_results = await asyncio.wait_for(
                        asyncio.to_thread(
                            self.rag_service.retrieval_based_search,
                            query=user_query,
                            collections=collections,
                            top_k=1
                        ),
                        timeout=0.85
                    )
                    
                    if search_results:
                        context = search_results[0].get('text', '').strip()
                        if context:
                            # Add RAG context as a system message
                            rag_message = f"[RAG Context] Use this relevant information to answer the user's question:\n{context}"
                            chat_ctx.add_message(role="system", content=rag_message)
                            logger.info(f"RAG context added: {context[:100]}...")
                except asyncio.TimeoutError:
                    logger.warning("RAG search timed out (>850ms)")
                except Exception as e:
                    logger.error(f"RAG search error: {e}")
        
        # Call the default llm_node implementation
        async for event in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
            yield event

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
    async def send_email_tool(
        self, 
        ctx: RunContext, 
        tool_name: str,
        caller_name: str,
        caller_email: str,
        caller_phone: str = ""
    ) -> str:
        """Send email via Gmail API. For inbound calls, you MUST collect the caller's information first.
        
        IMPORTANT: Before calling this tool, you must ask the caller for:
        1. Their full name
        2. Their email address
        3. Their phone number (optional but recommended)
        
        Args:
            tool_name: The name of the email tool to use (e.g., 'confirm_appoinment')
            caller_name: The caller's full name (REQUIRED - ask the caller)
            caller_email: The caller's email address (REQUIRED - ask the caller)
            caller_phone: The caller's phone number (optional - ask the caller)
        """
        tools = await load_registered_tools_async(self.agent_config.get("user_id"))
        tool = next((t for tid, t in tools.items() if t.get("tool_name") == tool_name), None)
        if not tool or tool.get("tool_type") != "email": 
            logger.error(f"Tool not found or not email type: {tool_name}")
            return "error: tool not found or not an email tool"
        
        props = tool.get("schema", {}).get("properties", {})
        
        # Get template values from tool config
        subject_template = props.get("subject", {}).get("value", "")
        body_template = props.get("body", {}).get("value", "")
        cc = props.get("cc", {}).get("value", "")
        
        # Replace placeholders in subject and body with caller info
        final_subject = subject_template.replace("{{name}}", caller_name).replace("{{email}}", caller_email).replace("{{phone}}", caller_phone)
        final_body = body_template.replace("{{name}}", caller_name).replace("{{email}}", caller_email).replace("{{phone}}", caller_phone)
        
        # Get gmail_user_email from agent config
        gmail_user = self.agent_config.get("owner_email", GMAIL_USER_EMAIL)
        
        if not gmail_user:
            logger.error("Gmail not configured - gmail_user_email missing from config")
            return "error: Gmail not configured. Set gmail_user_email in config or authorize at /email/authorize"
        
        # Send to the caller's email address
        logger.info(f"Sending email to {caller_email} for {caller_name}")
        asyncio.create_task(send_gmail_email_async(caller_email, final_subject, final_body, cc, gmail_user))
        return f"success: email queued to {caller_email}"

    @function_tool
    async def get_products(self, ctx: RunContext, limit: int = 5) -> str:
        """
        Fetch products from the connected ecommerce store.
        Use this tool to get product information, pricing, and availability.
        
        Args:
            limit: Number of products to fetch (default: 5, max: 20)
        
        Returns:
            Formatted product information
        """
        # NOTE: Do NOT call session.say() here - it breaks Gemini's turn ordering
        
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
    async def get_orders(self, ctx: RunContext, limit: int = 5) -> str:
        """
        Fetch recent orders from the connected ecommerce store.
        Use this tool to check order status, history, and details.
        
        Args:
            limit: Number of orders to fetch (default: 5, max: 20)
        
        Returns:
            Formatted order information
        """
        # NOTE: Do NOT call session.say() here - it breaks Gemini's turn ordering
        
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

# async def request_fnc(req: JobRequest) -> None:
#     """Auto-accept job requests."""
#     logger.info(f"Accepting job for room: {req.room.name}")
#     await req.accept()

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
    
    # Extract config parameters from MongoDB
    language = agent_config.get("language", "en")
    voice_id = agent_config.get("voice_id", "21m00Tcm4TlvDq8ikWAM")  # Default: Rachel
    agent_instruction = agent_config.get("agent_instruction", "You are a helpful assistant.")
    escalation_condition = agent_config.get("escalation_condition", "")
    collection_names = agent_config.get("collections", [])  # Note: field name is 'collections' in DB
    
    logger.info(f"Config loaded for {called_number} - Language: {language}, Voice ID: {voice_id}")
    logger.info(f"Escalation Condition: {escalation_condition}")
    logger.info(f"Collection Names: {collection_names}")
    
    # Initialize ecommerce client if credentials are provided
    ecommerce_creds = agent_config.get("ecommerce_credentials")
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
    
    # 3. Initialize AI Components
    # Initialize STT (Deepgram Nova-3) - use language from config
    stt_instance = deepgram.STT(model="nova-3", language=language, interim_results=True)
    
    # Initialize TTS (ElevenLabs - optimized for low latency) - use config values
    tts_instance = elevenlabs.TTS(
        base_url="https://api.eu.residency.elevenlabs.io/v1",
        api_key=os.getenv("ELEVEN_API_KEY"),
        model="eleven_flash_v2_5",  # Flash model = fastest (~150ms vs turbo ~250ms)
        voice_id=voice_id,
        language=language,
        streaming_latency=3,  # 0 = lowest latency (was 1)
    )

    # 4. Initialize LLM (Gemini 2.5 Flash)
    llm_instance = google.LLM(model="gemini-2.5-flash", temperature=0.3)
    

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
    recording_started = asyncio.Event()  # Signal when recording is ready
    gcs_bucket = os.getenv("GCS_BUCKET") or os.getenv("GCS_BUCKET_NAME")
    session_start_time = datetime.utcnow()

    async def start_recording():
        nonlocal egress_id
        try:
            creds_json_raw = os.getenv("GCP_CREDENTIALS_JSON")
            if not gcs_bucket or not creds_json_raw: 
                logger.warning("Recording skipped: GCS_BUCKET_NAME or GCP_CREDENTIALS_JSON missing")
                recording_started.set()  # Signal even if not started
                return
            
            # Fix escaped newlines in private_key (common issue with env vars)
            try:
                creds_dict = json.loads(creds_json_raw)
                if "private_key" in creds_dict:
                    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
                creds_json = json.dumps(creds_dict)
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
                            gcp=api.GCPUpload(bucket=gcs_bucket, credentials=creds_json),
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
                        # organisation_id=agent_config.get("organisation_id"),
                        metadata=metadata
                    )
                    logger.info("Transcript and metadata saved to MongoDB")
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")

    # Register shutdown callbacks - pass async functions directly (they will be awaited)
    # Order matters: stop_recording first while API is still connected, then cleanup
    ctx.add_shutdown_callback(stop_recording)
    ctx.add_shutdown_callback(cleanup_and_save)

    # 6. Start Session
    # Build full instructions with escalation condition if provided
    full_instructions = agent_instruction
    if escalation_condition:
        full_instructions += f"\n\nEscalation Condition: {escalation_condition}. When this condition is met, use the transfer_to_human tool to transfer the call."
    
    # Load registered tools and add their descriptions to instructions
    user_id = agent_config.get("user_id")
    registered_tools = await load_registered_tools_async(user_id)
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
            full_instructions += "\n\nIMPORTANT: For inbound calls, you MUST ask the caller for their name, email address, and phone number BEFORE using the send_email_tool. Use the collected information when calling the tool."
            logger.info(f"Added {len(registered_tools)} tool descriptions to instructions")
    
    logger.info(f"Agent Instructions: {full_instructions[:200]}...")
    
    # Update agent_config with extracted collection_names for RAG
    agent_config['collections'] = collection_names
    
    assistant = Assistant(
        instructions=full_instructions,
        agent_config=agent_config
    )
    
    # Set the session reference in the assistant for tool access
    assistant._agent_session = session
    
    await session.start(room=ctx.room, agent=assistant, room_input_options=RoomInputOptions(noise_cancellation=noise_cancellation.BVC()))
    
    # Start recording in background
    asyncio.create_task(start_recording())
    
    # 7. Greeting
    greeting = agent_config.get("greeting_message", "Hello, how can I help you today?")
    await session.say(greeting, allow_interruptions=True)

def run_agent():
    worker_options = agents.WorkerOptions(
        entrypoint_fnc=entrypoint,
        # request_fnc=request_fnc,
        agent_name="inbound-agent"
    )
    agents.cli.run_app(worker_options)

if __name__ == "__main__":
    run_agent()