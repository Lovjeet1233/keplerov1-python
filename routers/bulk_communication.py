"""
Bulk Communication API endpoint - orchestrates calls, SMS, and email
"""

from datetime import datetime
from fastapi import APIRouter, HTTPException
from typing import Optional
from utils.logger import log_info, log_error, log_exception
from model import (
    BulkCommunicationRequest,
    BulkCommunicationResponse,
    ContactResult,
    OutboundCallRequest,
    SMSRequest,
    EmailRequest
)

# Import the endpoint functions directly
from routers.calls import outbound_call
from routers.sms import send_sms
from routers.email import send_email

router = APIRouter(prefix="/bulk-communication", tags=["Bulk Communication"])


async def make_call_request(phone: str, name: str, dynamic_instruction: Optional[str], 
                            language: str, emotion: str) -> dict:
    """
    Make a call using the outbound call service.
    
    Returns:
        dict with 'status', 'transcript', and optionally 'error'
    """
    try:
        log_info(f"Making call to {phone} for {name}")
        
        # Create the call request
        call_request = OutboundCallRequest(
            phone_number=phone,
            name=name,
            dynamic_instruction=dynamic_instruction,
            language=language,
            emotion=emotion
        )
        
        # Call the endpoint function directly
        result = await outbound_call(call_request)
        
        return {
            "status": result.status,
            "transcript": result.transcript
        }
    except HTTPException as e:
        log_error(f"Call failed for {phone}: {e.detail}")
        return {
            "status": "failed",
            "transcript": None,
            "error": e.detail
        }
    except Exception as e:
        log_exception(f"Error making call to {phone}: {str(e)}")
        return {
            "status": "failed",
            "transcript": None,
            "error": str(e)
        }


async def send_sms_request(phone: str, message: str) -> dict:
    """
    Send SMS using the SMS service.
    
    Returns:
        dict with 'status' and optionally 'error'
    """
    try:
        log_info(f"Sending SMS to {phone}")
        
        # Create the SMS request
        sms_request = SMSRequest(
            body=message,
            number=phone
        )
        
        # Call the endpoint function directly
        result = await send_sms(sms_request)
        
        return {"status": result.status}
    except HTTPException as e:
        log_error(f"SMS failed for {phone}: {e.detail}")
        return {
            "status": "failed",
            "error": e.detail
        }
    except Exception as e:
        log_exception(f"Error sending SMS to {phone}: {str(e)}")
        return {
            "status": "failed",
            "error": str(e)
        }


async def send_email_request(email: str, subject: str, body: str, is_html: bool = False) -> dict:
    """
    Send email using the email service.
    
    Returns:
        dict with 'status' and optionally 'error'
    """
    try:
        log_info(f"Sending email to {email}")
        
        # Create the email request
        email_request = EmailRequest(
            receiver_email=email,
            subject=subject,
            body=body,
            is_html=is_html
        )
        
        # Call the endpoint function directly
        result = await send_email(email_request)
        
        return {"status": result.status}
    except HTTPException as e:
        log_error(f"Email failed for {email}: {e.detail}")
        return {
            "status": "failed",
            "error": e.detail
        }
    except Exception as e:
        log_exception(f"Error sending email to {email}: {str(e)}")
        return {
            "status": "failed",
            "error": str(e)
        }


async def process_contact(contact, request: BulkCommunicationRequest) -> ContactResult:
    """
    Process a single contact with the specified communication types.
    
    Args:
        contact: Contact object with name, email, phone
        request: BulkCommunicationRequest with communication settings
        
    Returns:
        ContactResult with status of all communications
    """
    created_at = datetime.utcnow().isoformat()
    errors = {}
    
    call_status = None
    transcript = None
    sms_status = None
    email_status = None
    
    log_info(f"Processing contact: {contact.name}")
    
    # 1. Make call if requested
    if "call" in request.communication_types:
        if not contact.phone:
            call_status = "skipped"
            errors["call"] = "No phone number provided"
            log_error(f"Cannot make call to {contact.name}: no phone number")
        else:
            call_result = await make_call_request(
                phone=contact.phone,
                name=contact.name,
                dynamic_instruction=request.dynamic_instruction,
                language=request.language,
                emotion=request.emotion
            )
            call_status = call_result["status"]
            transcript = call_result.get("transcript")
            if call_result.get("error"):
                errors["call"] = call_result["error"]
    
    # 2. Send SMS if requested
    if "sms" in request.communication_types:
        if not contact.phone:
            sms_status = "skipped"
            errors["sms"] = "No phone number provided"
            log_error(f"Cannot send SMS to {contact.name}: no phone number")
        elif not request.sms_body:
            sms_status = "skipped"
            errors["sms"] = "No SMS body provided in request"
            log_error(f"Cannot send SMS to {contact.name}: no SMS body in request")
        else:
            sms_result = await send_sms_request(
                phone=contact.phone,
                message=request.sms_body.message
            )
            sms_status = sms_result["status"]
            if sms_result.get("error"):
                errors["sms"] = sms_result["error"]
    
    # 3. Send email if requested
    if "email" in request.communication_types:
        if not contact.email:
            email_status = "skipped"
            errors["email"] = "No email address provided"
            log_error(f"Cannot send email to {contact.name}: no email address")
        elif not request.email_body:
            email_status = "skipped"
            errors["email"] = "No email body provided in request"
            log_error(f"Cannot send email to {contact.name}: no email body in request")
        else:
            email_result = await send_email_request(
                email=contact.email,
                subject=request.email_body.subject,
                body=request.email_body.body,
                is_html=request.email_body.is_html
            )
            email_status = email_result["status"]
            if email_result.get("error"):
                errors["email"] = email_result["error"]
    
    ended_at = datetime.utcnow().isoformat()
    
    return ContactResult(
        name=contact.name,
        email=contact.email,
        phone=contact.phone,
        call_status=call_status,
        transcript=transcript,
        sms_status=sms_status,
        email_status=email_status,
        created_at=created_at,
        ended_at=ended_at,
        errors=errors if errors else None
    )


@router.post("/send", response_model=BulkCommunicationResponse)
async def bulk_communication(request: BulkCommunicationRequest):
    """
    Send bulk communications (calls, SMS, email) to one or more contacts.
    
    This endpoint orchestrates multiple communication channels:
    1. Makes calls first (if selected) and captures transcripts
    2. Sends SMS messages (if selected and sms_body provided)
    3. Sends emails (if selected and email_body provided)
    
    Args:
        request: BulkCommunicationRequest containing:
            - contacts: List of contacts with name, email, phone
            - communication_types: List of communication types ["call", "sms", "email"]
            - sms_body: SMS message body (required if "sms" in communication_types)
            - email_body: Email subject and body (required if "email" in communication_types)
            - dynamic_instruction: Custom instructions for AI agent (for calls)
            - language: TTS language (for calls, default: "en")
            - emotion: TTS emotion (for calls, default: "Calm")
        
    Returns:
        BulkCommunicationResponse with detailed results for each contact including:
            - transcript (if call was made)
            - call_status
            - sms_status
            - email_status
            - created_at
            - ended_at
            - errors (if any)
    """
    try:
        log_info(f"Bulk communication request for {len(request.contacts)} contact(s)")
        log_info(f"Communication types: {', '.join(request.communication_types)}")
        
        # Validate that we have the necessary information for each communication type
        if "sms" in request.communication_types and not request.sms_body:
            raise HTTPException(
                status_code=400,
                detail="SMS body is required when 'sms' is in communication_types"
            )
        
        if "email" in request.communication_types and not request.email_body:
            raise HTTPException(
                status_code=400,
                detail="Email body is required when 'email' is in communication_types"
            )
        
        # Validate communication types
        valid_types = ["call", "sms", "email"]
        for comm_type in request.communication_types:
            if comm_type not in valid_types:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid communication type: {comm_type}. Must be one of {valid_types}"
                )
        
        # Process each contact
        results = []
        for contact in request.contacts:
            result = await process_contact(contact, request)
            results.append(result)
        
        log_info(f"Bulk communication completed for {len(results)} contact(s)")
        
        return BulkCommunicationResponse(
            status="success",
            message=f"Processed {len(results)} contact(s) successfully",
            total_contacts=len(results),
            results=results
        )
    
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error in bulk communication: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Bulk communication error: {str(e)}")

