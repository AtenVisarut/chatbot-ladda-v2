"""
Test script for LINE webhook
Simulates LINE webhook events for local testing
"""

import requests
import json
import base64
import hashlib
import hmac
import os
from dotenv import load_dotenv

load_dotenv()

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
WEBHOOK_URL = "http://localhost:8000/webhook"

def generate_signature(body: str, secret: str) -> str:
    """Generate LINE webhook signature"""
    hash_digest = hmac.new(
        secret.encode('utf-8'),
        body.encode('utf-8'),
        hashlib.sha256
    ).digest()
    return base64.b64encode(hash_digest).decode('utf-8')

def test_text_message():
    """Test webhook with text message"""
    print("\n" + "=" * 60)
    print("Testing TEXT MESSAGE webhook")
    print("=" * 60)
    
    payload = {
        "destination": "xxxxxxxxxx",
        "events": [
            {
                "type": "message",
                "message": {
                    "type": "text",
                    "id": "123456789",
                    "text": "สวัสดี"
                },
                "timestamp": 1462629479859,
                "source": {
                    "type": "user",
                    "userId": "U4af4980629..."
                },
                "replyToken": "test-reply-token-12345",
                "mode": "active"
            }
        ]
    }
    
    body = json.dumps(payload)
    signature = generate_signature(body, LINE_CHANNEL_SECRET)
    
    headers = {
        "Content-Type": "application/json",
        "X-Line-Signature": signature
    }
    
    try:
        response = requests.post(WEBHOOK_URL, data=body, headers=headers)
        print(f"\n✅ Status Code: {response.status_code}")
        print(f"📝 Response: {response.json()}")
    except Exception as e:
        print(f"❌ Error: {e}")

def test_image_message():
    """Test webhook with image message"""
    print("\n" + "=" * 60)
    print("Testing IMAGE MESSAGE webhook")
    print("=" * 60)
    
    payload = {
        "destination": "xxxxxxxxxx",
        "events": [
            {
                "type": "message",
                "message": {
                    "type": "image",
                    "id": "325708",
                    "contentProvider": {
                        "type": "line"
                    }
                },
                "timestamp": 1462629479859,
                "source": {
                    "type": "user",
                    "userId": "U4af4980629..."
                },
                "replyToken": "test-reply-token-67890",
                "mode": "active"
            }
        ]
    }
    
    body = json.dumps(payload)
    signature = generate_signature(body, LINE_CHANNEL_SECRET)
    
    headers = {
        "Content-Type": "application/json",
        "X-Line-Signature": signature
    }
    
    try:
        response = requests.post(WEBHOOK_URL, data=body, headers=headers)
        print(f"\n✅ Status Code: {response.status_code}")
        print(f"📝 Response: {response.json()}")
    except Exception as e:
        print(f"❌ Error: {e}")

def test_health_endpoint():
    """Test health check endpoint"""
    print("\n" + "=" * 60)
    print("Testing HEALTH endpoint")
    print("=" * 60)
    
    try:
        response = requests.get("http://localhost:8000/health")
        print(f"\n✅ Status Code: {response.status_code}")
        print(f"📝 Response: {json.dumps(response.json(), indent=2)}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("LINE Webhook Test Suite")
    print("=" * 60)
    print("\n⚠️  Make sure your server is running on http://localhost:8000")
    print("   Start it with: python main.py\n")
    
    input("Press Enter to start tests...")
    
    # Run tests
    test_health_endpoint()
    test_text_message()
    
    print("\n" + "=" * 60)
    print("⚠️  Image message test requires actual LINE message ID")
    print("   This will fail unless you have a real message ID from LINE")
    response = input("\nRun image message test anyway? (yes/no): ")
    
    if response.lower() == 'yes':
        test_image_message()
    
    print("\n" + "=" * 60)
    print("✅ Testing complete!")
    print("=" * 60)
