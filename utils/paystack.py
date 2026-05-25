import os
import hmac
import hashlib
import requests
from flask import current_app
from requests.exceptions import RequestException
import logging

logger = logging.getLogger(__name__)

class PaystackService:
    def __init__(self):
        # Prefer app config, fallback to environment variable
        self.secret_key = current_app.config.get('PAYSTACK_SECRET_KEY') or os.getenv('PAYSTACK_SECRET_KEY')
        self.base_url = "https://api.paystack.co"
        
    def initialize_transaction(self, email: str, amount: float, reference: str = None, callback_url: str = None, metadata: dict = None) -> dict:
        """
        Initialize a Paystack transaction.
        Amount should be in the base currency (e.g., Naira). It will be converted to kobo.
        """
        if not self.secret_key:
            return {"status": False, "message": "Paystack secret key not configured."}

        url = f"{self.base_url}/transaction/initialize"
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json"
        }
        
        # Paystack expects amount in kobo (base currency unit)
        amount_kobo = int(float(amount) * 100)
        
        payload = {
            "email": email,
            "amount": amount_kobo,
        }
        
        if reference:
            payload["reference"] = reference
        if callback_url:
            payload["callback_url"] = callback_url
        if metadata:
            payload["metadata"] = metadata
            
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except RequestException as e:
            logger.error(f"Paystack initialization failed: {str(e)}")
            return {"status": False, "message": str(e)}
            
    def verify_transaction(self, reference: str) -> dict:
        """
        Verify a transaction by its reference.
        """
        if not self.secret_key:
            return {"status": False, "message": "Paystack secret key not configured."}

        url = f"{self.base_url}/transaction/verify/{reference}"
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except RequestException as e:
            logger.error(f"Paystack verification failed: {str(e)}")
            return {"status": False, "message": str(e)}

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify that the webhook request actually came from Paystack.
        """
        if not self.secret_key:
            return False
            
        computed_hmac = hmac.new(
            self.secret_key.encode('utf-8'),
            payload,
            hashlib.sha512
        ).hexdigest()
        
        return hmac.compare_digest(computed_hmac, signature)
