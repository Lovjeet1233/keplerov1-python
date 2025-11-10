# Inbound Call Service

This service handles incoming calls to your phone number using LiveKit and AI agents.

## Quick Start

### Start the Inbound Agent
```bash
cd voice_backend/inboundService
python entry.py
```

### Test It
Call: **+14789002879**

The agent will automatically answer and assist the caller.

## Files

- `entry.py` - Start the agent (main command)
- `update_trunk.py` - Update SIP trunk configuration
- `services/agent_service.py` - Agent logic
- `common/config/settings.py` - Configuration
- `COMMANDS.md` - All available commands
- `INBOUND_CALL_SETUP.md` - Detailed setup guide

## Configuration

**Phone Number**: +14789002879  
**Trunk ID**: ST_bpkhY3edJzk4  
**Trunk Name**: iitroorkee3

## Documentation

- 📚 **[COMMANDS.md](COMMANDS.md)** - Quick command reference
- 📖 **[INBOUND_CALL_SETUP.md](INBOUND_CALL_SETUP.md)** - Complete setup guide

## Requirements

Make sure `.env` file in project root contains:
- LIVEKIT_URL
- LIVEKIT_API_KEY
- LIVEKIT_API_SECRET
- OPENAI_API_KEY
- DEEPGRAM_API_KEY
- CARTESIA_API_KEY

## Logs

- `inbound_entry_debug.log` - Entry point logs
- `inbound_agent_debug.log` - Agent service logs
- `transcripts/inbound/` - Call transcripts

