"""
Tool Registration API endpoints
Allows dynamic registration and management of tools with structured schemas
"""

import json
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from utils.logger import log_info, log_error, log_warning
from model import (
    RegisterToolRequest,
    RegisterToolResponse,
    DeleteToolRequest,
    DeleteToolResponse
)

router = APIRouter(prefix="/tools", tags=["Tools"])

# Path to tools configuration file
TOOLS_FILE = Path("tools.json")


def load_tools() -> Dict[str, Any]:
    """
    Load tools from tools.json file.
    
    Returns:
        Dictionary of tools indexed by tool_id
    """
    if not TOOLS_FILE.exists():
        log_info("tools.json not found, creating empty tools registry")
        return {}
    
    try:
        with open(TOOLS_FILE, 'r', encoding='utf-8') as f:
            tools = json.load(f)
        log_info(f"Loaded {len(tools)} tools from registry")
        return tools
    except json.JSONDecodeError as e:
        log_error(f"Invalid JSON in tools.json: {str(e)}")
        raise HTTPException(status_code=500, detail="Tools registry is corrupted")
    except Exception as e:
        log_error(f"Error loading tools: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading tools: {str(e)}")


def save_tools(tools: Dict[str, Any]) -> None:
    """
    Save tools to tools.json file.
    
    Args:
        tools: Dictionary of tools to save
    """
    try:
        with open(TOOLS_FILE, 'w', encoding='utf-8') as f:
            json.dump(tools, f, indent=4, ensure_ascii=False)
        log_info(f"Saved {len(tools)} tools to registry")
    except Exception as e:
        log_error(f"Error saving tools: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving tools: {str(e)}")


def create_tool_schema(request: RegisterToolRequest) -> dict:
    """
    Create a structured JSON schema from tool request.
    
    Args:
        request: Tool registration request
        
    Returns:
        Structured tool schema
    """
    # Build properties schema
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
    
    # Create the complete tool schema
    tool_schema = {
        "tool_name": request.tool_name,
        "tool_type": request.tool_type,
        "description": request.description,
        "schema": {
            "type": "object",
            "properties": properties_schema,
            "required": required_fields
        }
    }
    
    return tool_schema


@router.post("/register", response_model=RegisterToolResponse)
async def register_tool(request: RegisterToolRequest):
    """
    Register or update a tool with structured schema.
    
    This endpoint allows you to dynamically register tools (like email, SMS, API calls, etc.)
    with their properties and validation rules. If a tool with the same name and type already
    exists, it will be updated. Otherwise, a new tool will be created.
    
    Args:
        request: RegisterToolRequest containing:
            - tool_name: Name of the tool (e.g., "send_email", "send_sms")
            - tool_type: Type of tool (e.g., "email", "sms", "api_call")
            - description: Description of what the tool does
            - properties: List of tool properties with name, type, description, and required flag
    
    Returns:
        RegisterToolResponse with:
            - status: "success" or "error"
            - message: Description of the operation
            - tool_id: Unique identifier for the tool
            - tool: Complete tool schema
    
    Example Request:
        {
            "tool_name": "send_email",
            "tool_type": "email",
            "description": "Send an email to recipients with optional CC",
            "properties": [
                {
                    "name": "to",
                    "type": "string",
                    "description": "Recipient email address",
                    "required": true,
                    "value": ""
                },
                {
                    "name": "cc",
                    "type": "string",
                    "description": "CC email address",
                    "required": false,
                    "value": ""
                },
                {
                    "name": "subject",
                    "type": "string",
                    "description": "Email subject",
                    "required": true,
                    "value": ""
                },
                {
                    "name": "body",
                    "type": "string",
                    "description": "Email body content. You can write {{name}}, {{email}} to insert values that the AI gathered",
                    "required": true,
                    "value": ""
                }
            ]
        }
    """
    try:
        log_info(f"Registering tool: {request.tool_name} (type: {request.tool_type})")
        
        # Load existing tools
        tools = load_tools()
        
        # Check if tool already exists (by name and type)
        existing_tool_id = None
        for tool_id, tool_data in tools.items():
            if (tool_data.get("tool_name") == request.tool_name and 
                tool_data.get("tool_type") == request.tool_type):
                existing_tool_id = tool_id
                break
        
        # Create tool schema
        tool_schema = create_tool_schema(request)
        
        # Generate or use existing tool_id
        if existing_tool_id:
            tool_id = existing_tool_id
            tools[tool_id] = tool_schema
            operation = "updated"
            log_info(f"Tool '{request.tool_name}' updated with ID: {tool_id}")
        else:
            tool_id = str(uuid.uuid4())
            tools[tool_id] = tool_schema
            operation = "created"
            log_info(f"Tool '{request.tool_name}' created with ID: {tool_id}")
        
        # Save tools to file
        save_tools(tools)
        
        return RegisterToolResponse(
            status="success",
            message=f"Tool '{request.tool_name}' {operation} successfully",
            tool_id=tool_id,
            tool=tool_schema
        )
    
    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error registering tool: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error registering tool: {str(e)}")


@router.post("/delete", response_model=DeleteToolResponse)
async def delete_tool(request: DeleteToolRequest):
    """
    Delete a tool by its tool_id.
    
    Args:
        request: DeleteToolRequest containing:
            - tool_id: Unique identifier of the tool to delete
    
    Returns:
        DeleteToolResponse with:
            - status: "success" or "error"
            - message: Description of the operation
            - tool_id: ID of the deleted tool
    
    Example Request:
        {
            "tool_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        }
    """
    try:
        log_info(f"Deleting tool with ID: {request.tool_id}")
        
        # Load existing tools
        tools = load_tools()
        
        # Check if tool exists
        if request.tool_id not in tools:
            log_warning(f"Tool not found: {request.tool_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Tool with ID '{request.tool_id}' not found"
            )
        
        # Get tool info before deletion
        tool_name = tools[request.tool_id].get("tool_name", "unknown")
        
        # Delete the tool
        del tools[request.tool_id]
        
        # Save updated tools
        save_tools(tools)
        
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
async def list_tools():
    """
    List all registered tools.
    
    Returns:
        Dictionary of all registered tools with their schemas
    
    Response:
        {
            "status": "success",
            "count": 2,
            "tools": {
                "tool-id-1": {
                    "tool_name": "send_email",
                    "tool_type": "email",
                    "description": "Send an email",
                    "schema": {...}
                },
                "tool-id-2": {...}
            }
        }
    """
    try:
        log_info("Listing all registered tools")
        tools = load_tools()
        
        return {
            "status": "success",
            "count": len(tools),
            "tools": tools
        }
    
    except Exception as e:
        log_error(f"Error listing tools: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error listing tools: {str(e)}")


@router.get("/get/{tool_id}")
async def get_tool(tool_id: str):
    """
    Get a specific tool by ID.
    
    Args:
        tool_id: Unique identifier of the tool
    
    Returns:
        Tool schema and details
    
    Response:
        {
            "status": "success",
            "tool_id": "a1b2c3d4...",
            "tool": {
                "tool_name": "send_email",
                "tool_type": "email",
                "description": "Send an email",
                "schema": {...}
            }
        }
    """
    try:
        log_info(f"Getting tool: {tool_id}")
        tools = load_tools()
        
        if tool_id not in tools:
            raise HTTPException(
                status_code=404,
                detail=f"Tool with ID '{tool_id}' not found"
            )
        
        return {
            "status": "success",
            "tool_id": tool_id,
            "tool": tools[tool_id]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error getting tool: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting tool: {str(e)}")

