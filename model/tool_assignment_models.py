"""
Pydantic models for tool assignment API requests and responses.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AssignToolRequest(BaseModel):
    """Request to assign a tool to a user."""
    
    user_id: str = Field(..., description="User identifier")
    tool_id: str = Field(..., description="Tool identifier from global registry")
    user_config: Optional[Dict[str, Any]] = Field(
        None,
        description="User-specific tool configuration (e.g., CRM table_id, search_schema)",
    )
    enabled: bool = Field(True, description="Whether the tool is enabled")
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Additional metadata (assigned_by, notes, etc.)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_123",
                "tool_id": "crm_search_v1",
                "user_config": {
                    "tableId": "6a1b28acde2598f108c0471e",
                    "search_schema": [
                        {"name": "email_address", "description": "Customer email"},
                        {"name": "phone_number", "description": "Customer phone"},
                    ],
                    "crm_base_url": "https://crm-virid-seven-35.vercel.app/api",
                },
                "enabled": True,
                "metadata": {"assigned_by": "admin", "tier": "premium"},
            }
        }


class UpdateAssignmentRequest(BaseModel):
    """Request to update an existing tool assignment."""
    
    enabled: Optional[bool] = Field(None, description="New enabled status")
    user_config: Optional[Dict[str, Any]] = Field(
        None, description="New user configuration"
    )
    metadata: Optional[Dict[str, Any]] = Field(None, description="New metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "enabled": False,
                "user_config": {"tableId": "new_table_id"},
            }
        }


class AssignToolResponse(BaseModel):
    """Response for tool assignment operations."""
    
    status: str = Field(..., description="Operation status (success/error)")
    message: str = Field(..., description="Human-readable message")
    assignment_id: Optional[str] = Field(None, description="Assignment identifier")
    operation: Optional[str] = Field(None, description="Operation performed (created/updated)")
    assignment: Optional[Dict[str, Any]] = Field(None, description="Assignment details")


class DeleteAssignmentRequest(BaseModel):
    """Request to delete a tool assignment."""
    
    assignment_id: str = Field(..., description="Assignment identifier")
    user_id: Optional[str] = Field(
        None, description="Optional user_id for verification"
    )


class DeleteAssignmentResponse(BaseModel):
    """Response for assignment deletion."""
    
    status: str = Field(..., description="Operation status")
    message: str = Field(..., description="Human-readable message")
    assignment_id: str = Field(..., description="Deleted assignment ID")
    tool_id: Optional[str] = Field(None, description="Tool ID that was unassigned")


class BulkEnableToolsRequest(BaseModel):
    """Request to enable/disable multiple tools for a user."""
    
    user_id: str = Field(..., description="User identifier")
    tool_ids: List[str] = Field(..., description="List of tool IDs to enable/disable")
    enabled: bool = Field(True, description="Enable or disable the tools")

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_123",
                "tool_ids": ["crm_search_v1", "crm_create_v1", "crm_update_v1"],
                "enabled": True,
            }
        }


class BulkEnableToolsResponse(BaseModel):
    """Response for bulk enable/disable operation."""
    
    status: str = Field(..., description="Operation status")
    message: str = Field(..., description="Human-readable message")
    updated_count: int = Field(..., description="Number of assignments updated")
