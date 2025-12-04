def create_flutterwave_transaction(
    self, user, campaign, amount, currency, request_id=None
):
    """Create Flutterwave payment transaction for matchmaking"""
    try:
        # Generate unique transaction reference
        if request_id:
            tx_ref = f"KIMBELA_MATCHMAKING_{request_id}_{int(time.time())}"
        else:
            tx_ref = f"KIMBELA_AD_{campaign.id}_{int(time.time())}"

        # Use appropriate callback URL
        if request_id:
            redirect_url = url_for("payments.flutterwave_callback", _external=True)
        else:
            redirect_url = url_for("payments.flutterwave_callback", _external=True)

        payment_data = {
            "tx_ref": tx_ref,
            "amount": str(float(amount)),
            "currency": currency,
            "redirect_url": redirect_url,
            "customer": {
                "email": user.email,
                "name": user.first_name or user.email.split("@")[0],
            },
            "meta": {
                "user_id": user.id,
                "request_id": request_id,
                "campaign_id": campaign.id if campaign else None,
            },
            "customizations": {
                "title": "Kimbela Matchmaking" if request_id else "Kimbela Ads",
                "description": (
                    f"Matchmaking Request"
                    if request_id
                    else f"Ad Campaign: {campaign.title}"
                ),
                "logo": url_for("static", filename="images/logo.png", _external=True),
            },
        }

        headers = {
            "Authorization": f"Bearer {self.flutterwave_secret_key}",
            "Content-Type": "application/json",
        }

        response = requests.post(
            f"{self.flutterwave_base_url}/payments", headers=headers, json=payment_data
        )

        if response.status_code == 200:
            result = response.json()

            if result.get("status") == "success":
                payment_url = result["data"]["link"]

                # Create payment record
                payment = PaymentTransaction(
                    user_id=user.id,
                    campaign_id=(
                        request_id
                        if request_id
                        else (campaign.id if campaign else None)
                    ),
                    amount=amount,
                    currency=currency,
                    gateway_payment_id=tx_ref,
                    gateway="flutterwave",
                    status="pending",
                    transaction_type="matchmaking" if request_id else "ad_campaign",
                )
                db.session.add(payment)
                db.session.commit()

                return {
                    "success": True,
                    "payment_url": payment_url,
                    "gateway_payment_id": tx_ref,
                    "message": "Payment initiated successfully",
                }
            else:
                error_msg = result.get("message", "Unknown Flutterwave error")
                return {"success": False, "error": f"Flutterwave error: {error_msg}"}
        else:
            return {
                "success": False,
                "error": f"Payment gateway HTTP error: {response.status_code}",
            }

    except Exception as e:
        return {"success": False, "error": f"Payment processing error: {str(e)}"}
