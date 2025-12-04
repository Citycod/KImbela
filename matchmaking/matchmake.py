from flask import (
    Flask,
    url_for,
    redirect,
    render_template,
    request,
    flash,
    Blueprint,
    session,
    current_app,
    jsonify,
)

from models import (
    MatchmakingPackage,
    MatchmakingRequest,
    MatchmakingLike,
    MatchmakingView,
    User,
    MatchmakingPayments,
)
from datetime import datetime, timedelta
import humanize
from sqlalchemy import event
from flask_wtf.csrf import generate_csrf
from werkzeug.security import check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
import cloudinary.uploader, os
from dotenv import load_dotenv
import requests, json
from extensions import db, bcrypt
from werkzeug.utils import secure_filename
import cloudinary.uploader
import cloudinary.utils
from scheduler import (
    manual_trigger_matchmaking_expiry_check,
    manual_trigger_expired_matchmaking_check,
)
import logging, secrets, re
from payments.payment_service import MatchmakingPaymentService
from flask_mail import Message
from extensions import mail

load_dotenv()

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path)

# Cloudinary config
import cloudinary

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

match = Blueprint("match", __name__)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# Helper functions
def calculate_age(dob):
    """Calculate age from date of birth"""
    if not dob:
        return 0
    today = datetime.utcnow().date()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def allowed_file(filename, allowed_extensions=None):
    """Check if file extension is allowed"""
    if allowed_extensions is None:
        allowed_extensions = {"png", "jpg", "jpeg", "gif", "webp"}
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


# Main Routes
@match.route("/requests", methods=["GET", "POST"])
@login_required
def requests():
    """Main matchmaking requests page"""
    packages = MatchmakingPackage.query.filter_by(is_active=True).all()
    return render_template("requests.html", packages=packages)


@match.route("/view_requests", methods=["GET"])
@login_required
def view_requests():
    """Main page to browse matchmaking requests"""
    return render_template("view_requests.html")


@match.route("/create")
@login_required
def create_request():
    """Page to create a new matchmaking request"""
    packages = MatchmakingPackage.query.filter_by(is_active=True).all()
    return render_template("requests.html", packages=packages)


# API Routes
@match.route("/api/requests", methods=["GET"])
@login_required
def get_requests():
    """API endpoint to get matchmaking requests with filtering and pagination"""
    try:
        # Get query parameters
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 12, type=int)
        search = request.args.get("search", "")
        min_age = request.args.get("min_age", type=int)
        max_age = request.args.get("max_age", type=int)
        gender = request.args.get("gender", "")
        location = request.args.get("location", "")
        sort_by = request.args.get("sort_by", "newest")

        current_app.logger.info(f"Fetching requests for user {current_user.id}")

        # Base query - include active, paid requests that haven't expired
        query = MatchmakingRequest.query.filter(
            MatchmakingRequest.status == "active",
            MatchmakingRequest.end_date > datetime.utcnow(),
            MatchmakingRequest.payment_status == "completed",
        )

        # Apply filters
        if search:
            query = query.filter(
                db.or_(
                    MatchmakingRequest.about_you.ilike(f"%{search}%"),
                    MatchmakingRequest.ideal_partner.ilike(f"%{search}%"),
                    MatchmakingRequest.your_interests.ilike(f"%{search}%"),
                )
            )

        if min_age:
            query = query.filter(MatchmakingRequest.min_age >= min_age)

        if max_age:
            query = query.filter(MatchmakingRequest.max_age <= max_age)

        if gender and gender != "any":
            query = query.filter(
                db.or_(
                    MatchmakingRequest.partner_gender == gender,
                    MatchmakingRequest.partner_gender == "any",
                )
            )

        if location:
            query = query.join(User).filter(
                db.or_(
                    User.city.ilike(f"%{location}%"),
                    User.country.ilike(f"%{location}%"),
                )
            )

        # Apply sorting
        if sort_by == "newest":
            query = query.order_by(MatchmakingRequest.created_at.desc())
        elif sort_by == "oldest":
            query = query.order_by(MatchmakingRequest.created_at.asc())
        elif sort_by == "popular":
            query = query.order_by(MatchmakingRequest.likes.desc())
        elif sort_by == "ending":
            query = query.order_by(MatchmakingRequest.end_date.asc())

        # Paginate results
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        requests_data = []
        for req in pagination.items:
            # Track view (but not for current user's own requests)
            if req.user_id != current_user.id:
                view = MatchmakingView.query.filter_by(
                    user_id=current_user.id, request_id=req.id
                ).first()

                if not view:
                    view = MatchmakingView(user_id=current_user.id, request_id=req.id)
                    db.session.add(view)
                    req.views += 1

            # Check if current user liked this request
            is_liked = (
                MatchmakingLike.query.filter_by(
                    user_id=current_user.id, request_id=req.id
                ).first()
                is not None
            )

            # Calculate age
            age = calculate_age(req.user.dob) if req.user.dob else 0

            # Calculate days remaining
            days_remaining = (req.end_date - datetime.utcnow()).days
            days_remaining = max(0, days_remaining)

            # Get interests
            interests = []
            if req.your_interests:
                try:
                    interests = json.loads(req.your_interests)
                except:
                    interests = []

            # Check if this request belongs to current user
            is_own_request = req.user_id == current_user.id

            requests_data.append(
                {
                    "id": req.id,
                    "user": {
                        "id": req.user.id,
                        "full_name": req.user.full_name,
                        "age": age,
                        "location": f"{req.user.city or ''}, {req.user.country or ''}".strip(
                            ", "
                        ),
                        "profile_pic": req.user.profile_pic
                        or url_for("static", filename="assets/img/default-avatar.png"),
                    },
                    "about_you": req.about_you or "",
                    "ideal_partner": req.ideal_partner or "",
                    "partner_preferences": {
                        "min_age": req.min_age or 18,
                        "max_age": req.max_age or 99,
                        "gender": req.partner_gender or "any",
                        "ethnicity": req.partner_ethnicity or "any",
                        "religion": req.partner_religion or "any",
                    },
                    "interests": interests,
                    "lifestyles": (
                        req.get_lifestyles() if hasattr(req, "get_lifestyles") else []
                    ),
                    "image": req.image,
                    "views": req.views or 0,
                    "likes": req.likes or 0,
                    "matches": req.matches or 0,
                    "created_at": (
                        req.created_at.strftime("%Y-%m-%d") if req.created_at else ""
                    ),
                    "expires_in": days_remaining,
                    "package": req.package.name if req.package else "Basic",
                    "is_liked": is_liked,
                    "is_own_request": is_own_request,
                }
            )

        db.session.commit()

        return jsonify(
            {
                "success": True,
                "requests": requests_data,
                "total": pagination.total,
                "pages": pagination.pages,
                "has_next": pagination.has_next,
                "has_prev": pagination.has_prev,
            }
        )

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error fetching matchmaking requests: {str(e)}")
        return jsonify({"success": False, "error": "Failed to load requests"}), 500


@match.route("/api/requests/<int:request_id>")
@login_required
def get_request_detail(request_id):
    """Get detailed information for a specific matchmaking request"""
    try:
        req = MatchmakingRequest.query.get_or_404(request_id)

        # Track view
        view = MatchmakingView.query.filter_by(
            user_id=current_user.id, request_id=req.id
        ).first()

        if not view:
            view = MatchmakingView(user_id=current_user.id, request_id=req.id)
            db.session.add(view)
            req.views += 1
            db.session.commit()

        # Check if current user liked this request
        is_liked = (
            MatchmakingLike.query.filter_by(
                user_id=current_user.id, request_id=req.id
            ).first()
            is not None
        )

        request_data = {
            "id": req.id,
            "user": {
                "id": req.user.id,
                "full_name": req.user.full_name,
                "age": calculate_age(req.user.dob),
                "location": f"{req.user.city}, {req.user.country}",
                "profile_pic": req.user.profile_pic,
                "about_me": req.user.about_me,
                "occupation": req.user.occupation,
                "education": req.user.educational_level,
            },
            "about_you": req.about_you,
            "ideal_partner": req.ideal_partner,
            "partner_preferences": {
                "min_age": req.min_age,
                "max_age": req.max_age,
                "gender": req.partner_gender,
                "ethnicity": req.partner_ethnicity,
                "religion": req.partner_religion,
            },
            "interests": req.get_your_interests(),
            "partner_interests": req.get_partner_interests(),
            "lifestyles": req.get_lifestyles(),
            "target_countries": req.get_target_countries(),
            "image": req.image,
            "views": req.views,
            "likes": req.likes,
            "matches": req.matches,
            "created_at": req.created_at.strftime("%B %d, %Y"),
            "expires_in": (req.end_date - datetime.utcnow()).days,
            "package": req.package.name,
            "is_liked": is_liked,
        }

        return jsonify({"success": True, "request": request_data})

    except Exception as e:
        current_app.logger.error(
            f"Error fetching matchmaking request {request_id}: {str(e)}"
        )
        return (
            jsonify({"success": False, "error": "Failed to load request details"}),
            500,
        )


@match.route("/create-request", methods=["POST"])
@login_required
def create_matchmaking_request():
    """Create a new matchmaking request with payment integration"""
    try:
        data = request.get_json()

        # Handle both direct data and nested request_data
        if "request_data" in data:
            request_data = data["request_data"]
            package_id = data.get("package_id")
        else:
            request_data = data
            package_id = data.get("package_id")

        # Validate required fields
        if not package_id:
            return jsonify({"success": False, "error": "Package ID is required"}), 400

        # Get package
        package = MatchmakingPackage.query.get(package_id)
        if not package:
            return jsonify({"success": False, "error": "Invalid package selected"}), 400

        # Check if user already has an active request
        existing_request = MatchmakingRequest.query.filter_by(
            user_id=current_user.id, status="active"
        ).first()

        if existing_request:
            # Check if the existing request is expired
            if (
                existing_request.end_date
                and existing_request.end_date <= datetime.utcnow()
            ):
                # Mark expired request as inactive
                existing_request.status = "expired"
                db.session.commit()
            else:
                # Return proper error with request details
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "You already have an active matchmaking request",
                            "existing_request": {
                                "id": existing_request.id,
                                "status": existing_request.status,
                                "end_date": (
                                    existing_request.end_date.isoformat()
                                    if existing_request.end_date
                                    else None
                                ),
                                "days_remaining": (
                                    (existing_request.end_date - datetime.utcnow()).days
                                    if existing_request.end_date
                                    else 0
                                ),
                                "package": (
                                    existing_request.package.name
                                    if existing_request.package
                                    else "Unknown"
                                ),
                            },
                            "options": [
                                "Wait for your current request to expire",
                                "Deactivate your current request and create a new one",
                                "Upgrade your current package",
                            ],
                        }
                    ),
                    400,
                )

        # Validate required fields in request_data
        required_fields = ["about_you", "ideal_partner"]
        for field in required_fields:
            if not request_data.get(field):
                return (
                    jsonify(
                        {"success": False, "error": f"Missing required field: {field}"}
                    ),
                    400,
                )

        # Create new request with pending status
        new_request = MatchmakingRequest(
            user_id=current_user.id,
            package_id=package.id,
            min_age=request_data.get("min_age"),
            max_age=request_data.get("max_age"),
            partner_gender=request_data.get("partner_gender", "any"),
            partner_ethnicity=request_data.get("partner_ethnicity"),
            partner_religion=request_data.get("partner_religion"),
            partner_interests=json.dumps(request_data.get("partner_interests", [])),
            target_countries=json.dumps(request_data.get("countries", [])),
            about_you=request_data["about_you"],
            ideal_partner=request_data["ideal_partner"],
            your_interests=json.dumps(request_data.get("your_interests", [])),
            lifestyles=json.dumps(request_data.get("lifestyles", [])),
            image=request_data.get("image"),
            status="pending",  # Will be activated after payment
            payment_status="pending",
            payment_gateway="flutterwave",
        )

        db.session.add(new_request)
        db.session.commit()

        print(f"✅ Matchmaking request created with ID: {new_request.id}")

        return jsonify(
            {
                "success": True,
                "request_id": new_request.id,
                "message": "Matchmaking request created successfully! Proceed to payment.",
            }
        )

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating matchmaking request: {str(e)}")
        return (
            jsonify(
                {"success": False, "error": "Failed to create matchmaking request"}
            ),
            500,
        )


@match.route("/initiate-matchmaking-payment", methods=["POST"])
@login_required
def initiate_matchmaking_payment():
    """Initiate payment for a matchmaking request using dedicated service"""
    try:
        data = request.get_json()
        print(f"🟡 [INITIATE MATCHMAKING PAYMENT] Received data: {data}")

        # Required fields for matchmaking
        request_id = data.get("request_id")
        currency = data.get("currency", "USD").upper()
        package_id = data.get("campaign_id")  # This comes from frontend as campaign_id

        print(
            f"🟡 [INITIATE MATCHMAKING PAYMENT] request_id: {request_id}, currency: {currency}, package_id: {package_id}"
        )

        if not request_id or not package_id:
            print(
                "🔴 [INITIATE MATCHMAKING PAYMENT] Request ID and Package ID are required"
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Request ID and Package ID are required",
                    }
                ),
                400,
            )

        # Load matchmaking request with package
        matchmaking_request = MatchmakingRequest.query.options(
            db.joinedload(MatchmakingRequest.package)
        ).get(request_id)

        if not matchmaking_request:
            print(
                f"🔴 [INITIATE MATCHMAKING PAYMENT] Matchmaking request not found: {request_id}"
            )
            return (
                jsonify({"success": False, "error": "Matchmaking request not found"}),
                404,
            )

        if matchmaking_request.user_id != current_user.id:
            print(
                f"🔴 [INITIATE MATCHMAKING PAYMENT] Unauthorized access to request {request_id}"
            )
            return (
                jsonify({"success": False, "error": "Unauthorized access to request"}),
                403,
            )

        if matchmaking_request.payment_status == "completed":
            print(
                f"🔴 [INITIATE MATCHMAKING PAYMENT] Request already paid: {request_id}"
            )
            return jsonify({"success": False, "error": "Request already paid"}), 400

        # Verify package matches
        if str(matchmaking_request.package_id) != str(package_id):
            print(
                f"🔴 [INITIATE MATCHMAKING PAYMENT] Package mismatch: request has {matchmaking_request.package_id}, got {package_id}"
            )
            return jsonify({"success": False, "error": "Package mismatch"}), 400

        # Ensure package exists and has a valid price
        package = matchmaking_request.package
        if not package:
            print(
                f"🔴 [INITIATE MATCHMAKING PAYMENT] Package not found for request {request_id}"
            )
            return jsonify({"success": False, "error": "Package not found"}), 404

        if package.price is None or package.price <= 0:
            print(
                f"🔴 [INITIATE MATCHMAKING PAYMENT] Invalid package price for request {request_id}: {package.price}"
            )
            return jsonify({"success": False, "error": "Package price is invalid"}), 400

        print(
            f"🟡 [INITIATE MATCHMAKING PAYMENT] Found package: {package.name}, price: {package.price}"
        )

        # Use dedicated MatchmakingPaymentService
        payment_service = MatchmakingPaymentService()

        print(
            f"🟡 [INITIATE MATCHMAKING PAYMENT] Calling create_matchmaking_payment..."
        )
        result = payment_service.create_matchmaking_payment(
            user=current_user,
            matchmaking_request=matchmaking_request,
            package=package,
            currency=currency,
        )

        print(f"🟡 [INITIATE MATCHMAKING PAYMENT] Payment service result: {result}")

        if result.get("success"):
            print(
                f"✅ [INITIATE MATCHMAKING PAYMENT] Payment initiated successfully for request {request_id}"
            )
            return jsonify(result)
        else:
            error_msg = result.get("error", "Payment initiation failed")
            print(
                f"🔴 [INITIATE MATCHMAKING PAYMENT] Payment initiation failed: {error_msg}"
            )
            return jsonify({"success": False, "error": error_msg}), 400

    except Exception as e:
        print(f"🔴 [INITIATE MATCHMAKING PAYMENT] Exception: {str(e)}")
        import traceback

        print(f"🔴 [INITIATE MATCHMAKING PAYMENT] Traceback: {traceback.format_exc()}")
        return (
            jsonify({"success": False, "error": f"Internal server error: {str(e)}"}),
            500,
        )


@match.route("/payment-callback")
@login_required
def payment_callback():
    """Handle Flutterwave payment callback for matchmaking"""
    try:
        # Get parameters from Flutterwave callback
        status = request.args.get("status")
        tx_ref = request.args.get("tx_ref")
        transaction_id = request.args.get("transaction_id")

        print(
            f"🟡 [PAYMENT CALLBACK] Received callback - Status: {status}, TX_REF: {tx_ref}, Transaction ID: {transaction_id}"
        )

        if not status or not transaction_id:
            flash("Invalid payment callback parameters", "error")
            return redirect(url_for("match.requests"))

        # Verify payment with Flutterwave using MatchmakingPaymentService
        payment_service = MatchmakingPaymentService()
        verification_result = payment_service.verify_flutterwave_payment(transaction_id)

        print(f"🟡 [PAYMENT CALLBACK] Verification result: {verification_result}")

        if not verification_result["success"]:
            flash("Payment verification failed", "error")
            return redirect(url_for("match.requests"))

        flutterwave_data = verification_result["data"]

        # Find the matchmaking payment
        matchmaking_payment = payment_service.get_payment_by_reference(tx_ref)

        print(f"🟡 [PAYMENT CALLBACK] Found payment: {matchmaking_payment}")

        if not matchmaking_payment or matchmaking_payment.user_id != current_user.id:
            flash("Payment transaction not found", "error")
            return redirect(url_for("match.requests"))

        # Handle payment status
        if status == "successful" and flutterwave_data.get("status") == "successful":
            # Successful payment
            print(f"🟡 [PAYMENT CALLBACK] Processing successful payment...")
            success = payment_service.handle_matchmaking_payment_success(
                matchmaking_payment, flutterwave_data
            )

            if success:
                print(f"✅ [PAYMENT CALLBACK] Payment processed successfully")
                flash(
                    "Payment successful! Your matchmaking request is now active.",
                    "success",
                )
                return redirect(url_for("match.view_requests"))
            else:
                print(f"🔴 [PAYMENT CALLBACK] Failed to process successful payment")
                flash(
                    "Error activating your matchmaking request. Please contact support.",
                    "error",
                )
                return redirect(url_for("match.requests"))
        else:
            # Failed payment
            print(f"🟡 [PAYMENT CALLBACK] Processing failed payment...")
            payment_service.handle_matchmaking_payment_failure(
                matchmaking_payment, flutterwave_data
            )
            flash("Payment failed. Please try again.", "error")
            return redirect(url_for("match.requests"))

    except Exception as e:
        current_app.logger.error(f"Payment callback error: {str(e)}")
        import traceback

        current_app.logger.error(
            f"Payment callback traceback: {traceback.format_exc()}"
        )
        flash("Error processing payment callback", "error")
        return redirect(url_for("match.requests"))


# Interaction Routes
@match.route("/api/requests/<int:request_id>/like", methods=["POST"])
@login_required
def like_request(request_id):
    """Like or unlike a matchmaking request"""
    try:
        req = MatchmakingRequest.query.get_or_404(request_id)

        # Check if user is trying to like their own request
        if req.user_id == current_user.id:
            return (
                jsonify(
                    {"success": False, "error": "You cannot like your own request"}
                ),
                400,
            )

        existing_like = MatchmakingLike.query.filter_by(
            user_id=current_user.id, request_id=request_id
        ).first()

        if existing_like:
            # Unlike
            db.session.delete(existing_like)
            req.likes = max(0, req.likes - 1)
            liked = False
        else:
            # Like
            new_like = MatchmakingLike(user_id=current_user.id, request_id=request_id)
            db.session.add(new_like)
            req.likes += 1
            liked = True

            # Create notification for the request owner
            if req.user_id != current_user.id:
                req.user.create_notification(
                    actor=current_user,
                    notification_type="matchmaking_like",
                    entity_id=request_id,
                    entity_type="matchmaking_request",
                    custom_message=f"{current_user.full_name} liked your matchmaking request",
                )

        db.session.commit()

        return jsonify({"success": True, "liked": liked, "like_count": req.likes})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error liking request {request_id}: {str(e)}")
        return jsonify({"success": False, "error": "Failed to process like"}), 500


@match.route("/api/requests/<int:request_id>/message", methods=["POST"])
@login_required
def send_message(request_id):
    """Send a message to the owner of a matchmaking request"""
    try:
        data = request.get_json()
        message_content = data.get("message", "").strip()

        if not message_content:
            return jsonify({"success": False, "error": "Message cannot be empty"}), 400

        req = MatchmakingRequest.query.get_or_404(request_id)

        # Check if user is messaging themselves
        if req.user_id == current_user.id:
            return (
                jsonify({"success": False, "error": "You cannot message yourself"}),
                400,
            )

        # Check if users are blocked
        if not current_user.can_interact_with(req.user):
            return (
                jsonify({"success": False, "error": "You cannot message this user"}),
                400,
            )

        # Create notification
        req.user.create_notification(
            actor=current_user,
            notification_type="matchmaking_message",
            entity_id=request_id,
            entity_type="matchmaking_request",
            custom_message=f"{current_user.full_name} sent you a message about your matchmaking request: {message_content}",
        )

        # Increment matches count
        req.matches += 1
        db.session.commit()

        return jsonify({"success": True, "message": "Message sent successfully!"})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(
            f"Error sending message to request {request_id}: {str(e)}"
        )
        return jsonify({"success": False, "error": "Failed to send message"}), 500


# User Management Routes
@match.route("/my-requests")
@login_required
def my_requests():
    """Get current user's matchmaking requests"""
    try:
        requests = (
            MatchmakingRequest.query.filter_by(user_id=current_user.id)
            .order_by(MatchmakingRequest.created_at.desc())
            .all()
        )

        requests_data = []
        for req in requests:
            requests_data.append(
                {
                    "id": req.id,
                    "about_you": req.about_you,
                    "ideal_partner": req.ideal_partner,
                    "views": req.views,
                    "likes": req.likes,
                    "matches": req.matches,
                    "status": req.status,
                    "created_at": req.created_at.strftime("%B %d, %Y"),
                    "end_date": req.end_date.strftime("%B %d, %Y"),
                    "package": req.package.name,
                    "is_active": req.status == "active"
                    and req.end_date > datetime.utcnow(),
                }
            )

        return jsonify({"success": True, "requests": requests_data})

    except Exception as e:
        current_app.logger.error(f"Error fetching user requests: {str(e)}")
        return jsonify({"success": False, "error": "Failed to load your requests"}), 500


@match.route("/api/my-active-request")
@login_required
def get_my_active_request():
    """Get current user's active matchmaking request"""
    try:
        active_request = MatchmakingRequest.query.filter_by(
            user_id=current_user.id, status="active"
        ).first()

        if not active_request:
            return jsonify({"success": True, "has_active_request": False})

        # Calculate days remaining
        days_remaining = (active_request.end_date - datetime.utcnow()).days
        days_remaining = max(0, days_remaining)

        return jsonify(
            {
                "success": True,
                "has_active_request": True,
                "request": {
                    "id": active_request.id,
                    "about_you": active_request.about_you,
                    "ideal_partner": active_request.ideal_partner,
                    "package": (
                        active_request.package.name
                        if active_request.package
                        else "Basic"
                    ),
                    "created_at": active_request.created_at.strftime("%Y-%m-%d"),
                    "end_date": active_request.end_date.strftime("%Y-%m-%d"),
                    "days_remaining": days_remaining,
                    "views": active_request.views or 0,
                    "likes": active_request.likes or 0,
                    "matches": active_request.matches or 0,
                    "status": active_request.status,
                },
            }
        )

    except Exception as e:
        current_app.logger.error(f"Error fetching active request: {str(e)}")
        return (
            jsonify({"success": False, "error": "Failed to fetch active request"}),
            500,
        )


@match.route("/api/requests/<int:request_id>/deactivate", methods=["POST"])
@login_required
def deactivate_request(request_id):
    """Deactivate a matchmaking request"""
    try:
        request_to_deactivate = MatchmakingRequest.query.filter_by(
            id=request_id, user_id=current_user.id
        ).first_or_404()

        if request_to_deactivate.status != "active":
            return jsonify({"success": False, "error": "Request is not active"}), 400

        request_to_deactivate.status = "inactive"
        db.session.commit()

        return jsonify({"success": True, "message": "Request deactivated successfully"})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deactivating request {request_id}: {str(e)}")
        return jsonify({"success": False, "error": "Failed to deactivate request"}), 500


@match.route("/api/requests/<int:request_id>/extend", methods=["POST"])
@login_required
def extend_request(request_id):
    """Extend a matchmaking request by purchasing additional time"""
    try:
        data = request.get_json()
        extension_days = data.get("extension_days", 30)

        request_to_extend = MatchmakingRequest.query.filter_by(
            id=request_id, user_id=current_user.id
        ).first_or_404()

        if request_to_extend.status != "active":
            return (
                jsonify({"success": False, "error": "Cannot extend inactive request"}),
                400,
            )

        # Extend the end date
        request_to_extend.end_date += timedelta(days=extension_days)
        db.session.commit()

        return jsonify(
            {
                "success": True,
                "message": f"Request extended by {extension_days} days",
                "new_end_date": request_to_extend.end_date.strftime("%Y-%m-%d"),
            }
        )

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error extending request {request_id}: {str(e)}")
        return jsonify({"success": False, "error": "Failed to extend request"}), 500


# Utility Routes
@match.route("/upload-image", methods=["POST"])
@login_required
def upload_image():
    """Handle image upload for matchmaking requests"""
    try:
        if "image" not in request.files:
            return jsonify({"success": False, "error": "No image file provided"}), 400

        file = request.files["image"]
        if file.filename == "":
            return jsonify({"success": False, "error": "No image selected"}), 400

        # Define allowed image extensions
        image_extensions = {"png", "jpg", "jpeg", "gif", "webp"}

        if file and allowed_file(file.filename, image_extensions):
            # Upload to Cloudinary
            result = cloudinary.uploader.upload(
                file,
                folder="kimbela/matchmaking",
                transformation=[
                    {"width": 400, "height": 400, "crop": "fill"},
                    {"quality": "auto", "fetch_format": "auto"},
                ],
            )

            return jsonify({"success": True, "image_url": result["secure_url"]})
        else:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Invalid file type. Please upload an image (PNG, JPG, JPEG, GIF, WEBP)",
                    }
                ),
                400,
            )

    except Exception as e:
        current_app.logger.error(f"Image upload error: {str(e)}")
        return jsonify({"success": False, "error": "Failed to upload image"}), 500


@match.route("/packages")
@login_required
def get_packages():
    """Get available matchmaking packages"""
    try:
        packages = MatchmakingPackage.query.filter_by(is_active=True).all()

        packages_data = []
        for package in packages:
            packages_data.append(
                {
                    "id": package.id,
                    "name": package.name,
                    "description": package.description,
                    "price": package.price,
                    "duration_days": package.duration_days,
                    "features": package.features.split(",") if package.features else [],
                }
            )

        return jsonify({"success": True, "packages": packages_data})

    except Exception as e:
        current_app.logger.error(f"Error fetching packages: {str(e)}")
        return jsonify({"success": False, "error": "Failed to load packages"}), 500


@match.route("/stats")
@login_required
def get_stats():
    """Get matchmaking statistics"""
    try:
        total_requests = MatchmakingRequest.query.filter_by(status="active").count()
        total_matches = (
            db.session.query(db.func.sum(MatchmakingRequest.matches)).scalar() or 0
        )
        new_this_week = MatchmakingRequest.query.filter(
            MatchmakingRequest.created_at >= datetime.utcnow() - timedelta(days=7)
        ).count()

        user_requests = MatchmakingRequest.query.filter_by(
            user_id=current_user.id
        ).count()
        user_likes = MatchmakingLike.query.filter_by(user_id=current_user.id).count()

        return jsonify(
            {
                "success": True,
                "stats": {
                    "total_requests": total_requests,
                    "total_matches": total_matches,
                    "new_this_week": new_this_week,
                    "user_requests": user_requests,
                    "user_likes": user_likes,
                },
            }
        )

    except Exception as e:
        current_app.logger.error(f"Error fetching stats: {str(e)}")
        return jsonify({"success": False, "error": "Failed to load statistics"}), 500


# Payment Management Routes
@match.route("/api/my-payments")
@login_required
def get_my_payments():
    """Get current user's matchmaking payment history"""
    try:
        payment_service = MatchmakingPaymentService()
        payments = payment_service.get_user_payments(current_user.id)

        payments_data = [payment.to_dict() for payment in payments]

        return jsonify({"success": True, "payments": payments_data})

    except Exception as e:
        current_app.logger.error(f"Error fetching user payments: {str(e)}")
        return (
            jsonify({"success": False, "error": "Failed to fetch payment history"}),
            500,
        )


@match.route("/api/payments/<int:payment_id>")
@login_required
def get_payment_details(payment_id):
    """Get matchmaking payment details"""
    try:
        payment = MatchmakingPayments.query.filter_by(
            id=payment_id, user_id=current_user.id
        ).first_or_404()

        return jsonify({"success": True, "payment": payment.to_dict()})

    except Exception as e:
        current_app.logger.error(f"Error fetching payment {payment_id}: {str(e)}")
        return (
            jsonify({"success": False, "error": "Failed to fetch payment details"}),
            500,
        )


# Debug Routes
@match.route("/debug/requests")
def debug_requests():
    """Debug endpoint to check requests in database"""
    requests = MatchmakingRequest.query.all()
    result = []
    for req in requests:
        result.append(
            {
                "id": req.id,
                "user_id": req.user_id,
                "status": req.status,
                "about_you": req.about_you[:50] if req.about_you else None,
                "created_at": req.created_at.isoformat() if req.created_at else None,
                "end_date": req.end_date.isoformat() if req.end_date else None,
                "is_active": req.status == "active"
                and (req.end_date is None or req.end_date > datetime.utcnow()),
            }
        )
    return jsonify(result)


@match.route("/debug/all-requests")
@login_required
def debug_all_requests():
    """Debug endpoint to see ALL matchmaking requests"""
    all_requests = MatchmakingRequest.query.all()
    current_time = datetime.utcnow()

    result = {
        "current_time": current_time.isoformat(),
        "current_user_id": current_user.id,
        "total_requests": len(all_requests),
        "requests": [],
    }

    for req in all_requests:
        is_active = req.status == "active" and (
            req.end_date is None or req.end_date > current_time
        )
        result["requests"].append(
            {
                "id": req.id,
                "user_id": req.user_id,
                "status": req.status,
                "payment_status": req.payment_status,
                "about_you": (
                    req.about_you[:100] + "..."
                    if req.about_you and len(req.about_you) > 100
                    else req.about_you
                ),
                "end_date": req.end_date.isoformat() if req.end_date else None,
                "is_active": is_active,
                "is_current_user": req.user_id == current_user.id,
                "days_remaining": (
                    (req.end_date - current_time).days
                    if req.end_date and req.end_date > current_time
                    else 0
                ),
                "package": req.package.name if req.package else "No package",
            }
        )

    return jsonify(result)


@match.route("/debug/flutterwave-keys")
def debug_flutterwave_keys():
    """Debug endpoint to check Flutterwave configuration"""
    import os

    keys_info = {
        "FLW_PUBLIC_KEY": os.getenv("FLW_PUBLIC_KEY"),
        "FLW_SECRET_KEY": os.getenv("FLW_SECRET_KEY"),
        "FLUTTERWAVE_PUBLIC_KEY": os.getenv("FLUTTERWAVE_PUBLIC_KEY"),
        "FLUTTERWAVE_SECRET_KEY": os.getenv("FLUTTERWAVE_SECRET_KEY"),
        "keys_found": {
            "FLW_PUBLIC_KEY": bool(os.getenv("FLW_PUBLIC_KEY")),
            "FLW_SECRET_KEY": bool(os.getenv("FLW_SECRET_KEY")),
            "FLUTTERWAVE_PUBLIC_KEY": bool(os.getenv("FLUTTERWAVE_PUBLIC_KEY")),
            "FLUTTERWAVE_SECRET_KEY": bool(os.getenv("FLUTTERWAVE_SECRET_KEY")),
        },
    }
    return jsonify(keys_info)


@match.route("/test-payment-with-keys")
@login_required
def test_payment_with_keys():
    """Test payment service with actual keys"""
    try:
        print("🟡 [TEST PAYMENT] Starting test payment route...")

        # RE-IMPORT requests to ensure it's the module, not a function
        import requests as http_requests

        print(f"🔍 [DEBUG] requests module type: {type(http_requests)}")

        # Step 1: Create payment service
        print("🟡 [TEST PAYMENT] Step 1: Creating MatchmakingPaymentService...")
        payment_service = MatchmakingPaymentService()
        print("✅ [TEST PAYMENT] Step 1: Payment service created successfully")

        # Step 2: Prepare headers
        print("🟡 [TEST PAYMENT] Step 2: Preparing request headers...")
        secret_key = payment_service.flutterwave_secret_key
        headers = {
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json",
        }

        # Step 3: Make the API request using the re-imported module
        print("🟡 [TEST PAYMENT] Step 3: Making API request to Flutterwave...")
        test_response = http_requests.get(
            f"{payment_service.flutterwave_base_url}/banks/NG",
            headers=headers,
            timeout=10,
        )
        print(
            f"✅ [TEST PAYMENT] Step 3: API request completed - Status: {test_response.status_code}"
        )

        return jsonify(
            {
                "success": True,
                "keys_configured": True,
                "test_api_status": test_response.status_code,
                "test_api_message": (
                    "API connection successful"
                    if test_response.status_code == 200
                    else f"API returned {test_response.status_code}"
                ),
                "public_key_prefix": payment_service.flutterwave_public_key[:20]
                + "...",
                "secret_key_prefix": payment_service.flutterwave_secret_key[:20]
                + "...",
            }
        )

    except Exception as e:
        print(f"🔴 [TEST PAYMENT] Exception: {str(e)}")
        import traceback

        print(f"🔴 [TEST PAYMENT] Traceback: {traceback.format_exc()}")
        return (
            jsonify({"success": False, "error": str(e), "keys_configured": False}),
            500,
        )


@match.route("/test-payment-service")
@login_required
def test_payment_service():
    """Test if payment service is working"""
    try:
        service = MatchmakingPaymentService()

        return jsonify(
            {
                "success": True,
                "service_initialized": True,
                "public_key_configured": service.flutterwave_public_key is not None,
                "secret_key_configured": service.flutterwave_secret_key is not None,
                "environment_variables": {
                    "FLW_PUBLIC_KEY": os.getenv("FLW_PUBLIC_KEY") is not None,
                    "FLW_SECRET_KEY": os.getenv("FLW_SECRET_KEY") is not None,
                    "FLUTTERWAVE_PUBLIC_KEY": os.getenv("FLUTTERWAVE_PUBLIC_KEY")
                    is not None,
                    "FLUTTERWAVE_SECRET_KEY": os.getenv("FLUTTERWAVE_SECRET_KEY")
                    is not None,
                },
            }
        )
    except Exception as e:
        return (
            jsonify({"success": False, "error": str(e), "service_initialized": False}),
            500,
        )


# Admin Routes
@match.route("/admin/trigger-matchmaking-expiry-check", methods=["POST"])
@login_required
def admin_trigger_matchmaking_expiry():
    """Manually trigger matchmaking expiry check (admin only)"""
    try:
        success = manual_trigger_matchmaking_expiry_check()

        if success:
            flash("Matchmaking expiry check completed successfully!", "success")
        else:
            flash("Matchmaking expiry check completed with issues", "warning")

        return jsonify({"success": success})

    except Exception as e:
        current_app.logger.error(f"Manual matchmaking expiry trigger error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@match.route("/admin/trigger-expired-matchmaking", methods=["POST"])
@login_required
def admin_trigger_expired_matchmaking():
    """Manually trigger expired matchmaking check (admin only)"""
    try:
        expired_count = manual_trigger_expired_matchmaking_check()
        flash(f"Marked {expired_count} matchmaking requests as expired", "success")
        return jsonify({"success": True, "expired_count": expired_count})

    except Exception as e:
        current_app.logger.error(f"Manual expired matchmaking trigger error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500
