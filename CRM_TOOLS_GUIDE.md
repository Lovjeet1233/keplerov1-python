# CRM Tools Integration Guide

## Overview

Simple, direct CRM tool registration for users. No complex assignment tables - tools are registered directly per user, similar to the 11Labs pattern.

## Architecture

```
┌─────────────────────────────────────────┐
│         User Registration               │
│  POST /crm/register-search-tool         │
│  POST /crm/register-create-tool         │
│  POST /crm/register-update-tool         │
│                                         │
│  ┌────────────────────────────┐        │
│  │  Tool Store (MongoDB)      │        │
│  │  - user_id + tool_name     │        │
│  │  - table_id, schemas       │        │
│  │  - crm_base_url (from env) │        │
│  └────────────────────────────┘        │
│                │                        │
│                ▼                        │
│  ┌────────────────────────────┐        │
│  │  Tool Builder              │        │
│  │  Loads tools for user_id   │        │
│  └────────────────────────────┘        │
│                │                        │
│                ▼                        │
│  ┌────────────────────────────┐        │
│  │  LangChain Tools           │        │
│  │  Ready for chatbot         │        │
│  └────────────────────────────┘        │
└─────────────────────────────────────────┘
```

## Environment Setup

Add to `.env`:
```bash
CRM_BASE_URL=https://crm-virid-seven-35.vercel.app/api
```

## API Endpoints

### 1. Register CRM Search Tool

```bash
POST /crm/register-search-tool
```

**Request:**
```json
{
  "user_id": "user_123",
  "table_id": "6a1b28acde2598f108c0471e",
  "search_schema": [
    {"name": "email_address", "description": "Customer email"},
    {"name": "phone_number", "description": "Customer phone"}
  ],
  "tool_description": "Search customer records"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "CRM search tool created successfully",
  "tool_id": "abc123...",
  "user_id": "user_123",
  "tool": {
    "tool_id": "abc123...",
    "user_id": "user_123",
    "tool_name": "crm_search_records",
    "tool_type": "crm",
    "description": "Search customer records",
    "schema": {
      "type": "object",
      "tableId": "6a1b28acde2598f108c0471e",
      "crm_base_url": "https://crm-virid-seven-35.vercel.app/api",
      "search_schema": [...]
    }
  }
}
```

### 2. Register CRM Create Tool

```bash
POST /crm/register-create-tool
```

**Request:**
```json
{
  "user_id": "user_123",
  "table_id": "6a1b28acde2598f108c0471e",
  "data_schema": [
    {"name": "full_name", "description": "Customer full name"},
    {"name": "email_address", "description": "Customer email"},
    {"name": "phone_number", "description": "Customer phone"}
  ],
  "tool_description": "Create new customer record"
}
```

### 3. Register CRM Update Tool

```bash
POST /crm/register-update-tool
```

**Request:**
```json
{
  "user_id": "user_123",
  "table_id": "6a1b28acde2598f108c0471e",
  "lookup_column": "email_address",
  "update_schema": [
    {"name": "phone_number", "description": "Updated phone"},
    {"name": "appointment_date", "description": "Appointment date"}
  ],
  "tool_description": "Update customer record"
}
```

### 4. Update CRM Tool

```bash
PATCH /crm/tools/{tool_id}?table_id=new_table_id&tool_description=New description
```

### 5. Delete CRM Tool

```bash
DELETE /crm/tools/{tool_id}?user_id=user_123
```

### 6. Get User's CRM Tools

```bash
GET /crm/tools?user_id=user_123
```

**Response:**
```json
{
  "status": "success",
  "user_id": "user_123",
  "count": 3,
  "tools": {
    "tool_id_1": {
      "tool_name": "crm_search_records",
      "tool_type": "crm",
      "description": "Search customer records",
      "schema": {...}
    },
    "tool_id_2": {
      "tool_name": "crm_create_record",
      "tool_type": "crm",
      "description": "Create new customer record",
      "schema": {...}
    },
    "tool_id_3": {
      "tool_name": "crm_update_record",
      "tool_type": "crm",
      "description": "Update customer record",
      "schema": {...}
    }
  }
}
```

## Usage in Chatbot

```python
from services.tool_builder import get_tool_builder
from database.tool_store import get_tool_store

# Initialize (once at startup)
tool_store = get_tool_store()
tool_builder = get_tool_builder(tool_store)

# Build tools for a user
user_id = "user_123"
tools = tool_builder.build_tools_for_user(user_id)

# tools now contains LangChain StructuredTool instances
# Use with your LangGraph agent or LLM
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4")
agent = create_openai_functions_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools)

result = agent_executor.invoke({
    "input": "Search for customer with email john@example.com"
})
```

## Complete Example

### Step 1: Register All 3 CRM Tools for a User

```bash
# 1. Search Tool
curl -X POST http://localhost:8000/crm/register-search-tool \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "table_id": "6a1b28acde2598f108c0471e",
    "search_schema": [
      {"name": "email_address", "description": "Customer email"},
      {"name": "phone_number", "description": "Customer phone"}
    ]
  }'

# 2. Create Tool
curl -X POST http://localhost:8000/crm/register-create-tool \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "table_id": "6a1b28acde2598f108c0471e",
    "data_schema": [
      {"name": "full_name", "description": "Customer full name"},
      {"name": "email_address", "description": "Customer email"},
      {"name": "phone_number", "description": "Customer phone"}
    ]
  }'

# 3. Update Tool
curl -X POST http://localhost:8000/crm/register-update-tool \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "table_id": "6a1b28acde2598f108c0471e",
    "lookup_column": "email_address",
    "update_schema": [
      {"name": "phone_number", "description": "Updated phone"},
      {"name": "appointment_date", "description": "Appointment date"}
    ]
  }'
```

### Step 2: Verify Registration

```bash
curl -X GET "http://localhost:8000/crm/tools?user_id=user_123"
```

### Step 3: Use in Code

```python
# In your chatbot initialization
from services.tool_builder import get_tool_builder
from database.tool_store import get_tool_store

tool_store = get_tool_store()
tool_builder = get_tool_builder(tool_store)

# When user starts a conversation
user_id = "user_123"
tools = tool_builder.build_tools_for_user(user_id)

print(f"Loaded {len(tools)} tools for {user_id}")
# Output: Loaded 3 tools for user_123

# Tools are ready to use with LangChain
```

## Multi-Tenant Scenarios

### Different CRM Tables per User

```bash
# User A: Real Estate CRM
curl -X POST http://localhost:8000/crm/register-search-tool \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_a",
    "table_id": "real_estate_table_123",
    "search_schema": [
      {"name": "property_address", "description": "Property address"},
      {"name": "client_email", "description": "Client email"}
    ]
  }'

# User B: Healthcare CRM
curl -X POST http://localhost:8000/crm/register-search-tool \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_b",
    "table_id": "patients_table_456",
    "search_schema": [
      {"name": "patient_id", "description": "Patient ID"},
      {"name": "phone_number", "description": "Contact number"}
    ]
  }'
```

### Partial Tool Registration

```bash
# Free tier: Only search
curl -X POST http://localhost:8000/crm/register-search-tool \
  -d '{"user_id": "free_user", "table_id": "...", "search_schema": [...]}'

# Premium tier: All 3 tools
curl -X POST http://localhost:8000/crm/register-search-tool \
  -d '{"user_id": "premium_user", "table_id": "...", "search_schema": [...]}'
curl -X POST http://localhost:8000/crm/register-create-tool \
  -d '{"user_id": "premium_user", "table_id": "...", "data_schema": [...]}'
curl -X POST http://localhost:8000/crm/register-update-tool \
  -d '{"user_id": "premium_user", "table_id": "...", "update_schema": [...]}'
```

## Database Schema

### Collection: `integration-chatbot`

```javascript
{
  "_id": ObjectId("..."),
  "tool_id": "abc123...",
  "user_id": "user_123",
  "tool_name": "crm_search_records",
  "tool_type": "crm",
  "description": "Search customer records",
  "schema": {
    "type": "object",
    "tableId": "6a1b28acde2598f108c0471e",
    "crm_base_url": "https://crm-virid-seven-35.vercel.app/api",
    "search_schema": [
      {"name": "email_address", "description": "Customer email"},
      {"name": "phone_number", "description": "Customer phone"}
    ]
  },
  "created_at": ISODate("2026-06-06T..."),
  "updated_at": ISODate("2026-06-06T...")
}

// Indexes:
// - tool_id (unique)
// - user_id
// - user_id + tool_name + tool_type (unique)
```

## Key Differences from Complex Multi-Tenant System

✅ **Simpler**: No separate assignment table
✅ **Direct**: Tools registered directly for users
✅ **Cleaner**: CRM base URL from environment
✅ **Faster**: Fewer database queries
✅ **Easier**: Less code to maintain

## Benefits

- **Multi-Tenant**: Each user has isolated tools
- **Flexible**: Register 1, 2, or all 3 CRM tools
- **Configurable**: Different table_id per user
- **Scalable**: Add more users easily
- **Simple**: Straightforward API

## Troubleshooting

### "Tool store is not initialized"
- Check MongoDB connection
- Verify MONGODB_URI in .env
- Restart API server

### "CRM tool missing tableId"
- Ensure table_id is provided in request
- Check MongoDB document has tableId in schema

### CRM API errors
- Verify CRM_BASE_URL in .env
- Check CRM API is accessible
- Validate table_id exists in CRM

## Next Steps

1. Register tools for your users
2. Integrate with chatbot using `tool_builder`
3. Test CRM operations
4. Monitor usage in MongoDB
