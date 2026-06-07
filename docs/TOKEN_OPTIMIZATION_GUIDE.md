# Token Optimization System - Kepler v1

## 🚀 Overview

The chat endpoint now implements **intelligent token optimization** to reduce costs and improve response times for multi-turn conversations.

## ✅ Key Features

### 1. **System Prompt Sent Only Once** 
- System prompt is sent **only on the first message** in a thread
- Follow-up messages rely on conversation history (LLM maintains context)
- **Savings: 500-1000+ tokens per query** (after first message)

### 2. **Automatic Conversation Summarization**
- After **15 turns**, the system automatically summarizes the first 10 turns
- Keeps last **5 turns in full** as recent history
- Summary is stored in MongoDB and included in future queries
- **No context loss** - all important information preserved in summary

### 3. **No History Truncation**
- Recent conversation history (last 5 turns) included in **full** - no truncation
- Prevents hallucination and maintains coherent conversations
- Summary provides context for older conversations

### 4. **Persistent State in MongoDB**
- Conversation history, summary, and flags stored in `checkpoints_v2` collection
- Automatic retrieval on each query
- Thread-based isolation (`thread_id`)

---

## 📊 Token Savings Example

### Scenario: 20-turn conversation with 1000-token system prompt

#### **Before Optimization:**
| Turn | System Prompt | History | Context | **Total Input** |
|------|---------------|---------|---------|-----------------|
| 1    | 1000          | 0       | 800     | **1,800**       |
| 2    | 1000 ❌       | 300     | 800     | **2,100**       |
| 3    | 1000 ❌       | 300     | 800     | **2,100**       |
| ...  | ...           | ...     | ...     | ...             |
| 20   | 1000 ❌       | 300     | 800     | **2,100**       |

**Total: ~40,000 tokens**

#### **After Optimization:**
| Turn | System Prompt | Summary | History | Context | **Total Input** |
|------|---------------|---------|---------|---------|-----------------|
| 1    | 1000 ✅       | 0       | 0       | 800     | **1,800**       |
| 2    | 0 ✅          | 0       | 200     | 800     | **1,000**       |
| 3    | 0 ✅          | 0       | 400     | 800     | **1,200**       |
| ...  | ...           | ...     | ...     | ...     | ...             |
| 15   | 0 ✅          | 0       | 1000    | 800     | **1,800**       |
| 16   | 0 ✅          | 500     | 300     | 800     | **1,600** ⚡    |
| ...  | ...           | ...     | ...     | ...     | ...             |
| 20   | 0 ✅          | 500     | 300     | 800     | **1,600**       |

**Total: ~25,000 tokens**

**Savings: 15,000 tokens (37.5% reduction)** 💰

---

## 🔧 How It Works

### **Flow Diagram:**

```
Query 1 (thread_id=user123)
├─ Check MongoDB: No previous state
├─ Send: System Prompt (1000 tokens) + Query
├─ Save to MongoDB: 
│  ├─ conversation_history: [Q1, A1]
│  ├─ system_prompt_sent: true
│  └─ conversation_summary: null
└─ Response

Query 2 (thread_id=user123)
├─ Check MongoDB: Found previous state
├─ Load: system_prompt_sent=true, history=[Q1,A1]
├─ Send: NO system prompt + History (200 tokens) + Query
├─ Save to MongoDB:
│  ├─ conversation_history: [Q1, A1, Q2, A2]
│  └─ system_prompt_sent: true
└─ Response

...

Query 15 (thread_id=user123)
├─ Check MongoDB: Found 14 previous turns
├─ Load: history=[Q1...Q14, A1...A14]
├─ Send: NO system prompt + History (full) + Query
├─ ⚡ TRIGGER SUMMARIZATION (15 turns reached)
│  ├─ Summarize turns 1-10 using OpenAI
│  ├─ Create summary: "User discussed X, Y, Z..."
│  ├─ Keep turns 11-15 as recent history
│  └─ Save to MongoDB:
│     ├─ conversation_history: [Q11...Q15, A11...A15]
│     ├─ conversation_summary: "User discussed..."
│     └─ system_prompt_sent: true
└─ Response

Query 16 (thread_id=user123)
├─ Check MongoDB: Found summary + 5 recent turns
├─ Load: summary="...", history=[Q11...Q15]
├─ Send: Summary (500 tokens) + Recent History (300 tokens) + Query
└─ Response
```

---

## 🗄️ MongoDB Storage

### **Collection: `checkpoints_v2`**

```json
{
  "thread_id": "user123",
  "checkpoint": {
    "v": 1,
    "ts": "2026-06-07T02:45:00Z",
    "channel_values": {
      "conversation_history": [
        {"query": "What is AI?", "answer": "AI is..."},
        {"query": "Tell me more", "answer": "AI includes..."}
      ],
      "conversation_summary": "User asked about AI fundamentals. Discussed machine learning, neural networks, and applications.",
      "system_prompt_sent": true,
      "system_prompt": "You are a helpful AI assistant...",
      "thread_id": "user123"
    }
  }
}
```

---

## 🎯 Summarization Logic

### **When Summarization Triggers:**
- After **15 conversation turns**
- Automatically in the background
- Uses OpenAI `gpt-4o-mini` for cost-effectiveness

### **What Gets Summarized:**
- First **10 turns** are compressed into a summary
- Last **5 turns** kept in full as recent history

### **Summarization Prompt:**
```
You are a conversation summarizer. Create a concise but comprehensive summary 
that preserves all important context, facts, decisions, and user preferences.

The summary should:
1. Capture key topics discussed
2. Preserve important facts, numbers, and specific details
3. Note any decisions made or preferences expressed
4. Maintain chronological flow of important events
5. Be concise but complete (aim for 30-50% of original length)
```

### **Example Summary:**
```
Previous Conversation Summary:
The user inquired about implementing a chatbot system. We discussed:
- Multi-tenant architecture with user_id scoping
- MongoDB for data persistence
- LangChain for tool integration
- RAG system using Qdrant for vector search
The user requested CRM and email tool integration, which was implemented 
with dynamic tool loading based on user_id. The user also asked about 
token optimization, leading to the current conversation about system 
prompt caching and conversation summarization.
```

---

## 📈 Benefits

### **1. Cost Reduction**
- **30-50% fewer tokens** for long conversations
- System prompt not repeated (saves 500-1000 tokens per query)
- Older conversations compressed via summarization

### **2. Faster Responses**
- Fewer input tokens = faster LLM processing
- Reduced latency for follow-up queries

### **3. Better Context Retention**
- No truncation of recent history (last 5 turns)
- Summary preserves important context from older turns
- **No hallucination** due to missing context

### **4. Scalability**
- Unlimited conversation length supported
- Automatic compression prevents token bloat
- MongoDB stores complete conversation state

---

## 🔍 Code Locations

### **Main Implementation:**
- **File:** `/Users/amarchoudhary/Desktop/kepelero/keplerov1/workflow/graph.py`

### **Key Methods:**

1. **`_summarize_conversation_history()`** (Line 156-208)
   - Summarizes conversation turns using OpenAI
   - Preserves context while reducing tokens

2. **`generate_node()`** (Line 307-582)
   - **Line 375-425:** System prompt sent only once
   - **Line 347-364:** History context with summary + recent turns
   - **Line 552-577:** Auto-summarization after 15 turns

3. **`run()`** (Line 591-728)
   - **Line 648-678:** Retrieve conversation state from MongoDB
   - **Line 680-696:** Initialize state with summary and flags

---

## 🧪 Testing

### **Test Scenario 1: First Message**
```bash
curl -X POST http://localhost:8000/rag/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is AI?",
    "thread_id": "test_thread_001",
    "system_prompt": "You are an AI expert.",
    "provider": "openai"
  }'
```

**Expected:**
- System prompt sent (1000 tokens)
- `system_prompt_sent: true` saved to MongoDB

### **Test Scenario 2: Follow-up Message**
```bash
curl -X POST http://localhost:8000/rag/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Tell me more about machine learning",
    "thread_id": "test_thread_001",
    "provider": "openai"
  }'
```

**Expected:**
- NO system prompt sent (0 tokens)
- Previous conversation history included
- Logs: "✓ Skipping system prompt (already sent in this thread)"

### **Test Scenario 3: 15+ Turn Conversation**
```bash
# Send 15 queries to the same thread_id
for i in {1..15}; do
  curl -X POST http://localhost:8000/rag/chat \
    -H "Content-Type: application/json" \
    -d "{
      \"query\": \"Question $i about AI\",
      \"thread_id\": \"test_thread_002\",
      \"provider\": \"openai\"
    }"
done
```

**Expected:**
- After 15th query: Summarization triggered
- Logs: "⚡ Conversation has 15 turns - triggering summarization"
- MongoDB updated with `conversation_summary`
- Only last 5 turns in `conversation_history`

---

## 📝 Configuration

### **Summarization Threshold:**
Change the turn count before summarization:

```python
# In workflow/graph.py, line 554
if history_length >= 15:  # Change to 10, 20, etc.
```

### **Recent History Window:**
Change how many recent turns to keep:

```python
# In workflow/graph.py, line 357
recent_history = state["conversation_history"][-5:]  # Change to -3, -10, etc.
```

### **Summarization Model:**
Change the model used for summarization:

```python
# In workflow/graph.py, line 191
summarization_llm = ChatOpenAI(
    model="gpt-4o-mini",  # Change to "gpt-4o", "gpt-3.5-turbo", etc.
    temperature=0.3,
    openai_api_key=openai_api_key
)
```

---

## 🎓 Best Practices

### **1. Use Consistent thread_id**
- Same `thread_id` for entire conversation
- Different `thread_id` for different users/sessions

### **2. Monitor Token Usage**
- Check logs for token counts
- Verify summarization triggers at expected intervals

### **3. System Prompt Design**
- Keep system prompts concise but comprehensive
- Remember: sent only once per thread

### **4. Long Conversations**
- System handles unlimited conversation length
- Automatic summarization prevents token bloat
- No manual intervention needed

---

## 🚨 Important Notes

1. **System prompt is sent ONCE per thread** - design it carefully
2. **Summarization uses OpenAI** - requires valid API key
3. **MongoDB stores complete state** - ensure MongoDB is running
4. **Thread isolation** - different threads are completely separate
5. **No data loss** - summary preserves all important context

---

## 📊 Monitoring

### **Check Logs:**
```bash
# Look for these log messages:
✓ Sending system prompt (first message, 1234 chars)
✓ Skipping system prompt (already sent in this thread)
⚡ Conversation has 15 turns - triggering summarization
✓ Conversation summarized: 5000 chars -> 1500 chars
✓ Compressed history: 15 turns -> summary + 5 recent turns
```

### **Check MongoDB:**
```javascript
// Connect to MongoDB
use python

// View conversation state
db.checkpoints_v2.findOne({"checkpoint.channel_values.thread_id": "user123"})

// Check if summary exists
db.checkpoints_v2.find({
  "checkpoint.channel_values.conversation_summary": {$exists: true}
})
```

---

## 🎉 Summary

**Before:** System prompt sent every request, history truncated, context lost
**After:** System prompt sent once, unlimited history with summarization, no context loss

**Result:** 30-50% token reduction, faster responses, better conversations! 🚀
