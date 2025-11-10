"""
Twilio SMS-related API endpoints
"""

import os
from fastapi import APIRouter, HTTPException
from twilio.rest import Client
from dotenv import load_dotenv
from utils.logger import log_info, log_error, log_exception
from model import SMSRequest, SMSResponse

load_dotenv()

router = APIRouter(prefix="/sms", tags=["Twilio SMS"])

# Initialize Twilio client
account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
twilio_number = os.environ.get("TWILIO_NUMBER")

if not all([account_sid, auth_token, twilio_number]):
    log_error("Twilio credentials not found in environment variables")

try:
    client = Client(account_sid, auth_token)
    log_info("Twilio client initialized successfully")
except Exception as e:
    log_error(f"Failed to initialize Twilio client: {str(e)}")
    client = None


@router.post("/send", response_model=SMSResponse)
async def send_sms(request: SMSRequest):
    """
    Send an SMS message using Twilio.
    
    Args:
        request: SMSRequest containing:
            - body: The message content to send
            - number: The recipient's phone number (with country code, e.g., +1234567890)
        
    Returns:
        SMSResponse with status and message SID
    """
    try:
        log_info(f"SMS send request to: '{request.number}'")
        
        if not client:
            log_error("Twilio client not initialized")
            raise HTTPException(
                status_code=500,
                detail="Twilio service not available. Check your credentials."
            )
        
        # Validate phone number format
        if not request.number.startswith('+'):
            log_error(f"Invalid phone number format: '{request.number}'")
            raise HTTPException(
                status_code=400,
                detail="Phone number must start with '+' followed by country code (e.g., +1234567890)"
            )
        
        # Send the SMS message
        message = client.messages.create(
            body=request.body,
            from_=twilio_number,
            to=request.number
        )
        
        log_info(f"Successfully sent SMS to '{request.number}', SID: {message.sid}")
        
        return SMSResponse(
            status="success",
            message=f"SMS sent successfully to {request.number}",
            message_sid=message.sid,
            to_number=request.number
        )
    
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error sending SMS: {str(e)}")
        raise HTTPException(status_code=500, detail=f"SMS sending error: {str(e)}")

