"""
RAG-related API endpoints
"""

import os
import tempfile
import shutil
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
)

router = APIRouter(prefix="/rag", tags=["RAG"])


# Global variables (to be injected)
rag_service = None
rag_workflow = None
mongodb_manager = None


def init_rag_router(service, workflow, mongo_manager):
    """Initialize the router with RAG service, workflow, and MongoDB manager instances."""
    global rag_service, rag_workflow, mongodb_manager
    rag_service = service
    rag_workflow = workflow
    mongodb_manager = mongo_manager


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat endpoint that uses LangGraph workflow with retrieval and generation nodes.
    Supports conversation memory via thread_id.
    Stores chatbot instances and chat history in MongoDB.
    Supports multiple LLM providers (OpenAI, Gemini) with custom API keys.
    NOW SUPPORTS QUERYING FROM MULTIPLE COLLECTIONS!
    
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
        
    Returns:
        ChatResponse with generated answer and retrieved documents
        
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
    """
    try:
        # Get collections list (supports both old and new format)
        collections = request.get_collections()
        log_info(f"Chat request - Query: '{request.query}', Collections: {collections}, Thread: '{request.thread_id}'")
        
        # Validate that at least one collection is specified
        if not collections:
            raise HTTPException(
                status_code=400,
                detail="At least one collection must be specified (collection_name or collection_names)"
            )
        
        # Use thread_id as instance_id (or generate a default one)
        instance_id = request.thread_id if request.thread_id else "default"
        
        # Create or get chatbot instance in MongoDB
        try:
            existing_instance = mongodb_manager.get_chatbot_instance(instance_id)
            if not existing_instance:
                mongodb_manager.create_chatbot_instance(
                    instance_id=instance_id,
                    collection_name=request.collection_name or ",".join(collections),
                    metadata={
                        "top_k": request.top_k,
                        "created_via": "chat_endpoint",
                        "collections": collections
                    }
                )
                log_info(f"Created new chatbot instance: {instance_id}")
            else:
                # Update the instance's last used time
                mongodb_manager.update_chatbot_instance(
                    instance_id=instance_id,
                    update_data={"last_used": "now"}
                )
        except Exception as e:
            log_error(f"Error managing chatbot instance: {str(e)}")
            # Continue even if instance management fails
        
        # Run the RAG workflow (retrieve + generate) with multiple collections support
        log_info(f"Using provider: {request.provider}, Custom API key provided: {bool(request.api_key)}")
        result = rag_workflow.run(
            query=request.query,
            collection_name=request.collection_name,  # For backward compatibility
            collection_names=collections,  # New: multiple collections
            top_k=request.top_k,
            thread_id=request.thread_id,
            system_prompt=request.system_prompt,
            provider=request.provider,
            api_key=request.api_key
        )
        
        log_info(f"Workflow completed - Retrieved {len(result['retrieved_docs'])} documents from {len(collections)} collection(s)")
        
        # Store chat message in MongoDB
        try:
            mongodb_manager.store_chat_message(
                thread_id=result.get("thread_id", "default"),
                instance_id=instance_id,
                query=request.query,
                answer=result["answer"],
                retrieved_docs=result["retrieved_docs"],
                metadata={
                    "collection_name": request.collection_name,
                    "collection_names": collections,
                    "top_k": request.top_k
                }
            )
            log_info(f"Stored chat message in MongoDB for thread: {result.get('thread_id')}")
        except Exception as e:
            log_error(f"Error storing chat message: {str(e)}")
            # Continue even if storage fails
        
        return ChatResponse(
            query=request.query,
            answer=result["answer"],
            retrieved_docs=result["retrieved_docs"],
            context=result.get("context"),
            thread_id=result.get("thread_id")
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
    
    All data is ingested into a single Qdrant collection "main_collection" with 
    "source_collection" metadata set to the collection_name for logical separation.
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
        
        # Use async method for parallel ingestion
        # Note: collection_name here is the logical collection name (stored in metadata)
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
    
    Args:
        request: CreateCollectionRequest containing collection_name
        
    Returns:
        StatusResponse with creation status
    """
    try:
        log_info(f"Create collection request for: '{request.collection_name}'")
        rag_service.create_collection(collection_name=request.collection_name)
        log_info(f"Successfully created collection: '{request.collection_name}'")
        
        return StatusResponse(
            status="success",
            message=f"Collection '{request.collection_name}' created successfully",
            details={"vector_size": 1536, "distance_metric": "cosine"}
        )
    
    except Exception as e:
        log_exception(f"Error creating collection '{request.collection_name}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Create collection error: {str(e)}")


@router.post("/delete_collection", response_model=StatusResponse)
async def delete_collection(request: DeleteCollectionRequest):
    """
    Delete collection endpoint.
    
    Args:
        request: DeleteCollectionRequest containing collection_name
        
    Returns:
        StatusResponse with deletion status
    """
    try:
        log_info(f"Delete collection request for: '{request.collection_name}'")
        rag_service.delete_collection(collection_name=request.collection_name)
        log_info(f"Successfully deleted collection: '{request.collection_name}'")
        
        return StatusResponse(
            status="success",
            message=f"Collection '{request.collection_name}' deleted successfully"
        )
    
    except Exception as e:
        log_exception(f"Error deleting collection '{request.collection_name}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Delete collection error: {str(e)}")


@router.post("/ensure_indexes", response_model=StatusResponse)
async def ensure_indexes(collection_name: str = "main_collection"):
    """
    Ensure all required payload indexes exist on the collection.
    This endpoint is useful for fixing existing collections that were created
    before the multi-collection feature was added.
    
    Creates a keyword index on 'source_collection' field for efficient filtering.
    
    Args:
        collection_name: Name of the collection (default: "main_collection")
        
    Returns:
        StatusResponse with index creation status
        
    Example:
        POST /rag/ensure_indexes?collection_name=main_collection
    """
    try:
        log_info(f"Ensuring payload indexes for collection: '{collection_name}'")
        result = rag_service.ensure_payload_indexes(collection_name)
        log_info(f"Successfully ensured indexes for collection: '{collection_name}'")
        
        return StatusResponse(
            status="success",
            message=result["message"],
            details=result
        )
    
    except Exception as e:
        log_exception(f"Error ensuring indexes for collection '{collection_name}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ensure indexes error: {str(e)}")


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

