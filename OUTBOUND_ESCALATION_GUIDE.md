# Outbound Call with Escalation - API Guide

## Overview

The `/calls/outbound-with-escalation` endpoint allows you to initiate outbound calls with an AI agent that can escalate to a human supervisor when requested.

## Flow Diagram

```
1. API Call → Creates LiveKit Room
2. Agent Calls Customer → SIP Call Initiated
3. AI Agent Converses with Customer
4. Customer Requests Human → Agent Initiates Transfer
5. Agent Calls Supervisor → Provides Context
6. Supervisor Ready → Calls are Merged
7. Agent Disconnects → Customer & Supervisor Connected
```

## Prerequisites

### 1. Environment Variables

Create/update your `.env` file with the following variables:

```properties
# LiveKit Configuration (Required)
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret
LIVEKIT_URL=wss://your-livekit-server.livekit.cloud

# SIP Configuration (Required)
LIVEKIT_SIP_OUTBOUND_TRUNK=ST_vEtSehKXAp4d
LIVEKIT_SUPERVISOR_PHONE_NUMBER=+919911062767

# Twilio Number (Optional - for reference)
TWILIO_NUMBER=+12625925656

# Agent Configuration (Optional - can be set via API)
AGENT_INSTRUCTIONS="You are a helpful customer support agent for LiveKit."
CALLER_NAME=""
TTS_LANGUAGE=en
TTS_EMOTION=Calm
```

**Important:** Fix the typo in your current `.env`:
- ❌ `LIVEKIT_SUPERVISOR_PHONE_NUMBER=="+919911062767"` (double equals)
- ✅ `LIVEKIT_SUPERVISOR_PHONE_NUMBER="+919911062767"` (single equals)

### 2. Start the LiveKit Agent Worker

Before making API calls, you must start the `outbound.py` agent worker:

```bash
# Make sure you're in the project directory
cd C:\Users\amarc\OneDrive\Desktop\Kaplere

# Run the agent worker
python outbound.py
```

The agent will:
- Connect to LiveKit
- Listen for new rooms
- Handle customer conversations
- Manage escalations to supervisor

### 3. Start the API Server

In a separate terminal:

```bash
# Start the FastAPI server
python api.py
```

The API will be available at: `http://localhost:8000`

## API Endpoint

### POST `/calls/outbound-with-escalation`

**URL:** `http://localhost:8000/calls/outbound-with-escalation`

**Method:** `POST`

**Headers:**
```json
{
  "Content-Type": "application/json"
}
```

**Request Body:**

```json
{
  "phone_number": "+1234567890",
  "name": "John Doe",
  "dynamic_instruction": "You are calling to follow up on a support ticket about login issues.",
  "language": "en",
  "emotion": "Calm"
}
```

**Request Fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `phone_number` | string | ✅ Yes | - | Customer phone number with country code (e.g., +1234567890) |
| `name` | string | ❌ No | null | Customer's name for personalization |
| `dynamic_instruction` | string | ❌ No | null | Custom instructions for the AI agent |
| `language` | string | ❌ No | "en" | TTS language code (en, es, fr, etc.) |
| `emotion` | string | ❌ No | "Calm" | TTS emotion (Calm, Excited, Serious, etc.) |

**Response (Success):**

```json
{
  "status": "success",
  "message": "Outbound call with escalation initiated to +1234567890 for John Doe",
  "details": {
    "phone_number": "+1234567890",
    "original_input": "+1234567890",
    "name": "John Doe",
    "room_name": "outbound-a1b2c3d4e5f6",
    "participant_id": "PA_xxxxxxxxxxxxx",
    "sip_call_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "has_dynamic_instruction": true,
    "language": "en",
    "emotion": "Calm",
    "escalation_enabled": true,
    "supervisor_phone": "+919911062767"
  },
  "transcript": null
}
```

**Response (Error):**

```json
{
  "detail": "Invalid phone number format. Phone number must start with '+' followed by country code and number (e.g., +1234567890)"
}
```

## Testing Examples

### Example 1: Basic Outbound Call

```bash
curl -X POST "http://localhost:8000/calls/outbound-with-escalation" \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+919911062767",
    "name": "Customer Support Test"
  }'
```

### Example 2: Call with Custom Instructions

```bash
curl -X POST "http://localhost:8000/calls/outbound-with-escalation" \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+919911062767",
    "name": "Rajesh Kumar",
    "dynamic_instruction": "You are calling to remind about an upcoming appointment. Be friendly and helpful.",
    "language": "en",
    "emotion": "Calm"
  }'
```

### Example 3: Using Postman

1. Open Postman
2. Create new request:
   - Method: `POST`
   - URL: `http://localhost:8000/calls/outbound-with-escalation`
3. Set Headers:
   - Key: `Content-Type`, Value: `application/json`
4. Set Body (raw JSON):
```json
{
  "phone_number": "+919911062767",
  "name": "Test User",
  "dynamic_instruction": "You are a support agent following up on a ticket."
}
```
5. Click "Send"

### Example 4: Using Python

```python
import requests

url = "http://localhost:8000/calls/outbound-with-escalation"
payload = {
    "phone_number": "+919911062767",
    "name": "John Doe",
    "dynamic_instruction": "You are calling to provide an update on their order.",
    "language": "en",
    "emotion": "Calm"
}

response = requests.post(url, json=payload)
print(response.json())
```

## Conversation Flow

### Phase 1: AI Agent ↔ Customer

**Scenario:** Customer needs help but agent can't resolve the issue.

```
AI Agent: "Hello, this is the LiveKit support team. How can I help you today?"
Customer: "I'm having trouble with my account, and I need to speak to someone."
AI Agent: "I understand. Would you like me to connect you with a human supervisor?"
Customer: "Yes, please."
AI Agent: "Please hold while I connect you to a human agent."
```

**Status:** Customer on hold with hold music 🎵

### Phase 2: AI Agent ↔ Supervisor

**Scenario:** Agent briefs supervisor in a separate call.

```
AI Agent: "Hello, I have a customer who needs assistance. 
           They were having trouble with their account and requested to speak with someone.
           Are you ready to take this call?"
Supervisor: "Yes, please connect me."
AI Agent: "Connecting you to the customer now."
```

### Phase 3: Customer ↔ Supervisor

**Scenario:** Calls are merged, agent disconnects.

```
AI Agent: "You are on the line with my supervisor. I'll be hanging up now."
[Agent leaves]
Customer & Supervisor: [Continue conversation directly]
```

## Troubleshooting

### Issue: "LiveKit credentials not configured"

**Solution:** Ensure all required environment variables are set in `.env`:
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `LIVEKIT_URL`
- `LIVEKIT_SIP_OUTBOUND_TRUNK`

### Issue: "Escalation will fail if requested"

**Solution:** Set `LIVEKIT_SUPERVISOR_PHONE_NUMBER` in `.env`

### Issue: Call connects but no agent responds

**Solution:** Make sure `outbound.py` agent worker is running:
```bash
python outbound.py
```

### Issue: Invalid phone number format

**Solution:** Ensure phone number:
- Starts with `+`
- Includes country code
- Example: `+919911062767` (India), `+12625925656` (US)

### Issue: Agent worker crashes on Windows

**Solution:** The `outbound.py` already handles this by disabling the inference executor (lines 369-371)

## Comparison: Standard vs Escalation Endpoint

| Feature | `/calls/outbound` | `/calls/outbound-with-escalation` |
|---------|-------------------|-----------------------------------|
| AI Agent | ✅ Yes | ✅ Yes |
| Custom Instructions | ✅ Yes | ✅ Yes |
| Transcript Return | ✅ Yes (waits) | ❌ No (real-time only) |
| Escalation to Human | ❌ No | ✅ Yes |
| Hold Music | ❌ No | ✅ Yes (during transfer) |
| Call Merging | ❌ No | ✅ Yes |
| LiveKit Agent Required | ❌ No | ✅ Yes |
| Use Case | Simple automated calls | Customer support with escalation |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          API Server (api.py)                     │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │    POST /calls/outbound-with-escalation                   │  │
│  │    (routers/calls.py)                                     │  │
│  └────────────────────┬─────────────────────────────────────┘  │
└───────────────────────┼───────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                       LiveKit Server                             │
│                                                                   │
│  ┌───────────────┐     ┌──────────────┐    ┌─────────────────┐ │
│  │   Customer    │◄────┤   AI Agent   ├────►│   Supervisor    │ │
│  │   (SIP Call)  │     │ (outbound.py)│    │   (SIP Call)    │ │
│  └───────────────┘     └──────────────┘    └─────────────────┘ │
│                                                                   │
│  Rooms: outbound-xxxx (customer) → outbound-xxxx-supervisor     │
└─────────────────────────────────────────────────────────────────┘
```

## Next Steps

1. ✅ Fix `.env` typo (double equals → single equals)
2. ✅ Start `outbound.py` agent worker
3. ✅ Start API server
4. ✅ Test with your phone number
5. ✅ Request escalation during call
6. ✅ Verify supervisor receives call with context
7. ✅ Confirm calls merge successfully

## Support

For issues or questions:
- Check logs in agent worker terminal
- Check logs in API server terminal
- Verify LiveKit credentials
- Ensure phone numbers are in E.164 format (+country code + number)

---

**Created:** 2025-11-10  
**API Version:** 1.0.0  
**Endpoint:** `/calls/outbound-with-escalation`

