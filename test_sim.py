import requests
import json

# Automatically strips any hidden spaces around the keys
CONSUMER_KEY = "kbA7zOrdEGqN5rsCJN2yZKK1LS8B9LznGnqgZqRuAMHghUJh".strip()
CONSUMER_SECRET = "OWqtjPRNE7sYEGSkaFJ4s7mipuvhjIgBRPNMntqEwAVp5UCDwfZVG9t4Lgm8r6FA".strip()

print("1. Requesting access token...")
auth_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
response = requests.get(auth_url, auth=(CONSUMER_KEY, CONSUMER_SECRET))

print(f"Status Code: {response.status_code}")
print(f"Response Text: {response.text}")

if response.status_code == 200:
    token_data = response.json()
    access_token = token_data.get("access_token")
    print("Token obtained successfully:", access_token)
    
    # 2. Register Your Webhook URL
    print("\n2. Registering Webhook URL with Safaricom Sandbox...")
    register_url = "https://sandbox.safaricom.co.ke/mpesa/c2b/v1/registerurl"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    register_payload = {
        "ShortCode": "174379",
        "ResponseType": "Completed",
        "ConfirmationUrl": "https://gym-mpesa-logger.onrender.com/mpesa-webhook",
        "ValidationUrl": "https://gym-mpesa-logger.onrender.com/mpesa-webhook"
    }
    reg_response = requests.post(register_url, json=register_payload, headers=headers)
    print("Registration Response:", reg_response.json())

    # 3. Simulate a Payment
    print("\n3. Simulating a test payment of KES 1,500 for member 'John Doe'...")
    simulate_url = "https://sandbox.safaricom.co.ke/mpesa/c2b/v1/simulate"
    sim_payload = {
        "ShortCode": "174379",
        "CommandID": "CustomerPayBillOnline",
        "Amount": "1500",
        "Msisdn": "254708374149",
        "BillRefNumber": "John Doe"
    }
    sim_response = requests.post(simulate_url, json=sim_payload, headers=headers)
    print("Simulation Response:", sim_response.json())
else:
    print("Failed to get token. Let's check the output above.")