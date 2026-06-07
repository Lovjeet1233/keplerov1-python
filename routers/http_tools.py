"""
HTTP Tool Registration Router for Kepler v1 (Chatbot).
Register custom HTTP request tools for users.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from utils.logger import log_info, log_error
from model import RegisterToolResponse, DeleteToolResponse
from http_integration.schemas import (
    RegisterHTTPToolRequest,
    UpdateHTTPToolRequest,
)

router = APIRouter(prefix="/http-tools", tags=["HTTP Tool Registration"])

tool_store = None


def init_http_tools_router(store):
    """Initialize the router with a ToolStore instance."""
    global tool_store
    tool_store = store


def _create_http_tool_schema(
    tool_name: str,
    tool_description: str,
    method: str,
    url: str,
    parameters: list,
    headers: dict,
) -> dict:
    """Create a structured schema for HTTP tool storage."""
    return {
        "tool_name": tool_name,
        "tool_type": "http",
        "description": tool_description,
        "schema": {
            "type": "object",
            "method": method.upper(),
            "url": url,
            "parameters": parameters,
            "headers": headers or {},
        },
    }


@router.post("/register", response_model=RegisterToolResponse)
async def register_http_tool(request: RegisterHTTPToolRequest):
    """
    Register a custom HTTP tool for a user.
    
    This allows users to create dynamic HTTP request tools that can be used
    in their chatbot conversations.
    
    Args:
        request: RegisterHTTPToolRequest containing:
            - user_id: User identifier
            - tool_name: Name of the tool
            - tool_description: What the tool does
            - method: HTTP method (GET, POST, PUT, PATCH, DELETE)
            - url: API endpoint URL
            - parameters: List of parameters the tool accepts
            - headers: Optional HTTP headers
    
    Returns:
        RegisterToolResponse with tool_id and details
    """
    try:
        if tool_store is None:
            raise HTTPException(status_code=500, detail="Tool store is not initialized")

        log_info(f"Registering HTTP tool '{request.tool_name}' for user: {request.user_id}")

        # Convert parameters to dict format
        parameters_dicts = [
            {
                "name": param.name,
                "description": param.description,
                "type": param.type,
                "required": param.required,
                "default": param.default,
            }
            for param in request.parameters
        ]

        tool_schema = _create_http_tool_schema(
            tool_name=request.tool_name,
            tool_description=request.tool_description,
            method=request.method,
            url=request.url,
            parameters=parameters_dicts,
            headers=request.headers,
        )

        tool_id, operation, tool_payload = tool_store.register_tool(
            user_id=request.user_id,
            tool_schema=tool_schema,
        )

        log_info(f"HTTP tool {operation} for user {request.user_id}: {tool_id}")

        return RegisterToolResponse(
            status="success",
            message=f"HTTP tool '{request.tool_name}' {operation} successfully",
            tool_id=tool_id,
            user_id=request.user_id,
            tool=tool_payload,
        )

    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error registering HTTP tool: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error registering HTTP tool: {str(e)}"
        )


@router.patch("/tools/{tool_id}", response_model=RegisterToolResponse)
async def update_http_tool(tool_id: str, request: UpdateHTTPToolRequest):
    """
    Update an existing HTTP tool's configuration.
    
    Args:
        tool_id: Tool identifier
        request: UpdateHTTPToolRequest with fields to update
    
    Returns:
        Updated tool details
    """
    try:
        if tool_store is None:
            raise HTTPException(status_code=500, detail="Tool store is not initialized")

        log_info(f"Updating HTTP tool: {tool_id}")

        existing_tool = tool_store.get_tool(tool_id)
        if not existing_tool:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_id}' not found")

        # Update fields if provided
        if request.tool_description:
            existing_tool["description"] = request.tool_description
        if request.method:
            existing_tool["schema"]["method"] = request.method.upper()
        if request.url:
            existing_tool["schema"]["url"] = request.url
        if request.parameters is not None:
            existing_tool["schema"]["parameters"] = [
                {
                    "name": param.name,
                    "description": param.description,
                    "type": param.type,
                    "required": param.required,
                    "default": param.default,
                }
                for param in request.parameters
            ]
        if request.headers is not None:
            existing_tool["schema"]["headers"] = request.headers

        tool_schema = {
            "tool_name": existing_tool["tool_name"],
            "tool_type": existing_tool["tool_type"],
            "description": existing_tool["description"],
            "schema": existing_tool["schema"],
        }

        _, operation, tool_payload = tool_store.register_tool(
            user_id=existing_tool["user_id"],
            tool_schema=tool_schema,
        )

        log_info(f"HTTP tool updated: {tool_id}")

        return RegisterToolResponse(
            status="success",
            message=f"HTTP tool updated successfully",
            tool_id=tool_id,
            user_id=existing_tool["user_id"],
            tool=tool_payload,
        )

    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error updating HTTP tool: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error updating HTTP tool: {str(e)}"
        )


@router.delete("/tools/{tool_id}", response_model=DeleteToolResponse)
async def delete_http_tool(tool_id: str, user_id: Optional[str] = Query(None)):
    """
    Delete an HTTP tool.
    
    Args:
        tool_id: Tool identifier
        user_id: Optional user verification
    
    Returns:
        Deletion confirmation
    """
    try:
        if tool_store is None:
            raise HTTPException(status_code=500, detail="Tool store is not initialized")

        log_info(f"Deleting HTTP tool: {tool_id}")

        tool_name = tool_store.delete_tool(tool_id=tool_id, user_id=user_id)
        if not tool_name:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_id}' not found")

        log_info(f"HTTP tool deleted: {tool_id}")

        return DeleteToolResponse(
            status="success",
            message=f"HTTP tool '{tool_name}' deleted successfully",
            tool_id=tool_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error deleting HTTP tool: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error deleting HTTP tool: {str(e)}"
        )


@router.get("/tools")
async def get_user_http_tools(user_id: str = Query(..., description="User ID")):
    """
    Get all HTTP tools for a specific user.
    
    Args:
        user_id: User identifier
    
    Returns:
        List of HTTP tools with descriptions
    """
    try:
        if tool_store is None:
            raise HTTPException(status_code=500, detail="Tool store is not initialized")

        log_info(f"Getting HTTP tools for user: {user_id}")

        all_tools = tool_store.get_tools_by_user_id(user_id)
        
        # Filter only HTTP tools
        http_tools = {
            tool_id: tool_data
            for tool_id, tool_data in all_tools.items()
            if tool_data.get("tool_type") == "http"
        }

        return {
            "status": "success",
            "user_id": user_id,
            "count": len(http_tools),
            "tools": http_tools,
        }

    except Exception as e:
        log_error(f"Error getting HTTP tools: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error getting HTTP tools: {str(e)}"
        )
