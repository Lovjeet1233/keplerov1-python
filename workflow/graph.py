"""
LangGraph workflow for RAG-based chat with memory checkpointer
"""

from typing import TypedDict, List, Optional, Annotated
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.mongodb import MongoDBSaver
from pymongo import MongoClient
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from config.prompt import SYSTEM_PROMPT, RAG_PROMPT_TEMPLATE
from utils.logger import log_info, log_error, log_debug, log_warning


class GraphState(TypedDict):
    """
    State for the RAG workflow graph
    
    Attributes:
        query: User's question
        collection_name: Name of the Qdrant collection (deprecated, for backward compatibility)
        collection_names: List of logical collection names to search in
        top_k: Number of documents to retrieve
        retrieved_docs: Retrieved documents from knowledge base
        context: Formatted context from retrieved docs
        answer: Generated answer
        thread_id: Thread ID for conversation memory
        conversation_history: List of previous Q&A pairs
        system_prompt: Custom system prompt (optional)
        provider: LLM provider ("openai" or "gemini")
        api_key: API key for the provider
    """
    query: str
    collection_name: Optional[str]  # Deprecated
    collection_names: Optional[List[str]]  # New: supports multiple collections
    top_k: int
    retrieved_docs: List[dict]
    context: str
    answer: str
    thread_id: Optional[str]
    conversation_history: List[dict]
    system_prompt: Optional[str]
    provider: Optional[str]
    api_key: Optional[str]


class RAGWorkflow:
    """
    RAG Workflow using LangGraph with memory checkpointer
    """
    
    def __init__(self, rag_service, openai_api_key: str, mongodb_uri: str, memory_enabled: bool = True):
        """
        Initialize RAG Workflow
        
        Args:
            rag_service: RAGService instance for retrieval
            openai_api_key: OpenAI API key
            mongodb_uri: MongoDB connection URI
            memory_enabled: Enable memory checkpointing (default: True)
        """
        self.rag_service = rag_service
        self.memory_enabled = memory_enabled
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",  # Faster and cheaper than gpt-4.1-mini
            temperature=0.3,
            openai_api_key=openai_api_key
        )
        
        # OPTIMIZATION: Cache LLM instances to avoid re-initialization overhead
        self.llm_cache = {}  # key: (provider, api_key_hash) -> value: LLM instance
        
        # Initialize MongoDB checkpointer if memory is enabled
        self.memory = None
        if self.memory_enabled:
            try:
                client = MongoClient(mongodb_uri)
                # Use a new checkpoint collection name to avoid compatibility issues
                self.memory = MongoDBSaver(
                    client=client,
                    db_name="python",
                    checkpoint_collection_name="checkpoints_v2"
                )
                log_info("MongoDB checkpointer initialized with new collection")
            except Exception as e:
                log_error(f"Failed to initialize MongoDB checkpointer: {str(e)}")
                log_warning("Continuing without memory checkpointing")
                self.memory_enabled = False
                self.memory = None
        
        # Build the graph
        self.graph = self._build_graph()
        
        if self.memory_enabled:
            log_info("RAG Workflow initialized with MongoDB checkpointer enabled")
        else:
            log_info("RAG Workflow initialized without memory checkpointing")
    
    def _get_cached_llm(self, provider: str, api_key: Optional[str] = None):
        """
        Get or create a cached LLM instance to avoid re-initialization overhead.
        
        Args:
            provider: LLM provider ("openai" or "gemini")
            api_key: Optional API key for the provider
            
        Returns:
            Cached or newly created LLM instance
        """
        # Create cache key
        cache_key = (provider.lower(), api_key[:20] if api_key else "default")
        
        # Return cached instance if exists
        if cache_key in self.llm_cache:
            log_debug(f"Using cached LLM instance for {provider}")
            return self.llm_cache[cache_key]
        
        # Create new LLM instance
        log_info(f"Creating new LLM instance for {provider}")
        
        if provider.lower() == "gemini":
            if not api_key:
                raise ValueError("Gemini provider requires an API key")
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash-lite",  # OPTIMIZED: Changed from gemini-2.5-pro (5-10x faster)
                temperature=0.3,
                google_api_key=api_key
            )
        else:  # default to OpenAI
            if api_key:
                llm = ChatOpenAI(
                    model="gpt-4o-mini",
                    temperature=0.3,
                    openai_api_key=api_key
                )
            else:
                llm = self.llm  # Use default configured LLM
        
        # Cache the instance
        self.llm_cache[cache_key] = llm
        return llm
    
    def clear_llm_cache(self):
        """Clear the LLM cache (useful if API keys change or memory needs to be freed)"""
        self.llm_cache.clear()
        log_info("LLM cache cleared")
    
    def _build_graph(self) -> StateGraph:
        """
        Build the LangGraph workflow
        
        Returns:
            Compiled StateGraph
        """
        # Create the graph
        workflow = StateGraph(GraphState)
        
        # Add nodes
        workflow.add_node("retrieve", self.retrieve_node)
        workflow.add_node("generate", self.generate_node)
        
        # Define edges
        workflow.set_entry_point("retrieve")
        workflow.add_edge("retrieve", "generate")
        workflow.add_edge("generate", END)
        
        # Compile with or without memory
        if self.memory_enabled and self.memory:
            app = workflow.compile(checkpointer=self.memory)
            log_info("LangGraph workflow compiled successfully with memory checkpointer")
        else:
            app = workflow.compile()
            log_info("LangGraph workflow compiled successfully without memory checkpointer")
        
        return app
    
    def retrieve_node(self, state: GraphState) -> GraphState:
        """
        Retrieve relevant documents from the knowledge base.
        Supports multiple logical collections stored in a single Qdrant collection.
        
        Args:
            state: Current graph state
            
        Returns:
            Updated state with retrieved documents
        """
        import time as perf_time
        retrieve_start = perf_time.time()
        
        try:
            # Get collection names from state (supports both old and new format)
            collections = None
            if state.get("collection_names"):
                collections = state["collection_names"]
            elif state.get("collection_name"):
                collections = [state["collection_name"]]
            
            # If collections is empty list or None, search ALL documents
            if collections:
                log_debug(f"Retrieving documents from collections: {collections} for query: '{state['query']}'")
            else:
                log_debug(f"Retrieving documents from ALL collections for query: '{state['query']}'")
            
            # Retrieve documents using RAG service with multiple collections support
            # If collections is None or empty, searches all documents
            retrieved_docs = self.rag_service.retrieval_based_search(
                query=state["query"],
                collections=collections,
                top_k=state.get("top_k", 5)
            )
            
            log_info(f"⏱️ RETRIEVE: Completed in {(perf_time.time() - retrieve_start)*1000:.0f}ms")
            
            # Format context from retrieved documents
            if retrieved_docs:
                context = "\n\n".join([
                    f"Document {i+1} (from {doc.get('collection', 'unknown')}, Score: {doc['score']:.3f}):\n{doc['text']}"
                    for i, doc in enumerate(retrieved_docs)
                ])
                collection_count = len(collections) if collections else "all"
                log_info(f"Retrieved {len(retrieved_docs)} documents from {collection_count} collection(s)")
            else:
                context = "No relevant documents found in the knowledge base."
                log_info("No documents retrieved")
            
            # Update state
            state["retrieved_docs"] = retrieved_docs
            state["context"] = context
            
            return state
        
        except Exception as e:
            log_error(f"Error in retrieve node: {str(e)}")
            state["retrieved_docs"] = []
            state["context"] = "Error retrieving documents from knowledge base."
            return state
    
    def generate_node(self, state: GraphState) -> GraphState:
        """
        Generate answer based on retrieved context and conversation history
        
        Args:
            state: Current graph state
            
        Returns:
            Updated state with generated answer
        """
        import time as perf_time
        generate_start = perf_time.time()
        
        try:
            log_debug("Generating answer based on retrieved context and conversation history")
            
            # OPTIMIZATION: Use cached LLM instance to avoid re-initialization overhead
            provider = state.get("provider", "openai").lower()
            api_key = state.get("api_key")
            
            try:
                llm = self._get_cached_llm(provider, api_key)
                log_info(f"Using {provider} LLM (cached: {(provider, api_key[:20] if api_key else 'default') in self.llm_cache})")
            except ValueError as e:
                log_error(f"Error getting LLM: {str(e)}")
                state["answer"] = f"Error: {str(e)}"
                return state
            
            # Build conversation history context (OPTIMIZED: minimal format)
            history_context = ""
            if state.get("conversation_history"):
                history_items = []
                for item in state["conversation_history"][-2:]:  # Last 2 turns only
                    # Truncate long answers to save tokens (150 chars max)
                    answer_preview = item['answer'][:150] + "..." if len(item['answer']) > 150 else item['answer']
                    history_items.append(f"Q: {item['query']}\nA: {answer_preview}")
                if history_items:
                    history_context = "\n\nHistory:\n" + "\n".join(history_items)
            
            # Check if we have context from retrieval
            has_retrieval_context = (
                state.get("context") and 
                state["context"] != "No relevant documents found in the knowledge base." and
                state["context"] != "Error retrieving documents from knowledge base."
            )
            
            # Build the prompt based on available information
            # Use custom system prompt if provided, otherwise use default
            system_prompt_content = state.get("system_prompt") or SYSTEM_PROMPT
            messages = [SystemMessage(content=system_prompt_content)]
            
            if has_retrieval_context:
                # Use RAG template with retrieved context
                # OPTIMIZATION: Truncate context if too long (save tokens = faster generation)
                context_text = state["context"]
                if len(context_text) > 3000:  # Limit context to ~3000 chars
                    context_text = context_text[:3000] + "\n...(context truncated for speed)"
                
                prompt = RAG_PROMPT_TEMPLATE.format(
                    context=context_text,
                    question=state["query"]
                )
                if history_context:
                    prompt = history_context + "\n\n" + prompt
                messages.append(HumanMessage(content=prompt))
            else:
                # No retrieval context, but we might have conversation history
                if history_context:
                    prompt = f"{history_context}\n\nCurrent question: {state['query']}\n\nPlease answer based on our conversation history."
                    messages.append(HumanMessage(content=prompt))
                else:
                    state["answer"] = "I don't have enough information in the knowledge base to answer your question. Please try rephrasing or ask about a different topic."
                    return state
            
            # Generate answer using LLM (dynamic based on provider)
            llm_start = perf_time.time()
            response = llm.invoke(messages)
            state["answer"] = response.content
            log_info(f"⏱️ LLM CALL: Completed in {(perf_time.time() - llm_start)*1000:.0f}ms (provider: {provider})")
            
            # Update conversation history
            if not state.get("conversation_history"):
                state["conversation_history"] = []
            
            state["conversation_history"].append({
                "query": state["query"],
                "answer": state["answer"]
            })
            
            log_info(f"⏱️ GENERATE: Total node completed in {(perf_time.time() - generate_start)*1000:.0f}ms")
            log_debug(f"Generated answer: {state['answer'][:100]}...")
            
            return state
        
        except Exception as e:
            log_error(f"Error in generate node: {str(e)}")
            state["answer"] = "I encountered an error while generating the answer. Please try again."
            return state
    
    def run(
        self,
        query: str,
        collection_name: Optional[str] = None,
        collection_names: Optional[List[str]] = None,
        top_k: int = 5,
        thread_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        provider: Optional[str] = "openai",
        api_key: Optional[str] = None,
        skip_history: bool = False
    ) -> dict:
        """
        Run the RAG workflow with conversation memory.
        Supports querying multiple logical collections stored in a single Qdrant collection.
        
        Args:
            query: User's question
            collection_name: Single collection name (deprecated, for backward compatibility)
            collection_names: List of logical collection names to search in
            top_k: Number of documents to retrieve
            thread_id: Optional thread ID for conversation memory
            system_prompt: Optional custom system prompt (uses default if not provided)
            provider: LLM provider to use ("openai" or "gemini", default: "openai")
            api_key: Optional API key for the provider
            skip_history: Skip conversation history lookup for faster responses (default: False)
            
        Returns:
            Dictionary with answer and retrieved documents
        """
        import time as perf_time  # For performance timing
        
        try:
            run_start = perf_time.time()
            
            # Determine which collections to use
            collections = []
            if collection_names:
                collections = collection_names
            elif collection_name:
                collections = [collection_name]
            
            log_info(f"Running RAG workflow for query: '{query}' (collections: {collections}, thread: {thread_id or 'default'})")
            
            # Configuration for thread
            config = {
                "configurable": {
                    "thread_id": thread_id or "default"
                }
            }
            
            # OPTIMIZATION: Retrieve conversation history from checkpointer (optional for performance)
            conversation_history = []
            if not skip_history and thread_id:  # Only fetch history if thread_id is provided
                history_start = perf_time.time()
                try:
                    # Get the latest state from checkpointer for this thread
                    state_snapshot = self.graph.get_state(config)
                    if state_snapshot and hasattr(state_snapshot, 'values') and state_snapshot.values:
                        existing_history = state_snapshot.values.get("conversation_history", [])
                        if existing_history:
                            conversation_history = existing_history
                            log_info(f"Retrieved {len(conversation_history)} previous conversation turns in {(perf_time.time() - history_start)*1000:.0f}ms")
                except Exception as e:
                    log_debug(f"No previous conversation history found or error retrieving: {str(e)}")
            else:
                log_debug("Skipping conversation history lookup (no thread_id or skip_history=True)")
            
            # Initialize state with conversation history
            initial_state = {
                "query": query,
                "collection_name": collection_name,  # Keep for backward compatibility
                "collection_names": collections,  # New: support multiple collections
                "top_k": top_k,
                "retrieved_docs": [],
                "context": "",
                "answer": "",
                "thread_id": thread_id,
                "conversation_history": conversation_history,
                "system_prompt": system_prompt,
                "provider": provider,
                "api_key": api_key
            }
            
            # Execute the workflow
            try:
                result = self.graph.invoke(initial_state, config)
            except ValueError as ve:
                import traceback
                log_error(f"ValueError during workflow execution: {str(ve)}")
                log_error(f"Traceback:\n{traceback.format_exc()}")
                raise
            except TypeError as te:
                import traceback
                log_error(f"TypeError during workflow execution: {str(te)}")
                log_error(f"Traceback:\n{traceback.format_exc()}")
                raise
            
            total_time = (perf_time.time() - run_start) * 1000
            log_info(f"⏱️ WORKFLOW TOTAL: Completed in {total_time:.0f}ms")
            
            return {
                "answer": result["answer"],
                "retrieved_docs": result["retrieved_docs"],
                "context": result["context"],
                "thread_id": thread_id or "default",
                "conversation_history": result.get("conversation_history", [])
            }
        
        except Exception as e:
            import traceback
            log_error(f"Error running RAG workflow: {str(e)}")
            log_error(f"Full traceback:\n{traceback.format_exc()}")
            return {
                "answer": "An error occurred while processing your request.",
                "retrieved_docs": [],
                "context": "",
                "thread_id": thread_id or "default",
                "conversation_history": []
            }
    
    def get_conversation_history(self, thread_id: str) -> list:
        """
        Get conversation history for a thread
        
        Args:
            thread_id: Thread ID
            
        Returns:
            List of conversation Q&A pairs
        """
        try:
            log_info(f"Retrieving conversation history for thread: {thread_id}")
            
            config = {
                "configurable": {
                    "thread_id": thread_id
                }
            }
            
            # Get the latest state from checkpointer
            state_snapshot = self.graph.get_state(config)
            if state_snapshot and hasattr(state_snapshot, 'values') and state_snapshot.values:
                history = state_snapshot.values.get("conversation_history", [])
                log_info(f"Found {len(history)} conversation turns")
                return history
            
            return []
        except Exception as e:
            log_error(f"Error retrieving conversation history: {str(e)}")
            return []


def create_rag_workflow(
    rag_service, 
    openai_api_key: str, 
    mongodb_uri: str,
    memory_enabled: bool = True
) -> RAGWorkflow:
    """
    Factory function to create RAG workflow
    
    Args:
        rag_service: RAGService instance
        openai_api_key: OpenAI API key
        mongodb_uri: MongoDB connection URI
        memory_enabled: Enable memory checkpointing (default: True)
        
    Returns:
        RAGWorkflow instance
    """
    return RAGWorkflow(rag_service, openai_api_key, mongodb_uri, memory_enabled)

