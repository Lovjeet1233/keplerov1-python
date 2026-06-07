# HTTP Tool Registration Guide

## Overview

Create custom HTTP request tools dynamically for both **Chatbot (Kepler v1)** and **Voice Agent (ElevenLabs)**. Tools are automatically available after registration.

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                  HTTP TOOL REGISTRATION                    │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  CHATBOT (Kepler v1)          VOICE (ElevenLabs)         │
│  ┌──────────────────┐         ┌──────────────────┐       │
│  │ POST /http-tools │         │ POST /http-tools │       │
│  │ /register        │         │ /register        │       │
│  │                  │         │                  │       │
│  │ + user_id        │         │ + agent_id       │       │
│  │ + tool_name      │         │ + tool_name      │       │
│  │ + method         │         │ + method         │       │
│  │ + url            │         │ + url            │       │
│  │ + parameters     │         │ + parameters     │       │
│  └──────────────────┘         └──────────────────┘       │
│          │                             │                  │
│          ▼                             ▼                  │
│  ┌──────────────────┐         ┌──────────────────┐       │
│  │ MongoDB          │         │ ElevenLabs API   │       │
│  │ tool_store       │         │ + Auto-attach    │       │
│  └──────────────────┘         └──────────────────┘       │
│          │                             │                  │
│          ▼                             ▼                  │
│  ┌──────────────────┐         ┌──────────────────┐       │
│  │ Chatbot loads    │         │ Agent uses tool  │       │
│  │ tool on chat     │         │ in conversation  │       │
│  └──────────────────┘         └──────────────────┘       │
└────────────────────────────────────────────────────────────┘
```

## Kepler v1 (Chatbot) - HTTP Tools

### Endpoints

```
POST   /http-tools/register              - Register HTTP tool for user
PATCH  /http-tools/tools/{tool_id}       - Update HTTP tool
DELETE /http-tools/tools/{tool_id}       - Delete HTTP tool
GET    /http-tools/tools?user_id={id}    - Get all HTTP tools for user
```

### Register HTTP Tool

```bash
POST http://localhost:8000/http-tools/register
```

**Request:**
```json
{
  "user_id": "user_123",
  "tool_name": "fetch_weather",
  "tool_description": "Fetch current weather for a city",
  "method": "GET",
  "url": "https://api.weather.com/v1/current",
  "parameters": [
    {
      "name": "city",
      "description": "City name to get weather for",
      "type": "string",
      "required": true
    },
    {
      "name": "units",
      "description": "Temperature units (metric or imperial)",
      "type": "string",
      "required": false,
      "default": "metric"
    }
  ],
  "headers": {
    "Authorization": "Bearer YOUR_API_KEY"
  }
}
```

**Response:**
```json
{
  "status": "success",
  "message": "HTTP tool 'fetch_weather' created successfully",
  "tool_id": "abc123...",
  "user_id": "user_123",
  "tool": {
    "tool_id": "abc123...",
    "user_id": "user_123",
    "tool_name": "fetch_weather",
    "tool_type": "http",
    "description": "Fetch current weather for a city",
    "schema": {
      "type": "object",
      "method": "GET",
      "url": "https://api.weather.com/v1/current",
      "parameters": [...],
      "headers": {...}
    }
  }
}
```

### Use in Chatbot

```bash
# Chat request
POST http://localhost:8000/rag/chat
{
  "query": "What's the weather in New York?",
  "user_id": "user_123",
  "thread_id": "chat_456"
}
```

**Chatbot automatically:**
1. Loads HTTP tool for `user_123`
2. LLM decides to use `fetch_weather` tool
3. Calls `GET https://api.weather.com/v1/current?city=New York&units=metric`
4. Returns weather data to user

### Examples

#### Example 1: Weather API

```bash
curl -X POST http://localhost:8000/http-tools/register \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "tool_name": "get_weather",
    "tool_description": "Get current weather for any city",
    "method": "GET",
    "url": "https://api.openweathermap.org/data/2.5/weather",
    "parameters": [
      {
        "name": "q",
        "description": "City name",
        "type": "string",
        "required": true
      },
      {
        "name": "appid",
        "description": "API key",
        "type": "string",
        "required": true
      }
    ]
  }'
```

#### Example 2: Stock Price API

```bash
curl -X POST http://localhost:8000/http-tools/register \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "tool_name": "get_stock_price",
    "tool_description": "Get current stock price for a symbol",
    "method": "GET",
    "url": "https://api.stockmarket.com/v1/quote",
    "parameters": [
      {
        "name": "symbol",
        "description": "Stock symbol (e.g., AAPL, GOOGL)",
        "type": "string",
        "required": true
      }
    ],
    "headers": {
      "X-API-Key": "your_api_key_here"
    }
  }'
```

#### Example 3: POST Request (Create Resource)

```bash
curl -X POST http://localhost:8000/http-tools/register \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "tool_name": "create_ticket",
    "tool_description": "Create a support ticket",
    "method": "POST",
    "url": "https://api.helpdesk.com/v1/tickets",
    "parameters": [
      {
        "name": "title",
        "description": "Ticket title",
        "type": "string",
        "required": true
      },
      {
        "name": "description",
        "description": "Ticket description",
        "type": "string",
        "required": true
      },
      {
        "name": "priority",
        "description": "Priority level (low, medium, high)",
        "type": "string",
        "required": false,
        "default": "medium"
      }
    ],
    "headers": {
      "Authorization": "Bearer YOUR_TOKEN"
    }
  }'
```

---

## ElevenLabs Agent (Voice) - HTTP Tools

### Endpoints

```
POST   /api/v1/http-tools/register          - Register HTTP tool for agent
PATCH  /api/v1/http-tools/tools/{tool_id}   - Update HTTP tool
DELETE /api/v1/http-tools/tools/{tool_id}   - Delete HTTP tool
GET    /api/v1/http-tools/tools/{tool_id}   - Get HTTP tool details
```

### Register HTTP Tool

```bash
POST http://your-elevenlabs-api.com/api/v1/http-tools/register
```

**Request:**
```json
{
  "agent_id": "agent_7801ksx19awdfvcact04jd86km1t",
  "tool_name": "fetch_weather",
  "tool_description": "Fetch current weather for a city",
  "method": "GET",
  "url": "https://api.weather.com/v1/current",
  "parameters": [
    {
      "name": "city",
      "description": "City name to get weather for",
      "type": "string",
      "required": true
    }
  ]
}
```

**Response:**
```json
{
  "status": "success",
  "message": "HTTP tool 'fetch_weather' registered and attached to agent",
  "tool_id": "tool_xyz789",
  "agent_id": "agent_7801ksx19awdfvcact04jd86km1t"
}
```

**What Happens:**
1. Tool registered with ElevenLabs API
2. **Automatically attached** to the specified agent
3. Agent can now use the tool in voice conversations

### Use in Voice Call

```
User: "What's the weather in London?"
↓
Agent: [Uses fetch_weather tool]
↓
Agent: "The current weather in London is 15°C with partly cloudy skies."
```

### Examples

#### Example 1: Flight Status API

```bash
curl -X POST http://your-api.com/api/v1/http-tools/register \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent_abc123",
    "tool_name": "check_flight_status",
    "tool_description": "Check the status of a flight",
    "method": "GET",
    "url": "https://api.flightaware.com/v1/flights",
    "parameters": [
      {
        "name": "flight_number",
        "description": "Flight number (e.g., AA123)",
        "type": "string",
        "required": true
      }
    ]
  }'
```

#### Example 2: Restaurant Booking

```bash
curl -X POST http://your-api.com/api/v1/http-tools/register \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent_abc123",
    "tool_name": "book_restaurant",
    "tool_description": "Book a table at a restaurant",
    "method": "POST",
    "url": "https://api.opentable.com/v1/reservations",
    "parameters": [
      {
        "name": "restaurant_id",
        "description": "Restaurant ID",
        "type": "string",
        "required": true
      },
      {
        "name": "party_size",
        "description": "Number of guests",
        "type": "integer",
        "required": true
      },
      {
        "name": "date_time",
        "description": "Reservation date and time",
        "type": "string",
        "required": true
      }
    ]
  }'
```

---

## Comparison: Chatbot vs Voice Agent

| Feature | Chatbot (Kepler v1) | Voice Agent (ElevenLabs) |
|---------|---------------------|--------------------------|
| **Identifier** | `user_id` | `agent_id` |
| **Storage** | MongoDB | ElevenLabs API |
| **Auto-attach** | No (loads on chat) | Yes (immediate) |
| **Tool Loading** | Dynamic per request | Pre-configured |
| **Use Case** | Text chat | Voice calls |

---

## Complete Workflow

### Chatbot Workflow

```
1. Register HTTP tool
   POST /http-tools/register (user_id: "user_123")
   ↓
2. Tool saved in MongoDB
   Collection: integration-chatbot
   ↓
3. User chats
   POST /rag/chat (user_id: "user_123")
   ↓
4. Chatbot loads HTTP tool
   tool_builder.build_tools_for_user("user_123")
   ↓
5. LLM uses tool
   Calls HTTP endpoint with parameters
   ↓
6. Response returned to user
```

### Voice Agent Workflow

```
1. Register HTTP tool
   POST /api/v1/http-tools/register (agent_id: "agent_abc")
   ↓
2. Tool registered with ElevenLabs
   ElevenLabs API creates tool
   ↓
3. Tool auto-attached to agent
   Agent config updated
   ↓
4. User calls agent
   Voice conversation starts
   ↓
5. Agent uses tool
   ElevenLabs calls HTTP endpoint
   ↓
6. Response spoken to user
```

---

## Parameter Types

Supported parameter types:

- `string` - Text values
- `integer` - Whole numbers
- `number` - Decimal numbers
- `boolean` - true/false
- `array` - Lists
- `object` - JSON objects

---

## Best Practices

### 1. Tool Naming
- Use descriptive names: `get_weather`, `create_ticket`
- Use snake_case format
- Keep names concise but clear

### 2. Descriptions
- Be specific about what the tool does
- Include example use cases
- Mention required parameters

### 3. Parameters
- Mark truly required fields as `required: true`
- Provide defaults for optional parameters
- Use clear parameter descriptions

### 4. Security
- Store API keys in headers, not parameters
- Use environment variables for sensitive data
- Validate all inputs

### 5. Error Handling
- Tools should return meaningful error messages
- Handle API rate limits gracefully
- Log all tool executions

---

## Troubleshooting

### Tool Not Loading (Chatbot)

**Issue**: HTTP tool not available in chat

**Solution**:
1. Verify registration: `GET /http-tools/tools?user_id=user_123`
2. Check `user_id` matches in chat request
3. Check server logs for tool loading messages

### Tool Not Working (Voice Agent)

**Issue**: Agent doesn't use HTTP tool

**Solution**:
1. Verify `agent_id` is correct
2. Check tool was attached: Review agent config
3. Test tool endpoint manually
4. Check ElevenLabs logs

### HTTP Request Fails

**Issue**: Tool executes but API call fails

**Solution**:
1. Verify URL is accessible
2. Check API key/headers are correct
3. Validate parameter format
4. Test API endpoint with curl

---

## Summary

✅ **Chatbot**: Register with `user_id`, tools load dynamically
✅ **Voice Agent**: Register with `agent_id`, tools auto-attach
✅ **Both**: Support GET, POST, PUT, PATCH, DELETE
✅ **Both**: Custom parameters and headers
✅ **Both**: Automatic integration with LLM

**Next Steps:**
1. Register your first HTTP tool
2. Test in chatbot or voice call
3. Monitor tool usage in logs
4. Add more tools as needed
