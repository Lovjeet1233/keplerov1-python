"""
Tool Registration API endpoints
Allows dynamic registration and management of tools with structured schemas
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from utils.logger import log_info, log_error, log_warning
from model import (
    RegisterToolRequest,
    RegisterToolResponse,
    DeleteToolRequest,
    DeleteToolResponse
)

router = APIRouter(prefix="/tools", tags=["Tools"])

tool_store = None


def init_tools_router(store):
    """Initialize the router with a ToolStore instance."""
    global tool_store
    tool_store = store


def create_tool_schema(request: RegisterToolRequest) -> dict:
    """
    Create a structured JSON schema from tool request.
    
    Args:
        request: Tool registration request
        
    Returns:
        Structured tool schema
    """
    properties_schema = {}
    required_fields = []
    
    for prop in request.properties:
        properties_schema[prop.name] = {
            "type": prop.type,
            "description": prop.description or f"{prop.name} field",
            "value": prop.value if prop.value is not None else ""
        }
        if prop.required:
            required_fields.append(prop.name)
    
    return {
        "tool_name": request.tool_name,
        "tool_type": request.tool_type,
        "description": request.description,
        "schema": {
            "type": "object",
            "properties": properties_schema,
            "required": required_fields
        }
    }


@router.post("/register", response_model=RegisterToolResponse)
async def register_tool(request: RegisterToolRequest):
    """
    Register or update a tool with structured schema for a specific user.

    Tools are stored as separate MongoDB documents in the `integration-chatbot`
    collection, scoped by `user_id`.

    Args:
        request: RegisterToolRequest containing:
            - user_id: Owner of the tool template
            - tool_name: Name of the tool (e.g., "confirm_appointment")
            - tool_type: Type of tool (e.g., "email", "sms", "api_call")
            - description: Description of what the tool does
            - properties: List of tool properties with name, type, description, and required flag

    Returns:
        RegisterToolResponse with status, message, tool_id, user_id, and tool schema
    """
    try:
        if tool_store is None:
            raise HTTPException(status_code=500, detail="Tool store is not initialized")

        log_info(
            f"Registering tool: {request.tool_name} "
            f"(type: {request.tool_type}, user: {request.user_id})"
        )

        tool_schema = create_tool_schema(request)
        tool_id, operation, tool_payload = tool_store.register_tool(
            user_id=request.user_id,
            tool_schema=tool_schema,
        )

        return RegisterToolResponse(
            status="success",
            message=f"Tool '{request.tool_name}' {operation} successfully",
            tool_id=tool_id,
            user_id=request.user_id,
            tool=tool_payload,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error registering tool: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error registering tool: {str(e)}")


@router.post("/delete", response_model=DeleteToolResponse)
async def delete_tool(request: DeleteToolRequest):
    """Delete a tool by its tool_id."""
    try:
        if tool_store is None:
            raise HTTPException(status_code=500, detail="Tool store is not initialized")

        log_info(f"Deleting tool with ID: {request.tool_id}")

        tool_name = tool_store.delete_tool(
            tool_id=request.tool_id,
            user_id=request.user_id,
        )
        if not tool_name:
            log_warning(f"Tool not found: {request.tool_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Tool with ID '{request.tool_id}' not found"
            )

        log_info(f"Tool '{tool_name}' (ID: {request.tool_id}) deleted successfully")

        return DeleteToolResponse(
            status="success",
            message=f"Tool '{tool_name}' deleted successfully",
            tool_id=request.tool_id
        )
    
    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error deleting tool: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting tool: {str(e)}")


@router.get("/list")
async def list_tools(user_id: Optional[str] = Query(None)):
    """List registered tools, optionally filtered by user_id."""
    try:
        if tool_store is None:
            raise HTTPException(status_code=500, detail="Tool store is not initialized")

        log_info(f"Listing tools for user_id={user_id or 'ALL'}")
        tools = tool_store.list_tools(user_id=user_id)

        return {
            "status": "success",
            "count": len(tools),
            "user_id": user_id,
            "tools": tools
        }
    
    except Exception as e:
        log_error(f"Error listing tools: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error listing tools: {str(e)}")


@router.get("/get/{tool_id}")
async def get_tool(tool_id: str, user_id: Optional[str] = Query(None)):
    """Get a specific tool by ID, optionally scoped to user_id."""
    try:
        if tool_store is None:
            raise HTTPException(status_code=500, detail="Tool store is not initialized")

        log_info(f"Getting tool: {tool_id} (user_id={user_id})")
        tool = tool_store.get_tool(tool_id=tool_id, user_id=user_id)
        if not tool:
            raise HTTPException(
                status_code=404,
                detail=f"Tool with ID '{tool_id}' not found"
            )

        return {
            "status": "success",
            "tool_id": tool_id,
            "tool": tool
        }
    
    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error getting tool: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting tool: {str(e)}")
