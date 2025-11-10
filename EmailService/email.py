import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

load_dotenv()


class EmailService:
    """Service class for sending emails via SMTP."""
    
    def __init__(self, sender_email=None, app_password=None, smtp_server="smtp.gmail.com", smtp_port=465):
        """
        Initialize the Email Service.
        
        Args:
            sender_email (str): Sender's email address. Defaults to EMAIL_ADDRESS env var.
            app_password (str): App password for authentication. Defaults to EMAIL_PASSWORD env var.
            smtp_server (str): SMTP server address. Defaults to Gmail's SMTP server.
            smtp_port (int): SMTP server port. Defaults to 465 (SSL).
        """
        self.sender_email = sender_email or os.environ.get("EMAIL_ADDRESS")
        self.app_password = app_password or os.environ.get("EMAIL_PASSWORD")
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        
        if not self.sender_email or not self.app_password:
            raise ValueError("Email credentials not provided. Set EMAIL_ADDRESS and EMAIL_PASSWORD environment variables.")
    
    def send_email(self, receiver_email, subject, body, is_html=False):
        """
        Send an email to a recipient.
        
        Args:
            receiver_email (str): Recipient's email address.
            subject (str): Email subject line.
            body (str): Email body content.
            is_html (bool): Whether the body is HTML. Defaults to False (plain text).
            
        Returns:
            bool: True if email sent successfully, False otherwise.
        """
        try:
            # Create the email message
            msg = MIMEMultipart()
            msg["From"] = self.sender_email
            msg["To"] = receiver_email
            msg["Subject"] = subject
            
            # Attach the body
            content_type = "html" if is_html else "plain"
            msg.attach(MIMEText(body, content_type))
            
            # Connect and send
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                server.login(self.sender_email, self.app_password)
                server.send_message(msg)
            
            print(f"✅ Email sent successfully to {receiver_email}!")
            return True
            
        except Exception as e:
            print(f"❌ Error sending email: {e}")
            return False


# Example usage
if __name__ == "__main__":
    # Initialize the email service
    email_service = EmailService()
    
    # Send a test email
    email_service.send_email(
        receiver_email="recipient@example.com",
        subject="Test Email via SMTP",
        body="Hello! This is a test email sent via Python SMTP. 🚀"
    )
