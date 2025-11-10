"""
Main FastAPI application
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from RAGService import RAGService
from config.settings import config
from utils.logger import log_info, log_error
from workflow.graph import create_rag_workflow
from llmService.llm import LLMService
from database.mongo import get_mongodb_manager

# Import routers
from routers.rag import router as rag_router, init_rag_router
from routers.calls import router as calls_router
from routers.llm import router as llm_router, init_llm_router
from routers.sms import router as sms_router
from routers.email import router as email_router
from routers.bulk_communication import router as bulk_communication_router

# Initialize FastAPI app
app = FastAPI(
    title="ISLAND AI",
    description="API for Island AI",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Log startup
log_info("Initializing RAG Service API...")

# Initialize MongoDB Manager
try:
    mongodb_manager = get_mongodb_manager(
        mongodb_uri=config.MONGODB_URI,
        database_name="python"
    )
    log_info("MongoDB Manager initialized successfully")
except Exception as e:
    log_error(f"Failed to initialize MongoDB Manager: {str(e)}")
    raise

# Initialize RAG Service with config
try:
    rag_service = RAGService(
        qdrant_url=config.QDRANT_URL,
        qdrant_api_key=config.QDRANT_API_KEY,
        openai_api_key=config.OPENAI_API_KEY
    )
    log_info("RAG Service initialized successfully")
except Exception as e:
    log_error(f"Failed to initialize RAG Service: {str(e)}")
    raise

# Initialize RAG Workflow with LangGraph and MongoDB
try:
    rag_workflow = create_rag_workflow(
        rag_service=rag_service,
        openai_api_key=config.OPENAI_API_KEY,
        mongodb_uri=config.MONGODB_URI
    )
    log_info("RAG Workflow with LangGraph and MongoDB initialized successfully")
except Exception as e:
    log_error(f"Failed to initialize RAG Workflow: {str(e)}")
    raise

# Initialize LLM Service
try:
    llm_service = LLMService()
    log_info("LLM Service initialized successfully")
except Exception as e:
    log_error(f"Failed to initialize LLM Service: {str(e)}")
    raise

# Initialize routers with service instances
init_rag_router(rag_service, rag_workflow, mongodb_manager)
init_llm_router(llm_service)

# Include routers
app.include_router(rag_router)
app.include_router(calls_router)
app.include_router(llm_router)
app.include_router(sms_router)
app.include_router(email_router)
app.include_router(bulk_communication_router)


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "RAG Service API",
        "version": "1.0.0",
        "documentation": "/docs",
        "endpoint_groups": {
            "RAG": {
                "prefix": "/rag",
                "endpoints": [
                    "POST /rag/chat - Chat with RAG system",
                    "POST /rag/data_ingestion - Ingest data from multiple sources",
                    "POST /rag/create_collection - Create a new collection",
                    "POST /rag/delete_collection - Delete a collection",
                    "GET /rag/conversation_history/{thread_id} - Get conversation history"
                ]
            },
            "Calls": {
                "prefix": "/calls",
                "endpoints": [
                    "POST /calls/outbound - Initiate an outbound call",
                    "POST /calls/outbound-with-escalation - Initiate an outbound call with AI agent and supervisor escalation"
                ]
            },
            "LLM": {
                "prefix": "/llm",
                "endpoints": [
                    "POST /llm/elaborate_prompt - Elaborate a prompt"
                ]
            },
            "SMS": {
                "prefix": "/sms",
                "endpoints": [
                    "POST /sms/send - Send SMS via Twilio"
                ]
            },
            "Email": {
                "prefix": "/email",
                "endpoints": [
                    "POST /email/send - Send email via SMTP"
                ]
            },
            "Bulk Communication": {
                "prefix": "/bulk-communication",
                "endpoints": [
                    "POST /bulk-communication/send - Send bulk communications (calls, SMS, email) to contacts"
                ]
            }
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "RAG Service API",
        "services": {
            "rag": "operational",
            "calls": "operational",
            "llm": "operational",
            "sms": "operational",
            "email": "operational",
            "bulk_communication": "operational"
        }
    }


if __name__ == "__main__":
    import uvicorn
    log_info(f"Starting server on {config.API_HOST}:{config.API_PORT}")
    uvicorn.run(app, host=config.API_HOST, port=config.API_PORT)
