"""
LangGraph workflow for RAG-based chat with memory checkpointer
"""

from typing import TypedDict, List, Optional, Annotated
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.mongodb import MongoDBSaver
from pymongo import MongoClient
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
from config.prompt import SYSTEM_PROMPT, RAG_PROMPT_TEMPLATE
from utils.logger import log_info, log_error, log_debug


class GraphState(TypedDict):
    """
    State for the RAG workflow graph
    
    Attributes:
        query: User's question
        collection_name: Name of the Qdrant collection
        top_k: Number of documents to retrieve
        retrieved_docs: Retrieved documents from knowledge base
        context: Formatted context from retrieved docs
        answer: Generated answer
        thread_id: Thread ID for conversation memory
        conversation_history: List of previous Q&A pairs
        system_prompt: Custom system prompt (optional)
    """
    query: str
    collection_name: str
    top_k: int
    retrieved_docs: List[dict]
    context: str
    answer: str
    thread_id: Optional[str]
    conversation_history: List[dict]
    system_prompt: Optional[str]


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
            model="gpt-3.5-turbo",
            temperature=0.7,
            openai_api_key=openai_api_key
        )
        
        # Initialize MongoDB checkpointer if memory is enabled
        self.memory = None
        if self.memory_enabled:
            client = MongoClient(mongodb_uri)
            self.memory = MongoDBSaver(
                client=client,
                db_name="python",
                checkpoint_collection_name="checkpoints"
            )
            log_info("MongoDB checkpointer initialized")
        
        # Build the graph
        self.graph = self._build_graph()
        
        if self.memory_enabled:
            log_info("RAG Workflow initialized with MongoDB checkpointer enabled")
        else:
            log_info("RAG Workflow initialized without memory checkpointing")
    
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
        Retrieve relevant documents from the knowledge base
        
        Args:
            state: Current graph state
            
        Returns:
            Updated state with retrieved documents
        """
        try:
            log_info(f"Retrieving documents for query: '{state['query']}'")
            
            # Retrieve documents using RAG service
            retrieved_docs = self.rag_service.retrieval_based_search(
                query=state["query"],
                collection_name=state["collection_name"],
                top_k=state.get("top_k", 5)
            )
            
            # Format context from retrieved documents
            if retrieved_docs:
                context = "\n\n".join([
                    f"Document {i+1} (Score: {doc['score']:.3f}):\n{doc['text']}"
                    for i, doc in enumerate(retrieved_docs)
                ])
                log_info(f"Retrieved {len(retrieved_docs)} documents")
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
        try:
            log_info("Generating answer based on retrieved context and conversation history")
            
            # Build conversation history context
            history_context = ""
            if state.get("conversation_history"):
                history_items = []
                for item in state["conversation_history"][-3:]:  # Last 3 turns
                    history_items.append(f"User: {item['query']}\nAssistant: {item['answer']}")
                if history_items:
                    history_context = "\n\nPrevious conversation:\n" + "\n\n".join(history_items)
            
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
                prompt = RAG_PROMPT_TEMPLATE.format(
                    context=state["context"],
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
            
            # Generate answer using LLM
            response = self.llm.invoke(messages)
            state["answer"] = response.content
            
            # Update conversation history
            if not state.get("conversation_history"):
                state["conversation_history"] = []
            
            state["conversation_history"].append({
                "query": state["query"],
                "answer": state["answer"]
            })
            
            log_info("Answer generated successfully")
            log_debug(f"Generated answer: {state['answer'][:100]}...")
            
            return state
        
        except Exception as e:
            log_error(f"Error in generate node: {str(e)}")
            state["answer"] = "I encountered an error while generating the answer. Please try again."
            return state
    
    def run(
        self,
        query: str,
        collection_name: str,
        top_k: int = 5,
        thread_id: Optional[str] = None,
        system_prompt: Optional[str] = None
    ) -> dict:
        """
        Run the RAG workflow with conversation memory
        
        Args:
            query: User's question
            collection_name: Name of the Qdrant collection
            top_k: Number of documents to retrieve
            thread_id: Optional thread ID for conversation memory
            system_prompt: Optional custom system prompt (uses default if not provided)
            
        Returns:
            Dictionary with answer and retrieved documents
        """
        try:
            log_info(f"Running RAG workflow for query: '{query}' (thread: {thread_id or 'default'})")
            
            # Configuration for thread
            config = {
                "configurable": {
                    "thread_id": thread_id or "default"
                }
            }
            
            # Retrieve conversation history from checkpointer
            conversation_history = []
            try:
                # Get the latest state from checkpointer for this thread
                state_snapshot = self.graph.get_state(config)
                if state_snapshot and state_snapshot.values:
                    existing_history = state_snapshot.values.get("conversation_history", [])
                    if existing_history:
                        conversation_history = existing_history
                        log_info(f"Retrieved {len(conversation_history)} previous conversation turns")
            except Exception as e:
                log_debug(f"No previous conversation history found or error retrieving: {str(e)}")
            
            # Initialize state with conversation history
            initial_state = {
                "query": query,
                "collection_name": collection_name,
                "top_k": top_k,
                "retrieved_docs": [],
                "context": "",
                "answer": "",
                "thread_id": thread_id,
                "conversation_history": conversation_history,
                "system_prompt": system_prompt
            }
            
            # Execute the workflow
            result = self.graph.invoke(initial_state, config)
            
            log_info("RAG workflow completed successfully")
            
            return {
                "answer": result["answer"],
                "retrieved_docs": result["retrieved_docs"],
                "context": result["context"],
                "thread_id": thread_id or "default",
                "conversation_history": result.get("conversation_history", [])
            }
        
        except Exception as e:
            log_error(f"Error running RAG workflow: {str(e)}")
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
            if state_snapshot and state_snapshot.values:
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

