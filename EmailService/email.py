"""
Gmail Email Service - Provides Gmail API functionality with OAuth
"""

import os
import base64
from email.message import EmailMessage
from typing import Optional, List
from datetime import datetime

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from pymongo import MongoClient
from cryptography.fernet import Fernet


class GmailService:
    """Service class for Gmail operations with OAuth authentication."""
    
    def __init__(
        self,
        mongodb_uri: Optional[str] = None,
        db_name: str = "Findiy_Production_Python",
        collection_name: str = "gmail_credentials",
        encryption_key: Optional[str] = None,
        client_secrets_file: str = "credentials.json",
        redirect_uri: str = "http://localhost:8000/email/oauth2callback"
    ):
        """
        Initialize the Gmail Service.
        
        Args:
            mongodb_uri: MongoDB connection URI
            db_name: Database name for storing credentials
            collection_name: Collection name for storing credentials
            encryption_key: Fernet encryption key for token encryption
            client_secrets_file: Path to Google OAuth credentials.json
            redirect_uri: OAuth callback URI
        """
        # MongoDB Configuration
        self.mongodb_uri = mongodb_uri or os.getenv(
            "MONGODB_URI",
            "mongodb+srv://pythonProd:pythonfindiy25@findiy-main.t5gfeq.mongodb.net/Findiy_Production_Python?retryWrites=true&w=majority&appName=Findiy-main"
        )
        self.db_name = db_name
        self.collection_name = collection_name
        
        # Connect to MongoDB
        self._client = MongoClient(self.mongodb_uri)
        self._db = self._client[self.db_name]
        self._collection = self._db[self.collection_name]
        
        # Encryption
        default_key = "nybmG4fqyl5PZkymPJHsgBCCqxvf1jqwpENm-0-crVo="
        key = encryption_key or os.getenv('ENCRYPTION_KEY', default_key)
        self._cipher = Fernet(key.encode() if isinstance(key, str) else key)
        
        # OAuth Configuration
        self.client_secrets_file = client_secrets_file
        self.scopes = [
            'https://www.googleapis.com/auth/gmail.send',
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/userinfo.email'
        ]
        self.redirect_uri = redirect_uri
    
    def _encrypt_token(self, token: str) -> str:
        """Encrypt sensitive token data."""
        return self._cipher.encrypt(token.encode()).decode()
    
    def _decrypt_token(self, encrypted_token: str) -> str:
        """Decrypt token data."""
        return self._cipher.decrypt(encrypted_token.encode()).decode()
    
    def save_credentials(self, user_email: str, credentials: Credentials):
        """Save user credentials to MongoDB."""
        creds_data = {
            'user_email': user_email,
            'token': self._encrypt_token(credentials.token),
            'refresh_token': self._encrypt_token(credentials.refresh_token) if credentials.refresh_token else None,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': self._encrypt_token(credentials.client_secret),
            'scopes': credentials.scopes,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        self._collection.update_one(
            {'user_email': user_email},
            {'$set': creds_data},
            upsert=True
        )
    
    def get_credentials(self, user_email: str) -> Optional[Credentials]:
        """Retrieve user credentials from MongoDB."""
        doc = self._collection.find_one({'user_email': user_email})
        
        if not doc:
            return None
        
        try:
            token = self._decrypt_token(doc['token'])
            refresh_token = self._decrypt_token(doc['refresh_token']) if doc.get('refresh_token') else None
            client_secret = self._decrypt_token(doc['client_secret'])
            
            return Credentials(
                token=token,
                refresh_token=refresh_token,
                token_uri=doc['token_uri'],
                client_id=doc['client_id'],
                client_secret=client_secret,
                scopes=doc['scopes']
            )
        except Exception:
            self._collection.delete_one({'user_email': user_email})
            return None
    
    def delete_credentials(self, user_email: str) -> bool:
        """Delete user credentials from MongoDB."""
        result = self._collection.delete_one({'user_email': user_email})
        return result.deleted_count > 0
    
    def get_gmail_service(self, user_email: str):
        """Get Gmail API service with stored credentials."""
        creds = self.get_credentials(user_email)
        
        if not creds:
            raise ValueError(f"No credentials found for {user_email}")
        
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self.save_credentials(user_email, creds)
        
        return build('gmail', 'v1', credentials=creds)
    
    def get_authorization_url(self) -> tuple[str, str]:
        """
        Get the Google OAuth authorization URL.
        
        Returns:
            Tuple of (authorization_url, state)
        """
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
        os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
        
        flow = Flow.from_client_secrets_file(
            self.client_secrets_file,
            scopes=self.scopes,
            redirect_uri=self.redirect_uri
        )
        
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        
        # Store state temporarily
        self._collection.update_one(
            {'_id': 'oauth_state'},
            {'$set': {'state': state, 'timestamp': datetime.utcnow()}},
            upsert=True
        )
        
        return authorization_url, state
    
    def handle_oauth_callback(self, code: str, state: Optional[str] = None) -> str:
        """
        Handle OAuth callback and store credentials.
        
        Args:
            code: Authorization code from Google
            state: State parameter from callback
            
        Returns:
            User's email address
        """
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
        os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
        
        state_doc = self._collection.find_one({'_id': 'oauth_state'})
        stored_state = state_doc.get('state') if state_doc else None
        
        if stored_state and state and stored_state == state:
            flow = Flow.from_client_secrets_file(
                self.client_secrets_file,
                scopes=self.scopes,
                state=state,
                redirect_uri=self.redirect_uri
            )
        else:
            flow = Flow.from_client_secrets_file(
                self.client_secrets_file,
                scopes=self.scopes,
                redirect_uri=self.redirect_uri
            )
        
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        # Get user email from Google
        service = build('gmail', 'v1', credentials=credentials)
        profile = service.users().getProfile(userId='me').execute()
        user_email = profile['emailAddress']
        
        self.save_credentials(user_email, credentials)
        self._collection.delete_one({'_id': 'oauth_state'})
        
        return user_email
    
    def send_email(
        self,
        user_email: str,
        to: str,
        subject: str,
        body: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None
    ) -> dict:
        """
        Send an email via Gmail API.
        
        Args:
            user_email: The authenticated user's email
            to: Recipient email address
            subject: Email subject
            body: Email body content
            cc: Optional list of CC recipients
            bcc: Optional list of BCC recipients
            
        Returns:
            Dict with message_id, thread_id, and success status
        """
        service = self.get_gmail_service(user_email)
        
        message = EmailMessage()
        message.set_content(body)
        message['To'] = to
        message['Subject'] = subject
        
        if cc:
            message['Cc'] = ', '.join(cc)
        
        if bcc:
            message['Bcc'] = ', '.join(bcc)
        
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        send_message = {'raw': encoded_message}
        
        result = service.users().messages().send(
            userId='me',
            body=send_message
        ).execute()
        
        return {
            'success': True,
            'message_id': result['id'],
            'thread_id': result['threadId'],
            'message': f'Email sent successfully to {to}'
        }
    
    def list_connected_users(self) -> List[dict]:
        """List all connected Gmail accounts."""
        users = list(self._collection.find(
            {'user_email': {'$exists': True}},
            {'user_email': 1, 'created_at': 1, '_id': 0}
        ))
        return users
