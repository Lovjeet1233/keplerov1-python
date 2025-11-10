"""
Email-related API endpoints
"""

from fastapi import APIRouter, HTTPException
from dotenv import load_dotenv
from utils.logger import log_info, log_error, log_exception
from model import EmailRequest, EmailResponse
from EmailService.email import EmailService

load_dotenv()

router = APIRouter(prefix="/email", tags=["Email"])

# Initialize Email Service
try:
    email_service = EmailService()
    log_info("Email service initialized successfully")
except Exception as e:
    log_error(f"Failed to initialize Email service: {str(e)}")
    email_service = None


@router.post("/send", response_model=EmailResponse)
async def send_email(request: EmailRequest):
    """
    Send an email using SMTP.
    
    Args:
        request: EmailRequest containing:
            - receiver_email: The recipient's email address
            - subject: The email subject line
            - body: The email body content
            - is_html: Whether the body is HTML (optional, defaults to False)
        
    Returns:
        EmailResponse with status and confirmation message
    """
    try:
        log_info(f"Email send request to: '{request.receiver_email}'")
        
        if not email_service:
            log_error("Email service not initialized")
            raise HTTPException(
                status_code=500,
                detail="Email service not available. Check your credentials in environment variables."
            )
        
        # Validate email format (basic check)
        if not request.receiver_email or '@' not in request.receiver_email:
            log_error(f"Invalid email format: '{request.receiver_email}'")
            raise HTTPException(
                status_code=400,
                detail="Invalid email address format"
            )
        
        # Send the email
        success = email_service.send_email(
            receiver_email=request.receiver_email,
            subject=request.subject,
            body=request.body,
            is_html=request.is_html
        )
        
        if not success:
            log_error(f"Failed to send email to '{request.receiver_email}'")
            raise HTTPException(
                status_code=500,
                detail="Failed to send email. Please check the logs for more details."
            )
        
        log_info(f"Successfully sent email to '{request.receiver_email}'")
        
        return EmailResponse(
            status="success",
            message=f"Email sent successfully to {request.receiver_email}",
            receiver_email=request.receiver_email
        )
    
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error sending email: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Email sending error: {str(e)}")

