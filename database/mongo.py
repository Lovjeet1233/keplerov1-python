"""
MongoDB utilities for chatbot instances and conversation history management

Collections:
- instances: Chatbot instance metadata
- chat_history: Chat message history
- checkpoints: LangGraph conversation memory (managed by MongoDBSaver)
"""

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, DuplicateKeyError
from datetime import datetime
from typing import Optional, Dict, List, Any
from utils.logger import log_info, log_error, log_exception
import os


class MongoDBManager:
    """
    MongoDB Manager for handling chatbot instances and conversation history
    """
    
    def __init__(self, mongodb_uri: str, database_name: str = "python"):
        """
        Initialize MongoDB Manager
        
        Args:
            mongodb_uri: MongoDB connection URI
            database_name: Name of the database (default: "python")
        """
        try:
            self.client = MongoClient(mongodb_uri)
            # Test connection
            self.client.admin.command('ping')
            self.db = self.client[database_name]
            
            # Collections
            self.instances_collection = self.db["instances"]
            self.chat_history_collection = self.db["chat_history"]
            self.checkpoints_collection = self.db["checkpoints"]
            
            # Create indexes for better performance
            self._create_indexes()
            
            log_info(f"MongoDB Manager initialized successfully with database: {database_name}")
        except ConnectionFailure as e:
            log_error(f"Failed to connect to MongoDB: {str(e)}")
            raise
        except Exception as e:
            log_exception(f"Error initializing MongoDB Manager: {str(e)}")
            raise
    
    def _create_indexes(self):
        """Create indexes for collections"""
        try:
            # Indexes for instances collection
            self.instances_collection.create_index("instance_id", unique=True)
            self.instances_collection.create_index("created_at")
            
            # Indexes for chat_history collection
            self.chat_history_collection.create_index("thread_id")
            self.chat_history_collection.create_index("instance_id")
            self.chat_history_collection.create_index("timestamp")
            
            # Indexes for checkpoints collection (managed by LangGraph MongoDBSaver)
            # Note: LangGraph manages its own indexes for the checkpoints collection
            
            log_info("MongoDB indexes created successfully")
        except Exception as e:
            log_error(f"Error creating indexes: {str(e)}")
    
    # ==================== Chatbot Instance Methods ====================
    
    def create_chatbot_instance(
        self,
        instance_id: str,
        collection_name: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new chatbot instance
        
        Args:
            instance_id: Unique identifier for the instance
            collection_name: Name of the Qdrant collection to use
            metadata: Additional metadata for the instance
            
        Returns:
            Dictionary with instance details
        """
        try:
            instance_data = {
                "instance_id": instance_id,
                "collection_name": collection_name,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "is_active": True,
                "metadata": metadata or {}
            }
            
            result = self.instances_collection.insert_one(instance_data)
            log_info(f"Created chatbot instance: {instance_id}")
            
            instance_data["_id"] = str(result.inserted_id)
            return instance_data
            
        except DuplicateKeyError:
            log_error(f"Instance with ID '{instance_id}' already exists")
            raise ValueError(f"Instance with ID '{instance_id}' already exists")
        except Exception as e:
            log_exception(f"Error creating chatbot instance: {str(e)}")
            raise
    
    def get_chatbot_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """
        Get chatbot instance by ID
        
        Args:
            instance_id: Instance identifier
            
        Returns:
            Instance data or None if not found
        """
        try:
            instance = self.instances_collection.find_one({"instance_id": instance_id})
            if instance:
                instance["_id"] = str(instance["_id"])
                log_info(f"Retrieved chatbot instance: {instance_id}")
            return instance
        except Exception as e:
            log_exception(f"Error retrieving chatbot instance: {str(e)}")
            return None
    
    def update_chatbot_instance(
        self,
        instance_id: str,
        update_data: Dict[str, Any]
    ) -> bool:
        """
        Update chatbot instance
        
        Args:
            instance_id: Instance identifier
            update_data: Data to update
            
        Returns:
            True if successful, False otherwise
        """
        try:
            update_data["updated_at"] = datetime.utcnow()
            result = self.instances_collection.update_one(
                {"instance_id": instance_id},
                {"$set": update_data}
            )
            
            if result.modified_count > 0:
                log_info(f"Updated chatbot instance: {instance_id}")
                return True
            return False
        except Exception as e:
            log_exception(f"Error updating chatbot instance: {str(e)}")
            return False
    
    def delete_chatbot_instance(self, instance_id: str) -> bool:
        """
        Delete chatbot instance
        
        Args:
            instance_id: Instance identifier
            
        Returns:
            True if successful, False otherwise
        """
        try:
            result = self.instances_collection.delete_one({"instance_id": instance_id})
            if result.deleted_count > 0:
                log_info(f"Deleted chatbot instance: {instance_id}")
                return True
            return False
        except Exception as e:
            log_exception(f"Error deleting chatbot instance: {str(e)}")
            return False
    
    def list_chatbot_instances(
        self,
        active_only: bool = True,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List all chatbot instances
        
        Args:
            active_only: Filter for active instances only
            limit: Maximum number of instances to return
            
        Returns:
            List of instance data
        """
        try:
            query = {"is_active": True} if active_only else {}
            instances = list(
                self.instances_collection
                .find(query)
                .sort("created_at", -1)
                .limit(limit)
            )
            
            for instance in instances:
                instance["_id"] = str(instance["_id"])
            
            log_info(f"Retrieved {len(instances)} chatbot instances")
            return instances
        except Exception as e:
            log_exception(f"Error listing chatbot instances: {str(e)}")
            return []
    
    # ==================== Chat History Methods ====================
    
    def store_chat_message(
        self,
        thread_id: str,
        instance_id: str,
        query: str,
        answer: str,
        retrieved_docs: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Store a chat message in history
        
        Args:
            thread_id: Thread identifier
            instance_id: Instance identifier
            query: User query
            answer: Assistant answer
            retrieved_docs: Retrieved documents from RAG
            metadata: Additional metadata
            
        Returns:
            Message ID
        """
        try:
            message_data = {
                "thread_id": thread_id,
                "instance_id": instance_id,
                "query": query,
                "answer": answer,
                "retrieved_docs": retrieved_docs or [],
                "timestamp": datetime.utcnow(),
                "metadata": metadata or {}
            }
            
            result = self.chat_history_collection.insert_one(message_data)
            message_id = str(result.inserted_id)
            
            log_info(f"Stored chat message for thread: {thread_id}")
            return message_id
            
        except Exception as e:
            log_exception(f"Error storing chat message: {str(e)}")
            raise
    
    def get_chat_history(
        self,
        thread_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get chat history for a thread
        
        Args:
            thread_id: Thread identifier
            limit: Maximum number of messages to return
            
        Returns:
            List of chat messages
        """
        try:
            messages = list(
                self.chat_history_collection
                .find({"thread_id": thread_id})
                .sort("timestamp", 1)
                .limit(limit)
            )
            
            for message in messages:
                message["_id"] = str(message["_id"])
            
            log_info(f"Retrieved {len(messages)} messages for thread: {thread_id}")
            return messages
            
        except Exception as e:
            log_exception(f"Error retrieving chat history: {str(e)}")
            return []
    
    def get_chat_history_by_instance(
        self,
        instance_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get all chat history for an instance
        
        Args:
            instance_id: Instance identifier
            limit: Maximum number of messages to return
            
        Returns:
            List of chat messages
        """
        try:
            messages = list(
                self.chat_history_collection
                .find({"instance_id": instance_id})
                .sort("timestamp", -1)
                .limit(limit)
            )
            
            for message in messages:
                message["_id"] = str(message["_id"])
            
            log_info(f"Retrieved {len(messages)} messages for instance: {instance_id}")
            return messages
            
        except Exception as e:
            log_exception(f"Error retrieving chat history by instance: {str(e)}")
            return []
    
    def delete_chat_history(self, thread_id: str) -> int:
        """
        Delete chat history for a thread
        
        Args:
            thread_id: Thread identifier
            
        Returns:
            Number of messages deleted
        """
        try:
            result = self.chat_history_collection.delete_many({"thread_id": thread_id})
            deleted_count = result.deleted_count
            log_info(f"Deleted {deleted_count} messages for thread: {thread_id}")
            return deleted_count
            
        except Exception as e:
            log_exception(f"Error deleting chat history: {str(e)}")
            return 0
    
    # ==================== Connection Management ====================
    
    def close(self):
        """Close MongoDB connection"""
        try:
            self.client.close()
            log_info("MongoDB connection closed")
        except Exception as e:
            log_error(f"Error closing MongoDB connection: {str(e)}")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


# Singleton instance
_mongodb_manager = None


def get_mongodb_manager(mongodb_uri: Optional[str] = None, database_name: str = "python") -> MongoDBManager:
    """
    Get or create MongoDB Manager singleton instance
    
    Args:
        mongodb_uri: MongoDB connection URI (required for first call)
        database_name: Database name (default: "python")
        
    Returns:
        MongoDBManager instance
    """
    global _mongodb_manager
    
    if _mongodb_manager is None:
        if mongodb_uri is None:
            # Try to get from environment
            mongodb_uri = os.getenv("MONGODB_URI")
            if mongodb_uri is None:
                raise ValueError("MongoDB URI must be provided or set in MONGODB_URI environment variable")
        
        _mongodb_manager = MongoDBManager(mongodb_uri, database_name)
    
    return _mongodb_manager
