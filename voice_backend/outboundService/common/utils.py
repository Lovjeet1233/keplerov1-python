import os
import shutil
import json
import time
import logging
from typing import Optional
from .config.settings import TRANSCRIPT_DIR, SERVER_LOG_FILE

def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        filename=SERVER_LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

def clean_transcript_folder():
    """Clean and recreate transcript folder"""
    if os.path.exists(TRANSCRIPT_DIR):
        shutil.rmtree(TRANSCRIPT_DIR)
    os.makedirs(TRANSCRIPT_DIR, exist_ok=True)

def get_transcript(timeout: int = 400) -> Optional[dict]:
    """Poll for transcript.json for up to `timeout` seconds."""
    transcript_path = os.path.join(TRANSCRIPT_DIR, "transcript.json")
    waited = 0
    while waited < timeout:
        if os.path.exists(transcript_path):
            with open(transcript_path, "r") as f:
                return json.load(f)
        time.sleep(2)
        waited += 2
    return None

def validate_phone_number(phone_number: str) -> bool:
    """Validate phone number format"""
    # Basic validation - should start with + and contain only digits
    if not phone_number.startswith('+'):
        return False
    digits = phone_number[1:]  # Remove the + sign
    return digits.isdigit() and len(digits) >= 10

def format_phone_number(phone_number: str) -> str:
    """Format phone number to standard format"""
    # Remove any non-digit characters except +
    cleaned = ''.join(c for c in phone_number if c.isdigit() or c == '+')
    if not cleaned.startswith('+'):
        cleaned = '+' + cleaned
    return cleaned 