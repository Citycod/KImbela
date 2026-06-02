from flask import (
    Blueprint,
    request,
    jsonify,
    render_template,
    redirect,
    url_for,
    current_app,
    flash,
    abort,
)
from sqlalchemy import or_
from flask_login import login_required, current_user
from flask_wtf.csrf import generate_csrf
from extensions import db, mail, bcrypt, csrf
from models import (
    User,
    AdCampaign,
    AdPackage,
    PaymentTransaction,
    MatchmakingPayments,
    MarketplacePayment,
)
import cloudinary.uploader
import os, requests
import math
from email_service import EmailService
from resend_mail import Message
import json
from datetime import datetime, timedelta, date
import time
import time


from time_utils import utcnow
payments = Blueprint("payments", __name__)


def _find_payment_transaction_by_tx_ref(tx_ref):
    return PaymentTransaction.query.filter(
        or_(
            PaymentTransaction.gateway_reference == tx_ref,
            PaymentTransaction.gateway_payment_id == tx_ref,
        )
    ).first()


def _is_marketplace_tx_ref(tx_ref):
    return (tx_ref or "").startswith(("KIMBELA-MP-", "KIMBELA_MARKET_", "KIMBELA-SUB-"))


def _get_dashboard_ad_usd_to_ngn_rate():
    from .payment_service import BasePaymentService

    return BasePaymentService().get_ngn_rate("USD_TO_NGN_RATE")


def _get_dashboard_ad_daily_budget_bounds(placement=None):
    usd_min = 5.0 if placement == "dashboard-top" else 2.0
    usd_max = 50.0
    return {
        "usd_min": usd_min,
        "usd_max": usd_max,
        "ngn_min_input": math.ceil(usd_min), # Kept for backward compatibility if needed, but holds USD value
        "ngn_max_input": math.ceil(usd_max),
        "rate": 1.0,
        "est_reach_min_per_usd": 240,
        "est_reach_max_per_usd": 680,
        "est_clicks_min_per_usd": 5,
        "est_clicks_max_per_usd": 15,
    }


def _get_or_create_guest_advertiser(name, email):
    user = User.query.filter_by(email=email).first()
    if user:
        return user

    parts = (name or "").strip().split()
    first_name = parts[0] if parts else "Guest"
    last_name = " ".join(parts[1:]) if len(parts) > 1 else "Advertiser"
    random_password = os.urandom(12).hex()
    password_hash = bcrypt.generate_password_hash(random_password).decode("utf-8")

    user = User(
        first_name=first_name,
        last_name=last_name,
        email=email,
        password_hash=password_hash,
        city="Unknown",
        country="Unknown",
        state="",
        dob=date(1990, 1, 1),
        gender="other",
        phone_number="N/A",
        is_active=False,
    )
    db.session.add(user)
    db.session.commit()
    return user


def _require_debug_access():
    """Restrict debug endpoints to admins when explicitly enabled."""
    if not current_user.is_authenticated:
        abort(404)
    if not current_user.is_super_admin:
        abort(404)
    if not current_app.config.get("ENABLE_DEBUG_ROUTES"):
        abort(404)

DASHBOARD_AD_PLACEMENTS = {
    "dashboard-top": {
        "title": "Top Banner Spotlight",
        "subtitle": "Stretch across the feed with a bold, horizontal banner.",
        "image_width": 1600,
        "image_height": 400,
        "recommended_size": "1600 x 400 px",
    },
    "dashboard-sidebar": {
        "title": "Sidebar Boost",
        "subtitle": "Stay visible while people explore menus and features.",
        "image_width": 1200,
        "image_height": 900,
        "recommended_size": "1200 x 900 px",
    },
    "dashboard-vertical": {
        "title": "Vertical Feature",
        "subtitle": "A tall format for storytelling visuals and offers.",
        "image_width": 900,
        "image_height": 1200,
        "recommended_size": "900 x 1200 px",
    },
    "dashboard-spotlight": {
        "title": "Spotlight Card",
        "subtitle": "Catch attention in the premium side placement.",
        "image_width": 1400,
        "image_height": 900,
        "recommended_size": "1400 x 900 px",
    },
    "dashboard-bottom": {
        "title": "Sticky Bottom Banner",
        "subtitle": "Stay visible while people scroll the feed.",
        "image_width": 1600,
        "image_height": 240,
        "recommended_size": "1600 x 240 px",
    },
}


@payments.route("/ad-packages")
@login_required
def ad_packages():
    """Display available ad packages"""
    packages = AdPackage.query.filter_by(is_active=True).all()
    return render_template(
        "packages.html",
        packages=packages,
        ad_pricing=_get_dashboard_ad_daily_budget_bounds(),
    )




@payments.route("/ads/request", methods=["GET", "POST"])
def public_ad_request():
    placement = request.args.get("placement", "dashboard-top")
    placement_config = DASHBOARD_AD_PLACEMENTS.get(placement)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        company = request.form.get("company", "").strip()
        message = request.form.get("message", "").strip()

        if not name or not email:
            flash("Please provide your name and email.", "error")
            return redirect(url_for("payments.public_ad_request", placement=placement))

        recipient = (
            current_app.config.get("ADMIN_EMAIL")
            or current_app.config.get("MAIL_DEFAULT_SENDER")
        )
        if recipient:
            try:
                msg = Message(
                    subject="New Public Ad Request",
                    sender=current_app.config.get("MAIL_DEFAULT_SENDER"),
                    recipients=[recipient],
                )
                msg.body = (
                    f"New ad request from {name}\n"
                    f"Email: {email}\n"
                    f"Company: {company}\n"
                    f"Placement: {placement}\n"
                    f"Message: {message}"
                )
                mail.send(msg)
            except Exception:
                current_app.logger.exception("Failed to send public ad request email")
        flash("Thanks! We received your ad request and will reach out shortly.", "success")
        return redirect(url_for("payments.public_ad_request", placement=placement))

    return render_template(
        "public_ad_request.html",
        placement=placement,
        placement_config=placement_config,
    )


@payments.route("/public/dashboard-ads/<placement>")
def public_dashboard_ad_package(placement):
    placement_config = DASHBOARD_AD_PLACEMENTS.get(placement)
    if not placement_config:
        flash("Unknown ad placement", "error")
        return redirect(url_for("user.index"))

    return render_template(
        "dashboard_ad_package.html",
        placement=placement,
        placement_config=placement_config,
        csrf_token=generate_csrf(),
        is_public=True,
        return_url=url_for("user.index"),
        return_label="Back to home",
        upload_image_url=url_for("payments.public_upload_dashboard_ad_image", placement=placement),
        upload_video_url=url_for("payments.public_upload_dashboard_ad_video", placement=placement),
        create_campaign_url=url_for("payments.public_create_campaign"),
        initiate_payment_url=url_for("payments.public_initiate_payment"),
        ad_pricing=_get_dashboard_ad_daily_budget_bounds(placement),
    )


@payments.route("/public/dashboard-ads/<placement>/upload", methods=["POST"])
def public_upload_dashboard_ad_image(placement):
    placement_config = DASHBOARD_AD_PLACEMENTS.get(placement)
    if not placement_config:
        return jsonify({"success": False, "error": "Unknown ad placement"}), 400

    try:
        if "image" not in request.files:
            return jsonify({"success": False, "error": "No image provided"})

        image_file = request.files["image"]
        if image_file.filename == "":
            return jsonify({"success": False, "error": "No image selected"})

        upload_result = cloudinary.uploader.upload(
            image_file,
            folder="kimbela/dashboard-ads",
            width=placement_config["image_width"],
            height=placement_config["image_height"],
            crop="fit",
            quality="auto",
        )

        return jsonify(
            {
                "success": True,
                "image_url": upload_result["secure_url"],
                "public_id": upload_result["public_id"],
            }
        )

    except Exception as e:
        current_app.logger.error(f"❌ Public dashboard ad image upload failed: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@payments.route("/public/dashboard-ads/<placement>/upload-video", methods=["POST"])
def public_upload_dashboard_ad_video(placement):
    allowed_placements = {
        "dashboard-sidebar",
        "dashboard-vertical",
        "dashboard-spotlight",
    }
    if placement not in allowed_placements:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Video ads are only for left/right sidebar placements",
                }
            ),
            400,
        )

    try:
        if "video" not in request.files:
            return jsonify({"success": False, "error": "No video provided"})

        video_file = request.files["video"]
        if video_file.filename == "":
            return jsonify({"success": False, "error": "No video selected"})

        if not video_file.mimetype.startswith("video/"):
            return jsonify({"success": False, "error": "Invalid video type"}), 400

        upload_result = cloudinary.uploader.upload(
            video_file,
            folder="kimbela/dashboard-ads",
            resource_type="video",
            quality="auto",
        )

        return jsonify(
            {
                "success": True,
                "video_url": upload_result["secure_url"],
                "public_id": upload_result["public_id"],
            }
        )

    except Exception as e:
        current_app.logger.error(f"❌ Public dashboard ad video upload failed: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@payments.route("/public/create-campaign", methods=["POST"])
def public_create_campaign():
    try:
        data = request.get_json(silent=True) or request.form.to_dict()
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400

        name = data.get("contact_name") or data.get("name") or ""
        email = data.get("contact_email") or data.get("email") or ""
        company = data.get("contact_company") or data.get("company") or ""

        if not name or not email:
            return jsonify({"success": False, "error": "Name and email are required"}), 400

        daily_budget = data.get("daily_budget")
        duration_days = data.get("duration_days")
        title = data.get("title")
        description = data.get("description")
        target_url = data.get("target_url")
        call_to_action = data.get("call_to_action", "Learn More")
        image = data.get("image", "")
        currency = data.get("currency", "USD")
        placement = data.get("placement", "dashboard-top")

        if not title:
            return jsonify({"success": False, "error": "Ad title is required"}), 400
        if not target_url:
            return jsonify({"success": False, "error": "Target URL is required"}), 400
        if not daily_budget or not duration_days:
            return jsonify({"success": False, "error": "Budget and duration are required"}), 400
        if placement in DASHBOARD_AD_PLACEMENTS and not image:
            return jsonify({"success": False, "error": "Please upload a banner image"}), 400
        if placement != "sponsored" and placement not in DASHBOARD_AD_PLACEMENTS:
            return jsonify({"success": False, "error": "Invalid ad placement selected"}), 400

        try:
            daily_budget = float(daily_budget)
            duration_days = int(duration_days)
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Invalid budget or duration"}), 400

        ad_pricing = _get_dashboard_ad_daily_budget_bounds(placement)
        if daily_budget < ad_pricing["usd_min"]:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Minimum daily budget is ${ad_pricing['usd_min']:,.2f}",
                    }
                ),
                400,
            )
        if duration_days < 3:
            return jsonify({"success": False, "error": "Minimum duration is 3 days"}), 400

        user = _get_or_create_guest_advertiser(name, email)

        total_budget = daily_budget * duration_days
        details_prefix = f"Public Ad Request | {name} | {email}"
        if company:
            details_prefix += f" | {company}"
        if description:
            full_description = f"{details_prefix}\n{description}"
        else:
            full_description = details_prefix

        campaign = AdCampaign(
            user_id=user.id,
            title=title,
            description=full_description,
            image=image,
            target_url=target_url,
            call_to_action=call_to_action,
            budget=total_budget,
            daily_budget=daily_budget,
            duration_days=duration_days,
            currency=currency,
            placement=placement,
            status="pending",
            payment_status="pending",
            target_gender=None,
            target_age_min=31,
            target_age_max=65,
        )

        db.session.add(campaign)
        db.session.commit()

        return jsonify({"success": True, "campaign_id": campaign.id})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"❌ Public create campaign failed: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@payments.route("/public/initiate-payment", methods=["POST"])
def public_initiate_payment():
    try:
        data = request.get_json(silent=True) or request.form.to_dict()
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400

        campaign_id = data.get("campaign_id")
        currency = (data.get("currency") or "USD").upper()
        gateway = (data.get("gateway") or "flutterwave").lower()
        contact_payload = {
            "name": data.get("contact_name") or data.get("name") or "",
            "email": data.get("contact_email") or data.get("email") or "",
            "company": data.get("contact_company") or data.get("company") or "",
        }

        if not campaign_id:
            return jsonify({"success": False, "error": "Missing campaign"}), 400

        campaign = AdCampaign.query.get(campaign_id)
        if not campaign:
            return jsonify({"success": False, "error": "Campaign not found"}), 404

        user = User.query.get(campaign.user_id)
        if not user:
            return jsonify({"success": False, "error": "Campaign owner not found"}), 404

        from .payment_service_ad import AdCampaignPaymentService

        ad_service = AdCampaignPaymentService()
        result = ad_service.create_ad_campaign_payment(user, campaign, currency, gateway)
        if not result.get("success"):
            return jsonify(result), 400

        gateway_payment_id = result.get("gateway_payment_id")
        if gateway_payment_id:
            tx = PaymentTransaction.query.filter_by(
                gateway_payment_id=gateway_payment_id
            ).first()
            if tx:
                try:
                    import json

                    tx.gateway_metadata = json.dumps({"public_contact": contact_payload})
                    db.session.commit()
                except Exception:
                    db.session.rollback()

        return jsonify(result)

    except Exception as e:
        current_app.logger.error(f"❌ Public initiate payment failed: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500
@payments.route("/dashboard-ads/<placement>")
@login_required
def dashboard_ad_package(placement):
    """Display dashboard banner ad package page"""
    placement_config = DASHBOARD_AD_PLACEMENTS.get(placement)
    if not placement_config:
        flash("Unknown ad placement", "error")
        return redirect(url_for("payments.ad_packages"))

    return render_template(
        "dashboard_ad_package.html",
        placement=placement,
        placement_config=placement_config,
        ad_pricing=_get_dashboard_ad_daily_budget_bounds(placement),
    )


@payments.route("/dashboard-ads/<placement>/upload", methods=["POST"])
@login_required
def upload_dashboard_ad_image(placement):
    """Upload dashboard banner ad image to Cloudinary"""
    placement_config = DASHBOARD_AD_PLACEMENTS.get(placement)
    if not placement_config:
        return jsonify({"success": False, "error": "Unknown ad placement"}), 400

    try:
        if "image" not in request.files:
            return jsonify({"success": False, "error": "No image provided"})

        image_file = request.files["image"]
        if image_file.filename == "":
            return jsonify({"success": False, "error": "No image selected"})

        upload_result = cloudinary.uploader.upload(
            image_file,
            folder="kimbela/dashboard-ads",
            width=placement_config["image_width"],
            height=placement_config["image_height"],
            crop="fit",
            quality="auto",
        )

        current_app.logger.info(
            f"✅ Dashboard ad image uploaded for user {current_user.id}"
        )

        return jsonify(
            {
                "success": True,
                "image_url": upload_result["secure_url"],
                "public_id": upload_result["public_id"],
            }
        )

    except Exception as e:
        current_app.logger.error(f"❌ Dashboard ad image upload failed: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@payments.route("/dashboard-ads/<placement>/upload-video", methods=["POST"])
@login_required
def upload_dashboard_ad_video(placement):
    """Upload dashboard banner video to Cloudinary (sidebar placement only)"""
    allowed_placements = {
        "dashboard-sidebar",
        "dashboard-vertical",
        "dashboard-spotlight",
    }
    if placement not in allowed_placements:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Video ads are only for left/right sidebar placements",
                }
            ),
            400,
        )

    try:
        if "video" not in request.files:
            return jsonify({"success": False, "error": "No video provided"})

        video_file = request.files["video"]
        if video_file.filename == "":
            return jsonify({"success": False, "error": "No video selected"})

        if not video_file.mimetype.startswith("video/"):
            return jsonify({"success": False, "error": "Invalid video type"}), 400

        upload_result = cloudinary.uploader.upload(
            video_file,
            folder="kimbela/dashboard-ads",
            resource_type="video",
            quality="auto",
        )

        current_app.logger.info(
            f"✅ Dashboard ad video uploaded for user {current_user.id}"
        )

        return jsonify(
            {
                "success": True,
                "video_url": upload_result["secure_url"],
                "public_id": upload_result["public_id"],
            }
        )

    except Exception as e:
        current_app.logger.error(f"❌ Dashboard ad video upload failed: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@payments.route("/upload-image", methods=["POST"])
@login_required
def upload_image():
    """Upload ad image to Cloudinary"""
    try:
        if "image" not in request.files:
            return jsonify({"success": False, "error": "No image provided"})

        image_file = request.files["image"]
        if image_file.filename == "":
            return jsonify({"success": False, "error": "No image selected"})

        # Upload to Cloudinary
        upload_result = cloudinary.uploader.upload(
            image_file,
            folder="kimbela/ads",
            width=1200,
            height=630,
            crop="fit",
            quality="auto",
        )

        current_app.logger.info(
            f"✅ Image uploaded successfully for user {current_user.id}"
        )

        return jsonify(
            {
                "success": True,
                "image_url": upload_result["secure_url"],
                "public_id": upload_result["public_id"],
            }
        )

    except Exception as e:
        current_app.logger.error(f"❌ Image upload failed: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@payments.route("/payment-callback", methods=["GET", "POST"])
def payment_callback():
    """Handle payment callback from Flutterwave and redirect to appropriate pages"""
    try:
        from .payment_service import (
            PaymentService,
            AdCampaignPaymentService,
            MatchmakingPaymentService,
            BasePaymentService,
        )
        from flask import redirect, url_for, flash

        print("🟡 [PAYMENT CALLBACK] Received callback")
        payload = request.get_json(silent=True) or {}

        # Get transaction reference AND transaction ID from request
        tx_ref = request.args.get("tx_ref") or payload.get("tx_ref")
        status = request.args.get("status") or payload.get("status")
        transaction_id = request.args.get(
            "transaction_id"
        )  # Flutterwave's transaction ID

        print(
            f"🟡 [PAYMENT CALLBACK] tx_ref: {tx_ref}, status: {status}, transaction_id: {transaction_id}"
        )

        if not tx_ref:
            flash("Missing transaction reference", "error")
            return redirect(url_for("payments.payment_failed"))

        # Initialize payment services
        base_service = BasePaymentService()
        payment_service = PaymentService()
        ad_service = AdCampaignPaymentService()
        matchmaking_service = MatchmakingPaymentService()

        # Determine transaction type and handle accordingly
        if tx_ref.startswith("KIMBELA_AD_"):
            # Ad campaign payment
            transaction = _find_payment_transaction_by_tx_ref(tx_ref)
            if not transaction:
                print(f"🔴 [PAYMENT CALLBACK] Ad transaction not found: {tx_ref}")
                flash("Transaction not found", "error")
                return redirect(url_for("payments.payment_failed"))

            if transaction.gateway == "paystack":
                verification = base_service.resolve_paystack_verification(reference=tx_ref)
            else:
                verification = base_service.resolve_flutterwave_verification(
                    tx_ref=tx_ref, transaction_id=transaction_id
                )
                
            verification_data = verification.get("data", {}) or {}
            verified_status = (verification.get("verified_status") or "").strip().lower()

            if verified_status in {"successful", "completed"}:
                    # Update transaction and campaign
                    success = ad_service.handle_ad_payment_success(
                        transaction.id, verification_data
                    )
                    if success:
                        print(
                            f"✅ [PAYMENT CALLBACK] Ad payment processed successfully"
                        )
                        flash(
                            "Payment completed successfully! Your campaign is now active.",
                            "success",
                        )
                        return redirect(
                            url_for(
                                "payments.payment_success",
                                transaction_id=transaction.id,
                            )
                        )
                    else:
                        print(f"🔴 [PAYMENT CALLBACK] Failed to process ad payment")
                        flash(
                            "Failed to process payment. Please contact support.",
                            "error",
                        )
                        return redirect(url_for("payments.payment_failed"))
            elif verified_status in {"pending", "processing"}:
                ad_service.handle_ad_payment_failure(
                    transaction.id,
                    verification_data or {"status": verified_status},
                )
                flash(
                    "Payment received and is still being confirmed by Flutterwave.",
                    "info",
                )
                return redirect(url_for("payments.payment_failed"))
            else:
                ad_service.handle_ad_payment_failure(
                    transaction.id,
                    verification_data
                    or {"status": status or "failed", "message": verification.get("error")},
                )
                flash("Payment failed. Please try again.", "error")
                return redirect(url_for("payments.payment_failed"))

        elif tx_ref.startswith("KIMBELA_MATCH_"):
            # Matchmaking payment
            matchmaking_payment = MatchmakingPayments.query.filter_by(
                gateway_reference=tx_ref
            ).first()
            if not matchmaking_payment:
                print(f"🔴 [PAYMENT CALLBACK] Matchmaking payment not found: {tx_ref}")
                flash("Payment not found", "error")
                return redirect(url_for("payments.payment_failed"))

            if matchmaking_payment.gateway == "paystack":
                verification = base_service.resolve_paystack_verification(reference=tx_ref)
            else:
                verification = base_service.resolve_flutterwave_verification(
                    tx_ref=tx_ref, transaction_id=transaction_id
                )
                
            verification_data = verification.get("data", {}) or {}
            verified_status = (verification.get("verified_status") or "").strip().lower()

            if verified_status in {"successful", "completed"}:
                    # Update matchmaking payment and request
                    success = matchmaking_service.handle_matchmaking_payment_success(
                        matchmaking_payment, verification_data
                    )
                    if success:
                        print(
                            f"✅ [PAYMENT CALLBACK] Matchmaking payment processed successfully"
                        )
                        flash(
                            "Payment completed successfully! Your matchmaking request is now active.",
                            "success",
                        )
                        return redirect(
                            url_for(
                                "payments.payment_success",
                                transaction_id=matchmaking_payment.id,
                            )
                        )
                    else:
                        print(
                            f"🔴 [PAYMENT CALLBACK] Failed to process matchmaking payment"
                        )
                        flash(
                            "Failed to process payment. Please contact support.",
                            "error",
                        )
                        return redirect(url_for("payments.payment_failed"))
            elif verified_status in {"pending", "processing"}:
                matchmaking_service.handle_matchmaking_payment_failure(
                    matchmaking_payment,
                    verification_data or {"status": verified_status},
                )
                flash(
                    "Payment received and is still being confirmed by Flutterwave.",
                    "info",
                )
                return redirect(url_for("payments.payment_failed"))
            else:
                matchmaking_service.handle_matchmaking_payment_failure(
                    matchmaking_payment,
                    verification_data
                    or {"status": status or "failed", "message": verification.get("error")},
                )
                flash("Payment failed. Please try again.", "error")
                return redirect(url_for("payments.payment_failed"))
        elif tx_ref.startswith("KIMBELA-MP-") or tx_ref.startswith("KIMBELA_MARKET_"):
            marketplace_payment = MarketplacePayment.query.filter_by(
                gateway_reference=tx_ref
            ).first()
            if not marketplace_payment:
                print(f"🔴 [PAYMENT CALLBACK] Marketplace payment not found: {tx_ref}")
                flash("Payment not found", "error")
                return redirect(url_for("payments.payment_failed"))

            if marketplace_payment.gateway == "paystack":
                verification = base_service.resolve_paystack_verification(reference=tx_ref)
            else:
                verification = base_service.resolve_flutterwave_verification(
                    tx_ref=tx_ref, transaction_id=transaction_id
                )
                
            verification_data = verification.get("data", {}) or {}
            verified_status = (verification.get("verified_status") or "").strip().lower()

            if verified_status in {"successful", "completed"}:
                marketplace_payment.gateway_payment_id = str(
                    verification_data.get("id") or transaction_id or ""
                )
                marketplace_payment.gateway_status = verified_status
                marketplace_payment.status = "completed"
                marketplace_payment.gateway_metadata = json.dumps(verification_data)
                marketplace_payment.paid_at = utcnow()

                service = marketplace_payment.service
                if service:
                    service.subscription_status = "active"
                    service.subscription_expires = utcnow() + timedelta(days=30)
                    service.status = "pending"

                db.session.commit()
                flash(
                    "Payment successful! Your service is now pending review.",
                    "success",
                )
                return redirect(url_for("market.seller_dashboard"))
            elif verified_status in {"pending", "processing"}:
                marketplace_payment.gateway_status = verified_status
                marketplace_payment.gateway_metadata = json.dumps(
                    verification_data or {"status": verified_status}
                )
                marketplace_payment.updated_at = utcnow()
                db.session.commit()
                flash(
                    "Payment received and is still being confirmed by Flutterwave.",
                    "info",
                )
                return redirect(url_for("market.seller_dashboard"))
            else:
                marketplace_payment.status = "failed"
                marketplace_payment.gateway_status = verified_status or status
                marketplace_payment.gateway_metadata = json.dumps(
                    verification_data
                    or {"status": status or "failed", "message": verification.get("error")}
                )
                marketplace_payment.updated_at = utcnow()
                db.session.commit()
                flash("Payment failed. Please try again.", "error")
                return redirect(url_for("market.seller_dashboard"))
        else:
            print(f"🔴 [PAYMENT CALLBACK] Unknown transaction type: {tx_ref}")
            flash("Unknown transaction type", "error")
            return redirect(url_for("payments.payment_failed"))

    except Exception as e:
        print(f"🔴 [PAYMENT CALLBACK] Exception: {str(e)}")
        import traceback

        print(f"🔴 [PAYMENT CALLBACK] Traceback: {traceback.format_exc()}")
        flash("An error occurred during payment processing.", "error")
        return redirect(url_for("payments.payment_failed"))


@csrf.exempt
@payments.route("/flutterwave/webhook", methods=["POST"])
def flutterwave_webhook():
    """Handle verified Flutterwave webhooks for all supported payment types."""
    try:
        from .payment_service import (
            AdCampaignPaymentService,
            BasePaymentService,
            MatchmakingPaymentService,
            MarketplacePaymentService,
        )

        payload = request.get_json(silent=True) or {}
        current_app.logger.info(
            "🟡 [FLUTTERWAVE WEBHOOK] Received payload: %s", payload
        )

        webhook_hash = current_app.config.get("FLUTTERWAVE_WEBHOOK_HASH") or os.getenv(
            "FLW_WEBHOOK_HASH", ""
        )
        received_hash = request.headers.get("verif-hash", "")
        if webhook_hash and received_hash != webhook_hash:
            current_app.logger.warning("🔴 [FLUTTERWAVE WEBHOOK] Invalid webhook hash")
            return jsonify({"status": "error", "message": "Invalid signature"}), 401

        event_type = payload.get("event")
        if event_type != "charge.completed":
            return jsonify({"status": "ignored", "message": "Event not handled"}), 200

        data = payload.get("data", {}) or {}
        tx_ref = data.get("tx_ref")
        transaction_id = data.get("id")
        if not tx_ref:
            return (
                jsonify({"status": "error", "message": "Missing transaction reference"}),
                400,
            )

        base_service = BasePaymentService()
        verification = base_service.resolve_flutterwave_verification(
            tx_ref=tx_ref, transaction_id=transaction_id
        )
        verification_data = verification.get("data", {}) or data
        verified_status = (verification.get("verified_status") or "").strip().lower()
        if not verified_status:
            verified_status = (verification_data.get("status") or "").strip().lower()

        if tx_ref.startswith("KIMBELA_AD_"):
            transaction = _find_payment_transaction_by_tx_ref(tx_ref)
            if not transaction:
                return jsonify({"status": "error", "message": "Transaction not found"}), 404

            ad_service = AdCampaignPaymentService()
            if verified_status in {"successful", "completed"}:
                handled = ad_service.handle_ad_payment_success(
                    transaction.id, verification_data
                )
            else:
                handled = ad_service.handle_ad_payment_failure(
                    transaction.id,
                    verification_data
                    or {"status": verified_status or "failed", "message": verification.get("error")},
                )
        elif tx_ref.startswith("KIMBELA_MATCH_"):
            matchmaking_service = MatchmakingPaymentService()
            matchmaking_payment = matchmaking_service.get_payment_by_reference(tx_ref)
            if not matchmaking_payment:
                return jsonify({"status": "error", "message": "Payment not found"}), 404

            if verified_status in {"successful", "completed"}:
                handled = matchmaking_service.handle_matchmaking_payment_success(
                    matchmaking_payment, verification_data
                )
            else:
                handled = matchmaking_service.handle_matchmaking_payment_failure(
                    matchmaking_payment,
                    verification_data
                    or {"status": verified_status or "failed", "message": verification.get("error")},
                )
        elif _is_marketplace_tx_ref(tx_ref):
            marketplace_payment = MarketplacePayment.query.filter_by(
                gateway_reference=tx_ref
            ).first()
            if not marketplace_payment:
                return jsonify({"status": "error", "message": "Payment not found"}), 404

            marketplace_service = MarketplacePaymentService()
            if verified_status in {"successful", "completed"}:
                handled = marketplace_service.handle_marketplace_payment_success(
                    marketplace_payment, verification_data
                )
            else:
                handled = marketplace_service.handle_marketplace_payment_failure(
                    marketplace_payment,
                    verification_data
                    or {"status": verified_status or "failed", "message": verification.get("error")},
                )
        else:
            return (
                jsonify(
                    {
                        "status": "ignored",
                        "message": f"Unsupported transaction reference: {tx_ref}",
                    }
                ),
                200,
            )

        if not handled:
            return jsonify({"status": "error", "message": "Processing failed"}), 500

        return jsonify({"status": "success", "verified_status": verified_status}), 200

    except Exception as e:
        current_app.logger.exception("🔴 [FLUTTERWAVE WEBHOOK] Error: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@payments.route("/flutterwave-callback")
def flutterwave_callbackk():
    """Handle Flutterwave payment callback - REDIRECTS TO USER_DASHBOARD"""
    try:
        print(f"🟡 [FLUTTERWAVE_CALLBACK] Received callback with args: {request.args}")

        # Get parameters from Flutterwave
        status = request.args.get("status")
        tx_ref = request.args.get("tx_ref")
        transaction_id = request.args.get("transaction_id")

        print(
            f"🟡 [FLUTTERWAVE_CALLBACK] status: {status}, tx_ref: {tx_ref}, transaction_id: {transaction_id}"
        )

        # For this route, just redirect to the main callback handler
        # This ensures both callback URLs work the same way
        return redirect(
            url_for(
                "payments.payment_callback",
                status=status,
                tx_ref=tx_ref,
                transaction_id=transaction_id,
            )
        )

    except Exception as e:
        print(f"🔴 [FLUTTERWAVE_CALLBACK] Exception: {str(e)}")
        flash("An error occurred during payment processing.", "error")
        return redirect(url_for("user.user_dashboard"))


@payments.route("/flutterwave/callback", methods=["GET"])
def flutterwave_callback():
    """Flutterwave payment callback - FIXED VERSION"""
    try:
        from .payment_service import PaymentService

        status = request.args.get("status")
        tx_ref = request.args.get("tx_ref")
        transaction_id = request.args.get("transaction_id")

        print(
            f"🟡 [FLUTTERWAVE/CALLBACK] Received - status: {status}, tx_ref: {tx_ref}, transaction_id: {transaction_id}"
        )

        payment_service = PaymentService()

        # Find transaction by tx_ref (our reference)
        transaction = _find_payment_transaction_by_tx_ref(tx_ref)

        if not transaction:
            print(f"🔴 [CALLBACK] No transaction found for tx_ref: {tx_ref}")
            flash("Transaction not found", "error")
            return redirect(url_for("user.user_dashboard"))

        print(f"✅ [CALLBACK] Found transaction: {transaction.id}")

        # Verify payment with Flutterwave
        verification_result = payment_service.resolve_flutterwave_verification(
            tx_ref=tx_ref, transaction_id=transaction_id
        )
        print(f"🟡 [CALLBACK] Verification result: {verification_result}")

        if verification_result["success"]:
            payment_data = verification_result.get("data", {})
            actual_status = (
                verification_result.get("verified_status")
                or (payment_data.get("status") or "").strip().lower()
            )

            print(f"🟡 [CALLBACK] Payment status from Flutterwave: {actual_status}")

            if actual_status in {"successful", "completed"}:
                # Handle successful payment
                success = payment_service.handle_successful_payment(
                    transaction.id, payment_data
                )
                if success:
                    print("✅ [CALLBACK] Payment handled successfully")
                    flash(
                        "Payment completed successfully! Your campaign is now active.",
                        "success",
                    )
                else:
                    print("🔴 [CALLBACK] Failed to handle successful payment")
                    flash(
                        "Payment verification failed. Please contact support.", "error"
                    )
            else:
                # Handle failed payment
                payment_service.handle_failed_payment(transaction.id, payment_data)
                flash("Payment failed. Please try again.", "error")
        else:
            print(
                f"🔴 [CALLBACK] Payment verification failed: {verification_result.get('error')}"
            )
            flash("Payment verification failed. Please contact support.", "error")

        return redirect(url_for("user.user_dashboard"))

    except Exception as e:
        print(f"🔴 [CALLBACK] Exception: {str(e)}")
        import traceback

        print(f"🔴 [CALLBACK] Traceback: {traceback.format_exc()}")
        flash("An error occurred during payment processing.", "error")
        return redirect(url_for("user.user_dashboard"))


@payments.route("/payment-success/<int:transaction_id>")
@login_required
def payment_success(transaction_id):
    """Handle successful payment - REDIRECT TO DASHBOARD"""
    try:
        from .payment_service import PaymentService

        transaction = PaymentTransaction.query.get(transaction_id)

        if not transaction or transaction.user_id != current_user.id:
            flash("Transaction not found", "error")
            return redirect(url_for("user.user_dashboard"))

        # Verify payment is actually completed
        if transaction.status != "completed":
            payment_service = PaymentService()
            verification_result = payment_service.resolve_flutterwave_verification(
                tx_ref=transaction.gateway_reference or transaction.gateway_payment_id,
                transaction_id=transaction.gateway_payment_id,
            )

            if (
                verification_result["success"]
                and verification_result.get("verified_status") in {"successful", "completed"}
            ):
                payment_service.handle_successful_payment(
                    transaction.id, verification_result["data"]
                )
            else:
                flash("Payment verification failed", "error")
                return redirect(url_for("user.user_dashboard"))

        campaign = (
            AdCampaign.query.get(transaction.campaign_id)
            if transaction.campaign_id
            else None
        )

        if campaign:
            print(f"✅ [PAYMENT SUCCESS] Final campaign status:")
            print(f"   - status: {campaign.status}")
            print(f"   - payment_status: {campaign.payment_status}")
            print(f"   - start_date: {campaign.start_date}")
            print(f"   - end_date: {campaign.end_date}")

        flash("Payment completed successfully! Your campaign is now active.", "success")
        return redirect(url_for("user.user_dashboard"))

    except Exception as e:
        print(f"🔴 [PAYMENT SUCCESS] Error: {str(e)}")
        flash("An error occurred while processing your payment.", "error")
        return redirect(url_for("user.user_dashboard"))


@payments.route("/payment-failed")
@login_required
def payment_failed():
    """Handle failed payment"""
    current_app.logger.info(f"⚠️ User {current_user.id} viewed payment failed page")
    return render_template("payment_failed.html")


# @payments.route('/verify-payment', methods=['POST'])
# @login_required
# def verify_payment():
#     """Verify payment status (for AJAX calls)"""
#     try:
#         data = request.get_json()
#         reference = data.get('reference')

#         if not reference:
#             return jsonify({'success': False, 'error': 'No reference provided'})

#         payment_service = PaymentService()
#         result = payment_service.verify_paystack_payment(reference)

#         if result['success'] and result['data']['status'] == 'success':
#             # Find and update transaction
#             transaction = PaymentTransaction.query.filter_by(
#                 gateway_payment_id=reference,
#                 user_id=current_user.id
#             ).first()

#             if transaction:
#                 payment_service.handle_successful_payment(transaction.id, result['data'])

#                 # Send success email
#                 campaign = AdCampaign.query.get(transaction.campaign_id)
#                 package = AdPackage.query.get(campaign.package_id) if campaign else None

#                 if campaign and package:
#                     EmailService.send_ad_purchase_success(current_user, transaction, campaign, package)

#                 return jsonify({
#                     'success': True,
#                     'transaction_id': transaction.id,
#                     'status': 'completed'
#                 })

#         # Send failure email if payment failed
#         transaction = PaymentTransaction.query.filter_by(gateway_payment_id=reference).first()
#         if transaction:
#             campaign = AdCampaign.query.get(transaction.campaign_id)
#             package = AdPackage.query.get(campaign.package_id) if campaign else None

#             if package:
#                 EmailService.send_ad_purchase_failed(
#                     user=current_user,
#                     package=package,
#                     transaction=transaction,
#                     campaign=campaign,
#                     error_message="Payment verification failed"
#                 )

#         return jsonify({'success': False, 'error': 'Payment verification failed'})

#     except Exception as e:
#         current_app.logger.error(f"❌ Payment verification error: {str(e)}")
#         return jsonify({'success': False, 'error': str(e)})


@payments.route("/update-payment-status", methods=["POST"])
@login_required
def update_payment_status():
    """Update payment status (for manual updates)"""
    try:
        from .payment_service import PaymentService

        if not current_user.is_super_admin:
            return jsonify({"success": False, "error": "Access denied"})
        data = request.get_json()
        transaction_id = data.get("transaction_id")
        status = data.get("status")

        if not transaction_id or not status:
            return jsonify(
                {"success": False, "error": "Transaction ID and status are required"}
            )

        transaction = PaymentTransaction.query.get(transaction_id)

        if not transaction or transaction.user_id != current_user.id:
            return jsonify({"success": False, "error": "Transaction not found"})

        payment_service = PaymentService()

        if status == "completed":
            # Verify with payment gateway first
            if transaction.gateway == "paystack":
                verification_result = payment_service.verify_paystack_payment(
                    transaction.gateway_payment_id
                )
                if (
                    verification_result["success"]
                    and verification_result["data"]["status"] == "success"
                ):
                    payment_service.handle_successful_payment(
                        transaction.id, verification_result["data"]
                    )
                else:
                    return jsonify(
                        {"success": False, "error": "Payment verification failed"}
                    )

        return jsonify({"success": True, "message": "Payment status updated"})

    except Exception as e:
        current_app.logger.error(f"Payment status update error: {str(e)}")
        return jsonify({"success": False, "error": str(e)})


@payments.route("/ads/active")
def get_active_ads():
    """Get active ads for display"""
    try:
        active_ads = (
            AdCampaign.query.filter_by(status="active")
            .filter(AdCampaign.budget > 0)
            .filter(
                AdCampaign.start_date <= utcnow(),
                AdCampaign.end_date >= utcnow(),
            )
            .filter(
                or_(AdCampaign.placement == None, AdCampaign.placement == "sponsored")
            )
            .all()
        )

        ads_data = []
        for ad in active_ads:
            ads_data.append(
                {
                    "id": ad.id,
                    "title": ad.title,
                    "description": ad.description,
                    "image": ad.image,
                    "target_url": ad.target_url,
                    "call_to_action": ad.call_to_action,
                    "budget": ad.budget,
                    "status": "active",
                }
            )

        return jsonify(ads_data)
    except Exception as e:
        print(f"Error loading ads: {e}")
        return jsonify([])


@payments.route("/ads/track/impression/<int:ad_id>", methods=["POST"])
def track_ad_impression(ad_id):
    """Track ad impression"""
    try:
        ad = AdCampaign.query.get_or_404(ad_id)
        ad.impressions += 1
        db.session.commit()
        return jsonify({"success": True})
    except:
        return jsonify({"success": False})


@payments.route("/ads/track/click/<int:ad_id>", methods=["POST"])
def track_ad_click(ad_id):
    """Track ad click"""
    try:
        ad = AdCampaign.query.get_or_404(ad_id)
        ad.clicks += 1
        # Update CTR
        if ad.impressions > 0:
            ad.click_through_rate = (ad.clicks / ad.impressions) * 100
        db.session.commit()
        return jsonify({"success": True})
    except:
        return jsonify({"success": False})


@payments.route("/create-campaign", methods=["POST"])
@login_required
def create_campaign():
    """Create ad campaign with user-selected budget and targeting data"""
    try:
        data = request.get_json(silent=True)
        print(f"🔵 [CREATE CAMPAIGN] Received data: {data}")

        if not data:
            data = request.form.to_dict()
            if not data:
                return jsonify({"success": False, "error": "No data provided"}), 400

        # Extract and validate data with correct field names
        daily_budget = data.get("daily_budget")
        duration_days = data.get("duration_days")
        title = data.get("title")
        description = data.get("description")
        target_url = data.get("target_url")
        call_to_action = data.get("call_to_action", "Learn More")
        image = data.get("image", "")
        currency = data.get("currency", "USD")
        placement = data.get("placement", "sponsored")

        # ✅ Extract targeting data
        targeting = data.get("targeting", {}) or {}
        target_gender = targeting.get("gender", "all")
        target_age_min = targeting.get("age_min", 31)
        target_age_max = targeting.get("age_max", 65)
        target_locations = targeting.get("locations", [])
        target_interests = targeting.get("interests", [])
        target_language = targeting.get("language", "all")
        target_relationship = targeting.get("relationship", "all")
        target_education = targeting.get("education", "all")
        target_occupation = targeting.get("occupation", "all")
        target_country = data.get("target_country") or targeting.get("country")
        target_state = data.get("target_state") or targeting.get("state")
        target_city = data.get("target_city") or targeting.get("city")
        if not target_locations:
            raw_locations = data.get("target_countries")
            if raw_locations:
                try:
                    target_locations = json.loads(raw_locations)
                except (TypeError, ValueError):
                    target_locations = []

        print(
            f"🔵 [CREATE CAMPAIGN] Parsed: daily_budget={daily_budget}, duration_days={duration_days}, title={title}"
        )
        print(
            f"🔵 [CREATE CAMPAIGN] Targeting: gender={target_gender}, age={target_age_min}-{target_age_max}, locations={len(target_locations)}, interests={len(target_interests)}"
        )

        # Validate required fields
        validation_errors = []
        if not title:
            validation_errors.append("Ad title is required")
        if not target_url:
            validation_errors.append("Target URL is required")
        if not daily_budget:
            validation_errors.append("Daily budget is required")
        if not duration_days:
            validation_errors.append("Duration days is required")
        if placement in DASHBOARD_AD_PLACEMENTS and not image:
            validation_errors.append("Please upload a banner image for this placement")
        if placement != "sponsored" and placement not in DASHBOARD_AD_PLACEMENTS:
            validation_errors.append("Invalid ad placement selected")

        if validation_errors:
            print(f"🔴 [CREATE CAMPAIGN] Validation errors: {validation_errors}")
            return (
                jsonify({"success": False, "error": ", ".join(validation_errors)}),
                400,
            )

        # Convert and validate numeric fields
        try:
            daily_budget = float(daily_budget)
            duration_days = int(duration_days)
            target_age_min = int(target_age_min)
            target_age_max = int(target_age_max)
        except (TypeError, ValueError) as e:
            print(f"🔴 [CREATE CAMPAIGN] Numeric conversion error: {e}")
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Invalid budget, duration, or age format",
                    }
                ),
                400,
            )

        ad_pricing = _get_dashboard_ad_daily_budget_bounds(placement)
        if daily_budget < ad_pricing["usd_min"]:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Minimum daily budget is ${ad_pricing['usd_min']:,.2f}",
                    }
                ),
                400,
            )
        if duration_days < 3:
            return (
                jsonify({"success": False, "error": "Minimum duration is 3 days"}),
                400,
            )
        if (
            target_age_min < 31
            or target_age_max > 80
            or target_age_min > target_age_max
        ):
            return jsonify({"success": False, "error": "Invalid age range"}), 400

        # Calculate total budget
        total_budget = daily_budget * duration_days

        # ✅ Create campaign with ALL targeting data
        campaign = AdCampaign(
            user_id=current_user.id,
            title=title,
            description=description,
            image=image,
            target_url=target_url,
            call_to_action=call_to_action,
            budget=total_budget,
            daily_budget=daily_budget,
            duration_days=duration_days,
            currency=currency,  # ✅ Save currency
            placement=placement,
            status="pending",
            payment_status="pending",
            # ✅ Save all targeting data
            target_gender=(
                json.dumps([target_gender]) if target_gender != "all" else None
            ),
            target_age_min=target_age_min,
            target_age_max=target_age_max,
            target_country=target_country,
            target_state=target_state,
            target_city=target_city,
            target_countries=json.dumps(target_locations) if target_locations else None,
            target_interests=json.dumps(target_interests) if target_interests else None,
            target_language=target_language if target_language != "all" else None,
            # Set default values for other targeting fields
            target_education=json.dumps(target_education) if target_education else None,
            target_occupation=(
                json.dumps(target_occupation) if target_occupation else None
            ),
            target_relationship=(
                json.dumps(target_relationship) if target_relationship else None
            ),
        )

        db.session.add(campaign)
        db.session.commit()

        print(f"✅ [CREATE CAMPAIGN] Campaign created successfully: ID {campaign.id}")
        print(f"✅ [CREATE CAMPAIGN] Targeting saved: {campaign.get_targeting_data()}")

        return jsonify(
            {
                "success": True,
                "campaign_id": campaign.id,
                "message": "Campaign created successfully",
            }
        )

    except Exception as e:
        db.session.rollback()
        print(f"🔴 [CREATE CAMPAIGN] Campaign creation failed: {str(e)}")
        import traceback

        print(f"🔴 [CREATE CAMPAIGN] Traceback: {traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 500


@payments.route("/initiate-payment", methods=["POST"])
@login_required
def initiate_payment():
    """Fixed payment initiation route"""
    try:
        from .payment_service import PaymentService

        data = request.get_json()
        print(f"🟡 [INITIATE PAYMENT] Request content type: {request.content_type}")
        print(f"🟡 [INITIATE PAYMENT] Raw data: {request.data}")

        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400

        campaign_id = data.get("campaign_id")
        currency = data.get("currency", "USD").upper()
        gateway = (data.get("gateway") or "flutterwave").lower()

        print(
            f"🟡 [INITIATE PAYMENT] campaign_id: {campaign_id}, currency: {currency}, gateway: {gateway}"
        )

        # Validate required fields
        if not campaign_id:
            return jsonify({"success": False, "error": "Campaign ID is required"}), 400

        # ✅ ADD CURRENCY VALIDATION
        supported_currencies = ["USD"]
        if currency not in supported_currencies:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f'Currency {currency} is not supported. Please use one of: {", ".join(supported_currencies)}',
                    }
                ),
                400,
            )

        try:
            campaign_id = int(campaign_id)
        except (ValueError, TypeError):
            return (
                jsonify(
                    {"success": False, "error": "Invalid campaign ID format"}
                ),
                400,
            )

        # Rest of your existing code remains the same...
        campaign = AdCampaign.query.get(campaign_id)
        if not campaign:
            return jsonify({"success": False, "error": "Campaign not found"}), 404

        if campaign.user_id != current_user.id:
            return (
                jsonify({"success": False, "error": "Unauthorized access to campaign"}),
                403,
            )

        if campaign.payment_status == "paid":
            return jsonify({"success": False, "error": "Campaign already paid"}), 400

        print(
            f"🟡 [INITIATE PAYMENT] Campaign found: {campaign.title}, User: {current_user.email}"
        )

        from .payment_service_ad import AdCampaignPaymentService
        ad_service = AdCampaignPaymentService()

        result = ad_service.create_ad_campaign_payment(
            user=current_user,
            campaign=campaign,
            currency=currency,
            gateway=gateway
        )

        print(f"🟡 [INITIATE PAYMENT] Payment service result: {result}")

        if result.get("success"):
            return jsonify(result)
        else:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": result.get("error", "Payment initiation failed"),
                    }
                ),
                400,
            )

    except Exception as e:
        print(f"🔴 [INITIATE PAYMENT] Error: {str(e)}")
        import traceback

        print(f"🔴 [INITIATE PAYMENT] Traceback: {traceback.format_exc()}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@payments.route("/debug-payment-service", methods=["GET"])
@login_required
def debug_payment_service():
    from .payment_service import PaymentService

    """Debug PaymentService configuration"""
    _require_debug_access()
    payment_service = PaymentService()

    # Test with a recent campaign
    campaign = (
        AdCampaign.query.filter_by(user_id=current_user.id)
        .order_by(AdCampaign.created_at.desc())
        .first()
    )

    debug_info = {
        "service_initialized": True,
        "flutterwave_public_key": bool(payment_service.flutterwave_public_key),
        "flutterwave_secret_key": bool(payment_service.flutterwave_secret_key),
        "flutterwave_base_url": payment_service.flutterwave_base_url,
        "test_campaign_available": bool(campaign),
        "current_user": current_user.email,
    }

    if campaign:
        debug_info["campaign_id"] = campaign.id
        debug_info["campaign_title"] = campaign.title

        # Test creating a transaction
        result = payment_service.create_flutterwave_transaction(
            current_user, campaign, 1.0, "USD"
        )
        debug_info["payment_test_result"] = result

    return jsonify(debug_info)


@payments.route("/test-payment-flow/<int:campaign_id>", methods=["GET"])
@login_required
def test_payment_flow(campaign_id):
    from .payment_service import PaymentService

    """Test payment flow for a specific campaign"""
    _require_debug_access()
    try:
        campaign = AdCampaign.query.get(campaign_id)
        if not campaign or campaign.user_id != current_user.id:
            return jsonify(
                {"success": False, "error": "Campaign not found or unauthorized"}
            )

        # Calculate amount based on daily budget and duration
        amount = campaign.daily_budget * campaign.duration_days

        payment_service = PaymentService()

        print(
            f"🧪 [TEST PAYMENT] Testing with campaign {campaign_id}, amount: {amount}"
        )

        result = payment_service.create_flutterwave_transaction(
            current_user, campaign, amount, "USD"
        )

        return jsonify(
            {
                "success": True,
                "test_result": result,
                "campaign": {
                    "id": campaign.id,
                    "title": campaign.title,
                    "daily_budget": campaign.daily_budget,
                    "duration_days": campaign.duration_days,
                    "calculated_amount": amount,
                },
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


print("LEAVING PAYMENTSAASSSSSSS")


@payments.route("/test-flutterwave-direct", methods=["GET"])
@login_required
def test_flutterwave_direct():
    from .payment_service import PaymentService

    """Test Flutterwave API directly"""
    _require_debug_access()
    try:
        payment_service = PaymentService()

        # Simple test payload
        test_data = {
            "tx_ref": f"direct_test_{int(time.time())}",
            "amount": "10",  # Small test amount
            "currency": "USD",
            "redirect_url": "http://localhost:5000/user/dashboard",
            "payment_options": "card",
            "customer": {
                "email": current_user.email,
                "name": current_user.full_name,
            },
            "customizations": {
                "title": "Kimbela Test",
                "description": "Direct Flutterwave Test",
            },
        }

        headers = {
            "Authorization": f"Bearer {payment_service.flutterwave_secret_key}",
            "Content-Type": "application/json",
        }

        print(f"🧪 [DIRECT TEST] Sending to Flutterwave:")
        print(f"🧪 [DIRECT TEST] URL: https://api.flutterwave.com/v3/payments")
        print(f"🧪 [DIRECT TEST] Headers: {headers}")
        print(f"🧪 [DIRECT TEST] Data: {json.dumps(test_data, indent=2)}")

        response = requests.post(
            "https://api.flutterwave.com/v3/payments",
            headers=headers,
            json=test_data,
            timeout=30,
        )

        result = {
            "status_code": response.status_code,
            "success": response.status_code == 200,
            "response": (
                response.json() if response.status_code == 200 else response.text
            ),
        }

        print(f"🧪 [DIRECT TEST] Flutterwave response:")
        print(f"🧪 [DIRECT TEST] Status: {result['status_code']}")
        print(f"🧪 [DIRECT TEST] Response: {json.dumps(result, indent=2)}")

        return jsonify(result)

    except Exception as e:
        print(f"🔴 [DIRECT TEST] Error: {str(e)}")
        import traceback

        print(f"🔴 [DIRECT TEST] Traceback: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@payments.route("/diagnose-payment", methods=["GET"])
@login_required
def diagnose_payment():
    """Diagnose payment configuration"""
    try:
        from .payment_service import PaymentService

        payment_service = PaymentService()

        diagnostic_info = {
            "flutterwave_configured": bool(payment_service.flutterwave_secret_key),
            "base_url": current_app.config.get("BASE_URL"),
            "environment_variables": {
                "PUBLIC_KEY_loaded": bool(os.getenv("PUBLIC_KEY")),
                "SECRET_KEY_loaded": bool(os.getenv("SECRET_KEY")),
                "ENCRYPTION_KEY_loaded": bool(os.getenv("ENCRYPTION_KEY")),
            },
            "current_user": {
                "id": current_user.id,
                "email": current_user.email,
                "name": current_user.full_name,
            },
        }

        print(
            f"🔍 [DIAGNOSTIC] Payment configuration: {json.dumps(diagnostic_info, indent=2)}"
        )

        return jsonify(diagnostic_info)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@payments.route("/verify-payment", methods=["POST"])
@login_required
def verify_payment():
    """Verify payment status"""
    try:
        from .payment_service import PaymentService

        data = request.get_json()
        reference = data.get("reference")

        payment_service = PaymentService()
        result = payment_service.verify_flutterwave_payment(reference)

        return jsonify(result)

    except Exception as e:
        current_app.logger.error(f"Payment verification failed: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@payments.route("/get-supported-currencies", methods=["GET"])
@login_required
def get_supported_currencies():
    """Get list of currencies supported by your Flutterwave account"""
    try:
        # For Nigerian Flutterwave accounts, these are typically supported
        supported_currencies = ["USD"]

        # You could also fetch this dynamically from Flutterwave API
        # But for now, we'll use the common ones

        current_app.logger.info(
            f"✅ Supported currencies requested by user {current_user.id}"
        )

        return jsonify({"success": True, "currencies": supported_currencies})

    except Exception as e:
        current_app.logger.error(f"❌ Error getting supported currencies: {str(e)}")
        return (
            jsonify(
                {
                    "success": False,
                    "error": str(e),
                    "currencies": ["USD"],
                }
            ),
            500,
        )


@payments.route("/debug-transaction/<tx_ref>", methods=["GET"])
@login_required
def debug_transaction(tx_ref):
    """Debug transaction status"""
    _require_debug_access()
    try:
        transaction = PaymentTransaction.query.filter_by(
            gateway_payment_id=tx_ref
        ).first()
        if not transaction:
            return jsonify({"success": False, "error": "Transaction not found"})

        campaign = (
            AdCampaign.query.get(transaction.campaign_id)
            if transaction.campaign_id
            else None
        )

        debug_info = {
            "transaction": {
                "id": transaction.id,
                "status": transaction.status,
                "gateway_status": transaction.gateway_status,
                "gateway_payment_id": transaction.gateway_payment_id,
                "campaign_id": transaction.campaign_id,
                "amount": transaction.amount,
                "currency": transaction.currency,
                "created_at": (
                    transaction.created_at.isoformat()
                    if transaction.created_at
                    else None
                ),
                "updated_at": (
                    transaction.updated_at.isoformat()
                    if transaction.updated_at
                    else None
                ),
            },
            "campaign": (
                {
                    "id": campaign.id if campaign else None,
                    "title": campaign.title if campaign else None,
                    "status": campaign.status if campaign else None,
                    "payment_status": campaign.payment_status if campaign else None,
                    "start_date": (
                        campaign.start_date.isoformat()
                        if campaign and campaign.start_date
                        else None
                    ),
                    "end_date": (
                        campaign.end_date.isoformat()
                        if campaign and campaign.end_date
                        else None
                    ),
                    "payment_gateway": campaign.payment_gateway if campaign else None,
                    "payment_id": campaign.payment_id if campaign else None,
                }
                if campaign
                else None
            ),
        }

        return jsonify(debug_info)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@payments.route("/fix-campaign-status/<int:campaign_id>", methods=["POST"])
@login_required
def fix_campaign_status(campaign_id):
    """Manually fix campaign status"""
    try:
        campaign = AdCampaign.query.get(campaign_id)
        if not campaign or campaign.user_id != current_user.id:
            return jsonify(
                {"success": False, "error": "Campaign not found or unauthorized"}
            )

        # Find the successful transaction for this campaign
        transaction = PaymentTransaction.query.filter_by(
            campaign_id=campaign_id, status="completed"
        ).first()

        if transaction:
            # Update campaign with transaction data
            campaign.payment_status = "paid"
            campaign.status = "active"
            campaign.payment_gateway = transaction.gateway
            campaign.payment_id = transaction.gateway_payment_id
            campaign.start_date = utcnow()
            campaign.end_date = utcnow() + timedelta(
                days=campaign.duration_days
            )
            campaign.updated_at = utcnow()

            db.session.commit()

            return jsonify(
                {
                    "success": True,
                    "message": "Campaign status fixed successfully",
                    "campaign": {
                        "id": campaign.id,
                        "status": campaign.status,
                        "payment_status": campaign.payment_status,
                        "start_date": campaign.start_date.isoformat(),
                        "end_date": campaign.end_date.isoformat(),
                    },
                }
            )
        else:
            return jsonify(
                {
                    "success": False,
                    "error": "No completed transaction found for this campaign",
                }
            )

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
