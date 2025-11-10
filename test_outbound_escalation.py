"""
Quick test script for outbound call with escalation endpoint
Usage: python test_outbound_escalation.py
"""

import requests
import json
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# API Configuration
API_BASE_URL = "http://localhost:8000"
ENDPOINT = f"{API_BASE_URL}/calls/outbound-with-escalation"

# Test Configuration
TEST_PHONE = os.getenv("TEST_PHONE_NUMBER", "+919911062767")
TEST_NAME = "Test Customer"

def test_basic_call():
    """Test basic outbound call with escalation"""
    print("=" * 60)
    print("Testing: Basic Outbound Call with Escalation")
    print("=" * 60)
    
    payload = {
        "phone_number": TEST_PHONE,
        "name": TEST_NAME
    }
    
    print(f"\n📞 Calling: {TEST_PHONE}")
    print(f"👤 Name: {TEST_NAME}")
    print(f"\n🔗 Endpoint: {ENDPOINT}")
    print(f"📤 Request Payload:\n{json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(ENDPOINT, json=payload)
        
        print(f"\n📥 Response Status: {response.status_code}")
        print(f"📥 Response Body:\n{json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("\n✅ SUCCESS: Call initiated successfully!")
            print("\n💡 Next steps:")
            print("   1. Answer the call on your phone")
            print("   2. Talk to the AI agent")
            print("   3. Say 'I want to speak to a supervisor' to test escalation")
            print("   4. Supervisor should receive a call with context")
            print("   5. Supervisor says 'ready' to merge calls")
        else:
            print(f"\n❌ ERROR: {response.json().get('detail', 'Unknown error')}")
            
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Cannot connect to API server")
        print("   Make sure the API server is running:")
        print("   python api.py")
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")


def test_customer_support_call():
    """Test customer support scenario with custom instructions"""
    print("\n" + "=" * 60)
    print("Testing: Customer Support Call with Escalation")
    print("=" * 60)
    
    payload = {
        "phone_number": TEST_PHONE,
        "name": "Rajesh Kumar",
        "dynamic_instruction": "You are a LiveKit customer support agent calling to follow up on a support ticket about login issues. Be empathetic and helpful. If you cannot resolve the issue, offer to connect them with a supervisor.",
        "language": "en",
        "emotion": "Calm"
    }
    
    print(f"\n📞 Calling: {TEST_PHONE}")
    print(f"👤 Name: Rajesh Kumar")
    print(f"📋 Scenario: Customer Support Follow-up")
    print(f"\n🔗 Endpoint: {ENDPOINT}")
    print(f"📤 Request Payload:\n{json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(ENDPOINT, json=payload)
        
        print(f"\n📥 Response Status: {response.status_code}")
        print(f"📥 Response Body:\n{json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("\n✅ SUCCESS: Customer support call initiated!")
        else:
            print(f"\n❌ ERROR: {response.json().get('detail', 'Unknown error')}")
            
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Cannot connect to API server")
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")


def check_prerequisites():
    """Check if all prerequisites are met"""
    print("=" * 60)
    print("Checking Prerequisites")
    print("=" * 60)
    
    issues = []
    
    # Check API server
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✅ API server is running")
        else:
            print("⚠️  API server returned unexpected status")
            issues.append("API server issue")
    except:
        print("❌ API server is NOT running")
        issues.append("Start API server: python api.py")
    
    # Check required environment variables
    required_vars = [
        "LIVEKIT_API_KEY",
        "LIVEKIT_API_SECRET",
        "LIVEKIT_URL",
        "LIVEKIT_SIP_OUTBOUND_TRUNK"
    ]
    
    for var in required_vars:
        if os.getenv(var):
            print(f"✅ {var} is set")
        else:
            print(f"❌ {var} is NOT set")
            issues.append(f"Set {var} in .env file")
    
    # Check optional but important variables
    if os.getenv("LIVEKIT_SUPERVISOR_PHONE_NUMBER"):
        print(f"✅ LIVEKIT_SUPERVISOR_PHONE_NUMBER is set: {os.getenv('LIVEKIT_SUPERVISOR_PHONE_NUMBER')}")
    else:
        print("⚠️  LIVEKIT_SUPERVISOR_PHONE_NUMBER is NOT set")
        print("   (Escalation will not work, but calls will)")
        issues.append("Set LIVEKIT_SUPERVISOR_PHONE_NUMBER for escalation")
    
    print()
    
    if issues:
        print("⚠️  Issues found:")
        for issue in issues:
            print(f"   - {issue}")
        print()
        return False
    else:
        print("✅ All prerequisites met!")
        print()
        return True


def main():
    """Main test function"""
    print("\n" + "🚀 " * 20)
    print("   OUTBOUND CALL WITH ESCALATION - TEST SCRIPT")
    print("🚀 " * 20 + "\n")
    
    # Check prerequisites
    all_good = check_prerequisites()
    
    if not all_good:
        print("❌ Please fix the issues above before testing.\n")
        return
    
    # Ask user which test to run
    print("Select test to run:")
    print("  1. Basic call (minimal configuration)")
    print("  2. Customer support call (with custom instructions)")
    print("  3. Both tests")
    print("  0. Exit")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == "1":
        test_basic_call()
    elif choice == "2":
        test_customer_support_call()
    elif choice == "3":
        test_basic_call()
        input("\n⏸️  Press Enter to run next test...")
        test_customer_support_call()
    elif choice == "0":
        print("Exiting...")
        return
    else:
        print("Invalid choice")
    
    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)
    print("\n💡 Tips:")
    print("   - Check agent worker logs (python outbound.py)")
    print("   - Check API server logs (python api.py)")
    print("   - View detailed guide: OUTBOUND_ESCALATION_GUIDE.md")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {str(e)}")

