"""
MongoDB storage for registered integration tools.
Each tool is stored as a separate document scoped by user_id.
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pymongo import ASCENDING, MongoClient
from pymongo.errors import ConnectionFailure

from utils.logger import log_info, log_error, log_exception


class ToolStore:
    """Persist and retrieve registered tools from MongoDB."""

    def __init__(
        self,
        mongodb_uri: str,
        database_name: str = "synervo-python",
        collection_name: str = "integration-chatbot",
    ):
        try:
            self.client = MongoClient(mongodb_uri)
            self.client.admin.command("ping")
            self.collection = self.client[database_name][collection_name]
            self._create_indexes()
            log_info(
                f"ToolStore initialized (db={database_name}, collection={collection_name})"
            )
        except ConnectionFailure as e:
            log_error(f"Failed to connect ToolStore to MongoDB: {e}")
            raise
        except Exception as e:
            log_exception(f"Error initializing ToolStore: {e}")
            raise

    def _create_indexes(self) -> None:
        self.collection.create_index("tool_id", unique=True)
        self.collection.create_index("user_id")
        self.collection.create_index(
            [("user_id", ASCENDING), ("tool_name", ASCENDING), ("tool_type", ASCENDING)],
            unique=True,
            name="user_tool_name_type_unique",
        )

    def _serialize_tool(self, document: dict) -> dict:
        tool = {
            "tool_id": document["tool_id"],
            "user_id": document["user_id"],
            "tool_name": document["tool_name"],
            "tool_type": document["tool_type"],
            "description": document["description"],
            "schema": document["schema"],
            "created_at": document.get("created_at"),
            "updated_at": document.get("updated_at"),
        }
        return tool

    def register_tool(self, user_id: str, tool_schema: dict) -> tuple[str, str, dict]:
        """
        Create or update a tool for a user.

        Returns:
            (tool_id, operation, tool_payload)
        """
        now = datetime.now(timezone.utc)
        existing = self.collection.find_one(
            {
                "user_id": user_id,
                "tool_name": tool_schema["tool_name"],
                "tool_type": tool_schema["tool_type"],
            }
        )

        if existing:
            tool_id = existing["tool_id"]
            document = {
                **tool_schema,
                "tool_id": tool_id,
                "user_id": user_id,
                "updated_at": now,
            }
            self.collection.update_one({"tool_id": tool_id}, {"$set": document})
            operation = "updated"
        else:
            tool_id = str(uuid.uuid4())
            document = {
                **tool_schema,
                "tool_id": tool_id,
                "user_id": user_id,
                "created_at": now,
                "updated_at": now,
            }
            self.collection.insert_one(document)
            operation = "created"

        payload = self._serialize_tool(document)
        log_info(
            f"Tool '{tool_schema['tool_name']}' {operation} for user '{user_id}' (id={tool_id})"
        )
        return tool_id, operation, payload

    def delete_tool(self, tool_id: str, user_id: Optional[str] = None) -> Optional[str]:
        query = {"tool_id": tool_id}
        if user_id:
            query["user_id"] = user_id

        existing = self.collection.find_one(query)
        if not existing:
            return None

        self.collection.delete_one({"tool_id": tool_id})
        return existing.get("tool_name", "unknown")

    def get_tool(self, tool_id: str, user_id: Optional[str] = None) -> Optional[dict]:
        query = {"tool_id": tool_id}
        if user_id:
            query["user_id"] = user_id

        document = self.collection.find_one(query, {"_id": 0})
        if not document:
            return None
        return self._serialize_tool(document)

    def get_tools_by_user_id(self, user_id: str) -> Dict[str, Any]:
        """Return tools indexed by tool_id for a user."""
        tools: Dict[str, Any] = {}
        cursor = self.collection.find({"user_id": user_id}, {"_id": 0})
        for document in cursor:
            tool_id = document["tool_id"]
            tools[tool_id] = {
                "tool_name": document["tool_name"],
                "tool_type": document["tool_type"],
                "description": document["description"],
                "schema": document["schema"],
            }
        return tools

    def list_tools(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        query = {"user_id": user_id} if user_id else {}
        tools: Dict[str, Any] = {}
        cursor = self.collection.find(query, {"_id": 0})
        for document in cursor:
            tool_id = document["tool_id"]
            tools[tool_id] = self._serialize_tool(document)
        return tools


_tool_store: Optional[ToolStore] = None


def get_tool_store(
    mongodb_uri: Optional[str] = None,
    database_name: Optional[str] = None,
    collection_name: Optional[str] = None,
) -> ToolStore:
    global _tool_store

    if _tool_store is None:
        uri = mongodb_uri or os.getenv("MONGODB_URI")
        if not uri:
            raise ValueError("MONGODB_URI must be provided or set in environment")

        db_name = database_name or os.getenv("TOOLS_DB_NAME", "synervo-python")
        coll_name = collection_name or os.getenv(
            "TOOLS_COLLECTION_NAME", "integration-chatbot"
        )
        _tool_store = ToolStore(uri, db_name, coll_name)

    return _tool_store
