# API Structure Documentation

## Overview
The API has been modularized into separate routers for better organization and maintainability.

## File Structure

```
Kaplere/
├── api.py                          # Main application entry point
├── model/                          # Centralized Pydantic models
│   ├── __init__.py                # Model exports
│   └── model.py                   # All request/response models
├── routers/                        # Modularized API routers
│   ├── __init__.py                # Router exports
│   ├── rag.py                     # RAG-related endpoints
│   ├── calls.py                   # Outbound call endpoints
│   └── llm.py                     # LLM service endpoints
├── llmService/
│   └── llm.py                     # LLM service implementation
├── config/
│   ├── prompt.py                  # System prompts
│   └── settings.py                # Configuration settings
└── ...
```

## API Endpoints

### Main Routes
- `GET /` - Root endpoint with API information
- `GET /health` - Health check endpoint
- `GET /docs` - Interactive API documentation (Swagger UI)

### RAG Endpoints (Prefix: `/rag`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/rag/chat` | Chat with RAG system using conversation memory |
| POST | `/rag/data_ingestion` | Ingest data from URLs, PDFs, and Excel files |
| POST | `/rag/create_collection` | Create a new vector collection |
| POST | `/rag/delete_collection` | Delete an existing collection |
| GET | `/rag/conversation_history/{thread_id}` | Retrieve conversation history |

### Calls Endpoints (Prefix: `/calls`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/calls/outbound` | Initiate an outbound call with optional dynamic instructions |

### LLM Endpoints (Prefix: `/llm`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/llm/elaborate_prompt` | Elaborate a brief prompt into a detailed one |

## Centralized Models (`model/model.py`)

All Pydantic models are centralized in `model/model.py` for better organization and reusability:

### Common Models
- `StatusResponse` - Generic status response used across multiple endpoints

### RAG Models
- `ChatRequest` / `ChatResponse` - Chat endpoint models
- `DataIngestionRequest` - Data ingestion configuration
- `CreateCollectionRequest` / `DeleteCollectionRequest` - Collection management

### Calls Models
- `OutboundCallRequest` - Outbound call configuration

### LLM Models
- `ElaboratePromptRequest` / `ElaboratePromptResponse` - Prompt elaboration

## Router Details

### 1. RAG Router (`routers/rag.py`)
**Tag:** `RAG`  
**Prefix:** `/rag`

Handles all RAG-related operations including:
- Chat with context retrieval
- Data ingestion from multiple sources
- Collection management
- Conversation history

**Imports models from:** `model` package

### 2. Calls Router (`routers/calls.py`)
**Tag:** `Calls`  
**Prefix:** `/calls`

Handles outbound call operations:
- Phone number validation and formatting
- Dynamic instruction management
- Environment configuration updates

**Imports models from:** `model` package

### 3. LLM Router (`routers/llm.py`)
**Tag:** `LLM`  
**Prefix:** `/llm`

Handles LLM-related operations:
- Prompt elaboration
- AI-powered text transformations

**Imports models from:** `model` package

## Benefits of Modularization

1. **Separation of Concerns**: Each router handles a specific domain
2. **Maintainability**: Easier to locate and update specific functionality
3. **Scalability**: New endpoints can be added without cluttering the main file
4. **Testing**: Each router can be tested independently
5. **Documentation**: Better organized API documentation by tags
6. **Centralized Models**: All Pydantic models in one place for easy reuse and consistency
7. **No Duplication**: Models are defined once and imported where needed
8. **Type Safety**: Centralized models ensure consistent typing across the API

## Migration Notes

### Old vs New Endpoints

| Old Endpoint | New Endpoint |
|-------------|--------------|
| `/chat` | `/rag/chat` |
| `/data_ingestion` | `/rag/data_ingestion` |
| `/create_collection` | `/rag/create_collection` |
| `/delete_collection` | `/rag/delete_collection` |
| `/conversation_history/{thread_id}` | `/rag/conversation_history/{thread_id}` |
| `/outbound_call` | `/calls/outbound` |
| `/elaborate_prompt` | `/llm/elaborate_prompt` |

### API Compatibility
To maintain backward compatibility, you can optionally add aliases in `api.py` if needed.

## Example Usage

### Chat with RAG
```bash
POST /rag/chat
{
  "query": "What is machine learning?",
  "collection_name": "knowledge_base",
  "top_k": 5,
  "thread_id": "user-123"
}
```

### Initiate Outbound Call
```bash
POST /calls/outbound
{
  "phone_number": "+1234567890",
  "name": "John Doe",
  "dynamic_instruction": "Ask about appointment confirmation",
  "language": "en",
  "emotion": "Calm"
}
```

**Available Parameters:**
- `phone_number` (required): Phone number with country code (e.g., +1234567890)
- `name` (optional): Caller's name for personalization
- `dynamic_instruction` (optional): Custom instructions for the AI agent
- `language` (optional, default: "en"): TTS language (e.g., "en", "es", "fr")
- `emotion` (optional, default: "Calm"): TTS emotion (e.g., "Calm", "Excited", "Serious")

**Response:**
The endpoint waits for the call to complete and returns the transcript automatically. It polls the `transcripts/` folder every 10 seconds (max 5 minutes) for `transcript.json`, then returns and deletes it.

```json
{
  "status": "success",
  "message": "Outbound call completed to +1234567890 for John Doe",
  "details": {
    "phone_number": "+1234567890",
    "original_input": "+1234567890",
    "name": "John Doe",
    "has_dynamic_instruction": true,
    "language": "en",
    "emotion": "Calm",
    "transcript_received": true
  },
  "transcript": {
    // Full transcript data from the call
  }
}
```

### Elaborate Prompt
```bash
POST /llm/elaborate_prompt
{
  "prompt": "Write about AI"
}
```

## Running the Application

```bash
python api.py
```

Or with uvicorn:
```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

## Interactive Documentation

Once the server is running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

The documentation will show endpoints organized by tags (RAG, Calls, LLM).

