"""
LangGraph workflow for RAG-based chat with memory checkpointer
"""

from typing import TypedDict, List, Optional, Annotated
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.mongodb import MongoDBSaver
from pymongo import MongoClient
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
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
        conversation_summary: Summarized history of older conversations
        system_prompt: Custom system prompt (optional)
        system_prompt_sent: Flag to track if system prompt was already sent
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
    conversation_summary: Optional[str]  # Summarized older conversations
    system_prompt: Optional[str]
    system_prompt_sent: Optional[bool]  # Track if system prompt already sent
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
        
        # Store ecommerce tools at class level (not in state to avoid serialization issues)
        self._ecommerce_tools = None
        
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
    
    def _summarize_conversation_history(self, conversation_history: List[dict], openai_api_key: str) -> str:
        """
        Summarize conversation history using OpenAI to compress old conversations.
        
        Args:
            conversation_history: List of conversation turns to summarize
            openai_api_key: OpenAI API key for summarization
            
        Returns:
            Summarized conversation text
        """
        try:
            log_info(f"Summarizing {len(conversation_history)} conversation turns...")
            
            # Build conversation text
            conversation_text = ""
            for i, turn in enumerate(conversation_history, 1):
                conversation_text += f"Turn {i}:\nUser: {turn['query']}\nAssistant: {turn['answer']}\n\n"
            
            # Create summarization prompt
            summarization_prompt = f"""You are a conversation summarizer. Your task is to create a concise but comprehensive summary of the following conversation that preserves all important context, facts, decisions, and user preferences.

The summary should:
1. Capture key topics discussed
2. Preserve important facts, numbers, and specific details
3. Note any decisions made or preferences expressed
4. Maintain chronological flow of important events
5. Be concise but complete (aim for 30-50% of original length)

Conversation to summarize:
{conversation_text}

Provide a clear, well-structured summary:"""
            
            # Use OpenAI for summarization
            summarization_llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0.3,
                openai_api_key=openai_api_key
            )
            
            response = summarization_llm.invoke([HumanMessage(content=summarization_prompt)])
            summary = response.content
            
            log_info(f"✓ Conversation summarized: {len(conversation_text)} chars -> {len(summary)} chars")
            return summary
            
        except Exception as e:
            log_error(f"Error summarizing conversation: {str(e)}")
            # Fallback: return a simple concatenation
            return "Previous conversation context: " + " | ".join(
                [f"Q: {t['query'][:50]}... A: {t['answer'][:50]}..." for t in conversation_history[:5]]
            )
    
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
            
            # SKIP RAG retrieval if no collections specified AND tools are available (tool-only mode)
            if not collections and self._ecommerce_tools:
                log_info("⏭️ RETRIEVE: Skipped (no collections specified, tool-only mode)")
                state["retrieved_docs"] = []
                state["context"] = ""
                return state
            
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
        Generate answer based on retrieved context and conversation history.
        Supports tool calling for ecommerce integration.
        
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
            ecommerce_tools = self._ecommerce_tools or []
            
            try:
                llm = self._get_cached_llm(provider, api_key)
                log_info(f"Using {provider} LLM (cached: {(provider, api_key[:20] if api_key else 'default') in self.llm_cache})")
            except ValueError as e:
                log_error(f"Error getting LLM: {str(e)}")
                state["answer"] = f"Error: {str(e)}"
                return state
            
            # Bind ecommerce tools to LLM if available
            # Tools are already created with @tool decorator, so they can be bound directly
            if ecommerce_tools:
                for t in ecommerce_tools:
                    log_info(f"  - Tool: {t.name} - {t.description[:50]}...")
                
                llm = llm.bind_tools(ecommerce_tools)
                log_info(f"✓ Bound {len(ecommerce_tools)} ecommerce tools to LLM ({provider})")
            
            # OPTIMIZATION: Build conversation context with summary + recent history (NO TRUNCATION)
            history_context = ""
            
            # Include conversation summary if exists (compressed old conversations)
            if state.get("conversation_summary"):
                history_context += f"\n\nPrevious Conversation Summary:\n{state['conversation_summary']}\n"
                log_info(f"Including conversation summary ({len(state['conversation_summary'])} chars)")
            
            # Include recent conversation history (last 5 turns, NO truncation)
            if state.get("conversation_history"):
                recent_history = state["conversation_history"][-5:]  # Last 5 turns (increased from 2)
                if recent_history:
                    history_items = []
                    for item in recent_history:
                        # NO TRUNCATION - include full query and answer
                        history_items.append(f"User: {item['query']}\nAssistant: {item['answer']}")
                    history_context += "\n\nRecent Conversation:\n" + "\n\n".join(history_items)
                    log_info(f"Including {len(recent_history)} recent conversation turns (full content)")
            
            # Check if we have context from retrieval
            has_retrieval_context = (
                state.get("context") and 
                state["context"] != "No relevant documents found in the knowledge base." and
                state["context"] != "Error retrieving documents from knowledge base."
            )
            
            # OPTIMIZATION: Only send system prompt on first message in thread
            # Check if system prompt was already sent in this thread
            is_first_message = not state.get("system_prompt_sent", False)
            
            messages = []
            
            if is_first_message:
                # First message - send full system prompt
                system_prompt_content = state.get("system_prompt") or SYSTEM_PROMPT
                
                # Add tool instructions if tools are available
                if ecommerce_tools:
                    # Check which tools are available
                    tool_names = [t.name for t in ecommerce_tools]
                    has_ecommerce = "get_products" in tool_names or "get_orders" in tool_names
                    has_email = "send_email" in tool_names
                    
                    if has_ecommerce:
                        system_prompt_content += """

IMPORTANT: You have access to ecommerce tools that connect to a real store. You MUST use these tools when users ask about:
- Products, items, catalog, inventory, stock, or what's available
- Orders, purchases, sales, or transactions
- Pricing, costs, or product information

When a user asks about products or orders, ALWAYS call the appropriate tool first before responding. The tools will give you real, up-to-date information from the store.

Available ecommerce tools:
- get_products: Use this to fetch current products from the store
- get_orders: Use this to fetch recent orders from the store"""
                    
                    if has_email:
                        system_prompt_content += """

IMPORTANT: You have access to an email tool. You MUST use this tool when:
- The user wants to send an email
- The user wants to schedule or confirm an appointment (send confirmation email)
- The user asks you to communicate something via email
- The user provides recipient email, subject, and body content

When sending emails, ALWAYS use the send_email tool with the recipient's email address, subject line, and body content.

Available email tool:
- send_email: Use this to send an email. Requires: to (recipient email), subject (email subject), body (email content)"""
                
                messages.append(SystemMessage(content=system_prompt_content))
                log_info(f"✓ Sending system prompt (first message, {len(system_prompt_content)} chars)")
                
                # Mark system prompt as sent
                state["system_prompt_sent"] = True
            else:
                # Follow-up message - NO system prompt, rely on conversation history
                log_info("✓ Skipping system prompt (already sent in this thread)")
            
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
                # No retrieval context, but we might have conversation history or ecommerce tools
                if history_context or ecommerce_tools:
                    prompt = f"{history_context}\n\nCurrent question: {state['query']}\n\nPlease answer the question."
                    messages.append(HumanMessage(content=prompt))
                else:
                    state["answer"] = "I don't have enough information in the knowledge base to answer your question. Please try rephrasing or ask about a different topic."
                    return state
            
            # Generate answer using LLM (with tool calling support)
            llm_start = perf_time.time()
            response = llm.invoke(messages)
            
            # Check if LLM wants to call tools
            log_info(f"LLM response has tool_calls attribute: {hasattr(response, 'tool_calls')}")
            if hasattr(response, 'tool_calls'):
                log_info(f"Tool calls: {response.tool_calls}")
            
            if hasattr(response, 'tool_calls') and response.tool_calls:
                log_info(f"✓ LLM requested {len(response.tool_calls)} tool calls")
                
                # Execute tool calls - tools are synchronous (use asyncio.run internally)
                tool_results = []
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call.get("args", {})
                    
                    log_info(f"  Executing tool: {tool_name} with args: {tool_args}")
                    
                    # Find and execute the tool
                    for t in ecommerce_tools:
                        if t.name == tool_name:
                            try:
                                result = t.invoke(tool_args)
                                tool_results.append({
                                    "tool_call_id": tool_call["id"],
                                    "content": result
                                })
                                log_info(f"  ✓ Tool {tool_name} executed successfully")
                            except Exception as e:
                                log_error(f"  ✗ Error executing tool {tool_name}: {e}")
                                tool_results.append({
                                    "tool_call_id": tool_call["id"],
                                    "content": f"Error: {str(e)}"
                                })
                            break
                
                # Add tool results to messages and get final answer
                messages.append(AIMessage(content=response.content or "", tool_calls=response.tool_calls))
                for tool_result in tool_results:
                    messages.append(ToolMessage(
                        content=tool_result["content"],
                        tool_call_id=tool_result["tool_call_id"]
                    ))
                
                # Get final answer with tool results
                log_info(f"  Getting final answer with tool results...")
                final_response = llm.invoke(messages)
                state["answer"] = final_response.content
                log_info(f"✓ Generated answer using tool results")
            else:
                log_info(f"✗ LLM did not request any tool calls (ecommerce_tools available: {bool(ecommerce_tools)})")
                
                # FALLBACK: If ecommerce query detected but LLM didn't call tools, force execution
                if ecommerce_tools:
                    query_lower = state["query"].lower()
                    is_product_query = any(keyword in query_lower for keyword in 
                        ['product', 'item', 'stock', 'available', 'price', 'cost', 'catalog', 'inventory', 'list', 'sell', 'buy'])
                    is_order_query = any(keyword in query_lower for keyword in 
                        ['order', 'purchase', 'bought', 'transaction', 'sale'])
                    
                    if is_product_query or is_order_query:
                        log_warning(f"✓ FALLBACK: Forcing tool execution for ecommerce query")
                        
                        # Execute appropriate tool
                        tool_result = None
                        for t in ecommerce_tools:
                            if is_product_query and t.name == "get_products":
                                tool_result = t.invoke({"limit": 10})
                                log_info(f"  ✓ Forced get_products execution")
                                break
                            elif is_order_query and t.name == "get_orders":
                                tool_result = t.invoke({"limit": 10})
                                log_info(f"  ✓ Forced get_orders execution")
                                break
                        
                        if tool_result:
                            # Re-prompt LLM with tool results
                            enhanced_prompt = f"Here is the store data:\n\n{tool_result}\n\nUser question: {state['query']}\n\nPlease provide a helpful answer based on this data."
                            messages.append(HumanMessage(content=enhanced_prompt))
                            final_response = llm.invoke(messages)
                            state["answer"] = final_response.content
                            log_info(f"✓ Generated answer using forced tool data")
                        else:
                            state["answer"] = response.content
                    else:
                        state["answer"] = response.content
                else:
                    state["answer"] = response.content
            
            log_info(f"⏱️ LLM CALL: Completed in {(perf_time.time() - llm_start)*1000:.0f}ms (provider: {provider})")
            
            # Update conversation history
            if not state.get("conversation_history"):
                state["conversation_history"] = []
            
            state["conversation_history"].append({
                "query": state["query"],
                "answer": state["answer"]
            })
            
            # OPTIMIZATION: Auto-summarize after 15 turns to maintain context without token bloat
            history_length = len(state["conversation_history"])
            if history_length >= 15:
                log_info(f"⚡ Conversation has {history_length} turns - triggering summarization")
                
                # Get API key for summarization (prefer user's key, fallback to default)
                summarization_key = api_key if provider == "openai" else self.llm.openai_api_key
                
                # Summarize the first 10 turns (keep last 5 as recent history)
                turns_to_summarize = state["conversation_history"][:10]
                
                # Generate summary
                new_summary = self._summarize_conversation_history(turns_to_summarize, summarization_key)
                
                # Combine with existing summary if present
                if state.get("conversation_summary"):
                    combined_summary = f"{state['conversation_summary']}\n\n--- Additional Context ---\n{new_summary}"
                    state["conversation_summary"] = combined_summary
                    log_info(f"✓ Combined with existing summary (total: {len(combined_summary)} chars)")
                else:
                    state["conversation_summary"] = new_summary
                    log_info(f"✓ Created new conversation summary ({len(new_summary)} chars)")
                
                # Keep only the last 5 turns in full history
                state["conversation_history"] = state["conversation_history"][10:]
                log_info(f"✓ Compressed history: 15 turns -> summary + 5 recent turns")
            
            log_info(f"⏱️ GENERATE: Total node completed in {(perf_time.time() - generate_start)*1000:.0f}ms")
            log_debug(f"Generated answer: {state['answer'][:100]}...")
            
            return state
        
        except Exception as e:
            import traceback
            log_error(f"Error in generate node: {str(e)}")
            log_error(f"Traceback: {traceback.format_exc()}")
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
        skip_history: bool = False,
        ecommerce_tools: Optional[List] = None
    ) -> dict:
        """
        Run the RAG workflow with conversation memory.
        Supports querying multiple logical collections stored in a single Qdrant collection.
        Supports tool calling for ecommerce integration.
        
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
            ecommerce_tools: Optional list of ecommerce tool functions to bind to LLM
            
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
            
            # Set ecommerce tools at class level (not in state to avoid serialization issues)
            self._ecommerce_tools = ecommerce_tools
            
            # Configuration for thread
            config = {
                "configurable": {
                    "thread_id": thread_id or "default"
                }
            }
            
            # OPTIMIZATION: Retrieve conversation state from checkpointer (history + summary + flags)
            conversation_history = []
            conversation_summary = None
            system_prompt_sent = False
            
            if not skip_history and thread_id:  # Only fetch history if thread_id is provided
                history_start = perf_time.time()
                try:
                    # Get the latest state from checkpointer for this thread
                    state_snapshot = self.graph.get_state(config)
                    if state_snapshot and hasattr(state_snapshot, 'values') and state_snapshot.values:
                        existing_history = state_snapshot.values.get("conversation_history", [])
                        existing_summary = state_snapshot.values.get("conversation_summary")
                        existing_prompt_flag = state_snapshot.values.get("system_prompt_sent", False)
                        
                        if existing_history:
                            conversation_history = existing_history
                            log_info(f"Retrieved {len(conversation_history)} previous conversation turns in {(perf_time.time() - history_start)*1000:.0f}ms")
                        
                        if existing_summary:
                            conversation_summary = existing_summary
                            log_info(f"Retrieved conversation summary ({len(existing_summary)} chars)")
                        
                        if existing_prompt_flag:
                            system_prompt_sent = True
                            log_info("System prompt already sent in this thread")
                            
                except Exception as e:
                    log_debug(f"No previous conversation state found or error retrieving: {str(e)}")
            else:
                log_debug("Skipping conversation history lookup (no thread_id or skip_history=True)")
            
            # Initialize state with conversation history, summary, and flags
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
                "conversation_summary": conversation_summary,
                "system_prompt": system_prompt,
                "system_prompt_sent": system_prompt_sent,
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
            
            # Clean up ecommerce tools after workflow completes
            self._ecommerce_tools = None
            
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
            
            # Clean up ecommerce tools even on error
            self._ecommerce_tools = None
            
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

