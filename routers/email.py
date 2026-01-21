"""
Email-related API endpoints using Gmail API with OAuth
"""

import os
import base64
from email.message import EmailMessage
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from pymongo import MongoClient
from cryptography.fernet import Fernet

from utils.logger import log_info, log_error, log_exception

router = APIRouter(prefix="/email", tags=["Email"])

# MongoDB Configuration
MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = "IslandAI"
COLLECTION_NAME = "gmail_credentials"

# Connect to MongoDB
_mongo_client = MongoClient(MONGODB_URI)
_db = _mongo_client[DB_NAME]
_collection = _db[COLLECTION_NAME]

# Encryption key - In production, store this in environment variable
DEFAULT_ENCRYPTION_KEY = "nybmG4fqyl5PZkymPJHsgBCCqxvf1jqwpENm-0-crVo="
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY', DEFAULT_ENCRYPTION_KEY).encode()
_cipher = Fernet(ENCRYPTION_KEY)

# OAuth Configuration
CLIENT_SECRETS_FILE = 'credentials.json'
SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/userinfo.email'
]
REDIRECT_URI = os.getenv('OAUTH_REDIRECT_URI', 'https://keplerov1-python-2.onrender.com/email/oauth2callback')


# Pydantic Models
class SendEmailRequest(BaseModel):
    """Request model for sending email via Gmail API."""
    to: EmailStr
    subject: str
    body: str
    cc: Optional[List[EmailStr]] = None
    bcc: Optional[List[EmailStr]] = None


class SendEmailResponse(BaseModel):
    """Response model for email sending."""
    success: bool
    message_id: str
    thread_id: str
    message: str


# Helper Functions
def _encrypt_token(token: str) -> str:
    """Encrypt sensitive token data."""
    return _cipher.encrypt(token.encode()).decode()


def _decrypt_token(encrypted_token: str) -> str:
    """Decrypt token data."""
    return _cipher.decrypt(encrypted_token.encode()).decode()


def _save_credentials_to_db(user_email: str, credentials: Credentials):
    """Save user credentials to MongoDB."""
    creds_data = {
        'user_email': user_email,
        'token': _encrypt_token(credentials.token),
        'refresh_token': _encrypt_token(credentials.refresh_token) if credentials.refresh_token else None,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': _encrypt_token(credentials.client_secret),
        'scopes': credentials.scopes,
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow()
    }
    
    _collection.update_one(
        {'user_email': user_email},
        {'$set': creds_data},
        upsert=True
    )
    log_info(f"Saved Gmail credentials for {user_email}")


def _get_credentials_from_db(user_email: str) -> Optional[Credentials]:
    """Retrieve user credentials from MongoDB."""
    doc = _collection.find_one({'user_email': user_email})
    
    if not doc:
        return None
    
    try:
        token = _decrypt_token(doc['token'])
        refresh_token = _decrypt_token(doc['refresh_token']) if doc.get('refresh_token') else None
        client_secret = _decrypt_token(doc['client_secret'])
        
        credentials = Credentials(
            token=token,
            refresh_token=refresh_token,
            token_uri=doc['token_uri'],
            client_id=doc['client_id'],
            client_secret=client_secret,
            scopes=doc['scopes']
        )
        
        return credentials
    except Exception as e:
        log_error(f"Failed to decrypt credentials for {user_email}: {str(e)}")
        _collection.delete_one({'user_email': user_email})
        raise HTTPException(
            status_code=401,
            detail="Stored credentials are invalid. Please re-authorize at /email/authorize"
        )


def _get_gmail_service(user_email: str):
    """Get Gmail service with stored credentials."""
    creds = _get_credentials_from_db(user_email)
    
    if not creds:
        raise HTTPException(
            status_code=401,
            detail="User not authenticated. Please authorize first at /email/authorize"
        )
    
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_credentials_to_db(user_email, creds)
        log_info(f"Refreshed Gmail credentials for {user_email}")
    
    return build('gmail', 'v1', credentials=creds)


def _get_user_email_from_google(credentials: Credentials) -> str:
    """Get user's email address from Google."""
    service = build('gmail', 'v1', credentials=credentials)
    profile = service.users().getProfile(userId='me').execute()
    return profile['emailAddress']


# Dependency to get user email from header
async def get_user_email(x_user_email: str = Header(...)) -> str:
    """Get user email from request header."""
    if not x_user_email:
        raise HTTPException(status_code=400, detail="X-User-Email header is required")
    return x_user_email


# API Endpoints
@router.get("/authorize")
async def authorize():
    """
    Redirect user to Google's OAuth page for Gmail authorization.
    
    After authorization, user will be redirected back with their credentials stored.
    Use the returned email in X-User-Email header for subsequent API requests.
    """
    try:
        # Allow insecure transport for local development
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
        
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        
        # Store state in MongoDB temporarily
        _collection.update_one(
            {'_id': 'oauth_state'},
            {'$set': {'state': state, 'timestamp': datetime.utcnow()}},
            upsert=True
        )
        
        log_info("Redirecting user to Google OAuth")
        return RedirectResponse(url=authorization_url)
    
    except Exception as e:
        log_exception(f"Authorization error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Authorization error: {str(e)}")


@router.get("/oauth2callback")
async def oauth2callback(code: str, state: Optional[str] = None):
    """
    Handle the callback from Google OAuth.
    
    This endpoint is called by Google after the user authorizes the application.
    """
    try:
        # Allow insecure transport for local development
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
        # Relax token scope validation (allows Google to return additional granted scopes)
        os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
        
        # Retrieve stored state from MongoDB
        state_doc = _collection.find_one({'_id': 'oauth_state'})
        stored_state = state_doc.get('state') if state_doc else None
        
        # Create flow with or without state validation
        if stored_state and state and stored_state == state:
            flow = Flow.from_client_secrets_file(
                CLIENT_SECRETS_FILE,
                scopes=SCOPES,
                state=state,
                redirect_uri=REDIRECT_URI
            )
        else:
            flow = Flow.from_client_secrets_file(
                CLIENT_SECRETS_FILE,
                scopes=SCOPES,
                redirect_uri=REDIRECT_URI
            )
        
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        user_email = _get_user_email_from_google(credentials)
        _save_credentials_to_db(user_email, credentials)
        
        # Clean up the stored state
        _collection.delete_one({'_id': 'oauth_state'})
        
        log_info(f"Gmail connected successfully for {user_email}")
        
        return {
            "success": True,
            "message": "Gmail connected successfully",
            "user_email": user_email,
            "note": "Use this email in X-User-Email header for API requests"
        }
    
    except Exception as e:
        log_exception(f"OAuth callback error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"OAuth callback error: {str(e)}")


@router.post("/send", response_model=SendEmailResponse)
async def send_email(
    email_data: SendEmailRequest,
    user_email: str = Depends(get_user_email)
):
    """
    Send an email via Gmail API.
    
    Requires X-User-Email header with authorized Gmail address.
    
    - **to**: Recipient email address
    - **subject**: Email subject
    - **body**: Email body content
    - **cc**: Optional list of CC recipients
    - **bcc**: Optional list of BCC recipients
    """
    try:
        log_info(f"Sending email from {user_email} to {email_data.to}")
        
        service = _get_gmail_service(user_email)
        
        message = EmailMessage()
        message.set_content(email_data.body)
        message['To'] = email_data.to
        message['Subject'] = email_data.subject
        
        if email_data.cc:
            message['Cc'] = ', '.join(email_data.cc)
        
        if email_data.bcc:
            message['Bcc'] = ', '.join(email_data.bcc)
        
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        send_message = {'raw': encoded_message}
        
        result = service.users().messages().send(
            userId='me',
            body=send_message
        ).execute()
        
        log_info(f"Email sent successfully from {user_email} to {email_data.to}")
        
        return SendEmailResponse(
            success=True,
            message_id=result['id'],
            thread_id=result['threadId'],
            message=f"Email sent successfully to {email_data.to}"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error sending email: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error sending email: {str(e)}")


@router.delete("/logout")
async def logout(user_email: str = Depends(get_user_email)):
    """
    Logout and delete user credentials.
    
    Requires X-User-Email header.
    """
    try:
        result = _collection.delete_one({'user_email': user_email})
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No credentials found for {user_email}"
            )
        
        log_info(f"Logged out user {user_email}")
        
        return {
            "success": True,
            "message": f"Successfully logged out {user_email}"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error during logout: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error during logout: {str(e)}")


@router.get("/connected-users")
async def list_connected_users():
    """List all connected Gmail accounts (Admin endpoint)."""
    try:
        users = list(_collection.find(
            {'user_email': {'$exists': True}},
            {'user_email': 1, 'created_at': 1, '_id': 0}
        ))
        return {
            "total_users": len(users),
            "users": users
        }
    except Exception as e:
        log_exception(f"Error listing users: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error listing users: {str(e)}")
