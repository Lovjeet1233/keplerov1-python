import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (4 levels up: common -> outboundService -> voice_backend -> project root)
env_path = Path(__file__).parent.parent.parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# LiveKit Configuration
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "your_livekit_api_key_here")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "your_livekit_api_secret_here")
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "your_livekit_url_here")

# SIP Configuration
SIP_TRUNK_ID = "ST_vEtSehKXAp4d"
ROOM_NAME = "my-assistant-room"
PARTICIPANT_IDENTITY = "sip-caller"
PARTICIPANT_NAME = "Phone Caller"

# Azure Storage Configuration
AZURE_ACCOUNT_NAME = "your_azure_account_name"
AZURE_ACCOUNT_KEY = "your_azure_account_key_here"
AZURE_CONTAINER_NAME = "your_container_name"

# Server Configuration
API_HOST = "127.0.0.1"
API_PORT = 8001

# File Paths
TRANSCRIPT_DIR = "transcripts"
SERVER_LOG_FILE = "server.log"

# Agent Configuration
DEFAULT_AGENT_INSTRUCTIONS = "You are a helpful voice AI assistant."
DEFAULT_TARGET_PHONE = ""

# Recording Configuration
RECORDING_FORMAT = "ogg"
RECORDING_SAMPLE_RATE = 24000
RECORDING_ENCODING = "pcm_s16le"

# TTS Configuration
TTS_MODEL = "sonic-3"
TTS_VOICE = "your_tts_voice_id_here"

# STT Configuration
STT_MODEL = "nova-3"
STT_LANGUAGE = "multi"

# LLM Configuration
LLM_MODEL = "gpt-4o-mini"

# VAD Configuration
VAD_MODEL = "silero"

# Timeout Configuration
TRANSCRIPT_TIMEOUT = 400
CALL_TIMEOUT = 60 