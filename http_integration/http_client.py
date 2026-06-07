"""
HTTP client for making dynamic HTTP requests.
"""

import httpx
from typing import Dict, Any, Optional
from utils.logger import log_info, log_error


class HTTPToolClient:
    """Client for making HTTP requests from tools."""
    
    def __init__(self, base_url: str = "", headers: Optional[Dict[str, str]] = None):
        """
        Initialize HTTP client.
        
        Args:
            base_url: Base URL for requests (optional)
            headers: Default headers to include in all requests
        """
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.default_headers = headers or {}
    
    async def request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Make an HTTP request.
        
        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE)
            url: Full URL or path (if base_url is set)
            params: Query parameters
            data: Request body data
            headers: Additional headers
        
        Returns:
            Response text or error message
        """
        try:
            # Combine base_url with path if needed
            full_url = url if url.startswith("http") else f"{self.base_url}/{url.lstrip('/')}"
            
            # Merge headers
            request_headers = {**self.default_headers, **(headers or {})}
            
            log_info(f"HTTP Tool Request: {method} {full_url}")
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(
                    method=method.upper(),
                    url=full_url,
                    params=params,
                    json=data if method.upper() in ["POST", "PUT", "PATCH"] else None,
                    headers=request_headers,
                )
                
                response.raise_for_status()
                
                log_info(f"HTTP Tool Response: {response.status_code}")
                
                # Try to return JSON if possible, otherwise text
                try:
                    return str(response.json())
                except:
                    return response.text
                    
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            log_error(f"HTTP Tool Error: {error_msg}")
            return f"Error: {error_msg}"
        except Exception as e:
            error_msg = f"Request failed: {str(e)}"
            log_error(f"HTTP Tool Error: {error_msg}")
            return f"Error: {error_msg}"
    
    def request_sync(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Make a synchronous HTTP request (for use in LangChain tools).
        
        Args:
            method: HTTP method
            url: Full URL or path
            params: Query parameters
            data: Request body data
            headers: Additional headers
        
        Returns:
            Response text or error message
        """
        try:
            full_url = url if url.startswith("http") else f"{self.base_url}/{url.lstrip('/')}"
            request_headers = {**self.default_headers, **(headers or {})}
            
            log_info(f"HTTP Tool Request (sync): {method} {full_url}")
            
            with httpx.Client(timeout=30.0) as client:
                response = client.request(
                    method=method.upper(),
                    url=full_url,
                    params=params,
                    json=data if method.upper() in ["POST", "PUT", "PATCH"] else None,
                    headers=request_headers,
                )
                
                response.raise_for_status()
                
                log_info(f"HTTP Tool Response: {response.status_code}")
                
                try:
                    return str(response.json())
                except:
                    return response.text
                    
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            log_error(f"HTTP Tool Error: {error_msg}")
            return f"Error: {error_msg}"
        except Exception as e:
            error_msg = f"Request failed: {str(e)}"
            log_error(f"HTTP Tool Error: {error_msg}")
            return f"Error: {error_msg}"
