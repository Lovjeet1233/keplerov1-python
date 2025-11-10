"""
Configuration file for RAG Service API
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Configuration class for RAG Service"""
    
    # Qdrant Configuration
    QDRANT_URL = os.getenv(
        "QDRANT_URL",
        "https://your-qdrant-instance.cloud.qdrant.io"
    )
    QDRANT_API_KEY = os.getenv(
        "QDRANT_API_KEY",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.Mr-rW6Q25j3PE6lJ1ciP1JEaRxkE66lzlBcM2HbQuLI"
    )
    
    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    
    # MongoDB Configuration
    MONGODB_URI = os.getenv(
        "MONGODB_URI",
        "mongodb+srv://LOVJEET:LOVJEETMONGO@cluster0.zpzj90m.mongodb.net"
    )
    
    # API Configuration
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", "8000"))
    
    # RAG Configuration
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
    VECTOR_SIZE = int(os.getenv("VECTOR_SIZE", "1536"))
    DEFAULT_TOP_K = int(os.getenv("DEFAULT_TOP_K", "5"))
    
    @classmethod
    def validate(cls):
        """Validate that required configuration is present"""
        if not cls.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required but not set")
        if not cls.QDRANT_API_KEY:
            raise ValueError("QDRANT_API_KEY is required but not set")
        if not cls.QDRANT_URL:
            raise ValueError("QDRANT_URL is required but not set")
        if not cls.MONGODB_URI:
            raise ValueError("MONGODB_URI is required but not set")


# Create a singleton config instance
config = Config()

