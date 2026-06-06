"""
CRM Tool Registration Router.
Register CRM tools (search, create, update) directly for users.
Simplified pattern matching 11Labs implementation - no separate assignment table needed.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import os

from utils.logger import log_info, log_error
from model import RegisterToolResponse, DeleteToolResponse
from crm_integration.schemas import (
    RegisterCRMSearchToolRequest,
    RegisterCRMCreateToolRequest,
    RegisterCRMUpdateToolRequest,
)

router = APIRouter(prefix="/crm", tags=["CRM Tools"])

tool_store = None

# CRM Base URL from environment
CRM_BASE_URL = os.getenv("CRM_BASE_URL", "https://crm-virid-seven-35.vercel.app/api").rstrip("/")


def init_crm_router(store):
    """Initialize the router with a ToolStore instance."""
    global tool_store
    tool_store = store


def _create_crm_tool_schema(
    tool_name: str,
    table_id: str,
    description: str,
    schema_data: dict,
) -> dict:
    """Create a structured schema for CRM tool storage."""
    return {
        "tool_name": tool_name,
        "tool_type": "crm",
        "description": description,
        "schema": {
            "type": "object",
            "tableId": table_id,
            "crm_base_url": CRM_BASE_URL,
            **schema_data,
        },
    }


@router.post("/register-search-tool", response_model=RegisterToolResponse)
async def register_crm_search_tool(request: RegisterCRMSearchToolRequest):
    """
    Register CRM search tool for a specific user.
    
    Args:
        request: Contains user_id, table_id, search_schema, optional description
    
    Returns:
        Tool ID and details
    """
    try:
        if tool_store is None:
            raise HTTPException(status_code=500, detail="Tool store is not initialized")

        log_info(f"Registering CRM search tool for user: {request.user_id}")

        search_schema_dicts = [
            {"name": field.name, "description": field.description}
            for field in request.search_schema
        ]

        description = request.tool_description or (
            f"Search CRM records in table {request.table_id}. "
            f"Fields: {', '.join([f.name for f in request.search_schema])}"
        )

        tool_schema = _create_crm_tool_schema(
            tool_name="crm_search_records",
            table_id=request.table_id,
            description=description,
            schema_data={"search_schema": search_schema_dicts},
        )

        tool_id, operation, tool_payload = tool_store.register_tool(
            user_id=request.user_id,
            tool_schema=tool_schema,
        )

        log_info(f"CRM search tool {operation} for user {request.user_id}: {tool_id}")

        return RegisterToolResponse(
            status="success",
            message=f"CRM search tool {operation} successfully",
            tool_id=tool_id,
            user_id=request.user_id,
            tool=tool_payload,
        )

    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error registering CRM search tool: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error registering CRM search tool: {str(e)}"
        )


@router.post("/register-create-tool", response_model=RegisterToolResponse)
async def register_crm_create_tool(request: RegisterCRMCreateToolRequest):
    """
    Register CRM create tool for a specific user.
    
    Args:
        request: Contains user_id, table_id, data_schema, optional description
    
    Returns:
        Tool ID and details
    """
    try:
        if tool_store is None:
            raise HTTPException(status_code=500, detail="Tool store is not initialized")

        log_info(f"Registering CRM create tool for user: {request.user_id}")

        data_schema_dicts = [
            {"name": field.name, "description": field.description}
            for field in request.data_schema
        ]

        field_names = ", ".join([f.name for f in request.data_schema])
        description = request.tool_description or (
            f"Create CRM record in table {request.table_id}. Fields: {field_names}"
        )

        tool_schema = _create_crm_tool_schema(
            tool_name="crm_create_record",
            table_id=request.table_id,
            description=description,
            schema_data={"data_schema": data_schema_dicts},
        )

        tool_id, operation, tool_payload = tool_store.register_tool(
            user_id=request.user_id,
            tool_schema=tool_schema,
        )

        log_info(f"CRM create tool {operation} for user {request.user_id}: {tool_id}")

        return RegisterToolResponse(
            status="success",
            message=f"CRM create tool {operation} successfully",
            tool_id=tool_id,
            user_id=request.user_id,
            tool=tool_payload,
        )

    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error registering CRM create tool: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error registering CRM create tool: {str(e)}"
        )


@router.post("/register-update-tool", response_model=RegisterToolResponse)
async def register_crm_update_tool(request: RegisterCRMUpdateToolRequest):
    """
    Register CRM update tool for a specific user.
    
    Args:
        request: Contains user_id, table_id, lookup_column, update_schema, optional description
    
    Returns:
        Tool ID and details
    """
    try:
        if tool_store is None:
            raise HTTPException(status_code=500, detail="Tool store is not initialized")

        log_info(f"Registering CRM update tool for user: {request.user_id}")

        update_schema_dicts = [
            {"name": field.name, "description": field.description}
            for field in request.update_schema
        ]

        field_names = ", ".join([f.name for f in request.update_schema])
        description = request.tool_description or (
            f"Update CRM record in table {request.table_id} by {request.lookup_column}. "
            f"Fields: {field_names}"
        )

        tool_schema = _create_crm_tool_schema(
            tool_name="crm_update_record",
            table_id=request.table_id,
            description=description,
            schema_data={
                "lookup_column": request.lookup_column,
                "update_schema": update_schema_dicts,
            },
        )

        tool_id, operation, tool_payload = tool_store.register_tool(
            user_id=request.user_id,
            tool_schema=tool_schema,
        )

        log_info(f"CRM update tool {operation} for user {request.user_id}: {tool_id}")

        return RegisterToolResponse(
            status="success",
            message=f"CRM update tool {operation} successfully",
            tool_id=tool_id,
            user_id=request.user_id,
            tool=tool_payload,
        )

    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error registering CRM update tool: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error registering CRM update tool: {str(e)}"
        )


@router.patch("/tools/{tool_id}", response_model=RegisterToolResponse)
async def update_crm_tool(
    tool_id: str,
    table_id: Optional[str] = None,
    tool_description: Optional[str] = None,
):
    """
    Update an existing CRM tool's configuration.
    
    Args:
        tool_id: Tool identifier
        table_id: New table ID (optional)
        tool_description: New description (optional)
    
    Returns:
        Updated tool details
    """
    try:
        if tool_store is None:
            raise HTTPException(status_code=500, detail="Tool store is not initialized")

        log_info(f"Updating CRM tool: {tool_id}")

        existing_tool = tool_store.get_tool(tool_id)
        if not existing_tool:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_id}' not found")

        if table_id:
            existing_tool["schema"]["tableId"] = table_id
        if tool_description:
            existing_tool["description"] = tool_description

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

        log_info(f"CRM tool updated: {tool_id}")

        return RegisterToolResponse(
            status="success",
            message=f"CRM tool updated successfully",
            tool_id=tool_id,
            user_id=existing_tool["user_id"],
            tool=tool_payload,
        )

    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error updating CRM tool: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error updating CRM tool: {str(e)}"
        )


@router.delete("/tools/{tool_id}", response_model=DeleteToolResponse)
async def delete_crm_tool(tool_id: str, user_id: Optional[str] = Query(None)):
    """
    Delete a CRM tool.
    
    Args:
        tool_id: Tool identifier
        user_id: Optional user verification
    
    Returns:
        Deletion confirmation
    """
    try:
        if tool_store is None:
            raise HTTPException(status_code=500, detail="Tool store is not initialized")

        log_info(f"Deleting CRM tool: {tool_id}")

        tool_name = tool_store.delete_tool(tool_id=tool_id, user_id=user_id)
        if not tool_name:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_id}' not found")

        log_info(f"CRM tool deleted: {tool_id}")

        return DeleteToolResponse(
            status="success",
            message=f"CRM tool '{tool_name}' deleted successfully",
            tool_id=tool_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error deleting CRM tool: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error deleting CRM tool: {str(e)}"
        )


@router.get("/tools")
async def get_user_crm_tools(user_id: str = Query(..., description="User ID")):
    """
    Get all CRM tools for a specific user.
    
    Args:
        user_id: User identifier
    
    Returns:
        List of CRM tools with descriptions
    """
    try:
        if tool_store is None:
            raise HTTPException(status_code=500, detail="Tool store is not initialized")

        log_info(f"Getting CRM tools for user: {user_id}")

        all_tools = tool_store.get_tools_by_user_id(user_id)
        
        # Filter only CRM tools
        crm_tools = {
            tool_id: tool_data
            for tool_id, tool_data in all_tools.items()
            if tool_data.get("tool_type") == "crm"
        }

        return {
            "status": "success",
            "user_id": user_id,
            "count": len(crm_tools),
            "tools": crm_tools,
        }

    except Exception as e:
        log_error(f"Error getting CRM tools: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error getting CRM tools: {str(e)}"
        )
