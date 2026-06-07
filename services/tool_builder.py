"""
Dynamic tool builder service.
Constructs LangChain tools from user tool assignments.
"""

from typing import Any, Dict, List
from langchain_core.tools import StructuredTool

from crm_integration import (
    build_crm_search_tool,
    build_crm_create_tool,
    build_crm_update_tool,
)
from http_integration import build_http_tool
from services.registered_tools import build_registered_email_tools
from utils.logger import log_info, log_error, log_warning


class ToolBuilder:
    """Build LangChain tools dynamically from user's registered tools."""

    def __init__(self, tool_store):
        """
        Initialize tool builder.

        Args:
            tool_store: Tool registry store
        """
        self.tool_store = tool_store

    def build_tools_for_user(
        self,
        user_id: str,
        email_base_url: str = None,
        x_user_email: str = None,
    ) -> List[StructuredTool]:
        """
        Build all enabled tools for a user.

        Args:
            user_id: User identifier
            email_base_url: Base URL for email API (for email tools)
            x_user_email: User email for email API (for email tools)

        Returns:
            List of LangChain StructuredTool instances
        """
        try:
            log_info(f"Building tools for user: {user_id}")

            # Get all tools registered for this user
            user_tools = self.tool_store.get_tools_by_user_id(user_id)

            if not user_tools:
                log_info(f"No tools found for user: {user_id}")
                return []

            tools = []

            for tool_id, tool_data in user_tools.items():
                tool_type = tool_data.get("tool_type")
                tool_name = tool_data.get("tool_name")
                tool_schema = tool_data.get("schema", {})

                try:
                    if tool_type == "crm":
                        crm_tool = self._build_crm_tool(tool_schema, tool_name)
                        if crm_tool:
                            tools.append(crm_tool)

                    elif tool_type == "http":
                        http_tool = self._build_http_tool(tool_schema, tool_name, tool_data.get("description"))
                        if http_tool:
                            tools.append(http_tool)

                    elif tool_type == "email":
                        if email_base_url and x_user_email:
                            email_tools = self._build_email_tools(
                                user_id, email_base_url, x_user_email
                            )
                            tools.extend(email_tools)
                        else:
                            log_warning(
                                f"Email tool {tool_id} enabled but email credentials not provided"
                            )

                    else:
                        log_warning(f"Unknown tool type: {tool_type} for tool {tool_id}")

                except Exception as e:
                    log_error(f"Error building tool {tool_id}: {str(e)}")
                    continue

            log_info(f"Built {len(tools)} tools for user {user_id}")
            return tools

        except Exception as e:
            log_error(f"Error building tools for user {user_id}: {str(e)}")
            return []

    def _build_crm_tool(
        self, tool_schema: Dict[str, Any], tool_name: str
    ) -> StructuredTool:
        """
        Build a CRM tool from tool schema.

        Args:
            tool_schema: Tool schema with configuration
            tool_name: Name of the CRM tool (crm_search_records, etc.)

        Returns:
            StructuredTool instance or None
        """
        try:
            table_id = tool_schema.get("tableId")
            crm_base_url = tool_schema.get("crm_base_url")
            tool_description = tool_schema.get("tool_description")

            if not table_id:
                log_error(f"CRM tool missing tableId in schema")
                return None

            if not crm_base_url:
                log_error(f"CRM tool missing crm_base_url in schema")
                return None

            if tool_name == "crm_search_records":
                search_schema = tool_schema.get("search_schema", [])
                if not search_schema:
                    log_error("CRM search tool missing search_schema")
                    return None

                return build_crm_search_tool(
                    table_id=table_id,
                    search_schema=search_schema,
                    crm_base_url=crm_base_url,
                    tool_description=tool_description,
                )

            elif tool_name == "crm_create_record":
                data_schema = tool_schema.get("data_schema", [])
                if not data_schema:
                    log_error("CRM create tool missing data_schema")
                    return None

                return build_crm_create_tool(
                    table_id=table_id,
                    data_schema=data_schema,
                    crm_base_url=crm_base_url,
                    tool_description=tool_description,
                )

            elif tool_name == "crm_update_record":
                lookup_column = tool_schema.get("lookup_column")
                update_schema = tool_schema.get("update_schema", [])

                if not lookup_column:
                    log_error("CRM update tool missing lookup_column")
                    return None
                if not update_schema:
                    log_error("CRM update tool missing update_schema")
                    return None

                return build_crm_update_tool(
                    table_id=table_id,
                    lookup_column=lookup_column,
                    update_schema=update_schema,
                    crm_base_url=crm_base_url,
                    tool_description=tool_description,
                )

            else:
                log_warning(f"Unknown CRM tool name: {tool_name}")
                return None

        except Exception as e:
            log_error(f"Error building CRM tool: {str(e)}")
            return None

    def _build_http_tool(
        self, tool_schema: Dict[str, Any], tool_name: str, tool_description: str
    ) -> StructuredTool:
        """
        Build an HTTP tool from tool schema.

        Args:
            tool_schema: Tool schema with configuration
            tool_name: Name of the HTTP tool
            tool_description: Description of the tool

        Returns:
            StructuredTool instance or None
        """
        try:
            method = tool_schema.get("method")
            url = tool_schema.get("url")
            parameters = tool_schema.get("parameters", [])
            headers = tool_schema.get("headers", {})

            if not method or not url:
                log_error(f"HTTP tool missing method or URL")
                return None

            return build_http_tool(
                tool_name=tool_name,
                tool_description=tool_description,
                method=method,
                url=url,
                parameters=parameters,
                headers=headers,
            )

        except Exception as e:
            log_error(f"Error building HTTP tool: {str(e)}")
            return None

    def _build_email_tools(
        self, user_id: str, email_base_url: str, x_user_email: str
    ) -> List[StructuredTool]:
        """
        Build email tools for a user.

        Args:
            user_id: User identifier
            email_base_url: Base URL for email API
            x_user_email: User email for API

        Returns:
            List of email tools
        """
        try:
            user_tools = self.tool_store.get_tools_by_user_id(user_id)

            email_tools = build_registered_email_tools(
                user_tools=user_tools,
                email_base_url=email_base_url,
                x_user_email=x_user_email,
            )

            return email_tools

        except Exception as e:
            log_error(f"Error building email tools: {str(e)}")
            return []

    def get_tool_system_prompt(self, user_id: str) -> str:
        """
        Generate system prompt describing available tools for a user.

        Args:
            user_id: User identifier

        Returns:
            System prompt text describing tools
        """
        try:
            user_tools = self.tool_store.get_tools_by_user_id(user_id)

            if not user_tools:
                return ""

            lines = ["Available tools for this conversation:"]

            for tool_id, tool_data in user_tools.items():
                tool_name = tool_data.get("tool_name", "unknown")
                tool_type = tool_data.get("tool_type", "unknown")
                description = tool_data.get("description", "No description")
                lines.append(f"- {tool_name} ({tool_type}): {description}")

            return "\n".join(lines)

        except Exception as e:
            log_error(f"Error generating tool system prompt: {str(e)}")
            return ""


_tool_builder: ToolBuilder = None


def get_tool_builder(tool_store) -> ToolBuilder:
    """Get or create singleton ToolBuilder instance."""
    global _tool_builder

    if _tool_builder is None:
        _tool_builder = ToolBuilder(tool_store)

    return _tool_builder
