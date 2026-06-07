# Island AI - Enterprise AI Communication Platform

A comprehensive AI-powered communication platform that combines RAG (Retrieval-Augmented Generation), real-time voice AI agents, and multi-channel communication orchestration. Built with FastAPI, LiveKit, OpenAI, and multiple enterprise integrations.

## 🚀 Key Features

### 🤖 AI & RAG
- **Retrieval-Augmented Generation (RAG)**: Intelligent chatbot with context from your knowledge base
- **Multiple Data Sources**: Ingest from PDFs, websites, Excel files simultaneously
- **Vector Search**: Powered by Qdrant with OpenAI embeddings
- **Conversation Memory**: Multi-turn conversations with MongoDB checkpointing
- **LangGraph Workflow**: State-machine architecture for reliable AI conversations

### 📞 Voice AI
- **Real-time Voice AI Agents**: LiveKit-powered voice conversations with STT/TTS
- **Outbound Calls**: Initiate calls with customizable AI agents
- **Inbound Call Handling**: Automatic call routing and agent dispatch
- **Call Escalation**: Smart transfer to human supervisors based on conditions
- **Dynamic Configuration**: Per-call customization of agent behavior
- **Transcript Capture**: Automatic conversation recording and retrieval

### 💬 Multi-Channel Communication
- **Bulk Communications**: Orchestrate calls, SMS, and emails to multiple contacts
- **SMS Integration**: Twilio-powered SMS messaging
- **Email Integration**: SMTP-based email delivery
- **Parallel Processing**: Handle multiple communications simultaneously

### 🎯 Advanced Features
- **Multi-language TTS**: Support for multiple languages via ElevenLabs
- **Custom Voice Selection**: Choose from various voice profiles
- **Escalation Conditions**: AI-driven call transfer logic
- **Custom SIP Trunks**: Flexible telephony routing
- **Comprehensive Logging**: Full audit trail of all operations

## 📋 Table of Contents

- [Installation](#installation)
- [Environment Configuration](#environment-configuration)
- [Quick Start](#quick-start)
- [API Endpoints](#api-endpoints)
  - [RAG Endpoints](#1-rag-endpoints)
  - [Voice Call Endpoints](#2-voice-call-endpoints)
  - [Communication Endpoints](#3-communication-endpoints)
- [Voice AI Setup](#voice-ai-setup)
- [Architecture](#architecture)
- [Usage Examples](#usage-examples)
- [Project Structure](#project-structure)

## 🔧 Installation

### Prerequisites
- Python 3.8+
- OpenAI API key
- Qdrant instance (cloud or local)
- MongoDB instance
- LiveKit server & credentials
- Twilio account (for SMS)
- SMTP server (for email)

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Required Python Packages

```
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
langchain==0.1.0
langchain-openai==0.0.2
langgraph==0.0.20
qdrant-client==1.7.0
openai==1.6.1
pymongo==4.6.0
livekit-agents
livekit-plugins-elevenlabs
livekit-plugins-deepgram
livekit-plugins-openai
twilio
pdfplumber==0.10.3
pandas==2.1.3
beautifulsoup4==4.12.2
python-dotenv==1.0.0
```

## ⚙️ Environment Configuration

Create a `.env` file in the project root:

```env
# ============================================================================
# AI & RAG Configuration
# ============================================================================
OPENAI_API_KEY=sk-your-openai-api-key
QDRANT_URL=https://your-qdrant-instance.cloud.qdrant.io
QDRANT_API_KEY=your-qdrant-api-key
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net

# ============================================================================
# LiveKit Configuration (Voice AI)
# ============================================================================
LIVEKIT_URL=wss://your-livekit-server.livekit.cloud
LIVEKIT_API_KEY=your-livekit-api-key
LIVEKIT_API_SECRET=your-livekit-api-secret

# SIP Configuration for Voice Calls
LIVEKIT_SIP_OUTBOUND_TRUNK=ST_your_trunk_id
LIVEKIT_SUPERVISOR_PHONE_NUMBER=+1234567890

# Voice AI Models
STT_MODEL=nova-2  # Deepgram speech-to-text
LLM_MODEL=gpt-4  # OpenAI model
ELEVENLABS_API_KEY=your-elevenlabs-api-key

# ============================================================================
# Communication Services
# ============================================================================
# Twilio (SMS)
TWILIO_ACCOUNT_SID=your-twilio-account-sid
TWILIO_AUTH_TOKEN=your-twilio-auth-token
TWILIO_PHONE_NUMBER=+1234567890

# SMTP (Email)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password

# ============================================================================
# API Configuration
# ============================================================================
API_HOST=0.0.0.0
API_PORT=8000

# RAG Settings
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
VECTOR_SIZE=1536
DEFAULT_TOP_K=5
```

## 🚀 Quick Start

### 1. Start the API Server

```bash
python api.py
```

The API will be available at `http://localhost:8000`

### 2. Start Voice AI Agent (for voice calls)

```bash
cd voice_backend/outboundService
python entry.py start
```

### 3. Access API Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

## 📡 API Endpoints

### 1. RAG Endpoints

#### Chat with RAG System
Query your knowledge base with conversational memory.

```bash
POST /rag/chat
```

**Request:**
```json
{
  "query": "What is machine learning?",
  "collection_name": "tech_docs",
  "top_k": 5,
  "thread_id": "user-123",
  "system_prompt": "You are a helpful AI assistant."
}
```

**Response:**
```json
{
  "query": "What is machine learning?",
  "answer": "Machine learning is a subset of artificial intelligence...",
  "retrieved_docs": [
    {
      "text": "Machine learning involves...",
      "score": 0.95,
      "chunk_index": 0
    }
  ],
  "context": "Document 1 (Score: 0.950):\nMachine learning...",
  "thread_id": "user-123"
}
```

#### Data Ingestion
Ingest data from multiple sources in parallel.

```bash
POST /rag/data_ingestion
```

**Multi-part Form Data:**
- `collection_name`: Collection name
- `url_links`: Comma-separated URLs
- `pdf_files`: PDF file(s)
- `excel_files`: Excel file(s)

**Example:**
```bash
curl -X POST "http://localhost:8000/rag/data_ingestion" \
  -F "collection_name=my_docs" \
  -F "url_links=https://example.com/page1,https://example.com/page2" \
  -F "pdf_files=@document.pdf" \
  -F "excel_files=@data.xlsx"
```

#### Collection Management

**Create Collection:**
```bash
POST /rag/create_collection
{
  "collection_name": "my_collection"
}
```

**Delete Collection:**
```bash
POST /rag/delete_collection
{
  "collection_name": "my_collection"
}
```

**Get Conversation History:**
```bash
GET /rag/conversation_history/{thread_id}
```

### 2. Voice Call Endpoints

#### Outbound Call
Initiate an AI-powered outbound call.

```bash
POST /calls/outbound
```

**Request:**
```json
{
  "phone_number": "+1234567890",
  "name": "John Doe",
  "dynamic_instruction": "You are a helpful customer service agent for Acme Corp.",
  "language": "en",
  "voice_id": "21m00Tcm4TlvDq8ikWAM",
  "sip_trunk_id": "ST_custom_trunk",
  "transfer_to": "+1987654321",
  "escalation_condition": "Transfer if customer requests supervisor or seems frustrated"
}
```

**Parameters:**
- `phone_number` (required): Phone number with country code
- `name` (optional): Caller's name for personalization
- `dynamic_instruction` (optional): Custom AI agent instructions
- `language` (optional): TTS language (default: "en")
- `voice_id` (optional): ElevenLabs voice ID
- `sip_trunk_id` (optional): Custom SIP trunk
- `transfer_to` (optional): Phone number for escalation
- `escalation_condition` (optional): When to escalate

**Response:**
```json
{
  "status": "success",
  "message": "Outbound call completed to +1234567890 for John Doe",
  "details": {
    "phone_number": "+1234567890",
    "name": "John Doe",
    "language": "en",
    "transcript_received": true
  },
  "transcript": {
    "messages": [
      {
        "role": "assistant",
        "content": "Hello John, how can I help you today?"
      },
      {
        "role": "user",
        "content": "I need help with my account"
      }
    ]
  }
}
```

#### Outbound Call with Escalation
Advanced call with supervisor escalation support.

```bash
POST /calls/outbound-with-escalation
```

Uses the same request format as `/calls/outbound` but enables full escalation workflow with LiveKit room management.

### 3. Communication Endpoints

#### Bulk Communication
Send calls, SMS, and emails to multiple contacts simultaneously.

```bash
POST /bulk-communication/send
```

**Request:**
```json
{
  "contacts": [
    {
      "name": "John Doe",
      "phone": "+1234567890",
      "email": "john@example.com"
    },
    {
      "name": "Jane Smith",
      "phone": "+1987654321",
      "email": "jane@example.com"
    }
  ],
  "communication_types": ["call", "sms", "email"],
  "sms_body": {
    "message": "Hello! This is a reminder about your appointment."
  },
  "email_body": {
    "subject": "Appointment Reminder",
    "body": "Hello,\n\nThis is a reminder about your upcoming appointment.",
    "is_html": false
  },
  "dynamic_instruction": "You are a friendly appointment reminder agent.",
  "language": "en",
  "voice_id": "21m00Tcm4TlvDq8ikWAM",
  "sip_trunk_id": "ST_custom_trunk",
  "transfer_to": "+1555123456",
  "escalation_condition": "Transfer if customer wants to reschedule"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Processed 2 contact(s) successfully",
  "total_contacts": 2,
  "results": [
    {
      "name": "John Doe",
      "phone": "+1234567890",
      "email": "john@example.com",
      "call_status": "success",
      "transcript": { "messages": [...] },
      "sms_status": "success",
      "email_status": "success",
      "created_at": "2024-01-15T10:30:00",
      "ended_at": "2024-01-15T10:32:30",
      "errors": null
    }
  ]
}
```

#### Send SMS

```bash
POST /sms/send
```

**Request:**
```json
{
  "body": "Your verification code is 123456",
  "number": "+1234567890"
}
```

#### Send Email

```bash
POST /email/send
```

**Request:**
```json
{
  "receiver_email": "user@example.com",
  "subject": "Welcome to our service",
  "body": "Thank you for signing up!",
  "is_html": false
}
```

### 4. LLM Endpoints

#### Elaborate Prompt
Enhance and elaborate a simple prompt.

```bash
POST /llm/elaborate_prompt
```

**Request:**
```json
{
  "prompt": "Write about AI"
}
```

## 🎤 Voice AI Setup

### Dynamic Configuration

The voice AI system uses `config.json` for dynamic per-call configuration. This file is automatically updated when you make calls through the API.

**Example config.json:**
```json
{
  "caller_name": "John Doe",
  "agent_instructions": "You are a helpful customer service agent.",
  "tts_language": "en",
  "voice_id": "21m00Tcm4TlvDq8ikWAM",
  "transfer_to": "+1987654321",
  "escalation_condition": "Transfer if customer requests supervisor",
  "last_updated": 1234567890.123
}
```

### Voice Agent Lifecycle

1. **Call Initiated**: API endpoint called with parameters
2. **Config Updated**: `config.json` written with call-specific settings
3. **Agent Spawned**: Voice agent reads config and joins LiveKit room
4. **Conversation**: AI handles conversation with STT/LLM/TTS pipeline
5. **Escalation** (if needed): Agent transfers call based on escalation condition
6. **Transcript Saved**: Conversation saved to `transcripts/transcript.json`
7. **API Response**: Transcript returned to caller

### Available Voices (ElevenLabs)

- `21m00Tcm4TlvDq8ikWAM` - Rachel (default, warm female)
- `AZnzlk1XvdvUeBnXmlld` - Domi (confident female)
- `EXAVITQu4vr4xnSDxMaL` - Bella (friendly female)
- `ErXwobaYiN019PkySvjV` - Antoni (calm male)
- `MF3mGyEYCl7XYWbV9V6O` - Elli (energetic female)
- `TxGEqnHWrfWFTfGW9XjX` - Josh (professional male)

### Supported Languages

- `en` - English
- `es` - Spanish
- `fr` - French
- `de` - German
- `it` - Italian
- `pt` - Portuguese
- `zh` - Chinese
- `ja` - Japanese
- And many more via ElevenLabs

## 🏗️ Architecture

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Server                         │
│                    (Island AI API)                          │
└───────┬─────────────────────────────────────────────────────┘
        │
        ├──────────────────────────────────────────────────────┐
        │                                                       │
        ▼                                                       ▼
┌──────────────────┐                              ┌─────────────────────┐
│   RAG Service    │                              │  Voice AI Service   │
│                  │                              │                     │
│ • Qdrant (Vector)│                              │ • LiveKit (WebRTC)  │
│ • OpenAI (LLM)   │                              │ • Deepgram (STT)    │
│ • LangGraph      │                              │ • OpenAI (LLM)      │
│ • MongoDB (Mem)  │                              │ • ElevenLabs (TTS)  │
└──────────────────┘                              │ • SIP Trunking      │
                                                  └─────────────────────┘
        │                                                       │
        ▼                                                       ▼
┌──────────────────────────────────────────────────────────────┐
│              Multi-Channel Communication                     │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   SMS        │  │   Email      │  │   Voice      │      │
│  │   (Twilio)   │  │   (SMTP)     │  │   (SIP)      │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└──────────────────────────────────────────────────────────────┘
```

### RAG Workflow (LangGraph)

```
┌───────────────────────────────────────────────────────────┐
│                    User Query                             │
└──────────────────────┬────────────────────────────────────┘
                       │
                       ▼
               ┌───────────────┐
               │  Entry Point  │
               └───────┬───────┘
                       │
                       ▼
               ┌───────────────┐
               │ Retrieve Node │ ◄── Query Qdrant Vector DB
               │               │     Get top-k documents
               └───────┬───────┘
                       │
                       ▼
               ┌───────────────┐
               │ Generate Node │ ◄── OpenAI GPT generates answer
               │               │     with retrieved context
               └───────┬───────┘
                       │
                       ▼
           ┌───────────────────────┐
           │ MongoDB Checkpointer  │ ◄── Save conversation state
           │  (Memory Persistence) │     for multi-turn chat
           └───────────────────────┘
                       │
                       ▼
               ┌───────────────┐
               │   Response    │
               └───────────────┘
```

### Voice AI Pipeline

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│   Caller    │────▶│   Deepgram   │────▶│  OpenAI     │────▶│  ElevenLabs  │
│  (Audio In) │     │     (STT)    │     │   (LLM)     │     │    (TTS)     │
└─────────────┘     └──────────────┘     └─────────────┘     └──────┬───────┘
                                                                      │
                                           ┌──────────────────────────┘
                                           │
                                           ▼
                                    ┌─────────────┐
                                    │  Caller     │
                                    │ (Audio Out) │
                                    └─────────────┘

         ┌────────────────────────────────────────────────────────┐
         │         Dynamic Config (config.json)                   │
         │  • Agent Instructions • Voice ID • Language            │
         │  • Transfer Number • Escalation Conditions             │
         └────────────────────────────────────────────────────────┘
```

## 📚 Usage Examples

### Example 1: Simple RAG Chat

```python
import requests

# Ingest data
requests.post("http://localhost:8000/rag/data_ingestion", 
    files={
        "collection_name": (None, "company_docs"),
        "url_links": (None, "https://example.com/about"),
        "pdf_files": open("handbook.pdf", "rb")
    }
)

# Query
response = requests.post("http://localhost:8000/rag/chat", json={
    "query": "What is the company vacation policy?",
    "collection_name": "company_docs",
    "top_k": 3
})

print(response.json()["answer"])
```

### Example 2: Make an AI Voice Call

```python
import requests

response = requests.post("http://localhost:8000/calls/outbound", json={
    "phone_number": "+1234567890",
    "name": "Sarah Johnson",
    "dynamic_instruction": "You are calling to confirm an appointment for tomorrow at 2 PM. Be friendly and professional.",
    "language": "en",
    "voice_id": "21m00Tcm4TlvDq8ikWAM"
})

print(f"Call status: {response.json()['status']}")
print(f"Transcript: {response.json()['transcript']}")
```

### Example 3: Bulk Communication Campaign

```python
import requests

response = requests.post("http://localhost:8000/bulk-communication/send", json={
    "contacts": [
        {"name": "Alice", "phone": "+1111111111", "email": "alice@example.com"},
        {"name": "Bob", "phone": "+2222222222", "email": "bob@example.com"}
    ],
    "communication_types": ["call", "sms", "email"],
    "sms_body": {"message": "Reminder: Your appointment is tomorrow at 2 PM."},
    "email_body": {
        "subject": "Appointment Reminder",
        "body": "Hello! This is a friendly reminder about your appointment.",
        "is_html": False
    },
    "dynamic_instruction": "Confirm the appointment and answer any questions."
})

for result in response.json()["results"]:
    print(f"{result['name']}: Call={result['call_status']}, SMS={result['sms_status']}, Email={result['email_status']}")
```

### Example 4: Call with Escalation

```python
import requests

response = requests.post("http://localhost:8000/calls/outbound", json={
    "phone_number": "+1234567890",
    "name": "Customer",
    "dynamic_instruction": "Handle technical support questions. You can help with basic issues.",
    "transfer_to": "+1999999999",
    "escalation_condition": "Transfer to supervisor if issue is complex or customer requests it",
    "voice_id": "21m00Tcm4TlvDq8ikWAM"
})
```

## 📁 Project Structure

```
Kaplere/
├── api.py                          # Main FastAPI application
├── requirements.txt                # Python dependencies
├── .env                           # Environment variables (create this)
├── config.json                    # Dynamic voice agent config (auto-generated)
│
├── config/                        # Configuration
│   ├── settings.py               # Settings management
│   └── prompt.py                 # RAG system prompts
│
├── model/                         # Pydantic models
│   └── model.py                  # Request/response models
│
├── routers/                       # API route handlers
│   ├── rag.py                    # RAG endpoints
│   ├── calls.py                  # Voice call endpoints
│   ├── sms.py                    # SMS endpoints
│   ├── email.py                  # Email endpoints
│   ├── llm.py                    # LLM endpoints
│   └── bulk_communication.py     # Bulk communication orchestration
│
├── voice_backend/                 # Voice AI services
│   ├── outboundService/
│   │   ├── entry.py              # Outbound agent entry point
│   │   ├── services/
│   │   │   ├── agent_service.py  # Voice AI agent logic
│   │   │   └── call_service.py   # Call initiation service
│   │   └── common/
│   │       ├── update_config.py  # Dynamic config management
│   │       └── utils.py          # Utility functions
│   │
│   └── inboundService/
│       ├── entry.py              # Inbound agent entry point
│       └── services/
│           └── agent_service.py  # Inbound call handling
│
├── workflow/                      # LangGraph workflows
│   └── graph.py                  # RAG workflow definition
│
├── RAGService.py                  # Core RAG service
├── database/
│   └── mongo.py                  # MongoDB connection manager
│
├── EmailService/
│   └── email.py                  # Email service
│
├── SMSService/
│   └── sms.py                    # SMS service
│
├── llmService/
│   └── llm.py                    # LLM service
│
├── utils/
│   └── logger.py                 # Centralized logging
│
├── logs/                         # Application logs (auto-created)
└── transcripts/                  # Call transcripts (auto-created)
```

## 🔐 Security Notes

1. **Never commit `.env` file** - Contains sensitive API keys
2. **Use environment variables** - All credentials should be in `.env`
3. **API Authentication** - Consider adding authentication middleware for production
4. **Rate Limiting** - Implement rate limiting for public endpoints
5. **Input Validation** - All inputs are validated via Pydantic models
6. **CORS Configuration** - Currently set to allow all origins (adjust for production)

## 🐛 Troubleshooting

### Voice Calls Not Working

1. Ensure LiveKit agent is running: `python voice_backend/outboundService/entry.py start`
2. Check LiveKit credentials in `.env`
3. Verify SIP trunk configuration
4. Check `agent_debug.log` for errors

### RAG Not Returning Results

1. Verify Qdrant connection
2. Check if collection exists and has data
3. Ensure OpenAI API key is valid
4. Review `logs/RAGService_*.log`

### MongoDB Connection Issues

1. Verify MongoDB URI format
2. Check network connectivity
3. Ensure database user has correct permissions

## 📊 Monitoring & Logs

### Log Files

- `logs/RAGService_YYYYMMDD.log` - RAG service logs
- `agent_debug.log` - Voice agent logs
- `console_output.log` - General application logs

### Health Check

```bash
curl http://localhost:8000/health
```

Returns operational status of all services.

## 🚀 Production Deployment

### Recommendations

1. **Use Docker** - Containerize the application
2. **Environment Variables** - Use secrets management (AWS Secrets Manager, etc.)
3. **Load Balancing** - Use nginx or cloud load balancer
4. **Database** - Use managed services (MongoDB Atlas, etc.)
5. **Monitoring** - Implement Prometheus/Grafana
6. **Logging** - Use ELK stack or cloud logging
7. **CI/CD** - Automate deployment with GitHub Actions

### Docker Example

```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "api.py"]
```

## 📝 License

MIT License

Copyright (c) 2024 Amar Choudhary

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

See [LICENSE](LICENSE) file for full details.

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📞 Support

For questions or issues:
- Check the logs in `logs/` directory
- Review API documentation at `/docs`
- Open an issue on GitHub

## 🎯 Roadmap

- [ ] WebSocket support for real-time updates
- [ ] Support for additional TTS providers
- [ ] Video call support
- [ ] Advanced analytics dashboard
- [ ] Multi-tenant support
- [ ] API authentication & authorization
- [ ] Webhook integrations
- [ ] Call recording storage (S3/Cloud)

---

## 👨‍💻 Author

**Amar Choudhary**

---

**Built with ❤️ using FastAPI, LiveKit, OpenAI, and modern AI technologies**
