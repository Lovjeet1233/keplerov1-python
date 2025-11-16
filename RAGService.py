import os
import pdfplumber
import pandas as pd
import requests
from bs4 import BeautifulSoup
from typing import List, Optional, Union
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import uuid
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor


class RAGService:
    """
    RAG Service for chatbot with data ingestion and retrieval capabilities.
    """
    
    def __init__(self, qdrant_url: str, qdrant_api_key: str, openai_api_key: str):
        """
        Initialize RAG Service with Qdrant and OpenAI credentials.
        
        Args:
            qdrant_url: URL for Qdrant instance
            qdrant_api_key: API key for Qdrant
            openai_api_key: API key for OpenAI
        """
        self.qdrant_client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
        self.embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key)
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len
        )
        self.executor = ThreadPoolExecutor(max_workers=5)
    
    def data_ingestion_pdf(self, pdf_path: str) -> str:
        """
        Extract text from PDF files using pdfplumber.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Extracted text from the PDF
        """
        text = ""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            return text
        except Exception as e:
            raise Exception(f"Error reading PDF: {str(e)}")
    
    def data_ingestion_websites(self, url: str) -> str:
        """
        Extract text from websites using BeautifulSoup.
        
        Args:
            url: URL of the website
            
        Returns:
            Extracted text from the website
        """
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get text
            text = soup.get_text()
            
            # Clean up text
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            
            return text
        except Exception as e:
            raise Exception(f"Error fetching website: {str(e)}")
    
    def data_ingestion_excel(self, excel_path: str) -> str:
        """
        Extract text from Excel files using pandas.
        
        Args:
            excel_path: Path to the Excel file
            
        Returns:
            Extracted text from the Excel file
        """
        try:
            df = pd.read_excel(excel_path)
            text = df.to_string(index=False)
            return text
        except Exception as e:
            raise Exception(f"Error reading Excel: {str(e)}")
    
    def create_collection(self, collection_name: str):
        """
        Create a collection in Qdrant with vector_size 1536 and cosine metric.
        
        Args:
            collection_name: Name of the collection to create
        """
        try:
            # Check if collection already exists
            collections = self.qdrant_client.get_collections().collections
            if any(col.name == collection_name for col in collections):
                print(f"Collection {collection_name} already exists.")
                return
            
            self.qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=1536, distance=Distance.COSINE)
            )
            print(f"Collection {collection_name} created successfully.")
        except Exception as e:
            raise Exception(f"Error creating collection: {str(e)}")
    
    def delete_collection(self, collection_name: str):
        """
        Delete a collection from Qdrant.
        
        Args:
            collection_name: Name of the collection to delete
        """
        try:
            self.qdrant_client.delete_collection(collection_name=collection_name)
            print(f"Collection {collection_name} deleted successfully.")
        except Exception as e:
            raise Exception(f"Error deleting collection: {str(e)}")
    
    def load_data_to_qdrant(
        self,
        collection_name: str,
        url_link: Optional[str] = None,
        pdf_file: Optional[str] = None,
        excel_file: Optional[str] = None
    ):
        """
        Load data into Qdrant using OpenAI Embeddings and recursive text splitter.
        
        Args:
            collection_name: Name of the collection
            url_link: URL to scrape (optional)
            pdf_file: Path to PDF file (optional)
            excel_file: Path to Excel file (optional)
        """
        try:
            # Ensure collection exists
            self.create_collection(collection_name)
            
            # Extract text based on source type
            text = ""
            if url_link:
                text = self.data_ingestion_websites(url_link)
            elif pdf_file:
                text = self.data_ingestion_pdf(pdf_file)
            elif excel_file:
                text = self.data_ingestion_excel(excel_file)
            else:
                raise ValueError("At least one data source must be provided")
            
            # Split text into chunks
            chunks = self.text_splitter.split_text(text)
            
            # Generate embeddings and prepare points
            points = []
            for i, chunk in enumerate(chunks):
                embedding = self.embeddings.embed_query(chunk)
                point = PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding,
                    payload={"text": chunk, "chunk_index": i}
                )
                points.append(point)
            
            # Upload to Qdrant
            self.qdrant_client.upsert(
                collection_name=collection_name,
                points=points
            )
            
            print(f"Successfully loaded {len(chunks)} chunks to collection {collection_name}")
            return {"status": "success", "chunks_loaded": len(chunks)}
        
        except Exception as e:
            raise Exception(f"Error loading data to Qdrant: {str(e)}")
    
    def retrieval_based_search(self, query: str, collection_name: str, top_k: int = 5) -> List[dict]:
        """
        Perform vector search to retrieve relevant documents from the corpus.
        
        Args:
            query: Search query
            collection_name: Name of the collection to search in
            top_k: Number of top results to return
            
        Returns:
            List of relevant documents with scores
        """
        try:
            # Generate query embedding
            query_embedding = self.embeddings.embed_query(query)
            
            # Search in Qdrant
            search_results = self.qdrant_client.search(
                collection_name=collection_name,
                query_vector=query_embedding,
                limit=top_k
            )
            
            # Format results
            results = []
            for result in search_results:
                results.append({
                    "text": result.payload.get("text", ""),
                    "score": result.score,
                    "chunk_index": result.payload.get("chunk_index", 0)
                })
            
            return results
        
        except Exception as e:
            raise Exception(f"Error performing search: {str(e)}")
    
    async def async_data_ingestion_pdf(self, pdf_path: str) -> str:
        """
        Async extract text from PDF files using pdfplumber.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Extracted text from the PDF
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self.data_ingestion_pdf, pdf_path)
    
    async def async_data_ingestion_websites(self, url: str) -> str:
        """
        Async extract text from websites using BeautifulSoup.
        
        Args:
            url: URL of the website
            
        Returns:
            Extracted text from the website
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self.data_ingestion_websites, url)
    
    async def async_data_ingestion_excel(self, excel_path: str) -> str:
        """
        Async extract text from Excel files using pandas.
        
        Args:
            excel_path: Path to the Excel file
            
        Returns:
            Extracted text from the Excel file
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self.data_ingestion_excel, excel_path)
    
    async def load_data_to_qdrant_async(
        self,
        collection_name: str,
        url_links: Optional[List[str]] = None,
        pdf_files: Optional[List[str]] = None,
        excel_files: Optional[List[str]] = None
    ):
        """
        Async load data into Qdrant from multiple sources in parallel.
        
        Args:
            collection_name: Name of the collection
            url_links: List of URLs to scrape (optional)
            pdf_files: List of PDF file paths (optional)
            excel_files: List of Excel file paths (optional)
            
        Returns:
            Dictionary with ingestion results
        """
        try:
            # Ensure collection exists
            self.create_collection(collection_name)
            
            # Collect all text extraction tasks
            tasks = []
            source_types = []
            
            if url_links:
                for url in url_links:
                    tasks.append(self.async_data_ingestion_websites(url))
                    source_types.append(f"URL: {url}")
            
            if pdf_files:
                for pdf_file in pdf_files:
                    tasks.append(self.async_data_ingestion_pdf(pdf_file))
                    source_types.append(f"PDF: {pdf_file}")
            
            if excel_files:
                for excel_file in excel_files:
                    tasks.append(self.async_data_ingestion_excel(excel_file))
                    source_types.append(f"Excel: {excel_file}")
            
            if not tasks:
                raise ValueError("At least one data source must be provided")
            
            # Execute all extraction tasks in parallel
            print(f"Starting parallel ingestion of {len(tasks)} sources...")
            texts = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results and prepare chunks
            all_chunks = []
            successful_sources = []
            failed_sources = []
            
            for i, (text, source_type) in enumerate(zip(texts, source_types)):
                if isinstance(text, Exception):
                    print(f"Failed to ingest {source_type}: {str(text)}")
                    failed_sources.append({"source": source_type, "error": str(text)})
                    continue
                
                # Split text into chunks
                chunks = self.text_splitter.split_text(text)
                all_chunks.extend(chunks)
                successful_sources.append({"source": source_type, "chunks": len(chunks)})
                print(f"Successfully extracted {len(chunks)} chunks from {source_type}")
            
            if not all_chunks:
                raise Exception("No data was successfully extracted from any source")
            
            # Generate embeddings and prepare points
            print(f"Generating embeddings for {len(all_chunks)} chunks...")
            points = []
            for i, chunk in enumerate(all_chunks):
                embedding = self.embeddings.embed_query(chunk)
                point = PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding,
                    payload={"text": chunk, "chunk_index": i}
                )
                points.append(point)
            
            # Upload to Qdrant
            self.qdrant_client.upsert(
                collection_name=collection_name,
                points=points
            )
            
            print(f"Successfully loaded {len(all_chunks)} chunks to collection {collection_name}")
            
            return {
                "status": "success",
                "total_chunks_loaded": len(all_chunks),
                "sources_processed": len(successful_sources),
                "sources_failed": len(failed_sources),
                "successful_sources": successful_sources,
                "failed_sources": failed_sources if failed_sources else None
            }
        
        except Exception as e:
            raise Exception(f"Error loading data to Qdrant: {str(e)}")
