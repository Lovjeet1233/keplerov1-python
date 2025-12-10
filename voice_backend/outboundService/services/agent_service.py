import os
import json
import asyncio
import logging
import sys
import aiohttp
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path
from typing import Optional
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
# from voice_backend.outboundService.common.config.settings import ROOM_NAME
from dotenv import load_dotenv
from common.config.settings import (
    TTS_MODEL, TTS_VOICE, STT_MODEL, STT_LANGUAGE, LLM_MODEL, TRANSCRIPT_DIR, PARTICIPANT_IDENTITY
)
from common.update_config import load_dynamic_config
from livekit.plugins import elevenlabs

# Add project root to path for database imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))
from database.mongo import get_mongodb_manager

load_dotenv()

# ------------------------------------------------------------
# Environment / LiveKit admin credentials (fetched from env)
# ------------------------------------------------------------
LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

# SMTP Configuration
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("EMAIL_ADDRESS", "")
SMTP_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("EMAIL_ADDRESS", SMTP_USERNAME)

# Tools registry path
TOOLS_FILE = Path(__file__).parent.parent.parent.parent / "tools.json"

# Global caches to avoid repeated file I/O during conversation
_TOOLS_CACHE = None
_DYNAMIC_CONFIG_CACHE = None
_CACHE_TIMESTAMP = 0
CACHE_TTL = 60  # Cache for 60 seconds

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
logger.info("Agent Service Module Loading")
logger.info(f"LIVEKIT_URL: {LIVEKIT_URL or 'NOT SET'}")
logger.info(f"LIVEKIT_API_KEY: {LIVEKIT_API_KEY}")
logger.info(f"LIVEKIT_API_SECRET: {LIVEKIT_API_SECRET}")
logger.info(f"OPENAI_API_KEY: {'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}")
logger.info(f"STT_MODEL: {STT_MODEL}")
logger.info(f"LLM_MODEL: {LLM_MODEL}")
logger.info("=" * 60)


# ------------------------------------------------------------
# Utility: Load registered tools from tools.json (with caching)
# ------------------------------------------------------------
def load_registered_tools():
    """
    Load registered tools from tools.json file with caching.
    Cache is refreshed every CACHE_TTL seconds to avoid blocking I/O during conversation.
    
    Returns:
        Dictionary of tools indexed by tool_id
    """
    global _TOOLS_CACHE, _CACHE_TIMESTAMP
    import time
    
    current_time = time.time()
    
    # Return cached tools if still valid
    if _TOOLS_CACHE is not None and (current_time - _CACHE_TIMESTAMP) < CACHE_TTL:
        return _TOOLS_CACHE
    
    try:
        if not TOOLS_FILE.exists():
            logger.warning(f"Tools file not found at {TOOLS_FILE}")
            return {}
        
        with open(TOOLS_FILE, 'r', encoding='utf-8') as f:
            tools = json.load(f)
        
        # Update cache
        _TOOLS_CACHE = tools
        _CACHE_TIMESTAMP = current_time
        
        logger.info(f"Loaded {len(tools)} registered tools (cached for {CACHE_TTL}s)")
        return tools
    except Exception as e:
        logger.error(f"Error loading tools: {str(e)}")
        # Return stale cache if available, otherwise empty dict
        return _TOOLS_CACHE if _TOOLS_CACHE is not None else {}


def get_tool_by_name(tool_name: str) -> Optional[dict]:
    """
    Get a tool by its name.
    
    Args:
        tool_name: Name of the tool to retrieve
        
    Returns:
        Tool schema or None if not found
    """
    tools = load_registered_tools()
    for tool_id, tool_data in tools.items():
        if tool_data.get("tool_name") == tool_name:
            return tool_data
    return None


async def send_smtp_email(to: str, subject: str, body: str, cc: Optional[str] = None):
    """
    Send an email using SMTP asynchronously (non-blocking).
    
    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body content
        cc: CC email address (optional)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = SMTP_FROM_EMAIL
        msg['To'] = to
        msg['Subject'] = subject
        
        if cc:
            msg['Cc'] = cc
        
        # Attach body
        msg.attach(MIMEText(body, 'plain'))
        
        # Build recipient list
        recipients = [to]
        if cc:
            recipients.append(cc)
        
        # Connect to SMTP server asynchronously
        logger.info(f"Connecting to SMTP server: {SMTP_SERVER}:{SMTP_PORT}")
        
        # Use async SMTP client
        smtp = aiosmtplib.SMTP(hostname=SMTP_SERVER, port=SMTP_PORT)
        await smtp.connect()
        await smtp.starttls()
        await smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
        await smtp.sendmail(SMTP_FROM_EMAIL, recipients, msg.as_string())
        await smtp.quit()
        
        logger.info(f"Email sent successfully to {to}")
        return True
            
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")
        return False


# ------------------------------------------------------------
# Utility: cleanup previous rooms with safe guards
# ------------------------------------------------------------
async def cleanup_previous_rooms(api_key, api_secret, server_url, prefix="agent-room"):
    """
    Attempt to delete previously created rooms whose name starts with `prefix`.
    This function is defensive: if the admin API isn't available it logs and continues.
    """
    if not (api_key and api_secret and server_url):
        logger.warning("LiveKit admin credentials or URL not provided — skipping room cleanup.")
        return

    try:
        logger.info("Attempting to list & cleanup previous rooms (prefix=%s)...", prefix)
        # Use LiveKitAPI for room management
        lk_api = api.LiveKitAPI(url=server_url, api_key=api_key, api_secret=api_secret)
        room_service = lk_api.room
        
        # List all rooms
        active_rooms = await room_service.list_rooms(api.ListRoomsRequest())
        
        # active_rooms may be an object with .rooms or be a list depending on SDK
        rooms_iterable = getattr(active_rooms, "rooms", active_rooms)
        deleted = 0
        for room in rooms_iterable:
            name = getattr(room, "name", None) or room
            if name and name.startswith(prefix):
                logger.info("Room cleanup: Deleting old room: %s", name)
                try:
                    # Delete the room using the request object
                    await room_service.delete_room(api.DeleteRoomRequest(room=name))
                    deleted += 1
                except Exception as e:
                    logger.warning("Failed to delete room %s: %s", name, e)
        
        # Close the API connection
        await lk_api.aclose()
        logger.info("Room cleanup finished - deleted %d rooms matching prefix '%s'", deleted, prefix)
    except Exception as e:
        logger.warning("Room cleanup failed (non-fatal). Reason: %s", e, exc_info=True)


# ------------------------------------------------------------
# Assistant definition
# ------------------------------------------------------------
class Assistant(Agent):
    def __init__(self, instructions: str = None) -> None:
        if instructions is None:
            instructions = os.getenv("AGENT_INSTRUCTIONS", "You are a helpful voice AI assistant.")
        logger.info(f"Agent initialized with instructions: {instructions}")
        super().__init__(instructions=instructions)

    @function_tool
    async def transfer_to_human(self, ctx: RunContext) -> str:
        """Transfer active SIP caller to a human number. if it satisfies the escalation condition, transfer to the human number."""
        job_ctx = get_job_context()
        if job_ctx is None:
            logger.error("Job context not found")
            return "error"
        
        # Load transfer_to from dynamic config (using cache to avoid blocking I/O)
        global _DYNAMIC_CONFIG_CACHE, _CACHE_TIMESTAMP
        import time
        
        current_time = time.time()
        
        # Refresh cache if expired
        if _DYNAMIC_CONFIG_CACHE is None or (current_time - _CACHE_TIMESTAMP) >= CACHE_TTL:
            _DYNAMIC_CONFIG_CACHE = load_dynamic_config()
            _CACHE_TIMESTAMP = current_time
        
        transfer_to_number = _DYNAMIC_CONFIG_CACHE.get("transfer_to", "+919911062767")
        
        # Ensure the transfer_to number has the "tel:" prefix for SIP
        if not transfer_to_number.startswith("tel:"):
            transfer_to = f"tel:{transfer_to_number}"
        else:
            transfer_to = transfer_to_number
        
        logger.info(f"Transfer requested to: {transfer_to}")

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
            logger.info(f"Transferred participant {sip_participant.identity} to {transfer_to}")
            return "transferred"
        except Exception as e:
            logger.error(f"Failed to transfer call: {e}", exc_info=True)
            return "error"

    @function_tool
    async def end_call(self, ctx: RunContext) -> str:
        """End call gracefully."""
        logger_local = logging.getLogger("phone-assistant")
        job_ctx = get_job_context()
        if job_ctx is None:
            logger_local.error("Failed to get job context")
            return "error"

        try:
            await job_ctx.api.room.delete_room(api.DeleteRoomRequest(room=job_ctx.room.name))
            logger_local.info(f"Successfully ended call for room {job_ctx.room.name}")
            return "ended"
        except Exception as e:
            logger_local.error(f"Failed to end call: {e}", exc_info=True)
            return "error"
    
    @function_tool
    async def send_email_tool(
        self, 
        ctx: RunContext,
        tool_name: str,
        to: str,
        subject: Optional[str] = None,
        body: Optional[str] = None,
        cc: Optional[str] = None
    ) -> str:
        """
        Send an email using a registered tool from tools.json.
        Email is sent in background to avoid blocking the conversation.
        
        Args:
            tool_name: Name of the registered email tool (e.g., "confirm_appoinment")
            to: Recipient email address
            subject: Email subject (optional, uses tool default if not provided)
            body: Email body (optional, uses tool default if not provided)
            cc: CC email address (optional)
            
        Returns:
            "success" if email queued successfully, "error" otherwise
        """
        try:
            logger.info(f"Attempting to send email using tool: {tool_name}")
            
            # Load the tool configuration (using cache)
            tool = get_tool_by_name(tool_name)
            if not tool:
                logger.error(f"Tool '{tool_name}' not found in registry")
                return "error: tool not found"
            
            # Check if it's an email tool
            if tool.get("tool_type") != "email":
                logger.error(f"Tool '{tool_name}' is not an email tool (type: {tool.get('tool_type')})")
                return "error: not an email tool"
            
            # Get default values from tool schema
            properties = tool.get("schema", {}).get("properties", {})
            
            # Use provided values or fall back to tool defaults
            final_subject = subject if subject is not None else properties.get("subject", {}).get("value", "")
            final_body = body if body is not None else properties.get("body", {}).get("value", "")
            final_cc = cc if cc is not None else properties.get("cc", {}).get("value", "")
            
            # Validate required fields
            if not to:
                logger.error("Recipient email address (to) is required")
                return "error: recipient email required"
            
            if not final_subject:
                logger.error("Email subject is required")
                return "error: subject required"
            
            if not final_body:
                logger.error("Email body is required")
                return "error: body required"
            
            logger.info(f"Queueing email to: {to}")
            logger.info(f"Subject: {final_subject}")
            logger.info(f"Tool: {tool_name}")
            
            # Send email in background (fire and forget - don't block conversation)
            asyncio.create_task(
                send_smtp_email(
                    to=to,
                    subject=final_subject,
                    body=final_body,
                    cc=final_cc if final_cc else None
                )
            )
            
            logger.info(f"Email queued successfully using tool '{tool_name}'")
            return "success: email queued"
                
        except Exception as e:
            logger.error(f"Error in send_email_tool: {str(e)}", exc_info=True)
            return f"error: {str(e)}"
    
    @function_tool
    async def query_knowledge_base(
        self,
        ctx: RunContext,
        query: str,
        top_k: int = 5
    ) -> str:
        """
        Query the RAG knowledge base to retrieve relevant information.
        Use this when the user asks questions that require looking up information from documents.
        
        Args:
            query: The question or query to search for in the knowledge base
            
        Returns:
            Answer from the knowledge base or error message
        """
        try:
            # Get collection_name from dynamic config
            dynamic_config = load_dynamic_config()
            collection_name = dynamic_config.get("collection_name", "default")
            
            logger.info(f"RAG query: '{query}' in collection '{collection_name}'")
            
            # Get API base URL from environment
            api_base_url = os.getenv("API_BASE_URL", "http://localhost:8000")
            rag_endpoint = f"{api_base_url}/rag/chat"
            
            # Prepare request payload
            payload = {
                "query": query,
                "collection_name": collection_name,
                "top_k": top_k
            }
            
            logger.info(f"Sending RAG request to: {rag_endpoint}")
            
            # Make async HTTP request to RAG endpoint
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    rag_endpoint,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        answer = result.get("answer", "No answer found")
                        logger.info(f"RAG query successful, answer length: {len(answer)} chars")
                        return answer
                    else:
                        error_text = await response.text()
                        logger.error(f"RAG endpoint returned {response.status}: {error_text}")
                        return f"error: Failed to query knowledge base (status {response.status})"
            
        except asyncio.TimeoutError:
            logger.error("RAG query timed out")
            return "error: Knowledge base query timed out"
        except Exception as e:
            logger.error(f"Error in query_knowledge_base: {str(e)}", exc_info=True)
            return f"error: {str(e)}"


# ------------------------------------------------------------
# Agent entrypoint
# ------------------------------------------------------------
async def entrypoint(ctx: agents.JobContext):
    """Main entrypoint for the voice agent service."""
    logger.info("=" * 60)
    logger.info(f"ENTRYPOINT CALLED - Room: {ctx.room.name}")
    logger.info("=" * 60)

    # Load dynamic configuration from config.json
    try:
        logger.info("Loading dynamic configuration from config.json...")
        
        dynamic_config = load_dynamic_config()
        caller_name = dynamic_config.get("caller_name", "Guest")
        dynamic_instruction = dynamic_config.get("agent_instructions", "You are a helpful voice AI assistant.")
        language = dynamic_config.get("tts_language", "en")
        voice_id = dynamic_config.get("voice_id", "21m00Tcm4TlvDq8ikWAM")
        escalation_condition = dynamic_config.get("escalation_condition")
        provider = dynamic_config.get("provider", "openai").lower()
        api_key = dynamic_config.get("api_key")

        # Build full instructions with escalation condition if provided
        if escalation_condition:
            instructions = f"{dynamic_instruction} Below is the escalation condition: {escalation_condition}"
        else:
            instructions = dynamic_instruction
        
        # Load registered tools and add to instructions
        tools = load_registered_tools()
        if tools:
            email_tools = [(t.get("tool_name"), t) for tid, t in tools.items() if t.get("tool_type") == "email"]
            if email_tools:
                # Build detailed tool descriptions for AI
                tools_info = "\n\n=== AVAILABLE EMAIL TOOLS ==="
                for tool_name, tool_data in email_tools:
                    tools_info += f"\n\nTool: {tool_name}"
                    tools_info += f"\nDescription: {tool_data.get('description', 'No description')}"
                    
                    # Add properties information
                    properties = tool_data.get('schema', {}).get('properties', {})
                    if properties:
                        tools_info += "\nParameters:"
                        for prop_name, prop_data in properties.items():
                            prop_desc = prop_data.get('description', '')
                            prop_value = prop_data.get('value', '')
                            prop_required = "REQUIRED" if prop_name in tool_data.get('schema', {}).get('required', []) else "optional"
                            
                            tools_info += f"\n  - {prop_name} ({prop_required}): {prop_desc}"
                            if prop_value:
                                tools_info += f"\n    Default value: {prop_value}"
                
                tools_info += "\n\nTo use: Call send_email_tool(tool_name='<name>', to='<email>', subject='<optional>', body='<optional>', cc='<optional>')"
                tools_info += "\nIf subject or body are not provided, the tool's default values will be used."
                
                instructions += tools_info
                logger.info(f"  - Loaded {len(email_tools)} email tool(s) with full schemas")
        
        logger.info("✓ Dynamic configuration loaded successfully")
        logger.info(f"  - Caller Name: {caller_name}")
        logger.info(f"  - TTS Language: {language}")
        logger.info(f"  - Voice ID: {voice_id}")
        logger.info(f"  - LLM Provider: {provider}")
        if api_key:
            logger.info(f"  - Custom API Key: {'***' + api_key[-4:] if len(api_key) > 4 else '***'}")
        logger.info(f"  - Agent Instructions: {dynamic_instruction[:100]}...")
        if escalation_condition:
            logger.info(f"  - Escalation Condition: {escalation_condition}")
        
        # Log full instructions to see what AI knows (first 500 chars)
        logger.info(f"  - Full Instructions Preview: {instructions[:500]}...")
        if len(instructions) > 500:
            logger.info(f"  - Total Instruction Length: {len(instructions)} characters")
        
        # # Write full instructions to a debug file for inspection
        # try:
        #     debug_file = Path("agent_instructions_debug.txt")
        #     with open(debug_file, 'w', encoding='utf-8') as f:
        #         f.write("=" * 80 + "\n")
        #         f.write("FULL AI AGENT INSTRUCTIONS\n")
        #         f.write("=" * 80 + "\n\n")
        #         f.write(instructions)
        #         f.write("\n\n" + "=" * 80 + "\n")
        #     logger.info(f"  - Full instructions written to: {debug_file}")
        # except Exception as e:
        #     logger.warning(f"Could not write debug file: {str(e)}")
    except Exception as e:
        logger.warning(f"Failed to load dynamic config, using defaults: {str(e)}")
        caller_name = "Guest"
        instructions = "You are a helpful voice AI assistant."
        language = "en"
        voice_id = "21m00Tcm4TlvDq8ikWAM"
        provider = "openai"
        api_key = None
    
    # Static config from environment
    room_prefix_for_cleanup = os.getenv("ROOM_CLEANUP_PREFIX", "agent-room")

    # --------------------------------------------------------
    # Prepare cleanup callback (save transcript and clean resources)
    # --------------------------------------------------------
    # Track session start time for duration calculation
    session_start_time = None
    
    async def cleanup_and_save():
        """
        Non-blocking cleanup that runs in background.
        This ensures participant disconnect doesn't block the server.
        """
        try:
            logger.info("Cleanup started (non-blocking)...")
            
            # session may not be defined if start() failed — guard it
            if "session" in locals() and session is not None and hasattr(session, "history"):
                transcript_data = session.history.to_dict()
                
                # Save to MongoDB in background (don't block disconnect)
                try:
                    # Get caller information from dynamic config (use cached version)
                    logger.info("Saving transcript to MongoDB...")
                    dynamic_config = load_dynamic_config()
                    caller_name = dynamic_config.get("caller_name", "Guest")
                    contact_number = dynamic_config.get("contact_number")
                    
                    # Generate caller_id from room name
                    caller_id = ctx.room.name if ctx.room else f"call_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    
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
                        
                        # Build metadata with duration
                        metadata = {
                            "room_name": ctx.room.name if ctx.room else None,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        if duration_seconds is not None:
                            metadata["duration_seconds"] = duration_seconds
                            metadata["duration_formatted"] = f"{duration_seconds // 60}m {duration_seconds % 60}s"
                        
                        transcript_id = mongo_manager.save_transcript(
                            transcript=transcript_data,
                            caller_id=caller_id,
                            name=caller_name,
                            contact_number=contact_number,
                            metadata=metadata
                        )
                        logger.info(f"Transcript saved to MongoDB with ID: {transcript_id}")
                    else:
                        logger.warning("MONGODB_URI not set, skipping MongoDB transcript save")
                except Exception as mongo_error:
                    logger.error(f"Failed to save transcript to MongoDB: {mongo_error}", exc_info=True)
                    # Don't fail the cleanup if MongoDB save fails
            else:
                logger.warning("No session history to save (session not created or no history).")
            
            logger.info("Cleanup completed successfully")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)

    # Wrap cleanup in background task to avoid blocking server on disconnect
    async def cleanup_wrapper():
        """Non-blocking wrapper that schedules cleanup as background task"""
        # Schedule cleanup in background without waiting for it
        asyncio.create_task(cleanup_and_save())
        logger.info("[OK] Cleanup task scheduled (non-blocking)")
        # Return immediately - don't wait for cleanup to finish
    
    ctx.add_shutdown_callback(cleanup_wrapper)
    logger.info("[OK] Shutdown callback added (non-blocking)")

    # --------------------------------------------------------
    # Initialize core components
    # --------------------------------------------------------
    try:
        logger.info("Initializing session components...")

        logger.info("Step 1: Initializing STT (Deepgram)")
        stt_instance = deepgram.STT(model=STT_MODEL, language=STT_LANGUAGE)

        logger.info(f"Step 2: Initializing LLM ({provider})")
        
        # Initialize LLM based on provider from config
        if provider == "gemini":
            if api_key:
                logger.info("Using Gemini with custom API key")
                # Set the API key in environment for Google plugin
                os.environ["GOOGLE_API_KEY"] = api_key
                llm_instance = google.LLM(model="gemini-2.5-pro")
                logger.info("[OK] Gemini LLM initialized with custom API key")
            else:
                logger.warning("Gemini provider selected but no API key provided, falling back to OpenAI")
                llm_instance = openai.LLM(model=LLM_MODEL)
                logger.info("[OK] OpenAI LLM initialized (fallback)")
        else:  # default to OpenAI
            if api_key:
                logger.info("Using OpenAI with custom API key")
                # Set the API key in environment for OpenAI plugin
                os.environ["OPENAI_API_KEY"] = api_key
                llm_instance = openai.LLM(model="gpt-4.1-mini")
                logger.info("[OK] OpenAI LLM initialized with custom API key")
            else:
                logger.info("Using default OpenAI configuration")
                llm_instance = openai.LLM(model=LLM_MODEL)
                logger.info("[OK] OpenAI LLM initialized with default config")

        logger.info("Step 3: Initializing TTS (ElevenLabs)")
        try:
            tts_instance = elevenlabs.TTS(
                base_url="https://api.eu.residency.elevenlabs.io/v1",
                voice_id=voice_id,
                language=language,
                model="eleven_flash_v2_5"
            )
        #     tts_instance = cartesia.TTS(
        #     model='sonic-3',
        #     voice='a0e99841-438c-4a64-b679-ae501e7d6091',
        #     language='en',
        #     speed=1.0,
        #     sample_rate=24000
        # )

            logger.info("[OK] ElevenLabs TTS initialized successfully")
        except Exception as tts_error:
            logger.warning(f"ElevenLabs TTS initialization failed: {tts_error}")
            logger.info("Falling back to OpenAI TTS...")
            # Fallback to OpenAI TTS
            tts_instance = openai.TTS(
                voice="alloy",
                model="tts-1"
            )
            logger.info("[OK] OpenAI TTS initialized as fallback")

        logger.info("Step 4: Creating AgentSession")
        session = AgentSession(vad=silero.VAD.load(),stt=stt_instance, llm=llm_instance, tts=tts_instance)
        logger.info("[OK] All session components initialized")
    except Exception as e:
        logger.error(f"[ERROR] Failed initializing session components: {e}", exc_info=True)
        raise

    # --------------------------------------------------------
    # Optional: cleanup previous rooms BEFORE connecting
    # --------------------------------------------------------
    try:
        # await cleanup_previous_rooms(LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL, prefix=room_prefix_for_cleanup)
        pass
    except Exception as e:
        logger.warning("cleanup_previous_rooms raised an exception (non-fatal): %s", e, exc_info=True)

    # --------------------------------------------------------
    # Connect to room
    # --------------------------------------------------------
    try:
        logger.info("Connecting to room...")
        await ctx.connect()
        logger.info("[OK] Connected to room successfully")
    except Exception as e:
        logger.error("Failed to connect to room: %s", e, exc_info=True)
        # If connection fails, raise so the worker can restart or exit cleanly
        raise

    # --------------------------------------------------------
    # Initialize assistant and start session
    # --------------------------------------------------------
    assistant = Assistant(instructions=instructions)
    room_options = RoomInputOptions(noise_cancellation=noise_cancellation.BVC())

    try:
        logger.info("Starting agent session...")
        
        # Track session start time for duration calculation
        session_start_time = datetime.utcnow()
        logger.info(f"Session start time recorded: {session_start_time.isoformat()}")

        await session.start(room=ctx.room, agent=assistant, room_input_options=room_options)
        logger.info("[OK] Agent session started successfully")
    except Exception as e:
        logger.error("Failed to start AgentSession: %s", e, exc_info=True)
        # ensure we attempt a graceful shutdown/cleanup
        try:
            await ctx.shutdown()
        except Exception:
            pass
        raise

    # --------------------------------------------------------
    # Greeting logic AFTER session start and stream stabilization
    # --------------------------------------------------------
    # await asyncio.sleep(2)  # Let audio streams stabilize

    # Multi-language greeting support
    greetings = {
        "en": f"Hello {caller_name}, I'm your Assistant from Aistein.",
        "it": f"Ciao {caller_name}, sono il tuo Assistente di Aistein.",
        "es": f"Hola {caller_name}, soy tu Asistente de Aistein.",
        "ar": f"مرحبا {caller_name}، أنا مساعدك من Aistein.",
        "tr": f"Merhaba {caller_name}, ben Aistein'dan Asistanınızım.",
        "hi": f"नमस्ते {caller_name}, मैं Aistein से आपका सहायक हूँ।"
    }
    
    # Default to English if language not supported
    greeting_instruction = greetings.get(language, greetings["en"])
    try:
        # Guard that session is running (some SDKs expose is_running)
        is_running = getattr(session, "is_running", None)
        if is_running is None or is_running:
            await session.generate_reply(instructions=greeting_instruction)
            logger.info("[OK] Greeting sent successfully")
        else:
            logger.warning("Session reports not running — skipping greeting.")
    except Exception as e:
        logger.error(f"[ERROR] Failed sending greeting: {e}", exc_info=True)

    # --------------------------------------------------------
    # Wait for shutdown
    # --------------------------------------------------------
    logger.info("Session running — waiting for termination signal...")
    try:
        # Wait for the job context to terminate (standard in livekit-agents 1.2+)
        # await ctx.wait_for_termination()
        logger.info("Termination signal received")
    except asyncio.CancelledError:
        logger.info("Session cancelled - shutting down gracefully")
    except Exception as e:
        logger.error(f"[ERROR] Error while waiting for shutdown: {e}", exc_info=True)
    finally:
        # Fast cleanup - don't block the server
        logger.info("Initiating resource cleanup...")
        
        logger.info("=" * 60)
        logger.info(f"ENTRYPOINT FINISHED - Room: {ctx.room.name}")
        logger.info("=" * 60)


# ------------------------------------------------------------
# CLI entrypoint
# ------------------------------------------------------------
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
