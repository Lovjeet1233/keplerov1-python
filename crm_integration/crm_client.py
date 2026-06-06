"""
CRM API Client for making HTTP requests to CRM backend.
"""

from typing import Any, Dict, Optional
import httpx
from utils.logger import log_info, log_error, log_exception


class CRMClient:
    """HTTP client for CRM API operations."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        """
        Initialize CRM client.

        Args:
            base_url: Base URL for CRM API (e.g., https://crm.example.com/api)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def search_records(
        self,
        table_id: str,
        filters: Optional[Dict[str, str]] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Search CRM records with filters.

        Args:
            table_id: CRM table identifier
            filters: Field filters (e.g., {"email_address": "test@example.com"})
            page: Page number
            limit: Results per page

        Returns:
            API response with records
        """
        try:
            params = {"tableId": table_id, "page": str(page), "limit": str(limit)}
            if filters:
                params.update(filters)

            log_info(f"CRM Search: table={table_id}, filters={filters}")

            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    f"{self.base_url}/voice/records",
                    params=params,
                )
                response.raise_for_status()
                result = response.json()
                log_info(f"CRM Search successful: {len(result.get('records', []))} records found")
                return result

        except httpx.HTTPStatusError as e:
            log_error(f"CRM Search HTTP error: {e.response.status_code} - {e.response.text}")
            return {
                "error": f"HTTP {e.response.status_code}",
                "message": e.response.text,
                "records": [],
            }
        except Exception as e:
            log_exception(f"CRM Search error: {str(e)}")
            return {"error": "Request failed", "message": str(e), "records": []}

    def create_record(
        self, table_id: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a new CRM record.

        Args:
            table_id: CRM table identifier
            data: Record data (e.g., {"full_name": "John", "email": "john@example.com"})

        Returns:
            API response with created record
        """
        try:
            payload = {"tableId": table_id, "data": data}

            log_info(f"CRM Create: table={table_id}, data={data}")

            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/voice/records",
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
                log_info(f"CRM Create successful: record_id={result.get('id')}")
                return result

        except httpx.HTTPStatusError as e:
            log_error(f"CRM Create HTTP error: {e.response.status_code} - {e.response.text}")
            return {
                "error": f"HTTP {e.response.status_code}",
                "message": e.response.text,
                "success": False,
            }
        except Exception as e:
            log_exception(f"CRM Create error: {str(e)}")
            return {"error": "Request failed", "message": str(e), "success": False}

    def update_record(
        self,
        table_id: str,
        lookup: Dict[str, str],
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Update an existing CRM record.

        Args:
            table_id: CRM table identifier
            lookup: Field to identify record (e.g., {"email_address": "john@example.com"})
            data: Fields to update (e.g., {"phone_number": "+1234567890"})

        Returns:
            API response with update status
        """
        try:
            payload = {"tableId": table_id, "lookup": lookup, "data": data}

            log_info(f"CRM Update: table={table_id}, lookup={lookup}, data={data}")

            with httpx.Client(timeout=self.timeout) as client:
                response = client.patch(
                    f"{self.base_url}/voice/records",
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
                log_info(f"CRM Update successful")
                return result

        except httpx.HTTPStatusError as e:
            log_error(f"CRM Update HTTP error: {e.response.status_code} - {e.response.text}")
            return {
                "error": f"HTTP {e.response.status_code}",
                "message": e.response.text,
                "success": False,
            }
        except Exception as e:
            log_exception(f"CRM Update error: {str(e)}")
            return {"error": "Request failed", "message": str(e), "success": False}
