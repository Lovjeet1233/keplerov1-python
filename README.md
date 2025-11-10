# RAG Service API

A Retrieval-Augmented Generation (RAG) service built with FastAPI, Qdrant, and OpenAI for chatbot functionality with multiple data ingestion sources.

## Features

- **Multiple Data Sources**: Ingest data from PDFs, websites, and Excel files
- **Vector Search**: Powered by Qdrant with OpenAI embeddings
- **LangGraph Workflow**: Two-node architecture (retrieve → generate) with memory checkpointer
- **Conversation Memory**: Support for multi-turn conversations via thread_id
- **REST API**: Easy-to-use FastAPI endpoints
- **Collection Management**: Create and delete Qdrant collections
- **Centralized Logging**: Comprehensive logging for debugging and monitoring

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables:
Create a `.env` file in the project root:
```env
# Qdrant Configuration
QDRANT_URL=https://your-qdrant-instance.cloud.qdrant.io
QDRANT_API_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.Mr-rW6Q25j3PE6lJ1ciP1JEaRxkE66lzlBcM2HbQuLI

# OpenAI Configuration
OPENAI_API_KEY=your-openai-api-key

# API Configuration (optional)
API_HOST=0.0.0.0
API_PORT=8000

# RAG Configuration (optional)
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
```

3. Run the API:
```bash
python api.py
```

The API will be available at `http://localhost:8000`

## API Endpoints

### 1. Chat Endpoint
Retrieve relevant documents from the knowledge base.

**Endpoint**: `POST /chat`

**Request Body**:
```json
{
  "query": "What is machine learning?",
  "collection_name": "my_collection",
  "top_k": 5,
  "thread_id": "user-123"
}
```

**Response**:
```json
{
  "query": "What is machine learning?",
  "answer": "Machine learning is a subset of artificial intelligence...",
  "retrieved_docs": [
    {
      "text": "Machine learning is...",
      "score": 0.95,
      "chunk_index": 0
    }
  ],
  "context": "Document 1 (Score: 0.950):\nMachine learning is...",
  "thread_id": "user-123"
}
```

**Example using curl**:
```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is machine learning?",
    "collection_name": "my_collection",
    "top_k": 5,
    "thread_id": "user-123"
  }'
```

**Note**: The `thread_id` parameter is optional but recommended for maintaining conversation context across multiple requests. Use the same thread_id for a conversation session.

### 2. Create Collection Endpoint
Create a new collection in Qdrant for storing document embeddings.

**Endpoint**: `POST /create_collection`

**Request Body**:
```json
{
  "collection_name": "my_collection"
}
```

**Response**:
```json
{
  "status": "success",
  "message": "Collection 'my_collection' created successfully",
  "details": {
    "vector_size": 1536,
    "distance_metric": "cosine"
  }
}
```

**Example using curl**:
```bash
curl -X POST "http://localhost:8000/create_collection" \
  -H "Content-Type: application/json" \
  -d '{
    "collection_name": "my_collection"
  }'
```

**Note**: Collections are automatically created during data ingestion if they don't exist, but you can use this endpoint to pre-create collections.

### 3. Data Ingestion Endpoint
Ingest data from various sources into a collection. **Supports multiple sources simultaneously with parallel processing!**

**Endpoint**: `POST /data_ingestion`

**Request Parameters**:
- `collection_name` (form): Name of the collection
- `url_links` (form, optional): Comma-separated URLs for website scraping
- `pdf_files` (file[], optional): Multiple PDF files to upload
- `excel_files` (file[], optional): Multiple Excel files to upload

**Example - Ingest from Single URL**:
```bash
curl -X POST "http://localhost:8000/data_ingestion" \
  -F "collection_name=my_collection" \
  -F "url_links=https://example.com/article"
```

**Example - Ingest from Multiple URLs**:
```bash
curl -X POST "http://localhost:8000/data_ingestion" \
  -F "collection_name=my_collection" \
  -F "url_links=https://example.com/article1,https://example.com/article2"
```

**Example - Ingest from Multiple PDFs**:
```bash
curl -X POST "http://localhost:8000/data_ingestion" \
  -F "collection_name=my_collection" \
  -F "pdf_files=@/path/to/document1.pdf" \
  -F "pdf_files=@/path/to/document2.pdf"
```

**Example - Ingest from Multiple Sources (Parallel)**:
```bash
curl -X POST "http://localhost:8000/data_ingestion" \
  -F "collection_name=my_collection" \
  -F "url_links=https://example.com/article" \
  -F "pdf_files=@/path/to/document.pdf" \
  -F "excel_files=@/path/to/data.xlsx"
```

**Response**:
```json
{
  "status": "success",
  "message": "Successfully ingested 1 URL(s), 1 PDF(s), 1 Excel file(s) into collection 'my_collection'",
  "details": {
    "status": "success",
    "total_chunks_loaded": 156,
    "sources_processed": 3,
    "sources_failed": 0,
    "successful_sources": [
      {"source": "URL: https://example.com/article", "chunks": 45},
      {"source": "PDF: /tmp/tmpxxx.pdf", "chunks": 67},
      {"source": "Excel: /tmp/tmpyyy.xlsx", "chunks": 44}
    ],
    "failed_sources": null
  }
}
```

**Note**: All sources are processed **in parallel** for maximum performance. If one source fails, others will still be processed.

### 4. Delete Collection Endpoint
Delete a collection from Qdrant.

**Endpoint**: `POST /delete_collection`

**Request Body**:
```json
{
  "collection_name": "my_collection"
}
```

**Response**:
```json
{
  "status": "success",
  "message": "Collection 'my_collection' deleted successfully"
}
```

**Example using curl**:
```bash
curl -X POST "http://localhost:8000/delete_collection" \
  -H "Content-Type: application/json" \
  -d '{
    "collection_name": "my_collection"
  }'
```

## Testing the API

### Interactive API Documentation

Once the server is running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Example Workflow

1. **Create a collection** (optional - automatically created during ingestion):
```bash
curl -X POST "http://localhost:8000/create_collection" \
  -H "Content-Type: application/json" \
  -d '{
    "collection_name": "tech_docs"
  }'
```

2. **Ingest data from multiple sources in parallel**:
```bash
curl -X POST "http://localhost:8000/data_ingestion" \
  -F "collection_name=tech_docs" \
  -F "url_links=https://en.wikipedia.org/wiki/Machine_learning,https://en.wikipedia.org/wiki/Deep_learning" \
  -F "pdf_files=@/path/to/ml_book.pdf"
```

3. **Query the collection**:
```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is supervised learning?",
    "collection_name": "tech_docs",
    "top_k": 3
  }'
```

4. **Delete the collection** (when done):
```bash
curl -X POST "http://localhost:8000/delete_collection" \
  -H "Content-Type: application/json" \
  -d '{
    "collection_name": "tech_docs"
  }'
```

## Project Structure

```
.
├── config/
│   ├── __init__.py
│   ├── settings.py      # Configuration management with environment variables
│   └── prompt.py        # System prompts for RAG
├── utils/
│   ├── __init__.py
│   └── logger.py        # Centralized logging system
├── workflow/
│   ├── __init__.py
│   └── graph.py         # LangGraph workflow with retrieve & generate nodes
├── logs/                # Log files directory (auto-created)
├── RAGService.py        # Core RAG service implementation
├── api.py               # FastAPI application with endpoints
├── requirements.txt     # Python dependencies
├── .env                 # Environment variables (create this file)
├── .gitignore          # Git ignore rules
└── README.md           # This file
```

## LangGraph Workflow Architecture

The chat endpoint uses a LangGraph workflow with two nodes and memory checkpointer:

```
┌─────────────────────────────────────────────────┐
│           User Query + Collection               │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
         ┌───────────────┐
         │  Entry Point  │
         └───────┬───────┘
                 │
                 ▼
         ┌───────────────┐
         │ Retrieve Node │  ◄── Searches Qdrant vector DB
         │               │      Retrieves top-k documents
         └───────┬───────┘
                 │
                 ▼
         ┌───────────────┐
         │ Generate Node │  ◄── Uses OpenAI GPT-3.5-turbo
         │               │      Generates answer from context
         └───────┬───────┘
                 │
                 ▼
         ┌───────────────┐
         │   Response    │  ◄── Answer + Retrieved Docs
         └───────────────┘
```

### Workflow Features:

1. **Retrieve Node**: 
   - Searches the vector database using the user's query
   - Retrieves top-k most relevant documents
   - Formats context from retrieved documents

2. **Generate Node**:
   - Takes retrieved context and user query
   - Uses OpenAI to generate a comprehensive answer
   - Returns structured response with sources

3. **Memory Checkpointer**:
   - In-memory storage for conversation history during session
   - Maintains context across multiple turns using `thread_id`
   - Enables follow-up questions and contextual responses
   - Note: Memory is cleared when the server restarts

## RAGService Class Methods

### Data Ingestion Methods
- `data_ingestion_pdf(pdf_path)`: Extract text from PDF files
- `data_ingestion_websites(url)`: Extract text from websites
- `data_ingestion_excel(excel_path)`: Extract text from Excel files

### Collection Management
- `create_collection(collection_name)`: Create a new Qdrant collection
- `delete_collection(collection_name)`: Delete a Qdrant collection

### Data Loading and Retrieval
- `load_data_to_qdrant(collection_name, url_link, pdf_file, excel_file)`: Load data into Qdrant with embeddings
- `retrieval_based_search(query, collection_name, top_k)`: Perform vector search

## Logging

The application includes a centralized logging system that:
- Logs all API requests and responses
- Tracks errors and exceptions with full stack traces
- Writes logs to both console and files
- Creates daily log files in the `logs/` directory
- Formats logs with timestamps, log levels, and source information

Log files are automatically created in the `logs/` directory with the format: `RAGService_YYYYMMDD.log`

## Technical Details

- **Vector Size**: 1536 (OpenAI embeddings)
- **Distance Metric**: Cosine similarity
- **Text Splitting**: Recursive character text splitter (chunk_size=1000, chunk_overlap=200)
- **Web Framework**: FastAPI with async support
- **Vector Database**: Qdrant
- **Logging**: Centralized logging with file and console output
- **Parallel Processing**: Async data ingestion with ThreadPoolExecutor for concurrent processing of multiple sources

### Data Ingestion Performance

The API supports **parallel data ingestion** from multiple sources:
- Process URLs, PDFs, and Excel files simultaneously
- Use `asyncio.gather()` for concurrent execution
- Each source is processed independently - if one fails, others continue
- Significantly faster when ingesting multiple documents
- Example: Ingesting 3 URLs + 2 PDFs simultaneously is ~5x faster than sequential processing

## Requirements

- Python 3.8+
- OpenAI API key
- Qdrant instance (cloud or local)

## License

MIT License

