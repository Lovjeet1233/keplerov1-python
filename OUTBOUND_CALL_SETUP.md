# Outbound Call Setup with Dynamic Instructions

## Overview
The system now supports dynamic agent instructions and caller names that are automatically set when you make an outbound call through the API.

## How It Works

### 1. API Updates `.env` File Automatically
When you call the `/outbound_call` endpoint with `dynamic_instruction` and `name` parameters, the API automatically:
- Updates the `.env` file with `AGENT_INSTRUCTIONS` variable
- Updates the `.env` file with `CALLER_NAME` variable
- Sets the environment variables in the current process

### 2. Agent Reads from Environment Variables
The LiveKit agent service reads:
- `AGENT_INSTRUCTIONS` from `.env` - Used as the AI agent's system prompt
- `CALLER_NAME` from `.env` - Used to personalize the greeting

## Setup Instructions

### Step 1: Create `.env` File
Copy `ENV_TEMPLATE.txt` to `.env` and fill in your credentials:

```bash
cp ENV_TEMPLATE.txt .env
```

Required variables:
- `LIVEKIT_URL` - Your LiveKit server URL
- `LIVEKIT_API_KEY` - Your LiveKit API key
- `LIVEKIT_API_SECRET` - Your LiveKit API secret
- `OPENAI_API_KEY` - Your OpenAI API key
- `DEEPGRAM_API_KEY` - Your Deepgram API key
- `QDRANT_URL` - Your Qdrant database URL
- `QDRANT_API_KEY` - Your Qdrant API key

### Step 2: Start the LiveKit Agent (IMPORTANT - Do this FIRST)
```bash
cd voice_backend/outboundService
python entry.py
```

Wait for the agent to show:
```
✓ Connected to room successfully
✓ Agent session started successfully
Session running, keeping alive...
```

### Step 3: Make Outbound Call via API
Use the `/outbound_call` endpoint with dynamic parameters:

```bash
curl -X POST "http://localhost:8000/outbound_call" \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+919911062767",
    "name": "Amar",
    "dynamic_instruction": "You are a financial advisor helping users understand finance and investment strategies."
  }'
```

Or using Python:
```python
import requests

response = requests.post(
    "http://localhost:8000/outbound_call",
    json={
        "phone_number": "+919911062767",
        "name": "Amar",
        "dynamic_instruction": "You are a financial advisor helping users understand finance and investment strategies."
    }
)
print(response.json())
```

## API Request Parameters

```json
{
  "phone_number": "string (required)",  // E.g., "+919911062767"
  "name": "string (optional)",          // E.g., "Amar"
  "dynamic_instruction": "string (optional)"  // Custom agent behavior
}
```

## Examples

### Example 1: Financial Advisor Call
```json
{
  "phone_number": "+1234567890",
  "name": "John Smith",
  "dynamic_instruction": "You are a financial advisor from ProPAL AI. Help the caller understand investment strategies, retirement planning, and portfolio diversification. Be professional and clear."
}
```

### Example 2: Customer Support Call
```json
{
  "phone_number": "+1234567890",
  "name": "Sarah Johnson",
  "dynamic_instruction": "You are a customer support representative. Help resolve issues, answer questions about products, and provide excellent service. Be empathetic and solution-oriented."
}
```

### Example 3: Appointment Reminder
```json
{
  "phone_number": "+1234567890",
  "name": "Michael Chen",
  "dynamic_instruction": "You are calling to remind about an upcoming doctor's appointment tomorrow at 2 PM. Confirm if they can attend and offer to reschedule if needed."
}
```

## What Happens Behind the Scenes

1. **API receives call request** → Updates `.env` with:
   ```
   AGENT_INSTRUCTIONS="You are a financial advisor... The caller's name is Amar, address them by name."
   CALLER_NAME="Amar"
   ```

2. **API calls `make_outbound_call()`** → Creates SIP participant in LiveKit room

3. **Agent picks up call** → Reads `AGENT_INSTRUCTIONS` from `.env`

4. **Agent greets caller** → Uses personalized greeting:
   ```
   "Hello Amar! I'm an assistant from ProPAL AI. [Follows dynamic instructions]"
   ```

## Important Notes

⚠️ **Always start the agent BEFORE making calls**
- The agent must be running and connected to the room
- If you get a 404 error, the agent is not running

✅ **The `.env` file is automatically updated**
- You don't need to manually edit it before each call
- The API handles all dynamic updates

🔄 **For multiple sequential calls**
- The agent will use the latest instructions from `.env`
- Each call request updates the instructions automatically

## Troubleshooting

### Error: "TwirpError(code=not_found, status=404)"
**Solution**: Start the agent first (`python entry.py`)

### Error: "Invalid phone number format"
**Solution**: Phone number must start with `+` followed by country code (e.g., `+1234567890`)

### Agent not using custom instructions
**Solution**: Check that:
1. The `.env` file was updated (check the API logs)
2. The agent was restarted after updating `.env`
3. The `AGENT_INSTRUCTIONS` variable exists in `.env`

## Files Modified

- `api.py` - Added `update_env_file()` function and updated `/outbound_call` endpoint
- `call_service.py` - Simplified to only accept `phone_number`
- `agent_service.py` - Reads `AGENT_INSTRUCTIONS` and `CALLER_NAME` from environment
- `voice_backend/outboundService/common/config/settings.py` - Updated `SIP_TRUNK_ID`

## Next Steps

1. Copy `ENV_TEMPLATE.txt` to `.env` and fill in your credentials
2. Start the agent: `cd voice_backend/outboundService && python entry.py`
3. Test with a call: `POST /outbound_call` with your dynamic parameters
4. Monitor the agent logs to see the personalized interaction

