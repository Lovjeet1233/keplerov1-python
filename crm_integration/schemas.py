"""
CRM-specific Pydantic schemas for tool registration and configuration.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class CRMFieldSchema(BaseModel):
    """Schema for a single CRM field."""
    
    name: str = Field(..., description="CRM column name (e.g., full_name, email_address)")
    description: str = Field(
        ...,
        description="Description of what this field represents",
    )


class RegisterCRMSearchToolRequest(BaseModel):
    """Request to register a CRM search tool for a user."""
    
    user_id: str = Field(..., description="User ID to register this tool for")
    table_id: str = Field(..., description="CRM table ID")
    search_schema: List[CRMFieldSchema] = Field(
        ...,
        min_length=1,
        description="Fields that can be used to search records",
    )
    tool_description: Optional[str] = Field(
        None, description="Optional custom description for the tool"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_123",
                "table_id": "6a1b28acde2598f108c0471e",
                "search_schema": [
                    {"name": "email_address", "description": "Customer email to search by"},
                    {"name": "phone_number", "description": "Customer phone to search by"},
                ],
                "tool_description": "Search customer records in CRM",
            }
        }


class RegisterCRMCreateToolRequest(BaseModel):
    """Request to register a CRM create tool for a user."""
    
    user_id: str = Field(..., description="User ID to register this tool for")
    table_id: str = Field(..., description="CRM table ID")
    data_schema: List[CRMFieldSchema] = Field(
        ...,
        min_length=1,
        description="Fields required to create a new record",
    )
    tool_description: Optional[str] = Field(
        None, description="Optional custom description for the tool"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_123",
                "table_id": "6a1b28acde2598f108c0471e",
                "data_schema": [
                    {"name": "full_name", "description": "Customer full name"},
                    {"name": "phone_number", "description": "Customer phone number"},
                    {"name": "email_address", "description": "Customer email address"},
                    {"name": "appointment_date", "description": "Appointment date (YYYY-MM-DD)"},
                ],
                "tool_description": "Create new customer record in CRM",
            }
        }


class RegisterCRMUpdateToolRequest(BaseModel):
    """Request to register a CRM update tool for a user."""
    
    user_id: str = Field(..., description="User ID to register this tool for")
    table_id: str = Field(..., description="CRM table ID")
    lookup_column: str = Field(
        ...,
        description="Column used to find the record to update (e.g., email_address)",
    )
    update_schema: List[CRMFieldSchema] = Field(
        ...,
        min_length=1,
        description="Fields that can be updated",
    )
    tool_description: Optional[str] = Field(
        None, description="Optional custom description for the tool"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_123",
                "table_id": "6a1b28acde2598f108c0471e",
                "lookup_column": "email_address",
                "update_schema": [
                    {"name": "appointment_date", "description": "New appointment date"},
                    {"name": "phone_number", "description": "Updated phone number"},
                ],
                "tool_description": "Update customer record in CRM",
            }
        }
