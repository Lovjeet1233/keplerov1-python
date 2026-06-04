"""
Build LangChain tools from MongoDB-registered tool templates.
"""

from typing import Any, Dict, List, Optional

import httpx
from langchain_core.tools import StructuredTool
from pydantic import Field, create_model

from utils.logger import log_info, log_error


TEMPLATE_FIELDS = {"to", "subject", "body", "cc"}


def _apply_template(template: str, values: Dict[str, str]) -> str:
    result = template or ""
    for key, value in values.items():
        result = result.replace(f"{{{{{key}}}}}", str(value))
    return result


def _send_email_via_api(
    email_base_url: str,
    x_user_email: str,
    to: str,
    subject: str,
    body: str,
) -> str:
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{email_base_url}/email/send",
                headers={
                    "accept": "application/json",
                    "x-user-email": x_user_email,
                    "Content-Type": "application/json",
                },
                json={"to": to, "subject": subject, "body": body},
            )
            if response.status_code == 200:
                return f"Email sent successfully to {to}"
            return f"Failed to send email: {response.text}"
    except Exception as e:
        return f"Error sending email: {str(e)}"


def build_registered_email_tools(
    user_tools: Dict[str, Any],
    email_base_url: str,
    x_user_email: str,
) -> List[StructuredTool]:
    """Create one LangChain tool per registered email template."""
    tools: List[StructuredTool] = []

    for tool_config in user_tools.values():
        if tool_config.get("tool_type") != "email":
            continue

        tool_name = tool_config["tool_name"]
        description = tool_config["description"]
        props = tool_config.get("schema", {}).get("properties", {})
        required_fields = set(tool_config.get("schema", {}).get("required", []))

        dynamic_fields = [
            name for name in props.keys() if name not in TEMPLATE_FIELDS
        ]
        if "to" not in dynamic_fields and "to" in props:
            dynamic_fields.append("to")

        pydantic_fields = {}
        for field_name in dynamic_fields:
            field_desc = props.get(field_name, {}).get("description", field_name)
            if field_name in required_fields:
                pydantic_fields[field_name] = (str, Field(description=field_desc))
            else:
                pydantic_fields[field_name] = (
                    Optional[str],
                    Field(default="", description=field_desc),
                )

        args_schema = create_model(f"{tool_name}_args", **pydantic_fields)

        def make_handler(config: dict):
            config_props = config.get("schema", {}).get("properties", {})

            def handler(**kwargs) -> str:
                values = {key: val for key, val in kwargs.items() if val not in (None, "")}
                to = values.get("to") or config_props.get("to", {}).get("value", "")
                subject_template = config_props.get("subject", {}).get("value", "")
                body_template = config_props.get("body", {}).get("value", "")

                subject = _apply_template(subject_template, values)
                body = _apply_template(body_template, values)

                if not to:
                    return "Error: recipient email (to) is required"

                return _send_email_via_api(
                    email_base_url=email_base_url,
                    x_user_email=x_user_email,
                    to=to,
                    subject=subject,
                    body=body,
                )

            return handler

        tool = StructuredTool.from_function(
            func=make_handler(tool_config),
            name=tool_name,
            description=description,
            args_schema=args_schema,
        )
        tools.append(tool)
        log_info(f"Registered email tool loaded for chat: {tool_name}")

    return tools


def build_tool_system_prompt(user_tools: Dict[str, Any]) -> str:
    """Describe registered tools for the system prompt when credentials are missing."""
    if not user_tools:
        return ""

    lines = ["Registered tools available for this user:"]
    for tool_config in user_tools.values():
        lines.append(
            f"- {tool_config.get('tool_name')} ({tool_config.get('tool_type')}): "
            f"{tool_config.get('description')}"
        )
    return "\n".join(lines)
