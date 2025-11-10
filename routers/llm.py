"""
LLM-related API endpoints
"""

from fastapi import APIRouter, HTTPException
from utils.logger import log_info, log_exception
from model import ElaboratePromptRequest, ElaboratePromptResponse

router = APIRouter(prefix="/llm", tags=["LLM"])


# Global variable (to be injected)
llm_service = None


def init_llm_router(service):
    """Initialize the router with LLM service instance."""
    global llm_service
    llm_service = service


@router.post("/elaborate_prompt", response_model=ElaboratePromptResponse)
async def elaborate_prompt(request: ElaboratePromptRequest):
    """
    Elaborate a brief prompt into a more detailed and precise prompt.
    
    Args:
        request: ElaboratePromptRequest containing the prompt to elaborate
        
    Returns:
        ElaboratePromptResponse with original and elaborated prompts
    """
    try:
        log_info(f"Elaborate prompt request - Original: '{request.prompt[:100]}...'")
        
        # Use LLM service to elaborate the prompt
        elaborated = llm_service.elaborate_prompt(request.prompt)
        
        log_info(f"Successfully elaborated prompt - Length: {len(request.prompt)} -> {len(elaborated)}")
        
        return ElaboratePromptResponse(
            original_prompt=request.prompt,
            elaborated_prompt=elaborated
        )
    
    except Exception as e:
        log_exception(f"Error elaborating prompt: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Elaborate prompt error: {str(e)}")

