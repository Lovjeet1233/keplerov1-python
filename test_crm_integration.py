"""
Test script to verify CRM tools integration with chatbot.
"""

import requests
import json

BASE_URL = "http://localhost:8000"

def test_crm_integration():
    """Test complete CRM integration flow."""
    
    print("=" * 60)
    print("CRM TOOLS INTEGRATION TEST")
    print("=" * 60)
    
    user_id = "user_1234"
    
    # Step 1: Check if CRM tools are registered
    print(f"\n1. Checking CRM tools for user: {user_id}")
    response = requests.get(f"{BASE_URL}/crm/tools", params={"user_id": user_id})
    
    if response.status_code == 200:
        data = response.json()
        print(f"   ✓ Found {data['count']} CRM tool(s)")
        for tool_id, tool_data in data['tools'].items():
            print(f"     - {tool_data['tool_name']}: {tool_data['description']}")
    else:
        print(f"   ✗ Error: {response.text}")
        return
    
    # Step 2: Test chatbot with CRM tools
    print(f"\n2. Testing chatbot with CRM search query")
    chat_request = {
        "query": "Search for customer with email john@example.com",
        "collection_names": [""],
        "top_k": 5,
        "thread_id": "test_crm_thread",
        "system_prompt": "You are a helpful assistant with access to CRM tools. Use the CRM search tool to find customer information when asked.",
        "skip_history": False,
        "user_id": user_id
    }
    
    print(f"   Request: {json.dumps(chat_request, indent=2)}")
    
    response = requests.post(f"{BASE_URL}/rag/chat", json=chat_request)
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n   ✓ Response received:")
        print(f"     Query: {data['query']}")
        print(f"     Answer: {data['answer']}")
        print(f"     Latency: {data['latency_ms']:.2f}ms")
    else:
        print(f"   ✗ Error: {response.text}")
        return
    
    # Step 3: Test with create query
    print(f"\n3. Testing chatbot with CRM create query")
    chat_request = {
        "query": "Create a new customer named Jane Smith with email jane@example.com and phone +1234567890",
        "collection_names": [""],
        "thread_id": "test_crm_thread",
        "system_prompt": "You are a helpful assistant with access to CRM tools. Use the CRM create tool to add new customers when asked.",
        "user_id": user_id
    }
    
    response = requests.post(f"{BASE_URL}/rag/chat", json=chat_request)
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n   ✓ Response received:")
        print(f"     Answer: {data['answer']}")
    else:
        print(f"   ✗ Error: {response.text}")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_crm_integration()
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
