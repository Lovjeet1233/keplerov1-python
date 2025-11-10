# Inbound Call Service - Quick Commands

## Main Commands

### 1. Start Inbound Agent (PRIMARY COMMAND)
This is the main command to run the inbound call service:

```bash
cd voice_backend/inboundService
python entry.py
```

**What it does:**
- Starts the LiveKit agent
- Listens for incoming calls on +14789002879
- Automatically answers and handles conversations
- Saves transcripts after calls

**Expected Output:**
```
============================================================
INBOUND ENTRY POINT - Starting Inbound Call Agent
============================================================
✓ Connected to room successfully
✓ Agent session started successfully
Session running, keeping alive...
```

---

### 2. Update SIP Trunk Configuration
Update your inbound trunk settings:

```bash
cd voice_backend/inboundService
python update_trunk.py
```

**What it does:**
- Updates trunk ID: ST_bpkhY3edJzk4
- Configures phone number: +14789002879
- Sets trunk name: iitroorkee3

---

## Monitoring Commands

### View Live Logs
```bash
# Entry point logs
tail -f inbound_entry_debug.log

# Agent service logs
tail -f inbound_agent_debug.log
```

### View All Logs
```bash
# View full entry log
cat inbound_entry_debug.log

# View full agent log
cat inbound_agent_debug.log
```

### Check Transcripts
```bash
# List all call transcripts
ls -la transcripts/inbound/

# View latest transcript
cat transcripts/inbound/inbound_transcript_*.json | tail -100
```

---

## Testing Commands

### Test the Service
Simply call the phone number:
```
Call: +14789002879
```

The agent should answer automatically.

---

## Development Commands

### Run with Custom Instructions
```bash
# Set environment variable before running
export AGENT_INSTRUCTIONS="You are a helpful customer service assistant."
python entry.py
```

### Run with Different Language
```bash
export TTS_LANGUAGE="es"  # Spanish
export TTS_EMOTION="Excited"
python entry.py
```

---

## Cleanup Commands

### Clear Logs
```bash
# Clear log files
rm inbound_entry_debug.log inbound_agent_debug.log

# Or just truncate them
> inbound_entry_debug.log
> inbound_agent_debug.log
```

### Clear Old Transcripts
```bash
# Remove transcripts older than 7 days
find transcripts/inbound/ -name "*.json" -mtime +7 -delete
```

---

## Production Commands

### Run in Background
```bash
# Using nohup
nohup python entry.py > output.log 2>&1 &

# Using screen
screen -S inbound-agent
python entry.py
# Press Ctrl+A, then D to detach
```

### Stop Background Process
```bash
# Find the process
ps aux | grep entry.py

# Kill it
kill <PID>
```

### Run with Auto-Restart
```bash
# Using a simple loop
while true; do
    python entry.py
    echo "Agent crashed. Restarting in 5 seconds..."
    sleep 5
done
```

---

## Troubleshooting Commands

### Check Environment Variables
```bash
# Verify .env file exists
ls -la ../../.env

# Check specific variables
grep LIVEKIT_ ../../.env
grep OPENAI_ ../../.env
```

### Test Python Dependencies
```bash
# Check if all packages are installed
pip list | grep livekit
pip list | grep openai
pip list | grep deepgram
```

### Verify Network Connectivity
```bash
# Test LiveKit connection
ping your-livekit-server.livekit.cloud

# Check port availability
netstat -tuln | grep 8000
```

---

## Quick Start (All-in-One)

```bash
# 1. Navigate to directory
cd voice_backend/inboundService

# 2. Verify environment
cat ../../.env | grep LIVEKIT_

# 3. Start the agent
python entry.py

# 4. In another terminal, monitor logs
tail -f inbound_agent_debug.log

# 5. Test by calling +14789002879
```

---

## Configuration Files

| File | Purpose |
|------|---------|
| `entry.py` | Main entry point to start agent |
| `services/agent_service.py` | Agent logic and conversation handling |
| `common/config/settings.py` | Configuration (trunk ID, models, etc.) |
| `update_trunk.py` | Update SIP trunk settings |
| `../../.env` | Environment variables (API keys) |

---

## Key Information

- **Phone Number**: +14789002879
- **Trunk ID**: ST_bpkhY3edJzk4
- **Trunk Name**: iitroorkee3
- **Default Room**: inbound-call-room
- **Transcript Location**: transcripts/inbound/
- **Log Files**: 
  - inbound_entry_debug.log
  - inbound_agent_debug.log

---

## Support

If the agent isn't answering calls:
1. Verify `python entry.py` is running
2. Check logs for errors
3. Ensure .env has correct LiveKit credentials
4. Verify SIP trunk is configured correctly
5. Test phone number is active

For more detailed information, see `INBOUND_CALL_SETUP.md`

