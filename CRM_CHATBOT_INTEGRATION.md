# CRM Tools + Chatbot Integration ✅

## What Was Done

Integrated CRM tools into the RAG chatbot so they're **automatically available** when users chat.

## Changes Made

### Modified: `routers/rag.py`

Added CRM tool loading to the `/rag/chat` endpoint:

```python
# Import tool builder
from services.tool_builder import get_tool_builder

# In chat endpoint:
if request.user_id:
    # Load ALL registered tools for this user
    user_tools = get_tool_store().get_tools_by_user_id(request.user_id)
    
    # Build CRM tools automatically
    tool_builder = get_tool_builder(get_tool_store())
    crm_tools = tool_builder.build_tools_for_user(
        user_id=request.user_id,
        email_base_url=...,
        x_user_email=...
    )
    
    # Combine with other tools
    all_tools = crm_tools + ecommerce_tools + email_tools
```

## How It Works Now

### 1. User Registers CRM Tools

```bash
POST /crm/register-search-tool
{
  "user_id": "user_1234",
  "table_id": "6a1b28acde2598f108c0471e",
  "search_schema": [
    {"name": "email_address", "description": "Customer email"}
  ]
}
```

### 2. Tools Saved in MongoDB

```javascript
// Collection: synervo-python.integration-chatbot
{
  tool_id: "def69ce1-4a31-4c0a-b600-aea43c23a1db",
  user_id: "user_1234",
  tool_name: "crm_search_records",
  tool_type: "crm",
  schema: {
    tableId: "6a1b28acde2598f108c0471e",
    crm_base_url: "https://crm-virid-seven-35.vercel.app/api",
    search_schema: [...]
  }
}
```

### 3. User Chats with Bot

```bash
POST /rag/chat
{
  "query": "Search for customer with email john@example.com",
  "user_id": "user_1234",
  "system_prompt": "You are a helpful assistant with CRM access."
}
```

### 4. Chatbot Automatically Loads CRM Tools

```
Server logs:
✓ Loaded 1 registered tool(s) for user_id=user_1234
✓ Built 1 CRM tool(s) for user user_1234
  - crm_search_records: Search customer records in CRM
✓ Total tools available: 1 (CRM: 1, Ecommerce: 0, Email: 0)
```

### 5. LLM Uses CRM Tool

```
User: "Search for customer with email john@example.com"
↓
LLM: [Calls crm_search_records(email_address="john@example.com")]
↓
CRM API: Returns customer data
↓
Bot: "Found customer: John Doe, Phone: +1234567890"
```

## Complete Example

### Register All 3 CRM Tools

```bash
# 1. Search
curl -X POST http://localhost:8000/crm/register-search-tool \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_1234",
    "table_id": "6a1b28acde2598f108c0471e",
    "search_schema": [
      {"name": "email_address", "description": "Customer email"}
    ]
  }'

# 2. Create
curl -X POST http://localhost:8000/crm/register-create-tool \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_1234",
    "table_id": "6a1b28acde2598f108c0471e",
    "data_schema": [
      {"name": "full_name", "description": "Customer name"},
      {"name": "email_address", "description": "Customer email"},
      {"name": "phone_number", "description": "Customer phone"}
    ]
  }'

# 3. Update
curl -X POST http://localhost:8000/crm/register-update-tool \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_1234",
    "table_id": "6a1b28acde2598f108c0471e",
    "lookup_column": "email_address",
    "update_schema": [
      {"name": "phone_number", "description": "Updated phone"}
    ]
  }'
```

### Chat with CRM Tools

```bash
# Search query
curl -X POST http://localhost:8000/rag/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Find customer john@example.com",
    "user_id": "user_1234",
    "collection_names": [""],
    "thread_id": "chat_123",
    "system_prompt": "You are a CRM assistant. Use CRM tools to help users."
  }'

# Create query
curl -X POST http://localhost:8000/rag/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Add new customer Jane Smith, jane@example.com, +1234567890",
    "user_id": "user_1234",
    "thread_id": "chat_123"
  }'

# Update query
curl -X POST http://localhost:8000/rag/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Update John'\''s phone to +9999999999",
    "user_id": "user_1234",
    "thread_id": "chat_123"
  }'
```

## Testing

Run the test script:

```bash
python test_crm_integration.py
```

Expected output:
```
============================================================
CRM TOOLS INTEGRATION TEST
============================================================

1. Checking CRM tools for user: user_1234
   ✓ Found 1 CRM tool(s)
     - crm_search_records: Search customer records in CRM

2. Testing chatbot with CRM search query
   ✓ Response received:
     Query: Search for customer with email john@example.com
     Answer: [LLM response using CRM tool]
     Latency: 2500.00ms

3. Testing chatbot with CRM create query
   ✓ Response received:
     Answer: [LLM response using CRM tool]

============================================================
TEST COMPLETE
============================================================
```

## Key Features

✅ **Automatic Loading**: CRM tools loaded automatically when `user_id` is provided
✅ **Multi-Tool Support**: Search, Create, Update all available
✅ **Multi-Tenant**: Each user has their own tools
✅ **Seamless Integration**: Works alongside Email and Ecommerce tools
✅ **No Manual Activation**: Tools available immediately after registration

## Tool Priority

Tools are combined in this order:
1. **CRM Tools** (from MongoDB via tool_builder)
2. **Ecommerce Tools** (if credentials provided)
3. **Email Tools** (if credentials provided)

```python
all_tools = crm_tools + ecommerce_tools + email_tools
```

## Logs to Watch

When chatbot loads tools:
```
2026-06-06 23:00:00 - INFO - Loaded 3 registered tool(s) for user_id=user_1234
2026-06-06 23:00:00 - INFO - ✓ Built 3 CRM tool(s) for user user_1234
2026-06-06 23:00:00 - INFO -   - crm_search_records: Search customer records in CRM...
2026-06-06 23:00:00 - INFO -   - crm_create_record: Create CRM record in table...
2026-06-06 23:00:00 - INFO -   - crm_update_record: Update CRM record in table...
2026-06-06 23:00:00 - INFO - ✓ Total tools available: 3 (CRM: 3, Ecommerce: 0, Email: 0)
```

## Troubleshooting

### Tools Not Loading

**Issue**: Chatbot doesn't use CRM tools

**Solution**:
1. Check `user_id` is provided in chat request
2. Verify tools are registered: `GET /crm/tools?user_id=user_1234`
3. Check server logs for tool loading messages
4. Ensure `CRM_BASE_URL` is set in `.env`

### Tool Execution Errors

**Issue**: Tool is called but fails

**Solution**:
1. Verify CRM API is accessible
2. Check `table_id` exists in CRM
3. Validate field names in schema match CRM columns
4. Check CRM API logs for errors

### User Has No Tools

**Issue**: `No tools loaded for this request`

**Solution**:
1. Register tools first: `POST /crm/register-search-tool`
2. Verify registration: `GET /crm/tools?user_id=user_1234`
3. Check MongoDB: `db["integration-chatbot"].find({user_id: "user_1234"})`

## Multi-User Example

```python
# User A: Real estate agent
# Registered: crm_search, crm_create
POST /rag/chat {"user_id": "user_a", "query": "Find property owner..."}
# Loads: 2 CRM tools

# User B: Healthcare provider  
# Registered: crm_search, crm_update
POST /rag/chat {"user_id": "user_b", "query": "Update patient record..."}
# Loads: 2 CRM tools

# User C: No CRM tools
# Registered: None
POST /rag/chat {"user_id": "user_c", "query": "Hello"}
# Loads: 0 CRM tools
```

## Summary

🎉 **CRM tools are now fully integrated with the chatbot!**

- ✅ Register tools via `/crm/register-*-tool` endpoints
- ✅ Tools automatically load when user chats
- ✅ LLM decides when to use which tool
- ✅ Multi-tenant isolation maintained
- ✅ Works alongside Email and Ecommerce tools

**Next Steps:**
1. Register CRM tools for your users
2. Test with real CRM API
3. Monitor tool usage in logs
4. Add more tool types as needed
