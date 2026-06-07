"""
Pydantic schemas for HTTP tool registration.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class HTTPToolParameter(BaseModel):
    """Schema for a single HTTP tool parameter."""
    
    name: str = Field(..., description="Parameter name")
    description: str = Field(..., description="Parameter description")
    type: str = Field(
        default="string",
        description="Parameter type (string, integer, boolean, number, array, object)"
    )
    required: bool = Field(default=True, description="Whether parameter is required")
    default: Optional[Any] = Field(None, description="Default value for parameter")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "api_key",
                "description": "API key for authentication",
                "type": "string",
                "required": True
            }
        }


class RegisterHTTPToolRequest(BaseModel):
    """Request to register an HTTP tool for a user."""
    
    user_id: str = Field(..., description="User ID to register this tool for")
    tool_name: str = Field(..., description="Name of the tool (e.g., 'fetch_weather')")
    tool_description: str = Field(..., description="Description of what the tool does")
    method: str = Field(
        ...,
        description="HTTP method (GET, POST, PUT, PATCH, DELETE)"
    )
    url: str = Field(..., description="API endpoint URL")
    parameters: List[HTTPToolParameter] = Field(
        default=[],
        description="List of parameters the tool accepts"
    )
    headers: Optional[Dict[str, str]] = Field(
        default={},
        description="Optional HTTP headers to include"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_123",
                "tool_name": "fetch_weather",
                "tool_description": "Fetch current weather for a city",
                "method": "GET",
                "url": "https://api.weather.com/v1/current",
                "parameters": [
                    {
                        "name": "city",
                        "description": "City name to get weather for",
                        "type": "string",
                        "required": True
                    },
                    {
                        "name": "units",
                        "description": "Temperature units (metric or imperial)",
                        "type": "string",
                        "required": False,
                        "default": "metric"
                    }
                ],
                "headers": {
                    "Authorization": "Bearer YOUR_API_KEY"
                }
            }
        }


class UpdateHTTPToolRequest(BaseModel):
    """Request to update an existing HTTP tool."""
    
    tool_description: Optional[str] = Field(None, description="Updated description")
    method: Optional[str] = Field(None, description="Updated HTTP method")
    url: Optional[str] = Field(None, description="Updated URL")
    parameters: Optional[List[HTTPToolParameter]] = Field(None, description="Updated parameters")
    headers: Optional[Dict[str, str]] = Field(None, description="Updated headers")
    
    class Config:
        json_schema_extra = {
            "example": {
                "tool_description": "Fetch current weather and forecast",
                "url": "https://api.weather.com/v2/current"
            }
        }
