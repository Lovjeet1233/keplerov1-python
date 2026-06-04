"""
System prompts for RAG Service
"""

SYSTEM_PROMPT = """You are a helpful AI assistant. Answer questions using provided context and conversation history. Be concise (3-5 sentences), accurate, and direct. Use general knowledge when context is insufficient."""

RAG_PROMPT_TEMPLATE = """Context:
{context}

Question: {question}

Answer concisely using the context above:"""

RETRIEVAL_PROMPT = """Based on the user's question, retrieve relevant information from the knowledge base."""

GENERATION_PROMPT = """Generate a comprehensive answer based on the retrieved context and the user's question."""

ESCALATION_EVAL_PROMPT = """You are an escalation classifier for a customer support chatbot.

Escalation condition (when a human agent should take over):
{escalation_prompt}

Recent conversation:
{history}

Latest user message: {query}
Latest assistant reply: {answer}

Based on the escalation condition, should this conversation be escalated to a human agent now?

Respond with ONLY valid JSON in this exact format:
{{"escalated": true or false, "reason": "brief explanation"}}"""


# Prompt for the elaborate small prompt into precise one
ELABORATE_PROMPT = """You are an expert prompt engineer. Your task is to take a brief, simple prompt and elaborate it into a more detailed, precise, and actionable prompt.

Given prompt: {prompt}

Transform this prompt by:
1. Adding relevant context and background information
2. Clarifying the intent and expected output format
3. Including specific instructions or constraints if applicable
4. Making it more structured and detailed
5. Ensuring clarity and removing ambiguity

Return ONLY the elaborated prompt without any additional explanation or metadata.

Elaborated Prompt:"""