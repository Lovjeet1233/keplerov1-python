import os
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
auth_token  = os.environ.get("TWILIO_AUTH_TOKEN")
twilio_number = os.environ.get("TWILIO_NUMBER")  # e.g. "+1XXXXXXXXXX"

client = Client(account_sid, auth_token)

message = client.messages.create(
    body="Hello from Twilio! 🚀",
    from_=twilio_number,
    to="+917230088638"
)

print("Message SID:", message.sid)
