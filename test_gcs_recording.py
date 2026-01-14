"""
Test script to verify GCS recording uploads
Run: python test_gcs_recording.py [command] [args]
"""

import os
import json
import sys
from datetime import datetime, timedelta
from google.cloud import storage
from google.oauth2 import service_account
from dotenv import load_dotenv

load_dotenv()


def get_gcs_client():
    """Initialize GCS client with credentials from environment."""
    gcs_credentials_json = os.getenv("GCP_CREDENTIALS_JSON")
    gcs_bucket = os.getenv("GCS_BUCKET")
    
    if not gcs_credentials_json:
        raise ValueError("GCP_CREDENTIALS_JSON environment variable not set")
    if not gcs_bucket:
        raise ValueError("GCS_BUCKET environment variable not set")
    
    # Parse credentials - handle escaped newlines in private key
    credentials_dict = json.loads(gcs_credentials_json)
    
    # Fix escaped newlines in private_key (common issue with env vars)
    if "private_key" in credentials_dict:
        credentials_dict["private_key"] = credentials_dict["private_key"].replace("\\n", "\n")
    
    credentials = service_account.Credentials.from_service_account_info(credentials_dict)
    
    client = storage.Client(credentials=credentials, project=credentials_dict.get("project_id"))
    return client, gcs_bucket


def list_recordings(prefix="calls/", max_results=20):
    """List recordings in the GCS bucket."""
    try:
        client, bucket_name = get_gcs_client()
        bucket = client.bucket(bucket_name)
        
        print(f"\n{'='*60}")
        print(f"  GCS RECORDING CHECK")
        print(f"{'='*60}")
        print(f"Bucket: {bucket_name}")
        print(f"Prefix: {prefix}")
        print(f"{'='*60}\n")
        
        blobs = list(bucket.list_blobs(prefix=prefix, max_results=max_results))
        
        if not blobs:
            print("❌ No recordings found in the bucket")
            return []
        
        print(f"✅ Found {len(blobs)} recording(s):\n")
        
        recordings = []
        for blob in blobs:
            # Get blob metadata
            blob.reload()
            size_mb = blob.size / (1024 * 1024)
            created = blob.time_created
            
            print(f"  📁 {blob.name}")
            print(f"     Size: {size_mb:.2f} MB")
            print(f"     Created: {created}")
            print(f"     Content Type: {blob.content_type}")
            print()
            
            recordings.append({
                "name": blob.name,
                "size_mb": size_mb,
                "created": created,
                "content_type": blob.content_type
            })
        
        return recordings
        
    except Exception as e:
        print(f"❌ Error listing recordings: {e}")
        return []


def check_specific_recording(room_name: str):
    """Check if a specific recording exists for a room."""
    try:
        client, bucket_name = get_gcs_client()
        bucket = client.bucket(bucket_name)
        
        blob_name = f"calls/{room_name}.ogg"
        blob = bucket.blob(blob_name)
        
        print(f"\n{'='*60}")
        print(f"  CHECKING RECORDING FOR ROOM: {room_name}")
        print(f"{'='*60}\n")
        
        if blob.exists():
            blob.reload()
            size_mb = blob.size / (1024 * 1024)
            
            print(f"✅ Recording FOUND!")
            print(f"   Path: {blob_name}")
            print(f"   Size: {size_mb:.2f} MB")
            print(f"   Created: {blob.time_created}")
            print(f"   URL: gs://{bucket_name}/{blob_name}")
            
            # Generate signed URL for download (valid for 1 hour)
            try:
                signed_url = blob.generate_signed_url(
                    version="v4",
                    expiration=timedelta(hours=1),
                    method="GET"
                )
                print(f"\n   📥 Download URL (valid for 1 hour):")
                print(f"   {signed_url}")
            except Exception as e:
                print(f"\n   ⚠️ Could not generate signed URL: {e}")
            
            return True
        else:
            print(f"❌ Recording NOT FOUND for room: {room_name}")
            print(f"   Expected path: {blob_name}")
            return False
            
    except Exception as e:
        print(f"❌ Error checking recording: {e}")
        return False


def get_recent_recordings(hours=24):
    """Get recordings from the last N hours."""
    try:
        client, bucket_name = get_gcs_client()
        bucket = client.bucket(bucket_name)
        
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        print(f"\n{'='*60}")
        print(f"  RECENT RECORDINGS (Last {hours} hours)")
        print(f"{'='*60}\n")
        
        blobs = bucket.list_blobs(prefix="calls/")
        recent = []
        
        for blob in blobs:
            blob.reload()
            if blob.time_created.replace(tzinfo=None) > cutoff_time:
                recent.append(blob)
        
        if not recent:
            print(f"❌ No recordings found in the last {hours} hours")
            return []
        
        print(f"✅ Found {len(recent)} recording(s) in the last {hours} hours:\n")
        
        for blob in sorted(recent, key=lambda x: x.time_created, reverse=True):
            size_mb = blob.size / (1024 * 1024)
            print(f"  📁 {blob.name}")
            print(f"     Size: {size_mb:.2f} MB | Created: {blob.time_created}")
            print()
        
        return recent
        
    except Exception as e:
        print(f"❌ Error getting recent recordings: {e}")
        return []


def verify_gcs_connection():
    """Verify GCS connection and permissions."""
    try:
        client, bucket_name = get_gcs_client()
        bucket = client.bucket(bucket_name)
        
        print(f"\n{'='*60}")
        print(f"  GCS CONNECTION TEST")
        print(f"{'='*60}\n")
        
        print(f"Checking bucket: {bucket_name}")
        
        # Check if bucket exists
        if bucket.exists():
            print(f"✅ Bucket '{bucket_name}' exists and is accessible")
        else:
            print(f"❌ Bucket '{bucket_name}' does not exist or is not accessible")
            return False
        
        # Try to list (to verify read permissions)
        list(bucket.list_blobs(max_results=1))
        print(f"✅ Read permissions verified")
        
        # Check credentials info
        gcs_credentials_json = os.getenv("GCP_CREDENTIALS_JSON")
        credentials_dict = json.loads(gcs_credentials_json)
        print(f"✅ Project ID: {credentials_dict.get('project_id', 'N/A')}")
        print(f"✅ Service Account: {credentials_dict.get('client_email', 'N/A')}")
        
        return True
        
    except Exception as e:
        print(f"❌ GCS connection failed: {e}")
        return False


def download_recording(room_name: str, output_path: str = None):
    """Download a specific recording from GCS."""
    try:
        client, bucket_name = get_gcs_client()
        bucket = client.bucket(bucket_name)
        
        blob_name = f"calls/{room_name}.ogg"
        blob = bucket.blob(blob_name)
        
        if not blob.exists():
            print(f"❌ Recording not found: {blob_name}")
            return False
        
        if output_path is None:
            output_path = f"{room_name}.ogg"
        
        print(f"\n📥 Downloading {blob_name}...")
        blob.download_to_filename(output_path)
        print(f"✅ Downloaded to: {output_path}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error downloading recording: {e}")
        return False


def print_usage():
    """Print usage instructions."""
    print("\n" + "="*60)
    print("  GCS RECORDING VERIFICATION TOOL")
    print("="*60)
    print("\nUsage:")
    print("  python test_gcs_recording.py verify              - Test GCS connection")
    print("  python test_gcs_recording.py list                - List all recordings")
    print("  python test_gcs_recording.py recent [hours]      - Recent recordings (default: 24h)")
    print("  python test_gcs_recording.py check <room_name>   - Check specific room recording")
    print("  python test_gcs_recording.py download <room>     - Download a recording")
    print("  python test_gcs_recording.py all                 - Run all checks")
    print("\nExamples:")
    print("  python test_gcs_recording.py verify")
    print("  python test_gcs_recording.py check call-abc123")
    print("  python test_gcs_recording.py recent 6")
    print("  python test_gcs_recording.py download call-abc123")
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(0)
    
    command = sys.argv[1].lower()
    
    if command == "verify":
        verify_gcs_connection()
        
    elif command == "list":
        list_recordings()
        
    elif command == "recent":
        hours = int(sys.argv[2]) if len(sys.argv) > 2 else 24
        get_recent_recordings(hours)
        
    elif command == "check":
        if len(sys.argv) < 3:
            print("❌ Error: Room name required")
            print("Usage: python test_gcs_recording.py check <room_name>")
            sys.exit(1)
        room_name = sys.argv[2]
        check_specific_recording(room_name)
        
    elif command == "download":
        if len(sys.argv) < 3:
            print("❌ Error: Room name required")
            print("Usage: python test_gcs_recording.py download <room_name>")
            sys.exit(1)
        room_name = sys.argv[2]
        output_path = sys.argv[3] if len(sys.argv) > 3 else None
        download_recording(room_name, output_path)
        
    elif command == "all":
        print("\n" + "="*60)
        print("  RUNNING ALL CHECKS")
        print("="*60)
        
        if verify_gcs_connection():
            print("\n")
            list_recordings()
            print("\n")
            get_recent_recordings(24)
        else:
            print("\n❌ GCS connection failed - skipping other checks")
            
    else:
        print(f"❌ Unknown command: {command}")
        print_usage()
        sys.exit(1)
