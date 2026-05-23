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
from routers.tools import router as tools_router
from routers.integration import router as integration_router

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
app.include_router(tools_router)
app.include_router(integration_router)


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
                    "POST /calls/outbound-with-escalation - Initiate an outbound call with AI agent and supervisor escalation",
                    "POST /calls/setup-sip-trunk - Create and configure Twilio and LiveKit SIP trunks",
                    "POST /calls/create-livekit-trunk - Create LiveKit trunk from existing Twilio SIP address",
                    "POST /calls/create-inbound-trunk - Create inbound SIP trunk for receiving calls",
                    "POST /calls/create-dispatch-rule - Create dispatch rule to route incoming calls",
                    "POST /calls/setup-inbound-sip - Complete inbound SIP setup (trunk + dispatch rule)"
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
                    "GET /email/authorize - Start Gmail OAuth authorization",
                    "GET /email/oauth2callback - OAuth callback (automatic)",
                    "POST /email/send - Send email via Gmail API (requires X-User-Email header)",
                    "DELETE /email/logout - Remove stored Gmail credentials",
                    "GET /email/connected-users - List connected Gmail accounts"
                ]
            },
            "Bulk Communication": {
                "prefix": "/bulk-communication",
                "endpoints": [
                    "POST /bulk-communication/send - Send bulk communications (calls, SMS, email) to contacts"
                ]
            },
            "Tools": {
                "prefix": "/tools",
                "endpoints": [
                    "POST /tools/register - Register or update a tool with structured schema",
                    "POST /tools/delete - Delete a tool by tool_id",
                    "GET /tools/list - List all registered tools",
                    "GET /tools/get/{tool_id} - Get a specific tool by ID"
                ]
            },
            "Integration": {
                "prefix": "/integration",
                "description": "Third-party integrations for e-commerce, booking, and automation",
                "categories": {
                    "Setup": "POST /integration/setup/{platform} - Initialize integrations",
                    "Shopify": [
                        "GET /integration/shopify/products - Get all products",
                        "GET /integration/shopify/products/{id} - Get product",
                        "PUT /integration/shopify/products/{id} - Update product",
                        "GET /integration/shopify/orders - Get all orders",
                        "GET /integration/shopify/orders/{id} - Get order",
                        "GET /integration/shopify/test-connection - Test connection"
                    ],
                    "WooCommerce": [
                        "GET /integration/woocommerce/products - Get all products",
                        "GET /integration/woocommerce/products/{id} - Get product",
                        "PUT /integration/woocommerce/products/{id} - Update product",
                        "GET /integration/woocommerce/orders - Get all orders",
                        "GET /integration/woocommerce/orders/{id} - Get order",
                        "GET /integration/woocommerce/test-connection - Test connection"
                    ],
                    "Magento2": [
                        "GET /integration/magento2/products - Get all products",
                        "GET /integration/magento2/products/{sku} - Get product by SKU",
                        "PUT /integration/magento2/products/{sku} - Update product",
                        "GET /integration/magento2/orders - Get all orders",
                        "GET /integration/magento2/orders/{id} - Get order",
                        "GET /integration/magento2/test-connection - Test connection"
                    ],
                    "PrestaShop": [
                        "GET /integration/prestashop/products - Get all products",
                        "GET /integration/prestashop/products/{id} - Get product",
                        "GET /integration/prestashop/orders - Get all orders",
                        "GET /integration/prestashop/orders/{id} - Get order",
                        "GET /integration/prestashop/test-connection - Test connection"
                    ],
                    "Qapla": [
                        "GET /integration/qapla/products - Get all products",
                        "GET /integration/qapla/products/{id} - Get product",
                        "GET /integration/qapla/orders - Get all orders",
                        "GET /integration/qapla/orders/{id} - Get order",
                        "GET /integration/qapla/test-connection - Test connection"
                    ],
                    "Vertical Booking": [
                        "POST /integration/vertical-booking/generate-link - Generate booking link",
                        "GET /integration/vertical-booking/test-connection - Test connection"
                    ],
                    "Booking Expert": [
                        "POST /integration/booking-expert/generate-link - Generate booking link",
                        "GET /integration/booking-expert/test-connection - Test connection"
                    ],
                    "MCP Microservice": [
                        "POST /integration/mcp/request - Make HTTP request",
                        "POST /integration/mcp/set-header - Set/update header",
                        "DELETE /integration/mcp/remove-header/{key} - Remove header"
                    ],
                    "Google Sheets": [
                        "POST /integration/google-sheets/append-row - Append single row",
                        "POST /integration/google-sheets/append-rows - Append multiple rows",
                        "POST /integration/google-sheets/update-cell - Update cell",
                        "GET /integration/google-sheets/get-all-records - Get all records"
                    ],
                    "Registry": [
                        "GET /integration/registry/list-all - List all integrations",
                        "GET /integration/registry/by-category/{category} - Filter by category",
                        "GET /integration/registry/by-tag/{tag} - Filter by tag",
                        "GET /integration/registry/search?query= - Search integrations"
                    ],
                    "Management": [
                        "GET /integration/status/initialized - List initialized integrations",
                        "GET /integration/status/test-connections - Test all connections",
                        "DELETE /integration/remove/{name} - Remove integration",
                        "DELETE /integration/remove-all - Remove all integrations"
                    ]
                }
            }
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Island AI API",
        "services": {
            "rag": "operational",
            "calls": "operational",
            "llm": "operational",
            "sms": "operational",
            "email": "operational",
            "bulk_communication": "operational",
            "tools": "operational",
            "integration": "operational"
        }
    }


if __name__ == "__main__":
    import uvicorn
    log_info(f"Starting server on {config.API_HOST}:{config.API_PORT}")
    uvicorn.run(app, host=config.API_HOST, port=config.API_PORT)
