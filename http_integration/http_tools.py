"""
LangChain tool builder for HTTP requests.
Creates StructuredTool instances for dynamic HTTP operations.
"""

from typing import Any, Dict, List, Optional
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model

from .http_client import HTTPToolClient
from utils.logger import log_info


def build_http_tool(
    tool_name: str,
    tool_description: str,
    method: str,
    url: str,
    parameters: List[Dict[str, Any]],
    headers: Optional[Dict[str, str]] = None,
) -> StructuredTool:
    """
    Build a LangChain tool for HTTP requests.
    
    Args:
        tool_name: Name of the tool
        tool_description: Description of what the tool does
        method: HTTP method (GET, POST, PUT, PATCH, DELETE)
        url: API endpoint URL
        parameters: List of parameter definitions
        headers: Optional HTTP headers
    
    Returns:
        StructuredTool instance
    """
    
    # Create HTTP client
    client = HTTPToolClient(headers=headers)
    
    # Build Pydantic model for arguments dynamically
    fields = {}
    for param in parameters:
        param_name = param["name"]
        param_desc = param.get("description", "")
        param_type = param.get("type", "string")
        param_required = param.get("required", True)
        param_default = param.get("default", ...)
        
        # Map string types to Python types
        type_mapping = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        
        python_type = type_mapping.get(param_type, str)
        
        # Create field with proper default
        if param_required:
            fields[param_name] = (python_type, Field(..., description=param_desc))
        else:
            default_value = param_default if param_default != ... else None
            fields[param_name] = (Optional[python_type], Field(default_value, description=param_desc))
    
    # Create dynamic Pydantic model
    ArgsSchema = create_model(
        f"{tool_name}_args",
        **fields
    )
    
    # Create handler function
    def http_handler(**kwargs) -> str:
        """Execute HTTP request with provided parameters."""
        try:
            log_info(f"Executing HTTP tool: {tool_name} ({method} {url})")
            
            # Separate query params and body data based on method
            if method.upper() in ["GET", "DELETE"]:
                # Use as query parameters
                result = client.request_sync(
                    method=method,
                    url=url,
                    params=kwargs,
                    headers=headers,
                )
            else:
                # Use as request body
                result = client.request_sync(
                    method=method,
                    url=url,
                    data=kwargs,
                    headers=headers,
                )
            
            return result
            
        except Exception as e:
            error_msg = f"HTTP tool '{tool_name}' failed: {str(e)}"
            log_info(error_msg)
            return f"Error: {error_msg}"
    
    # Create and return StructuredTool
    return StructuredTool(
        name=tool_name,
        description=tool_description,
        func=http_handler,
        args_schema=ArgsSchema,
    )
