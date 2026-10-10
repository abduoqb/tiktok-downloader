import requests
import time
import json

BASE_URL = "http://127.0.0.1:5001"

def test_extraction_limit(username):
    print(f"Testing extraction for {username} with limit=5...")
    url = f"{BASE_URL}/api/extract"
    data = {"username": username, "limit": 5}
    try:
        response = requests.post(url, json=data)
        print(f"Extraction response: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Extraction failed: {e}")

if __name__ == "__main__":
    test_user = "tiboinshape" 
    test_extraction_limit(test_user)
