# Inbound Call Setup Guide

## Overview
This service handles incoming calls to your SIP trunk. When customers call your phone number, the LiveKit agent automatically answers and handles the conversation.

## How It Works

### Call Flow
1. Customer dials your phone number (e.g., +14789002879)
2. Call routes through your SIP trunk (ST_bpkhY3edJzk4)
3. LiveKit creates a room and connects the caller
4. Agent answers and greets the caller
5. Conversation proceeds with AI assistant
6. Transcript is saved when call ends

## Prerequisites

### 1. SIP Trunk Configuration
Your inbound trunk should be already configured with:
- **Trunk ID**: `ST_bpkhY3edJzk4`
- **Phone Number**: `+14789002879`
- **Name**: `iitroorkee3`

You can update your trunk using the `update_trunk.py` script:
```bash
cd voice_backend/inboundService
python update_trunk.py
```

### 2. Environment Variables
Make sure your `.env` file in the project root contains:

```env
# LiveKit Configuration
LIVEKIT_URL=wss://your-livekit-server.livekit.cloud
LIVEKIT_API_KEY=your_api_key
LIVEKIT_API_SECRET=your_api_secret

# AI Service Keys
OPENAI_API_KEY=your_openai_key
DEEPGRAM_API_KEY=your_deepgram_key
CARTESIA_API_KEY=your_cartesia_key

# Optional: Customize Agent Behavior
AGENT_INSTRUCTIONS="You are a helpful customer service assistant for Island AI. Answer questions professionally and courteously."
TTS_LANGUAGE=en
TTS_EMOTION=Calm
```

## Setup Instructions

### Step 1: Install Dependencies
Make sure all required packages are installed:
```bash
pip install -r requirements.txt
```

### Step 2: Start the Inbound Agent
```bash
cd voice_backend/inboundService
python entry.py
```

Wait for the agent to show:
```
✓ Connected to room successfully
✓ Agent session started successfully
Session running, keeping alive...
```

### Step 3: Test the Service
Call your phone number: **+14789002879**

The agent should:
1. Answer the call automatically
2. Greet you warmly
3. Ask how it can help
4. Respond to your questions

## Configuration Files

### `services/agent_service.py`
Main agent logic that:
- Handles incoming calls
- Manages conversation flow
- Saves transcripts
- Implements AI responses

### `common/config/settings.py`
Configuration including:
- SIP trunk ID: `ST_bpkhY3edJzk4`
- Phone number: `+14789002879`
- AI model settings
- Transcript storage location

### `entry.py`
Entry point that starts the agent service

## Customizing the Agent

### Change Agent Instructions
Edit your `.env` file:
```env
AGENT_INSTRUCTIONS="You are a sales assistant for XYZ Company. Help customers learn about our products and schedule demos."
```

### Change Voice Settings
```env
TTS_LANGUAGE=es  # Spanish
TTS_EMOTION=Excited  # More energetic voice
```

### Change AI Models
In `common/config/settings.py`:
```python
STT_MODEL = "nova-3"        # Speech-to-text
LLM_MODEL = "gpt-4o-mini"   # Language model
TTS_MODEL = "sonic-3"       # Text-to-speech
```

## Running Commands

### Start Inbound Agent (Main Command)
```bash
cd voice_backend/inboundService
python entry.py
```

### Update SIP Trunk
```bash
cd voice_backend/inboundService
python update_trunk.py
```

### View Logs
```bash
# Real-time logs
tail -f inbound_entry_debug.log
tail -f inbound_agent_debug.log

# View transcripts
ls -la transcripts/inbound/
cat transcripts/inbound/inbound_transcript_*.json
```

## Monitoring and Debugging

### Log Files
- `inbound_entry_debug.log` - Entry point logs
- `inbound_agent_debug.log` - Agent service logs
- `transcripts/inbound/` - Call transcripts

### Common Issues

#### Issue: "Agent not connecting"
**Solution**: 
1. Check your `.env` file has correct LiveKit credentials
2. Verify your LiveKit server is running
3. Check network connectivity

#### Issue: "No response to incoming calls"
**Solution**:
1. Ensure `python entry.py` is running
2. Check SIP trunk is correctly configured
3. Verify phone number is active

#### Issue: "Poor audio quality"
**Solution**:
1. Check internet connection stability
2. Verify Deepgram API key is valid
3. Review STT_MODEL settings

## Architecture

```
Incoming Call Flow:
  
  Customer Phone
       ↓
  Phone Number (+14789002879)
       ↓
  SIP Trunk (ST_bpkhY3edJzk4)
       ↓
  LiveKit Room (auto-created)
       ↓
  Inbound Agent (entry.py)
       ↓
  AI Assistant (agent_service.py)
       ↓
  Conversation + Transcript
```

## File Structure

```
voice_backend/inboundService/
├── entry.py                    # Start the agent
├── update_trunk.py             # Update SIP trunk config
├── INBOUND_CALL_SETUP.md      # This file
├── services/
│   ├── __init__.py
│   └── agent_service.py        # Main agent logic
├── common/
│   ├── __init__.py
│   └── config/
│       ├── __init__.py
│       └── settings.py         # Configuration
└── transcripts/inbound/        # Call transcripts (auto-created)
```

## Production Deployment

### Recommended Setup
1. Run agent as a system service (systemd/supervisor)
2. Use process manager (PM2 for Node.js-style management)
3. Set up monitoring and alerting
4. Configure log rotation
5. Enable auto-restart on failure

### Example Systemd Service
Create `/etc/systemd/system/inbound-agent.service`:
```ini
[Unit]
Description=LiveKit Inbound Call Agent
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/Kaplere/voice_backend/inboundService
ExecStart=/usr/bin/python3 entry.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable inbound-agent
sudo systemctl start inbound-agent
sudo systemctl status inbound-agent
```

## Next Steps

1. **Test Your Setup**
   - Call +14789002879
   - Verify agent answers and responds correctly
   - Check transcript is saved

2. **Customize for Your Use Case**
   - Update AGENT_INSTRUCTIONS in `.env`
   - Adjust voice settings (language, emotion)
   - Configure greeting message

3. **Production Deployment**
   - Set up monitoring
   - Configure auto-restart
   - Enable logging/alerting

## Support

For issues or questions:
1. Check logs in `inbound_entry_debug.log` and `inbound_agent_debug.log`
2. Verify environment variables in `.env`
3. Review LiveKit dashboard for connection status
4. Check SIP trunk configuration

## Quick Reference

| Command | Description |
|---------|-------------|
| `python entry.py` | Start inbound agent |
| `python update_trunk.py` | Update SIP trunk |
| `tail -f inbound_agent_debug.log` | View live logs |
| `ls transcripts/inbound/` | List call transcripts |

**Phone Number**: +14789002879  
**Trunk ID**: ST_bpkhY3edJzk4  
**Trunk Name**: iitroorkee3

