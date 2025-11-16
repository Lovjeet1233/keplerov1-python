import os
import json
import asyncio
import logging
import sys
import smtplib
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
from dotenv import load_dotenv
from common.config.settings import (
    TTS_MODEL, TTS_VOICE, STT_MODEL, STT_LANGUAGE, LLM_MODEL, TRANSCRIPT_DIR, PARTICIPANT_IDENTITY
)
from common.update_config import load_dynamic_config
from livekit.plugins import elevenlabs

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
logger.info(f"LIVEKIT_API_KEY: {'SET' if LIVEKIT_API_KEY else 'NOT SET'}")
logger.info(f"LIVEKIT_API_SECRET: {'SET' if LIVEKIT_API_SECRET else 'NOT SET'}")
logger.info(f"OPENAI_API_KEY: {'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}")
logger.info(f"STT_MODEL: {STT_MODEL}")
logger.info(f"LLM_MODEL: {LLM_MODEL}")
logger.info("=" * 60)


# ------------------------------------------------------------
# Utility: Load registered tools from tools.json
# ------------------------------------------------------------
def load_registered_tools():
    """
    Load registered tools from tools.json file.
    
    Returns:
        Dictionary of tools indexed by tool_id
    """
    try:
        if not TOOLS_FILE.exists():
            logger.warning(f"Tools file not found at {TOOLS_FILE}")
            return {}
        
        with open(TOOLS_FILE, 'r', encoding='utf-8') as f:
            tools = json.load(f)
        
        logger.info(f"Loaded {len(tools)} registered tools")
        return tools
    except Exception as e:
        logger.error(f"Error loading tools: {str(e)}")
        return {}


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


def send_smtp_email(to: str, subject: str, body: str, cc: Optional[str] = None):
    """
    Send an email using SMTP.
    
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
        
        # Connect to SMTP server
        logger.info(f"Connecting to SMTP server: {SMTP_SERVER}:{SMTP_PORT}")
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            
            # Send email
            recipients = [to]
            if cc:
                recipients.append(cc)
            
            server.sendmail(SMTP_FROM_EMAIL, recipients, msg.as_string())
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
        # RoomService behavior may vary by SDK version. We try the typical async interface.
        room_service = api.room_service.RoomService(api_key=api_key, api_secret=api_secret, host=server_url)
        active_rooms = await room_service.list_rooms()
        # active_rooms may be an object with .rooms or be a list depending on SDK
        rooms_iterable = getattr(active_rooms, "rooms", active_rooms)
        deleted = 0
        for room in rooms_iterable:
            name = getattr(room, "name", None) or room
            if name and name.startswith(prefix):
                logger.info("🧹 Deleting old room: %s", name)
                try:
                    # Try typical call patterns for different SDK versions:
                    if hasattr(room_service, "delete_room"):
                        # Some SDKs accept a string, some require a request object
                        try:
                            await room_service.delete_room(name)
                        except TypeError:
                            # fallback to api.DeleteRoomRequest
                            await room_service.delete_room(api.DeleteRoomRequest(room=name))
                    else:
                        # as a last resort, use the low-level admin API if available
                        await api.RoomService(api_key=api_key, api_secret=api_secret, host=server_url).delete_room(name)
                    deleted += 1
                except Exception as e:
                    logger.warning("Failed to delete room %s: %s", name, e)
        logger.info("🧹 Room cleanup finished — deleted %d rooms matching prefix '%s'", deleted, prefix)
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
        
        # Load transfer_to from dynamic config
        dynamic_config = load_dynamic_config()
        transfer_to_number = dynamic_config.get("transfer_to", "+919911062767")
        
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
        
        Args:
            tool_name: Name of the registered email tool (e.g., "confirm_appoinment")
            to: Recipient email address
            subject: Email subject (optional, uses tool default if not provided)
            body: Email body (optional, uses tool default if not provided)
            cc: CC email address (optional)
            
        Returns:
            "success" if email sent successfully, "error" otherwise
        """
        try:
            logger.info(f"Attempting to send email using tool: {tool_name}")
            
            # Load the tool configuration
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
            
            logger.info(f"Sending email to: {to}")
            logger.info(f"Subject: {final_subject}")
            logger.info(f"Tool: {tool_name}")
            
            # Send email using SMTP (only pass cc if it has a value)
            success = send_smtp_email(
                to=to,
                subject=final_subject,
                body=final_body,
                cc=final_cc if final_cc else None
            )
            
            if success:
                logger.info(f"Email sent successfully using tool '{tool_name}'")
                return "success"
            else:
                logger.error("Failed to send email")
                return "error: failed to send"
                
        except Exception as e:
            logger.error(f"Error in send_email_tool: {str(e)}", exc_info=True)
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
        logger.info(f"  - Agent Instructions: {dynamic_instruction[:100]}...")
        if escalation_condition:
            logger.info(f"  - Escalation Condition: {escalation_condition}")
        
        # Log full instructions to see what AI knows (first 500 chars)
        logger.info(f"  - Full Instructions Preview: {instructions[:500]}...")
        if len(instructions) > 500:
            logger.info(f"  - Total Instruction Length: {len(instructions)} characters")
        
        # Write full instructions to a debug file for inspection
        try:
            debug_file = Path("agent_instructions_debug.txt")
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write("FULL AI AGENT INSTRUCTIONS\n")
                f.write("=" * 80 + "\n\n")
                f.write(instructions)
                f.write("\n\n" + "=" * 80 + "\n")
            logger.info(f"  - Full instructions written to: {debug_file}")
        except Exception as e:
            logger.warning(f"Could not write debug file: {str(e)}")
    except Exception as e:
        logger.warning(f"Failed to load dynamic config, using defaults: {str(e)}")
        caller_name = "Guest"
        instructions = "You are a helpful voice AI assistant."
        language = "en"
        voice_id = "21m00Tcm4TlvDq8ikWAM"
    
    # Static config from environment
    room_prefix_for_cleanup = os.getenv("ROOM_CLEANUP_PREFIX", "agent-room")

    # --------------------------------------------------------
    # Prepare cleanup callback (save transcript)
    # --------------------------------------------------------
    async def cleanup_and_save():
        try:
            logger.info("Cleanup started...")
            os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
            filename = f"{TRANSCRIPT_DIR}/transcript.json"

            # session may not be defined if start() failed — guard it
            if "session" in locals() and session is not None and hasattr(session, "history"):
                with open(filename, "w") as f:
                    json.dump(session.history.to_dict(), f, indent=2)
                logger.info(f"Transcript saved to {filename}")
            else:
                logger.warning("No session history to save (session not created or no history).")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)

    ctx.add_shutdown_callback(cleanup_and_save)
    logger.info("[OK] Shutdown callback added")

    # --------------------------------------------------------
    # Initialize core components
    # --------------------------------------------------------
    try:
        logger.info("Initializing session components...")

        logger.info("Step 1: Initializing STT (Deepgram)")
        stt_instance = deepgram.STT(model=STT_MODEL, language=STT_LANGUAGE)

        logger.info("Step 2: Initializing LLM (OpenAI)")
        llm_instance = openai.LLM(model=LLM_MODEL)

        logger.info("Step 3: Initializing TTS (ElevenLabs)")
        tts_instance = elevenlabs.TTS(
            voice_id=voice_id,
            language=language,
            model="eleven_multilingual_v2"
        )

        logger.info("Step 4: Creating AgentSession")
        session = AgentSession(stt=stt_instance, llm=llm_instance, tts=tts_instance)
        logger.info("[OK] All session components initialized")
    except Exception as e:
        logger.error(f"[ERROR] Failed initializing session components: {e}", exc_info=True)
        raise

    # --------------------------------------------------------
    # Optional: cleanup previous rooms BEFORE connecting
    # --------------------------------------------------------
    try:
        await cleanup_previous_rooms(LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL, prefix=room_prefix_for_cleanup)
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
    await asyncio.sleep(2)  # Let audio streams stabilize

    greeting_instruction = (
        f"Hello {caller_name}, I’m your cricket coach from Island AI. "
        "How are you today? What would you like to practice?"
    )
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
    # Wait for shutdown (updated API)
    # --------------------------------------------------------
    logger.info("Session running — waiting for termination signal...")
    try:
        # newer livekit.agents versions use wait_for_termination()
        if hasattr(ctx, "wait_for_termination"):
            await ctx.wait_for_termination()
        else:
            # fallback to run_forever
            await agents.run_forever()
    except Exception as e:
        logger.error(f"[ERROR] Error while waiting for shutdown: {e}", exc_info=True)
    finally:
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
    try:
        agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
    except Exception as e:
        logger.error(f"[ERROR] Fatal error in run_agent: {e}", exc_info=True)
        raise
