"""
RAG-related API endpoints
"""

import os
import tempfile
import shutil
import asyncio
import time
import httpx
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Optional
from utils.logger import log_info, log_error, log_exception
from model import (
    ChatRequest,
    ChatResponse,
    DataIngestionRequest,
    CreateCollectionRequest,
    DeleteCollectionRequest,
    StatusResponse,
    EcommerceCredentials,
    EmailToolCredentials,
)

router = APIRouter(prefix="/rag", tags=["RAG"])


# Global variables (to be injected)
rag_service = None
rag_workflow = None
mongodb_manager = None

# Import ecommerce tools
try:
    from voice_backend.outboundService.services.tool import EcommerceClient
except ImportError:
    # Placeholder for compatibility
    class EcommerceClient:
        def __init__(self, **kwargs): pass
        async def get_products(self, limit=5): return "Ecommerce tools not available"
        async def get_orders(self, limit=5): return "Ecommerce tools not available"

# Import langchain tool decorator
from langchain_core.tools import tool


def init_rag_router(service, workflow, mongo_manager):
    """Initialize the router with RAG service, workflow, and MongoDB manager instances."""
    global rag_service, rag_workflow, mongodb_manager
    rag_service = service
    rag_workflow = workflow
    mongodb_manager = mongo_manager


# OPTIMIZATION: Async helper functions for non-blocking MongoDB operations
async def _manage_chatbot_instance_async(mongodb_manager, instance_id: str, request, collections):
    """Background task to manage chatbot instance - non-blocking"""
    try:
        existing_instance = mongodb_manager.get_chatbot_instance(instance_id)
        if not existing_instance:
            collection_info = request.collection_name or (
                ",".join(collections) if collections else "all"
            )
            mongodb_manager.create_chatbot_instance(
                instance_id=instance_id,
                collection_name=collection_info,
                metadata={
                    "top_k": request.top_k,
                    "created_via": "chat_endpoint",
                    "collections": collections if collections else "all"
                }
            )
            log_info(f"Created new chatbot instance: {instance_id}")
        else:
            mongodb_manager.update_chatbot_instance(
                instance_id=instance_id,
                update_data={"last_used": "now"}
            )
    except Exception as e:
        log_error(f"Error managing chatbot instance (background): {str(e)}")


async def _store_chat_message_async(mongodb_manager, thread_id: str, instance_id: str, 
                                    query: str, answer: str, retrieved_docs: list,
                                    collection_name: str, collections: list, top_k: int):
    """Background task to store chat message - non-blocking"""
    try:
        mongodb_manager.store_chat_message(
            thread_id=thread_id,
            instance_id=instance_id,
            query=query,
            answer=answer,
            retrieved_docs=retrieved_docs,
            metadata={
                "collection_name": collection_name,
                "collection_names": collections,
                "top_k": top_k
            }
        )
        log_info(f"Stored chat message in MongoDB for thread: {thread_id}")
    except Exception as e:
        log_error(f"Error storing chat message (background): {str(e)}")


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat endpoint that uses LangGraph workflow with retrieval and generation nodes.
    Supports conversation memory via thread_id.
    Stores chatbot instances and chat history in MongoDB.
    Supports multiple LLM providers (OpenAI, Gemini) with custom API keys.
    NOW SUPPORTS QUERYING FROM MULTIPLE COLLECTIONS!
    SUPPORTS ECOMMERCE INTEGRATION (WooCommerce, Shopify, etc.)!
    
    Args:
        request: ChatRequest containing:
            - query: User's question
            - collection_name: Single collection name (deprecated, for backward compatibility)
            - collection_names: List of collection names to query from (NEW!)
            - top_k: Number of documents to retrieve (default: 5)
            - thread_id: Thread ID for conversation memory (optional)
            - system_prompt: Custom system prompt (optional)
            - provider: LLM provider ("openai" or "gemini", default: "openai")
            - api_key: Custom API key for the provider (optional, uses default if not provided)
            - ecommerce_credentials: Credentials for ecommerce platform (optional)
        
    Returns:
        ChatResponse with generated answer, retrieved documents, and latency_ms
        
    Examples:
        Single collection (backward compatible):
        {
            "query": "What is machine learning?",
            "collection_name": "knowledge_base",
            "provider": "openai"
        }
        
        Multiple collections (NEW):
        {
            "query": "Compare our products",
            "collection_names": ["finance_docs", "product_docs", "legal_docs"],
            "provider": "openai",
            "top_k": 10
        }
        
        With ecommerce integration (WooCommerce):
        {
            "query": "What products do you have in stock?",
            "provider": "openai",
            "ecommerce_credentials": {
                "platform": "woocommerce",
                "base_url": "https://example.com/wp-json/wc/v3",
                "api_key": "ck_xxxxx",
                "api_secret": "cs_xxxxx"
            }
        }
        
        With email tool for appointment scheduling:
        {
            "query": "Schedule an appointment for John at john@example.com for tomorrow at 3pm",
            "provider": "openai",
            "system_prompt": "You are an appointment scheduling assistant. When a user wants to schedule an appointment, collect the necessary details (name, email, date, time) and send a confirmation email using the send_email tool. Format the email professionally with appointment details.",
            "email_credentials": {
                "x_user_email": "amarc8399@gmail.com",
                "base_url": "https://keplerov1-python-2.onrender.com"
            }
        }
    """
    # Start timing
    start_time = time.time()
    
    try:
        # Get collections list (supports both old and new format)
        collections = request.get_collections()
        
        # Initialize ecommerce client and create tools if credentials are provided
        ecommerce_client = None
        ecommerce_tools = []
        if request.ecommerce_credentials:
            try:
                ecommerce_client = EcommerceClient(
                    platform=request.ecommerce_credentials.platform,
                    base_url=request.ecommerce_credentials.base_url,
                    api_key=request.ecommerce_credentials.api_key,
                    api_secret=request.ecommerce_credentials.api_secret,
                    access_token=request.ecommerce_credentials.access_token
                )
                
                # Create tools using @tool decorator for proper LLM binding
                # Use ThreadPoolExecutor to run async code from sync context
                import concurrent.futures
                
                @tool
                def get_products(limit: int = 5) -> str:
                    """Fetch products from the connected ecommerce store. Use this tool when the user asks about products, items, catalog, what's available, stock, pricing, costs, or product listings. Returns a formatted list of products with names, prices, and availability."""
                    import asyncio
                    
                    def run_async():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            return loop.run_until_complete(ecommerce_client.get_products(min(limit, 20)))
                        finally:
                            loop.close()
                    
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(run_async)
                        return future.result()
                
                @tool
                def get_orders(limit: int = 5) -> str:
                    """Fetch recent orders from the connected ecommerce store. Use this tool when the user asks about orders, purchases, transactions, sales, order history, or order status. Returns a formatted list of orders with order IDs, status, and totals."""
                    import asyncio
                    
                    def run_async():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            return loop.run_until_complete(ecommerce_client.get_orders(min(limit, 20)))
                        finally:
                            loop.close()
                    
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(run_async)
                        return future.result()
                
                ecommerce_tools = [get_products, get_orders]
                log_info(f"✓ Ecommerce tools created with @tool decorator: {request.ecommerce_credentials.platform}")
                log_info(f"  - get_products: {get_products.name}")
                log_info(f"  - get_orders: {get_orders.name}")
            except Exception as e:
                log_error(f"Failed to initialize ecommerce client: {e}")
        
        # Initialize email tool if credentials are provided
        email_tools = []
        if request.email_credentials:
            try:
                email_base_url = request.email_credentials.base_url
                x_user_email = request.email_credentials.x_user_email
                
                @tool
                def send_email(to: str, subject: str, body: str) -> str:
                    """Send an email to a recipient. Use this tool when the user wants to send an email, schedule an appointment confirmation, or communicate via email. 
                    
                    Args:
                        to: The recipient's email address
                        subject: The email subject line
                        body: The email body content
                    
                    Returns:
                        A confirmation message indicating success or failure
                    """
                    import httpx
                    
                    def run_sync():
                        try:
                            with httpx.Client(timeout=30.0) as client:
                                response = client.post(
                                    f"{email_base_url}/email/send",
                                    headers={
                                        "accept": "application/json",
                                        "x-user-email": x_user_email,
                                        "Content-Type": "application/json"
                                    },
                                    json={
                                        "to": to,
                                        "subject": subject,
                                        "body": body
                                    }
                                )
                                if response.status_code == 200:
                                    return f"✓ Email sent successfully to {to}"
                                else:
                                    return f"✗ Failed to send email: {response.text}"
                        except Exception as e:
                            return f"✗ Error sending email: {str(e)}"
                    
                    return run_sync()
                
                email_tools = [send_email]
                log_info(f"✓ Email tool created with @tool decorator")
                log_info(f"  - send_email: {send_email.name}")
                log_info(f"  - x_user_email: {x_user_email}")
            except Exception as e:
                log_error(f"Failed to initialize email tool: {e}")
        
        # Combine all tools
        all_tools = ecommerce_tools + email_tools
        
        # If no collections specified, search ALL documents (set to None for all-search)
        if not collections:
            collections = None
            log_info(f"Chat request - Query: '{request.query}', Collections: ALL (no filter), Thread: '{request.thread_id}', Ecommerce: {bool(ecommerce_client)}")
        else:
            log_info(f"Chat request - Query: '{request.query}', Collections: {collections}, Thread: '{request.thread_id}', Ecommerce: {bool(ecommerce_client)}")
        
        # Use thread_id as instance_id (or generate a default one)
        instance_id = request.thread_id if request.thread_id else "default"
        
        # OPTIMIZATION: MongoDB instance management in background (non-blocking)
        asyncio.create_task(_manage_chatbot_instance_async(mongodb_manager, instance_id, request, collections))
        
        # Run the RAG workflow (retrieve + generate) with multiple collections support
        log_info(f"Using provider: {request.provider}, Custom API key provided: {bool(request.api_key)}, Elaborate: {request.elaborate}, Skip history: {request.skip_history}")
        
        # Add elaboration instruction to system prompt if requested
        enhanced_system_prompt = request.system_prompt or ""
        if request.elaborate:
            elaboration_instruction = "\n\nIMPORTANT: Provide detailed, elaborate responses with comprehensive explanations. Continue elaborating until the user explicitly says 'don't elaborate' or asks for shorter responses."
            enhanced_system_prompt += elaboration_instruction
        
        result = rag_workflow.run(
            query=request.query,
            collection_name=request.collection_name,  # For backward compatibility
            collection_names=collections,  # New: multiple collections
            top_k=request.top_k,
            thread_id=request.thread_id,
            system_prompt=enhanced_system_prompt,
            provider="openai",
            api_key=os.getenv("OPENAI_API_KEY"),
            skip_history=request.skip_history,  # Skip history for faster responses
            ecommerce_tools=all_tools if all_tools else None  # Pass all tools (ecommerce + email) if available
        )
        
        collection_count = len(collections) if collections else "all"
        log_info(f"Workflow completed - Retrieved {len(result['retrieved_docs'])} documents from {collection_count} collection(s)")
        
        # OPTIMIZATION: Store chat message in background (non-blocking)
        asyncio.create_task(_store_chat_message_async(
            mongodb_manager, 
            result.get("thread_id", "default"),
            instance_id,
            request.query,
            result["answer"],
            result["retrieved_docs"],
            request.collection_name,
            collections,
            request.top_k
        ))
        
        # Calculate latency in milliseconds
        latency_ms = (time.time() - start_time) * 1000
        log_info(f"Request completed in {latency_ms:.2f}ms")
        
        return ChatResponse(
            query=request.query,
            answer=result["answer"],
            retrieved_docs=result["retrieved_docs"],
            context=result.get("context"),
            thread_id=result.get("thread_id"),
            latency_ms=latency_ms
        )
    
    except Exception as e:
        log_exception(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")


@router.post("/data_ingestion", response_model=StatusResponse)
async def data_ingestion(
    collection_name: str = Form(...),
    url_links: Optional[str] = Form(None),  # Comma-separated URLs
    pdf_files: Optional[list[UploadFile]] = File(None),
    excel_files: Optional[list[UploadFile]] = File(None)
):
    """
    Data ingestion endpoint that accepts multiple sources simultaneously (URL, PDF, Excel).
    Processes all sources in parallel for faster ingestion.
    
    All data is ingested into FAISS index with collection_name as metadata for logical separation.
    This allows querying from multiple logical collections efficiently.
    
    Args:
        collection_name: Logical collection name to group the data (stored in metadata)
        url_links: Comma-separated URLs for website scraping (optional)
        pdf_files: List of PDF files to upload (optional)
        excel_files: List of Excel files to upload (optional)
        
    Returns:
        StatusResponse with ingestion status and details
    """
    temp_file_paths = []
    
    try:
        log_info(f"Data ingestion request for collection: '{collection_name}'")
        
        # Prepare URL links
        urls = []
        if url_links:
            urls = [url.strip() for url in url_links.split(',') if url.strip()]
            log_info(f"Received {len(urls)} URL(s)")
        
        # Prepare PDF files
        pdf_paths = []
        if pdf_files:
            for pdf_file in pdf_files:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
                    shutil.copyfileobj(pdf_file.file, temp_file)
                    pdf_paths.append(temp_file.name)
                    temp_file_paths.append(temp_file.name)
            log_info(f"Received {len(pdf_paths)} PDF file(s)")
        
        # Prepare Excel files
        excel_paths = []
        if excel_files:
            for excel_file in excel_files:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as temp_file:
                    shutil.copyfileobj(excel_file.file, temp_file)
                    excel_paths.append(temp_file.name)
                    temp_file_paths.append(temp_file.name)
            log_info(f"Received {len(excel_paths)} Excel file(s)")
        
        # Check if at least one source is provided
        if not urls and not pdf_paths and not excel_paths:
            log_error("No data sources provided")
            raise HTTPException(
                status_code=400,
                detail="At least one data source must be provided (url_links, pdf_files, or excel_files)"
            )
        
        # Log parallel ingestion start
        total_sources = len(urls) + len(pdf_paths) + len(excel_paths)
        log_info(f"Starting parallel ingestion of {total_sources} source(s)...")
        
        # Use async method for parallel ingestion (Qdrant-based)
        result = await rag_service.load_data_to_qdrant_async(
            logical_collection_name=collection_name,
            url_links=urls if urls else None,
            pdf_files=pdf_paths if pdf_paths else None,
            excel_files=excel_paths if excel_paths else None
        )
        
        # Clean up temp files
        for temp_path in temp_file_paths:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        
        log_info(f"Successfully ingested {result['total_chunks_loaded']} chunks from {result['sources_processed']} sources")
        
        # Build success message
        message_parts = []
        if urls:
            message_parts.append(f"{len(urls)} URL(s)")
        if pdf_paths:
            message_parts.append(f"{len(pdf_paths)} PDF(s)")
        if excel_paths:
            message_parts.append(f"{len(excel_paths)} Excel file(s)")
        
        message = f"Successfully ingested {', '.join(message_parts)} into collection '{collection_name}'"
        
        return StatusResponse(
            status="success",
            message=message,
            details=result
        )
    
    except HTTPException:
        raise
    except Exception as e:
        # Clean up temp files in case of error
        for temp_path in temp_file_paths:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
        log_exception(f"Error in data ingestion: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Data ingestion error: {str(e)}")


@router.post("/create_collection", response_model=StatusResponse)
async def create_collection(request: CreateCollectionRequest):
    """
    Create collection endpoint.
    
    Note: FAISS doesn't require explicit collection creation. Collections are created 
    automatically when data is ingested. This endpoint is maintained for API compatibility.
    
    Args:
        request: CreateCollectionRequest containing collection_name
        
    Returns:
        StatusResponse with creation status
    """
    try:
        log_info(f"Create collection request for: '{request.collection_name}' (FAISS auto-creates collections)")
        
        # FAISS doesn't need explicit collection creation
        # Collections are created automatically during data ingestion
        log_info(f"Collection '{request.collection_name}' will be created automatically on first data ingestion")
        
        return StatusResponse(
            status="success",
            message=f"Collection '{request.collection_name}' ready (FAISS auto-creates on ingestion)",
            details={
                "note": "FAISS collections are created automatically during data ingestion",
                "storage": "FAISS local vector database"
            }
        )
    
    except Exception as e:
        log_exception(f"Error in create collection endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Create collection error: {str(e)}")


@router.post("/delete_collection", response_model=StatusResponse)
async def delete_collection(request: DeleteCollectionRequest):
    """
    Delete collection endpoint - removes all documents from a specific collection.
    
    Note: FAISS doesn't support efficient deletion, so the index will be rebuilt
    without the specified collection's vectors.
    
    Args:
        request: DeleteCollectionRequest containing collection_name
        
    Returns:
        StatusResponse with deletion status
    """
    try:
        log_info(f"Delete collection request for: '{request.collection_name}'")
        
        # Check if collection exists
        stats = rag_service.get_stats()
        collections = stats.get("collections", {})
        
        if request.collection_name not in collections:
            raise HTTPException(
                status_code=404,
                detail=f"Collection '{request.collection_name}' not found. Available collections: {list(collections.keys())}"
            )
        
        docs_count = collections[request.collection_name]
        
        # Delete the collection
        rag_service.delete_collection(collection_name=request.collection_name)
        log_info(f"Successfully deleted collection: '{request.collection_name}' ({docs_count} documents)")
        
        return StatusResponse(
            status="success",
            message=f"Collection '{request.collection_name}' deleted successfully",
            details={
                "collection_name": request.collection_name,
                "documents_removed": docs_count
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error deleting collection '{request.collection_name}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Delete collection error: {str(e)}")


@router.post("/ensure_indexes", response_model=StatusResponse)
async def ensure_indexes(collection_name: str = "main_collection"):
    """
    Ensure all required payload indexes exist on the collection.
    
    Note: FAISS doesn't use payload indexes like Qdrant. This endpoint is maintained 
    for API compatibility but has no effect with FAISS.
    
    Args:
        collection_name: Name of the collection (ignored for FAISS)
        
    Returns:
        StatusResponse with index status
        
    Example:
        POST /rag/ensure_indexes?collection_name=main_collection
    """
    try:
        log_info(f"Ensure indexes request (not applicable for FAISS)")
        
        return StatusResponse(
            status="success",
            message="FAISS doesn't require payload indexes (maintained for API compatibility)",
            details={
                "note": "FAISS uses flat index structure without payload indexes",
                "storage": "FAISS local vector database"
            }
        )
    
    except Exception as e:
        log_exception(f"Error in ensure indexes endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ensure indexes error: {str(e)}")


@router.get("/collections")
async def list_collections():
    """
    Get list of all collections and their document counts.
    
    Returns:
        Dictionary with collection names and their respective document counts
    
    Example Response:
        {
            "status": "success",
            "total_collections": 3,
            "collections": {
                "langchain": 150,
                "insurance_docs": 75,
                "product_info": 200
            }
        }
    """
    try:
        stats = rag_service.get_stats()
        collections = stats.get("collections", {})
        
        log_info(f"Found {len(collections)} collections")
        
        return {
            "status": "success",
            "total_collections": len(collections),
            "collections": collections
        }
        
    except Exception as e:
        log_exception(f"Error listing collections: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list collections: {str(e)}")


@router.get("/conversation_history/{thread_id}")
async def get_conversation_history(thread_id: str):
    """
    Get conversation history for a specific thread from LangGraph memory.
    
    Args:
        thread_id: Thread ID to retrieve history for
        
    Returns:
        Dictionary with conversation history
    """
    try:
        log_info(f"Retrieving conversation history for thread: '{thread_id}'")
        history = rag_workflow.get_conversation_history(thread_id)
        
        return {
            "thread_id": thread_id,
            "conversation_count": len(history),
            "history": history
        }
    
    except Exception as e:
        log_exception(f"Error retrieving conversation history: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving history: {str(e)}")


@router.get("/chat_history/{thread_id}")
async def get_chat_history_from_mongodb(thread_id: str, limit: int = 50):
    """
    Get chat history for a specific thread from MongoDB.
    
    Args:
        thread_id: Thread ID to retrieve history for
        limit: Maximum number of messages to return (default: 50)
        
    Returns:
        Dictionary with chat history from MongoDB
    """
    try:
        log_info(f"Retrieving chat history from MongoDB for thread: '{thread_id}'")
        messages = mongodb_manager.get_chat_history(thread_id, limit)
        
        return {
            "thread_id": thread_id,
            "message_count": len(messages),
            "messages": messages
        }
    
    except Exception as e:
        log_exception(f"Error retrieving chat history from MongoDB: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving chat history: {str(e)}")


@router.get("/instances")
async def list_instances(active_only: bool = True, limit: int = 100):
    """
    List all chatbot instances from MongoDB.
    
    Args:
        active_only: Filter for active instances only (default: True)
        limit: Maximum number of instances to return (default: 100)
        
    Returns:
        Dictionary with list of instances
    """
    try:
        log_info(f"Listing chatbot instances (active_only={active_only}, limit={limit})")
        instances = mongodb_manager.list_chatbot_instances(active_only, limit)
        
        return {
            "instance_count": len(instances),
            "instances": instances
        }
    
    except Exception as e:
        log_exception(f"Error listing chatbot instances: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error listing instances: {str(e)}")


@router.get("/instances/{instance_id}")
async def get_instance(instance_id: str):
    """
    Get a specific chatbot instance from MongoDB.
    
    Args:
        instance_id: Instance ID to retrieve
        
    Returns:
        Dictionary with instance details
    """
    try:
        log_info(f"Retrieving chatbot instance: '{instance_id}'")
        instance = mongodb_manager.get_chatbot_instance(instance_id)
        
        if not instance:
            raise HTTPException(status_code=404, detail=f"Instance '{instance_id}' not found")
        
        return instance
    
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error retrieving chatbot instance: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving instance: {str(e)}")


@router.get("/instances/{instance_id}/history")
async def get_instance_history(instance_id: str, limit: int = 100):
    """
    Get all chat history for a specific instance from MongoDB.
    
    Args:
        instance_id: Instance ID
        limit: Maximum number of messages to return (default: 100)
        
    Returns:
        Dictionary with instance's chat history
    """
    try:
        log_info(f"Retrieving chat history for instance: '{instance_id}'")
        messages = mongodb_manager.get_chat_history_by_instance(instance_id, limit)
        
        return {
            "instance_id": instance_id,
            "message_count": len(messages),
            "messages": messages
        }
    
    except Exception as e:
        log_exception(f"Error retrieving instance chat history: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving instance history: {str(e)}")


@router.delete("/chat_history/{thread_id}")
async def delete_chat_history(thread_id: str):
    """
    Delete chat history for a specific thread from MongoDB.
    
    Args:
        thread_id: Thread ID to delete history for
        
    Returns:
        Dictionary with deletion status
    """
    try:
        log_info(f"Deleting chat history for thread: '{thread_id}'")
        deleted_count = mongodb_manager.delete_chat_history(thread_id)
        
        return {
            "status": "success",
            "thread_id": thread_id,
            "messages_deleted": deleted_count
        }
    
    except Exception as e:
        log_exception(f"Error deleting chat history: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting chat history: {str(e)}")

