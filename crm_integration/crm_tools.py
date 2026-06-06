"""
LangChain tool builders for CRM operations.
Creates StructuredTool instances for search, create, and update operations.
"""

from typing import Any, Dict, List, Optional
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model

from .crm_client import CRMClient
from utils.logger import log_info


def _schema_to_dict_list(schema: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Convert schema list to dict list format."""
    return [{"name": item["name"], "description": item["description"]} for item in schema]


def build_crm_search_tool(
    table_id: str,
    search_schema: List[Dict[str, str]],
    crm_base_url: str,
    tool_description: Optional[str] = None,
) -> StructuredTool:
    """
    Build a LangChain tool for CRM record search.

    Args:
        table_id: CRM table ID (fixed for this tool instance)
        search_schema: List of searchable fields [{"name": "email", "description": "..."}]
        crm_base_url: Base URL for CRM API
        tool_description: Optional custom description

    Returns:
        StructuredTool for searching CRM records
    """
    crm_client = CRMClient(base_url=crm_base_url)

    pydantic_fields = {}
    for field in search_schema:
        field_name = field["name"]
        field_desc = field["description"]
        pydantic_fields[field_name] = (
            Optional[str],
            Field(default=None, description=field_desc),
        )

    pydantic_fields["page"] = (
        Optional[int],
        Field(default=1, description="Page number (default 1)"),
    )
    pydantic_fields["limit"] = (
        Optional[int],
        Field(default=20, description="Results per page (default 20)"),
    )

    args_schema = create_model("CRMSearchArgs", **pydantic_fields)

    def search_handler(**kwargs) -> str:
        """Execute CRM search with provided filters."""
        filters = {k: v for k, v in kwargs.items() if v and k not in ["page", "limit"]}
        page = kwargs.get("page", 1)
        limit = kwargs.get("limit", 20)

        result = crm_client.search_records(
            table_id=table_id,
            filters=filters if filters else None,
            page=page,
            limit=limit,
        )

        if "error" in result:
            return f"Error searching CRM: {result.get('message', 'Unknown error')}"

        records = result.get("records", [])
        if not records:
            return "No records found matching the search criteria."

        return f"Found {len(records)} record(s): {records}"

    default_desc = (
        f"Search CRM records in table {table_id}. "
        f"Available search fields: {', '.join([f['name'] for f in search_schema])}. "
        "Provide any known field values to filter results."
    )

    tool = StructuredTool.from_function(
        func=search_handler,
        name="crm_search_records",
        description=tool_description or default_desc,
        args_schema=args_schema,
    )

    log_info(f"Built CRM search tool for table {table_id}")
    return tool


def build_crm_create_tool(
    table_id: str,
    data_schema: List[Dict[str, str]],
    crm_base_url: str,
    tool_description: Optional[str] = None,
) -> StructuredTool:
    """
    Build a LangChain tool for creating CRM records.

    Args:
        table_id: CRM table ID
        data_schema: List of required fields [{"name": "full_name", "description": "..."}]
        crm_base_url: Base URL for CRM API
        tool_description: Optional custom description

    Returns:
        StructuredTool for creating CRM records
    """
    crm_client = CRMClient(base_url=crm_base_url)

    pydantic_fields = {}
    for field in data_schema:
        field_name = field["name"]
        field_desc = field["description"]
        pydantic_fields[field_name] = (str, Field(description=field_desc))

    args_schema = create_model("CRMCreateArgs", **pydantic_fields)

    def create_handler(**kwargs) -> str:
        """Execute CRM record creation."""
        data = {k: v for k, v in kwargs.items() if v}

        result = crm_client.create_record(table_id=table_id, data=data)

        if "error" in result:
            return f"Error creating CRM record: {result.get('message', 'Unknown error')}"

        if result.get("success") or result.get("id"):
            return f"Successfully created CRM record with ID: {result.get('id', 'unknown')}"

        return f"CRM record creation completed: {result}"

    field_names = ", ".join([f["name"] for f in data_schema])
    default_desc = (
        f"Create a new CRM record in table {table_id}. "
        f"Required fields: {field_names}. "
        "Collect all required information before calling this tool."
    )

    tool = StructuredTool.from_function(
        func=create_handler,
        name="crm_create_record",
        description=tool_description or default_desc,
        args_schema=args_schema,
    )

    log_info(f"Built CRM create tool for table {table_id}")
    return tool


def build_crm_update_tool(
    table_id: str,
    lookup_column: str,
    update_schema: List[Dict[str, str]],
    crm_base_url: str,
    tool_description: Optional[str] = None,
) -> StructuredTool:
    """
    Build a LangChain tool for updating CRM records.

    Args:
        table_id: CRM table ID
        lookup_column: Column used to identify the record (e.g., "email_address")
        update_schema: List of updatable fields [{"name": "phone_number", "description": "..."}]
        crm_base_url: Base URL for CRM API
        tool_description: Optional custom description

    Returns:
        StructuredTool for updating CRM records
    """
    crm_client = CRMClient(base_url=crm_base_url)

    pydantic_fields = {
        lookup_column: (
            str,
            Field(description=f"Value of {lookup_column} to identify the record"),
        )
    }

    for field in update_schema:
        field_name = field["name"]
        field_desc = field["description"]
        pydantic_fields[field_name] = (
            Optional[str],
            Field(default=None, description=field_desc),
        )

    args_schema = create_model("CRMUpdateArgs", **pydantic_fields)

    def update_handler(**kwargs) -> str:
        """Execute CRM record update."""
        lookup_value = kwargs.get(lookup_column)
        if not lookup_value:
            return f"Error: {lookup_column} is required to identify the record"

        lookup = {lookup_column: lookup_value}
        data = {k: v for k, v in kwargs.items() if v and k != lookup_column}

        if not data:
            return "Error: No fields provided to update"

        result = crm_client.update_record(
            table_id=table_id, lookup=lookup, data=data
        )

        if "error" in result:
            return f"Error updating CRM record: {result.get('message', 'Unknown error')}"

        if result.get("success") or result.get("modified_count"):
            return f"Successfully updated CRM record identified by {lookup_column}={lookup_value}"

        return f"CRM record update completed: {result}"

    field_names = ", ".join([f["name"] for f in update_schema])
    default_desc = (
        f"Update a CRM record in table {table_id} identified by {lookup_column}. "
        f"Updatable fields: {field_names}. "
        f"Provide the {lookup_column} and at least one field to update."
    )

    tool = StructuredTool.from_function(
        func=update_handler,
        name="crm_update_record",
        description=tool_description or default_desc,
        args_schema=args_schema,
    )

    log_info(f"Built CRM update tool for table {table_id}")
    return tool
