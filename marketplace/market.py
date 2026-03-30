from time_utils import utcnow
# routes/market.py
from flask import (
    Blueprint,
    request,
    jsonify,
    render_template,
    redirect,
    url_for,
    current_app,
    flash,
    session,
    abort,
)
from flask_login import login_required, current_user
from extensions import db, cache
import traceback
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import joinedload
from flask_wtf.csrf import CSRFProtect, CSRFError
from models import (
    User,
    MarketplaceService,
    MarketplaceCategory,
    MarketplaceSubscription,
    MarketplaceReview,
    MarketplacePayment,
    MarketplaceClick,
    PaymentTransaction,
    MarketplaceSubscriptionPlan,
    MarketplaceSubscription,
    SellerRating,
    SiteSetting,
)
import cloudinary.uploader
import os, requests, json, uuid
from datetime import datetime, timedelta
from sqlalchemy import or_, desc, func
from werkzeug.utils import secure_filename
import time
from cache_utils import cache_response, invalidate_cache
import requests
from flask import send_file, make_response, jsonify
from io import BytesIO
import cloudinary
import cloudinary.api
import cloudinary.utils
import requests
from io import BytesIO
from urllib.parse import urlparse, unquote
import mimetypes
from payments.payment_service import PaymentService
from models import (
    MarketplacePayment,
    MarketplaceSubscriptionPlan,
    MarketplaceService,
    MarketplaceCategory,
    MarketplaceReview,
    MarketplaceClick,
    User,
    PaymentTransaction,
    SiteSetting,
)

from dotenv import load_dotenv


load_dotenv()

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path)

market = Blueprint("market", __name__)


def marketplace_payments_enabled():
    default_enabled = current_app.config.get("MARKETPLACE_PAYMENTS_ENABLED", False)
    try:
        SiteSetting.__table__.create(bind=db.engine, checkfirst=True)
        stored_value = SiteSetting.get_value("marketplace_payments_enabled")
        if stored_value is None:
            return default_enabled
        return str(stored_value).lower() in {"1", "true", "yes", "on"}
    except Exception as e:
        print(f"⚠️ Failed to load marketplace payments setting: {e}")
        return default_enabled


def apply_marketplace_seller_visibility_filter(query):
    if not marketplace_payments_enabled():
        return query.options(
            joinedload(MarketplaceService.seller).joinedload(
                User.marketplace_subscription
            )
        )

    now = utcnow()
    return query.join(
        User,
        and_(
            MarketplaceService.seller_id == User.id,
            User.marketplace_subscription_status == "active",
            or_(
                User.marketplace_subscription_expires == None,
                User.marketplace_subscription_expires >= now,
            ),
        ),
    ).options(
        joinedload(MarketplaceService.seller).joinedload(User.marketplace_subscription)
    )


def _require_debug_access():
    """Restrict debug endpoints to admins when explicitly enabled."""
    if not current_user.is_authenticated:
        abort(404)
    if not current_user.is_super_admin:
        abort(404)
    if not current_app.config.get("ENABLE_DEBUG_ROUTES"):
        abort(404)

# Initialize payment service
payment_service = PaymentService()


cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)


# Add this utility function at the top of your market.py routes file
import re
from urllib.parse import urlparse


def log_service_activity(service_id, action, user_id=None):
    """Log service activities (views, clicks, etc.)"""
    try:
        # You can save to database if needed
        print(
            f"📊 Service Activity: service_id={service_id}, action={action}, user_id={user_id}"
        )

        # Example database logging (uncomment if you have ServiceActivity model):
        # activity = ServiceActivity(
        #     service_id=service_id,
        #     action=action,
        #     user_id=user_id,
        #     ip_address=request.remote_addr if 'request' in globals() else None
        # )
        # db.session.add(activity)
        # db.session.commit()

    except Exception as e:
        print(f"❌ Failed to log service activity: {e}")


def parse_cloudinary_url(url):
    """Correctly parse Cloudinary URL to get public_id"""
    if not url or "cloudinary.com" not in url:
        return None

    # Parse the URL
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.split("/")

    print(f"Parsing URL: {url}")
    print(f"Path parts: {path_parts}")

    # Find the resource type
    resource_type = "image"  # default
    if "raw/upload" in url:
        resource_type = "raw"
    elif "image/upload" in url:
        resource_type = "image"

    # Find the 'upload' index
    try:
        upload_index = path_parts.index("upload")
    except ValueError:
        # Try alternative format
        for i, part in enumerate(path_parts):
            if (
                part in ["image", "raw", "video"]
                and i + 1 < len(path_parts)
                and path_parts[i + 1] == "upload"
            ):
                upload_index = i + 1
                resource_type = part
                break
        else:
            return None

    # Get everything after 'upload'
    # Skip version if present (starts with 'v')
    start_index = upload_index + 1
    if start_index < len(path_parts) and path_parts[start_index].startswith("v"):
        start_index += 1

    # Get the public_id (without file extension for API calls)
    public_id_parts = path_parts[start_index:]

    # Join all parts
    full_public_id = "/".join(public_id_parts)

    # Remove query parameters
    full_public_id = full_public_id.split("?")[0]

    # For PDFs, we need to preserve the .pdf extension
    public_id_for_api = full_public_id

    # Get filename
    filename = public_id_parts[-1] if public_id_parts else None
    if filename:
        filename = filename.split("?")[0]

    # Get cloud name
    cloud_name = (
        path_parts[1] if len(path_parts) > 1 else cloudinary.config().cloud_name
    )

    print(
        f"Parsed: cloud_name={cloud_name}, resource_type={resource_type}, public_id={public_id_for_api}"
    )

    return {
        "cloud_name": cloud_name,
        "resource_type": resource_type,
        "public_id": public_id_for_api,
        "filename": filename,
    }


# ==================== HELPER FUNCTIONS ====================


def allowed_file(filename):
    """Check if file extension is allowed"""
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "pdf", "doc", "docx"}
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def upload_to_cloudinary(file, folder="marketplace"):
    """Upload file to Cloudinary with proper settings"""
    try:
        upload_result = cloudinary.uploader.upload(
            file,
            folder=f"kimbela/{folder}",
            resource_type="auto",
            access_mode="public",  # MAKE PUBLIC
            type="upload",
            overwrite=False,
            timeout=30,
        )
        print(f"Upload successful: {upload_result.get('secure_url')}")
        print(f"Public ID: {upload_result.get('public_id')}")
        print(f"Access Mode: {upload_result.get('access_mode')}")
        return upload_result.get("secure_url")
    except Exception as e:
        print(f"Cloudinary upload error: {e}")
        return None


@market.route("/test-new-upload", methods=["GET"])
@login_required
def test_new_upload():
    """Test the fixed upload function"""
    if not current_user.is_super_admin:
        return "Admin access required", 403

    # Create a simple test file
    from PIL import Image
    import io

    # Create test image
    img = Image.new("RGB", (100, 100), color="blue")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="JPEG")
    img_byte_arr.seek(0)
    img_byte_arr.name = "test_upload.jpg"

    # Test upload
    url = upload_to_cloudinary(img_byte_arr, "test")

    if url:
        # Test access
        response = requests.get(url)

        result = f"""
        <h1>Upload Test Results</h1>
        <p><strong>Uploaded URL:</strong> <a href="{url}" target="_blank">{url}</a></p>
        <p><strong>Access Status:</strong> {response.status_code} {'✅' if response.status_code == 200 else '❌'}</p>
        <p><strong>File Size:</strong> {len(response.content)} bytes</p>
        """

        if response.status_code == 200:
            result += f'<img src="{url}" alt="Test image" style="max-width: 200px; border: 2px solid green;">'

        return result
    else:
        return "Upload failed"


@market.route("/make-files-public-fixed", methods=["GET"])
@login_required
def make_files_public_fixed():
    """Make all Cloudinary files publicly accessible - FIXED VERSION"""
    if not current_user.is_super_admin:
        return "Admin access required", 403

    try:
        fixed_count = 0
        errors = []

        # 1. Fix service cover images
        services = MarketplaceService.query.filter(
            MarketplaceService.cover_image.ilike("%cloudinary.com%")
        ).all()

        for service in services:
            if service.cover_image:
                parsed = parse_cloudinary_url(service.cover_image)
                if parsed:
                    try:
                        # Use public_id WITHOUT extension
                        result = cloudinary.api.update(
                            parsed["public_id"],  # This is WITHOUT .jpg extension
                            access_mode="public",
                            resource_type=parsed["resource_type"],
                        )
                        fixed_count += 1
                        print(
                            f"Fixed: {parsed['public_id']} → {result.get('access_mode')}"
                        )
                    except Exception as e:
                        errors.append(f"Error fixing {parsed['public_id']}: {str(e)}")

        # 2. Fix digital files
        services_with_digital = MarketplaceService.query.filter(
            MarketplaceService.digital_file.isnot(None)
        ).all()

        for service in services_with_digital:
            if service.digital_file:
                parsed = parse_cloudinary_url(service.digital_file)
                if parsed:
                    try:
                        # For PDFs, resource_type might be 'image' or 'raw'
                        # Try 'image' first, then 'raw'
                        try:
                            result = cloudinary.api.update(
                                parsed["public_id"],
                                access_mode="public",
                                resource_type="image",
                            )
                        except:
                            result = cloudinary.api.update(
                                parsed["public_id"],
                                access_mode="public",
                                resource_type="raw",
                            )

                        fixed_count += 1
                        print(f"Fixed digital: {parsed['public_id']}")
                    except Exception as e:
                        errors.append(
                            f"Error fixing digital {parsed['public_id']}: {str(e)}"
                        )

        response = f"Successfully made {fixed_count} files public.<br>"
        if errors:
            response += f"<br>Errors:<br>" + "<br>".join(
                errors[:10]
            )  # Show first 10 errors

        return response

    except Exception as e:
        return f"Error: {str(e)}", 500


@market.route("/debug-cloudinary", methods=["GET"])
@login_required
def debug_cloudinary():
    """Debug Cloudinary file issues"""
    _require_debug_access()
    if not current_user.is_super_admin:
        return "Admin access required", 403

    try:
        debug_info = []

        # Get Cloudinary account info
        try:
            account_info = cloudinary.api.ping()
            debug_info.append(f"Cloudinary Account: Connected - {account_info}")
        except Exception as e:
            debug_info.append(f"Cloudinary Connection Error: {e}")

        # List all resources in your account
        try:
            resources = cloudinary.api.resources(
                max_results=10, type="upload", prefix="kimbela/"
            )
            debug_info.append(
                f"Resources in 'kimbela/' folder: {len(resources.get('resources', []))}"
            )

            for resource in resources.get("resources", []):
                debug_info.append(
                    f"  - {resource['public_id']} (Type: {resource['resource_type']})"
                )
        except Exception as e:
            debug_info.append(f"Error listing resources: {e}")

        # Check specific problematic files
        problem_files = [
            "kimbela/services/cover/bps0r87dlhyhby1vsuzi.jpg",
            "kimbela/services/digital/fc8bhr4zh89upcv2mxka.pdf",
        ]

        for file_id in problem_files:
            try:
                resource = cloudinary.api.resource(file_id)
                debug_info.append(
                    f"✓ Found: {file_id} - Access: {resource.get('access_mode', 'unknown')}"
                )
            except Exception as e:
                debug_info.append(f"✗ Not found: {file_id} - Error: {str(e)}")

        # Check what cloud we're connected to
        debug_info.append(f"Configured Cloud Name: {cloudinary.config().cloud_name}")

        return "<br>".join(debug_info)

    except Exception as e:
        return f"Debug error: {str(e)}", 500


# In market.py, update the format_price function:


def format_price(price, currency="NGN"):
    """Format price with currency symbol"""
    if price is None or price == 0:
        return "Free"

    try:
        # Convert to float first to handle decimal
        price_float = float(price)

        # Currency symbols mapping
        currency_symbols = {
            "USD": "$",
            "EUR": "€",
            "GBP": "£",
            "KES": "KSh",
            "NGN": "₦",
            "GHS": "GH₵",
            "ZAR": "R",
            "XAF": "FCFA",
            "XOF": "CFA",
        }

        symbol = currency_symbols.get(currency, currency)

        # Format with comma separation
        formatted = f"{price_float:,.2f}"

        # Remove .00 if it's a whole number
        if formatted.endswith(".00"):
            formatted = formatted[:-3]

        return f"{symbol}{formatted}"
    except (ValueError, TypeError):
        return f"{currency}0"


def format_price_with_currency(price, currency="NGN"):
    """Format price with currency symbol for display in templates"""
    return format_price(price, currency)


def log_click(service_id, click_type, user_id=None):
    """Log a click on a service"""
    click = MarketplaceClick(
        service_id=service_id,
        user_id=user_id,
        click_type=click_type,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string,
    )
    db.session.add(click)
    db.session.commit()


def get_featured_sellers(limit=6):
    """Get random featured sellers based on performance"""
    # Get sellers with featured services
    featured_services = MarketplaceService.query.filter_by(
        is_featured=True, status="active"
    ).all()

    seller_ids = list(set([service.seller_id for service in featured_services]))

    if len(seller_ids) == 0:
        # Fallback to sellers with highest ratings
        sellers = (
            User.query.join(MarketplaceService)
            .filter(MarketplaceService.status == "active")
            .order_by(func.random())
            .limit(limit)
            .all()
        )
        return sellers

    # Get random sellers from featured list
    import random

    random.shuffle(seller_ids)
    selected_ids = seller_ids[: min(limit, len(seller_ids))]

    sellers = User.query.filter(User.id.in_(selected_ids)).all()

    # Add random sellers if not enough
    if len(sellers) < limit:
        additional = limit - len(sellers)
        extra_sellers = (
            User.query.filter(
                User.id.notin_(seller_ids),
                User.id != current_user.id if current_user.is_authenticated else True,
            )
            .order_by(func.random())
            .limit(additional)
            .all()
        )
        sellers.extend(extra_sellers)

    return sellers


# ==================== MAIN MARKETPLACE ROUTES ====================

# In your main_market route in market.py, update the price filtering section:



@market.route("/main_market", methods=["GET"])
def main_market():
    """Marketplace homepage"""
    # Get all active services with pagination
    page = request.args.get("page", 1, type=int)
    per_page = 12

    services_query = MarketplaceService.query.filter_by(status="active")
    services_query = apply_marketplace_seller_visibility_filter(services_query)

    # Filter by category (parent includes its subcategories)
    category_slug = request.args.get("category")
    if category_slug:
        slug_to_ids, _ = get_marketplace_category_maps()
        category_ids = slug_to_ids.get(category_slug)
        if category_ids:
            services_query = services_query.filter(
                MarketplaceService.category_id.in_(category_ids)
            )

    # Filter by search
    search_query = request.args.get("q")
    if search_query:
        services_query = services_query.filter(
            or_(
                MarketplaceService.title.ilike(f"%{search_query}%"),
                MarketplaceService.description.ilike(f"%{search_query}%"),
                MarketplaceService.short_description.ilike(f"%{search_query}%"),
            )
        )

    # Filter by price
    min_price = request.args.get("min_price")
    max_price = request.args.get("max_price")

    if min_price and min_price.isdigit():
        min_price = int(min_price)
        services_query = services_query.filter(MarketplaceService.price >= min_price)
    else:
        min_price = None

    if max_price and max_price.isdigit():
        max_price = int(max_price)
        services_query = services_query.filter(MarketplaceService.price <= max_price)
    else:
        max_price = None

    # Filter by service type
    service_type = request.args.get("type")
    if service_type:
        services_query = services_query.filter_by(service_type=service_type)

    # Filter by featured
    featured_only = request.args.get("featured") == "true"
    if featured_only:
        services_query = services_query.filter_by(is_featured=True)

    # Sorting preference (DB-level for speed)
    sort_by = request.args.get("sort", "newest")
    if sort_by == "featured":
        services_query = services_query.order_by(
            MarketplaceService.is_featured.desc(),
            MarketplaceService.created_at.desc(),
        )
    elif sort_by == "popular":
        services_query = services_query.order_by(MarketplaceService.views.desc())
    elif sort_by == "rating":
        services_query = services_query.order_by(MarketplaceService.average_rating.desc())
    elif sort_by == "price_low":
        services_query = services_query.order_by(MarketplaceService.price.asc())
    elif sort_by == "price_high":
        services_query = services_query.order_by(MarketplaceService.price.desc())
    else:
        services_query = services_query.order_by(MarketplaceService.created_at.desc())

    results = (
        services_query.limit(per_page + 1).offset((page - 1) * per_page).all()
    )
    has_next = len(results) > per_page
    paginated_services = results[:per_page]
    total_services = (page - 1) * per_page + len(paginated_services) + (1 if has_next else 0)
    total_sellers_displayed = len({s.seller_id for s in paginated_services})

    class CustomPagination:
        def __init__(self, items, page, per_page, total, pages, has_next):
            self.items = items  # This is now an attribute, not a method
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = pages
            self.has_next = has_next
            self.has_prev = page > 1
            self.next_num = page + 1 if page < self.pages else None
            self.prev_num = page - 1 if page > 1 else None

        def iter_pages(
            self, left_edge=2, right_edge=2, left_current=2, right_current=2
        ):
            last = 0
            for num in range(1, self.pages + 1):
                if (
                    num <= left_edge
                    or (
                        num > self.page - left_current - 1
                        and num < self.page + right_current
                    )
                    or num > self.pages - right_edge
                ):
                    if last + 1 != num:
                        yield None
                    yield num
                    last = num

    # Create a simple pagination dictionary instead of using Pagination class
    services = CustomPagination(
        items=paginated_services,
        page=page,
        per_page=per_page,
        total=total_services,
        pages=page + 1 if has_next else page,
        has_next=has_next,
    )

    # For statistics - get count of all visible services before limiting
    total_subscribed_services = total_services
    # =========== END LIMIT LOGIC ===========

    _, slug_to_name = get_marketplace_category_maps()
    category_name = slug_to_name.get(category_slug) if category_slug else None

    # Get price statistics from currently visible marketplace listings
    price_cache_key = (
        "marketplace:price_stats:paid"
        if marketplace_payments_enabled()
        else "marketplace:price_stats:free"
    )
    price_stats = cache.get(price_cache_key)
    if not price_stats:
        price_query = (
            db.session.query(
                func.min(MarketplaceService.price).label("min_price"),
                func.max(MarketplaceService.price).label("max_price"),
                func.avg(MarketplaceService.price).label("avg_price"),
            )
            .filter_by(status="active")
        )
        if marketplace_payments_enabled():
            price_query = price_query.join(User, MarketplaceService.seller_id == User.id)
            price_query = price_query.filter(User.marketplace_subscription_status == "active")
        row = price_query.first()
        price_stats = (
            row.min_price or 0,
            row.max_price or 10000,
            row.avg_price or 500,
        )
        cache.set(price_cache_key, price_stats, timeout=300)

    min_available, max_available, avg_price = price_stats

    # Set default price range values
    current_min = min_price or min_available
    current_max = max_price or max_available

    return render_template(
        "main_market.html",
        services=services,
        search_query=search_query,
        category_slug=category_slug,
        category_name=category_name,
        sort_by=sort_by,
        min_price=current_min,
        max_price=current_max,
        min_available=min_available,
        max_available=max_available,
        avg_price=avg_price,
        service_type=service_type,
        featured_only=featured_only,
        format_price=format_price,
        now=utcnow(),
        total_subscribed_services=total_subscribed_services,  # Total before limiting
        total_sellers_displayed=total_sellers_displayed,  # How many sellers are showing
        marketplace_payments_enabled=marketplace_payments_enabled(),
    )


def get_marketplace_category_maps():
    cache_key = "marketplace:category_slug_maps:v1"
    cached = cache.get(cache_key)
    if cached:
        return cached

    categories = MarketplaceCategory.query.filter_by(is_active=True).all()
    slug_to_name = {category.slug: category.name for category in categories}
    children_by_parent = {}
    for category in categories:
        if category.parent_id:
            children_by_parent.setdefault(category.parent_id, []).append(category.id)

    slug_to_ids = {}
    for category in categories:
        ids = [category.id]
        if category.parent_id is None:
            ids.extend(children_by_parent.get(category.id, []))
        slug_to_ids[category.slug] = ids

    cache.set(cache_key, (slug_to_ids, slug_to_name), timeout=600)
    return slug_to_ids, slug_to_name


@market.route("/service/<slug>", methods=["GET"])
def service_detail(slug):
    """View service details"""
    service = MarketplaceService.query.filter_by(slug=slug).first_or_404()

    # Check if service is active or user is seller/admin
    if service.status != "active" and (
        not current_user.is_authenticated
        or (current_user.id != service.seller_id and not current_user.is_super_admin)
    ):
        flash("This service is not available", "warning")
        return redirect(url_for("market.main_market"))

    # Increment views
    service.views = (service.views or 0) + 1
    db.session.commit()

    # Log view
    user_id = current_user.id if current_user.is_authenticated else None
    log_service_activity(service.id, "view", user_id)

    # Get related services
    related_services = (
        MarketplaceService.query.filter(
            MarketplaceService.category_id == service.category_id,
            MarketplaceService.id != service.id,
            MarketplaceService.status == "active",
        )
        .order_by(func.random())
        .limit(4)
        .all()
    )

    # Get reviews
    reviews = (
        MarketplaceReview.query.filter_by(service_id=service.id, status="approved")
        .order_by(desc(MarketplaceReview.created_at))
        .limit(10)
        .all()
    )

    # Get seller's other services
    seller_services = (
        MarketplaceService.query.filter_by(seller_id=service.seller_id, status="active")
        .filter(MarketplaceService.id != service.id)
        .limit(4)
        .all()
    )

    # Parse JSON fields with safe defaults
    contact_methods = []
    if service.contact_methods:
        try:
            contact_methods = json.loads(service.contact_methods)
        except:
            contact_methods = []

    gallery_images = []
    if service.gallery_images:
        try:
            gallery_images = json.loads(service.gallery_images)
        except:
            gallery_images = []

    features = []
    if service.features:
        try:
            features = json.loads(service.features)
        except:
            features = []

    # Ensure price has a default value
    service_price = service.price if service.price is not None else 0
    service_currency = service.currency or "KES"

    # Get currency symbols
    currency_symbols = {
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "KES": "#",
        "NGN": "₦",
        "GHS": "GH₵",
        "ZAR": "R",
    }

    # ========== FIXED WHATSAPP URL GENERATION ==========
    def generate_whatsapp_url(phone_number, message):
        """Generate a properly formatted WhatsApp URL with country code"""
        if not phone_number:
            return None

        import re
        from urllib.parse import quote

        # Clean phone number - remove all non-digit characters
        digits = re.sub(r"\D", "", str(phone_number))

        if not digits:
            return None

        # Convert to WhatsApp format
        if digits.startswith("0") and len(digits) == 11:
            # Format: 08012345678 → 2348012345678
            whatsapp_number = "234" + digits[1:]
        elif len(digits) == 10:
            # Format: 8012345678 → 2348012345678
            whatsapp_number = "234" + digits
        elif digits.startswith("234") and len(digits) == 13:
            # Already correct: 2348012345678
            whatsapp_number = digits
        else:
            # Try to use as-is
            whatsapp_number = digits

        # Remove any remaining non-digits (just in case)
        whatsapp_number = re.sub(r"\D", "", whatsapp_number)

        # Encode message
        encoded_message = quote(message)

        # Generate URL
        return f"https://wa.me/{whatsapp_number}?text={encoded_message}"

    # Generate WhatsApp URL for the service
    whatsapp_url = None
    if service.whatsapp_number:
        message = f"Hi! I'm interested in your service: {service.title}"
        whatsapp_url = generate_whatsapp_url(service.whatsapp_number, message)

        # Debug logging
        print(f"📱 WhatsApp Debug for service {service.id}:")
        print(f"  Raw number: {service.whatsapp_number}")
        print(f"  Generated URL: {whatsapp_url}")
    # ========== END FIX ==========

    return render_template(
        "service_detail.html",
        service=service,
        related_services=related_services,
        reviews=reviews,
        seller_services=seller_services,
        contact_methods=contact_methods,
        gallery_images=gallery_images,
        features=features,
        currency_symbols=currency_symbols,
        now=utcnow(),
        whatsapp_url=whatsapp_url,  # Pass the generated URL to template
    )


@market.route("/category/<slug>", methods=["GET"])
@login_required
def category_detail(slug):
    """View category details"""
    category = MarketplaceCategory.query.filter_by(slug=slug).first_or_404()

    # Get services in this category
    page = request.args.get("page", 1, type=int)
    per_page = 12

    services_query = MarketplaceService.query.filter_by(
        category_id=category.id, status="active"
    ).order_by(desc(MarketplaceService.created_at))

    services = services_query.paginate(page=page, per_page=per_page, error_out=False)

    # Get subcategories
    subcategories = (
        MarketplaceCategory.query.filter_by(parent_id=category.id, is_active=True)
        .order_by("sort_order")
        .all()
    )

    return render_template(
        "category_detail.html",
        category=category,
        services=services,
        subcategories=subcategories,
        format_price=format_price,
    )


# ==================== SELLER DASHBOARD ROUTES ====================
@market.route("/seller_dashboard", methods=["GET"])
@login_required
def seller_dashboard():
    """Seller dashboard with real data"""
    # Pagination for services
    page = request.args.get("page", 1, type=int)
    per_page = 10

    # Get seller's services with pagination
    services_query = MarketplaceService.query.filter_by(
        seller_id=current_user.id
    ).order_by(desc(MarketplaceService.created_at))

    services = services_query.paginate(page=page, per_page=per_page, error_out=False)

    # Calculate stats from database
    total_services = services_query.count()

    active_services = MarketplaceService.query.filter_by(
        seller_id=current_user.id, status="active"
    ).count()

    # Get total views (from service.views field)
    total_views_result = (
        db.session.query(func.sum(MarketplaceService.views))
        .filter_by(seller_id=current_user.id)
        .first()
    )
    total_views = total_views_result[0] or 0 if total_views_result else 0

    # Get total clicks (count from MarketplaceClick table)
    total_clicks_result = (
        db.session.query(func.count(MarketplaceClick.id))
        .join(MarketplaceService)
        .filter(MarketplaceService.seller_id == current_user.id)
        .first()
    )
    total_clicks = total_clicks_result[0] or 0 if total_clicks_result else 0

    # Calculate real earnings (sum of all service earnings)
    earnings_result = (
        db.session.query(func.sum(MarketplaceService.earnings))
        .filter_by(seller_id=current_user.id)
        .first()
    )
    total_earnings = earnings_result[0] or 0 if earnings_result else 0

    # Get average rating from reviews
    avg_rating_result = (
        db.session.query(func.avg(MarketplaceReview.rating))
        .join(MarketplaceService)
        .filter(
            MarketplaceService.seller_id == current_user.id,
            MarketplaceReview.status == "approved",
        )
        .first()
    )
    average_rating = round(avg_rating_result[0] or 0, 1) if avg_rating_result else 0

    # Get total reviews count
    total_reviews_result = (
        db.session.query(func.count(MarketplaceReview.id))
        .join(MarketplaceService)
        .filter(
            MarketplaceService.seller_id == current_user.id,
            MarketplaceReview.status == "approved",
        )
        .first()
    )
    total_reviews = total_reviews_result[0] or 0 if total_reviews_result else 0

    # Get recent activity (clicks)
    recent_activity = (
        MarketplaceClick.query.join(MarketplaceService)
        .filter(MarketplaceService.seller_id == current_user.id)
        .order_by(desc(MarketplaceClick.created_at))
        .limit(10)
        .all()
    )

    # Get currency symbols mapping
    currency_symbols = {
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "KES": "#",
        "NGN": "₦",
        "GHS": "GH₵",
        "ZAR": "R",
    }

    # Format price function with currency
    def format_price_with_currency(price, currency="KES"):
        symbol = currency_symbols.get(currency, "")
        return f"{symbol}{price:,.2f}" if price else f"{symbol}0.00"

    # Get service statistics by status
    service_stats = {}
    statuses = ["active", "pending", "draft", "paused"]
    for status in statuses:
        count = MarketplaceService.query.filter_by(
            seller_id=current_user.id, status=status
        ).count()
        service_stats[status] = count

    return render_template(
        "seller_dashboard.html",
        services=services,
        total_services=total_services,
        active_services=active_services,
        total_views=total_views,
        total_clicks=total_clicks,
        total_earnings=total_earnings,
        average_rating=average_rating,
        total_reviews=total_reviews,
        recent_activity=recent_activity,
        currency_symbols=currency_symbols,
        format_price=format_price_with_currency,
        service_stats=service_stats,
        now=utcnow(),
    )


@market.route("/create_service", methods=["GET", "POST"])
@login_required
def create_service():
    """Create a new service"""
    if request.method == "GET":
        ensure_marketplace_categories()
        # Get categories
        categories = (
            MarketplaceCategory.query.filter_by(is_active=True, parent_id=None)
            .order_by("sort_order")
            .all()
        )

        return render_template(
            "create_service.html", categories=categories, subscriptions=[]
        )

    # POST: Create service
    try:
        # Validate required fields
        title = request.form.get("title")
        category_id = request.form.get("category_id")
        description = request.form.get("description")

        # FIX: Handle price input with commas
        price_str = request.form.get("price", "0")

        # Remove commas and convert to float
        try:
            price = float(price_str.replace(",", "").strip())
        except (ValueError, AttributeError):
            price = 0.0

        currency = request.form.get("currency", "NGN")
        service_type = request.form.get("service_type", "service")
        subscription_id = request.form.get("subscription_id")

        # Debug logging
        print(
            f"Price from form: {price_str}, After conversion: {price}, Type: {type(price)}"
        )

        if not all([title, category_id, description]):
            flash("Please fill in all required fields", "danger")
            return redirect(url_for("market.create_service"))

        # Create slug from title
        slug = title.lower().replace(" ", "-") + "-" + str(int(time.time()))

        # Get subscription
        subscription = None
        if marketplace_payments_enabled() and subscription_id:
            subscription = MarketplaceSubscription.query.get(subscription_id)
            if not subscription:
                flash("Invalid subscription plan", "danger")
                return redirect(url_for("market.create_service"))

        # Determine if service is free
        is_free_value = False
        if price is None or price == 0:
            is_free_value = True
            price = 0.0  # Ensure price is set to 0

        # Debug form data
        print(f"Form data: {dict(request.form)}")
        print(f"Files: {dict(request.files)}")

        # Create service
        service = MarketplaceService(
            seller_id=current_user.id,
            category_id=category_id,
            title=title,
            slug=slug,
            description=description,
            short_description=request.form.get("short_description", "")[:500],
            service_type=service_type,
            price=price,  # Already converted to float
            currency=currency,
            is_free=is_free_value,
            phone_number=request.form.get("phone_number"),
            whatsapp_number=request.form.get("whatsapp_number"),
            email=request.form.get("email"),
            duration=request.form.get("duration"),
            availability=request.form.get("availability"),
            subscription_id=subscription_id if marketplace_payments_enabled() else None,
            subscription_status="pending" if subscription else "active",
            subscription_expires=(
                utcnow() + timedelta(days=30) if subscription else None
            ),
            status="pending" if subscription else "active",
        )

        # Handle contact methods
        contact_methods = []
        if request.form.get("contact_whatsapp"):
            contact_methods.append("whatsapp")
        if request.form.get("contact_phone"):
            contact_methods.append("phone")
        if request.form.get("contact_messenger"):
            contact_methods.append("messenger")
        if request.form.get("contact_email"):
            contact_methods.append("email")
        service.contact_methods = json.dumps(contact_methods)

        # Handle features
        features = []
        feature_count = int(request.form.get("feature_count", 0))
        for i in range(1, feature_count + 1):
            feature = request.form.get(f"feature_{i}")
            if feature:
                features.append(feature)
        service.features = json.dumps(features)

        # Handle cover image upload
        if "cover_image" in request.files:
            file = request.files["cover_image"]
            if file and allowed_file(file.filename):
                image_url = upload_to_cloudinary(file, "services/cover")
                if image_url:
                    service.cover_image = image_url

        # Handle gallery images
        gallery_images = []
        for i in range(1, 6):
            file_key = f"gallery_image_{i}"
            if file_key in request.files:
                file = request.files[file_key]
                if file and allowed_file(file.filename):
                    image_url = upload_to_cloudinary(file, "services/gallery")
                    if image_url:
                        gallery_images.append(image_url)
        if gallery_images:
            service.gallery_images = json.dumps(gallery_images)

        # Handle digital file upload
        if service_type == "digital" and "digital_file" in request.files:
            file = request.files["digital_file"]
            if file and allowed_file(file.filename):
                file_url = upload_to_cloudinary(file, "services/digital")
                if file_url:
                    service.digital_file = file_url
                    service.file_type = (
                        file.filename.rsplit(".", 1)[1].lower()
                        if "." in file.filename
                        else ""
                    )

        db.session.add(service)
        db.session.commit()

        invalidate_cache(f"dashboard_stats_{current_user.id}_*")
        invalidate_cache(f"dashboard_services_{current_user.id}_*")

        # Redirect to payment if subscription required
        if marketplace_payments_enabled() and subscription:
            return redirect(url_for("market.payment", service_id=service.id))

        flash(
            "Service created successfully and is now live in your seller dashboard and marketplace listings.",
            "success",
        )
        return redirect(url_for("market.seller_dashboard"))

    except Exception as e:
        db.session.rollback()
        print(f"Error creating service: {e}")
        flash(
            "An error occurred while creating the service. Please try again.", "danger"
        )
        return redirect(url_for("market.create_service"))


@market.route("/edit/<int:service_id>", methods=["GET", "POST"])
@login_required
def edit_service(service_id):
    """Edit a service"""
    service = MarketplaceService.query.get_or_404(service_id)

    # Check ownership
    if service.seller_id != current_user.id:
        flash("You don't have permission to edit this service", "danger")
        return redirect(url_for("market.seller_dashboard"))

    if request.method == "GET":
        ensure_marketplace_categories()
        categories = (
            MarketplaceCategory.query.filter_by(is_active=True, parent_id=None)
            .order_by("sort_order")
            .all()
        )
        subscriptions = (
            MarketplaceSubscription.query.filter_by(is_active=True)
            .order_by("sort_order")
            .all()
        )

        return render_template(
            "edit_service.html",
            service=service,
            categories=categories,
            subscriptions=subscriptions,
        )

    # POST: Update service
    try:
        service.title = request.form.get("title", service.title)
        service.category_id = request.form.get("category_id", service.category_id)
        service.description = request.form.get("description", service.description)
        service.short_description = request.form.get(
            "short_description", service.short_description
        )[:500]

        # FIX: Handle price input with commas
        price_str = request.form.get("price")
        if price_str is not None:
            try:
                # Remove commas and convert to float
                price = float(price_str.replace(",", "").strip())
                service.price = price
                service.is_free = price == 0
            except (ValueError, AttributeError):
                flash("Invalid price format. Please enter a valid number.", "danger")
                return redirect(url_for("market.edit_service", service_id=service_id))

        service.phone_number = request.form.get("phone_number")
        service.whatsapp_number = request.form.get("whatsapp_number")
        service.email = request.form.get("email")
        service.duration = request.form.get("duration")
        service.availability = request.form.get("availability")

        # Update contact methods
        contact_methods = []
        if request.form.get("contact_whatsapp"):
            contact_methods.append("whatsapp")
        if request.form.get("contact_phone"):
            contact_methods.append("phone")
        if request.form.get("contact_messenger"):
            contact_methods.append("messenger")
        if request.form.get("contact_email"):
            contact_methods.append("email")
        service.contact_methods = json.dumps(contact_methods)

        # Update features
        features = []
        feature_count = int(request.form.get("feature_count", 0))
        for i in range(1, feature_count + 1):
            feature = request.form.get(f"feature_{i}")
            if feature:
                features.append(feature)
        service.features = json.dumps(features)

        # Update cover image
        if "cover_image" in request.files:
            file = request.files["cover_image"]
            if file and allowed_file(file.filename):
                image_url = upload_to_cloudinary(file, "services/cover")
                if image_url:
                    service.cover_image = image_url

        # Update gallery images
        gallery_images = service.gallery_images_list
        for i in range(1, 6):
            file_key = f"gallery_image_{i}"
            if file_key in request.files:
                file = request.files[file_key]
                if file and allowed_file(file.filename):
                    image_url = upload_to_cloudinary(file, "services/gallery")
                    if image_url and image_url not in gallery_images:
                        gallery_images.append(image_url)

        # Handle remove gallery images
        remove_images = request.form.getlist("remove_gallery")
        gallery_images = [img for img in gallery_images if img not in remove_images]

        if gallery_images:
            service.gallery_images = json.dumps(gallery_images)
        else:
            service.gallery_images = None

        db.session.commit()

        flash("Service updated successfully!", "success")
        return redirect(url_for("market.seller_dashboard"))

    except Exception as e:
        db.session.rollback()
        print(f"Error updating service: {e}")
        flash(
            "An error occurred while updating the service. Please try again.", "danger"
        )
        return redirect(url_for("market.edit_service", service_id=service_id))


@market.route("/fix-existing-services", methods=["GET"])
@login_required
def fix_existing_services():
    """Fix all existing services' price and is_free fields"""
    try:
        services = MarketplaceService.query.filter_by(seller_id=current_user.id).all()
        fixed_count = 0

        for service in services:
            # Ensure price is a float
            if service.price is not None:
                # Convert to float if it's a string
                if isinstance(service.price, str):
                    try:
                        service.price = float(service.price.replace(",", "").strip())
                        fixed_count += 1
                    except (ValueError, AttributeError):
                        service.price = 0.0
                        service.is_free = True
                        fixed_count += 1

                # Update is_free based on actual price
                if service.price == 0:
                    service.is_free = True
                else:
                    service.is_free = False
                    fixed_count += 1

        db.session.commit()

        flash(f"Fixed {fixed_count} services", "success")
        return redirect(url_for("market.seller_dashboard"))

    except Exception as e:
        db.session.rollback()
        print(f"Error fixing services: {e}")
        flash("Error fixing services", "danger")
        return redirect(url_for("market.seller_dashboard"))


@market.route("/delete_service/<int:service_id>", methods=["DELETE", "POST"])
@login_required
def delete_service(service_id):
    """Delete a service - Accepts both DELETE and POST"""
    try:
        service = MarketplaceService.query.get(service_id)

        # Check if service exists
        if not service:
            return jsonify({"success": False, "error": "Service not found"}), 404

        # Check ownership
        if service.seller_id != current_user.id:
            return jsonify({"success": False, "error": "Permission denied"}), 403

        # Delete related clicks first
        MarketplaceClick.query.filter_by(service_id=service_id).delete()

        # Delete related reviews
        MarketplaceReview.query.filter_by(service_id=service_id).delete()

        # Delete the service
        db.session.delete(service)
        db.session.commit()

        invalidate_cache(f"dashboard_stats_{current_user.id}_*")
        invalidate_cache(f"dashboard_services_{current_user.id}_*")

        return jsonify({"success": True, "message": "Service deleted successfully"})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting service {service_id}: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@market.route("/toggle-status/<int:service_id>", methods=["POST"])
@login_required
def toggle_service_status(service_id):
    """Toggle service active status"""
    service = MarketplaceService.query.get_or_404(service_id)

    # Check ownership
    if service.seller_id != current_user.id:
        return jsonify({"success": False, "error": "Permission denied"}), 403

    try:
        if service.status == "active":
            service.status = "paused"
        elif service.status == "paused":
            service.status = "active"

        db.session.commit()
        return jsonify({"success": True, "status": service.status})
    except Exception as e:
        db.session.rollback()
        print(f"Error toggling service status: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== PAYMENT ROUTES ====================


@market.route("/payment/<int:service_id>", methods=["GET"])
@login_required
def payment(service_id):
    """Payment page for service subscription"""
    service = MarketplaceService.query.get_or_404(service_id)

    # Check ownership
    if service.seller_id != current_user.id:
        flash("Permission denied", "danger")
        return redirect(url_for("market.seller_dashboard"))

    # Check if already paid
    if service.subscription_status == "active":
        flash("Service subscription is already active", "info")
        return redirect(url_for("market.seller_dashboard"))

    subscription = service.subscription
    if not subscription:
        flash("No subscription required for this service", "info")
        return redirect(url_for("market.seller_dashboard"))

    return render_template(
        "payment.html",
        service=service,
        subscription=subscription,
        format_price=format_price,
    )


@market.route("/initiate-payment", methods=["POST"])
@login_required
def initiate_payment():
    """Initiate Flutterwave payment"""
    try:
        service_id = request.form.get("service_id")
        subscription_id = request.form.get("subscription_id")

        service = MarketplaceService.query.get_or_404(service_id)
        subscription = MarketplaceSubscription.query.get_or_404(subscription_id)

        # Check ownership
        if service.seller_id != current_user.id:
            return jsonify({"success": False, "error": "Permission denied"}), 403

        # Generate unique transaction reference
        tx_ref = f"KIMBELA-MP-{int(time.time())}-{service_id}"

        # Create payment record
        payment = MarketplacePayment(
            user_id=current_user.id,
            service_id=service_id,
            subscription_id=subscription_id,
            amount=subscription.price_usd,
            tokens_paid=subscription.price,
            gateway="flutterwave",
            gateway_reference=tx_ref,
            status="pending",
            description=f"Marketplace subscription: {subscription.name} for service: {service.title}",
        )
        db.session.add(payment)
        db.session.commit()

        # Prepare Flutterwave payment data
        payment_data = {
            "tx_ref": tx_ref,
            "amount": str(subscription.price_usd),
            "currency": "USD",
            "redirect_url": url_for("market.payment_callback", _external=True),
            "customer": {
                "email": current_user.email,
                "name": current_user.full_name,
                "phone_number": current_user.phone_number,
            },
            "customizations": {
                "title": "Kimbela Marketplace",
                "description": f"Subscription: {subscription.name}",
                "logo": url_for(
                    "static", filename="assets/img/kim.png", _external=True
                ),
            },
            "meta": {
                "service_id": service_id,
                "subscription_id": subscription_id,
                "payment_id": payment.id,
                "user_id": current_user.id,
            },
        }

        return jsonify(
            {
                "success": True,
                "payment_data": payment_data,
                "flutterwave_public_key": current_app.config.get(
                    "FLUTTERWAVE_PUBLIC_KEY"
                ),
            }
        )

    except Exception as e:
        db.session.rollback()
        print(f"Error initiating payment: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@market.route("/payment-callback", methods=["GET"])
@login_required
def payment_callback():
    """Handle Flutterwave payment callback"""
    try:
        tx_ref = request.args.get("tx_ref")
        transaction_id = request.args.get("transaction_id")
        status = request.args.get("status")

        # Verify payment with Flutterwave
        payment = MarketplacePayment.query.filter_by(
            gateway_reference=tx_ref
        ).first_or_404()

        if payment.user_id != current_user.id:
            flash("Unauthorized access", "danger")
            return redirect(url_for("market.seller_dashboard"))

        if status == "successful":
            # Update payment record
            payment.gateway_payment_id = transaction_id
            payment.gateway_status = "successful"
            payment.status = "completed"
            payment.paid_at = utcnow()

            # Update service subscription
            service = payment.service
            service.subscription_status = "active"
            service.subscription_expires = utcnow() + timedelta(days=30)
            service.status = "pending"  # Will be reviewed by admin

            # Create payment transaction record
            transaction = PaymentTransaction(
                user_id=current_user.id,
                amount=payment.amount,
                currency=payment.currency,
                gateway="flutterwave",
                gateway_reference=tx_ref,
                gateway_payment_id=transaction_id,
                gateway_status="successful",
                status="completed",
                description=f"Marketplace subscription payment for {service.title}",
                transaction_type="marketplace_subscription",
            )
            db.session.add(transaction)
            db.session.commit()

            flash("Payment successful! Your service is now pending review.", "success")

            # TODO: Send email confirmation

        else:
            payment.status = "failed"
            payment.gateway_status = status
            db.session.commit()
            flash("Payment failed. Please try again.", "danger")

        return redirect(url_for("market.seller_dashboard"))

    except Exception as e:
        print(f"Payment callback error: {e}")
        flash("An error occurred processing your payment", "danger")
        return redirect(url_for("market.seller_dashboard"))


# ==================== API ROUTES ====================


@market.route("/api/services", methods=["GET"])
def api_services():
    """API endpoint for services (for AJAX loading)"""
    try:
        page = request.args.get("page", 1, type=int)
        per_page = 12

        # Build query
        query = MarketplaceService.query.filter_by(status="active")
        query = apply_marketplace_seller_visibility_filter(query)

        # Apply filters
        category_id = request.args.get("category_id")
        if category_id:
            query = query.filter_by(category_id=category_id)

        search = request.args.get("search")
        if search:
            query = query.filter(
                or_(
                    MarketplaceService.title.ilike(f"%{search}%"),
                    MarketplaceService.description.ilike(f"%{search}%"),
                )
            )

        min_price = request.args.get("min_price", type=int)
        max_price = request.args.get("max_price", type=int)
        if min_price is not None:
            query = query.filter(MarketplaceService.price >= min_price)
        if max_price is not None:
            query = query.filter(MarketplaceService.price <= max_price)

        service_type = request.args.get("service_type")
        if service_type:
            query = query.filter_by(service_type=service_type)

        featured_only = request.args.get("featured") == "true"
        if featured_only:
            query = query.filter_by(is_featured=True)

        # Sort
        sort_by = request.args.get("sort", "newest")
        if sort_by == "popular":
            query = query.order_by(desc(MarketplaceService.views))
        elif sort_by == "rating":
            query = query.order_by(desc(MarketplaceService.average_rating))
        elif sort_by == "price_low":
            query = query.order_by(MarketplaceService.price)
        elif sort_by == "price_high":
            query = query.order_by(desc(MarketplaceService.price))
        else:  # newest
            query = query.order_by(desc(MarketplaceService.created_at))

        # Paginate
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        # Prepare response
        services = []
        for service in pagination.items:
            seller = service.seller
            services.append(
                {
                    "id": service.id,
                    "title": service.title,
                    "slug": service.slug,
                    "short_description": service.short_description,
                    "price": service.price,
                    "formatted_price": format_price(service.price),
                    "is_free": service.is_free,
                    "is_featured": service.is_featured,
                    "cover_image": service.cover_image
                    or url_for("static", filename="assets/img/default-service.jpg"),
                    "service_type": service.service_type,
                    "duration": service.duration,
                    "average_rating": service.average_rating,
                    "review_count": service.review_count,
                    "views": service.views,
                    "created_at": service.created_at.isoformat(),
                    "seller": {
                        "id": seller.id,
                        "name": seller.full_name,
                        "avatar": seller.profile_pic
                        or url_for("static", filename="assets/img/default-avatar.png"),
                        "rating": (
                            seller.avg_rating if hasattr(seller, "avg_rating") else 0
                        ),
                    },
                    "category": (
                        service.category.name if service.category else "Uncategorized"
                    ),
                }
            )

        return jsonify(
            {
                "success": True,
                "services": services,
                "has_next": pagination.has_next,
                "has_prev": pagination.has_prev,
                "page": pagination.page,
                "pages": pagination.pages,
                "total": pagination.total,
            }
        )

    except Exception as e:
        print(f"API services error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@market.route("/api/log-click/<int:service_id>", methods=["GET", "POST", "OPTIONS"])
def log_contact_click(service_id):
    """Log user clicks on contact methods - accepts GET and POST"""
    # Handle CORS preflight
    if request.method == "OPTIONS":
        response = jsonify({"status": "ok"})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add(
            "Access-Control-Allow-Headers", "Content-Type,Authorization"
        )
        response.headers.add(
            "Access-Control-Allow-Methods", "GET,PUT,POST,DELETE,OPTIONS"
        )
        return response

    try:
        print(
            f"📊 [LOG-CLICK] Received {request.method} request for service {service_id}"
        )

        # Get click type from either GET params or POST JSON
        click_type = None

        if request.method == "GET":
            click_type = request.args.get("type", "unknown")
        elif request.method == "POST":
            if request.is_json:
                data = request.get_json()
                click_type = data.get("type", "unknown")
            else:
                click_type = request.form.get("type", "unknown")

        if not click_type:
            click_type = "unknown"

        print(f"📊 Click type: {click_type}")

        # Get the service
        service = MarketplaceService.query.get(service_id)
        if not service:
            print(f"❌ Service not found: {service_id}")
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Service not found",
                        "service_id": service_id,
                    }
                ),
                404,
            )

        # Log to MarketplaceClick table
        click = MarketplaceClick(
            service_id=service_id,
            user_id=current_user.id if current_user.is_authenticated else None,
            click_type=click_type,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
        )
        db.session.add(click)

        # Also update service click count if it's a contact click
        if click_type in ["whatsapp", "phone", "email", "messenger"]:
            service.clicks = (service.clicks or 0) + 1

        db.session.commit()

        print(f"✅ Click logged - Service: {service_id}, Type: {click_type}")

        response = jsonify(
            {
                "success": True,
                "message": "Click logged",
                "service_id": service_id,
                "click_type": click_type,
            }
        )

        # Add CORS headers
        response.headers.add("Access-Control-Allow-Origin", "*")

        return response

    except Exception as e:
        db.session.rollback()
        print(f"❌ Error logging click: {e}")

        response = jsonify(
            {"success": False, "error": str(e), "service_id": service_id}
        )
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 500


@market.route("/api/log-contact_click/<int:service_id>", methods=["POST", "OPTIONS"])
def log_contact_click_fallback(service_id):
    """Fallback endpoint for legacy JavaScript calls"""
    # Handle CORS preflight
    if request.method == "OPTIONS":
        response = jsonify({"status": "ok"})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add(
            "Access-Control-Allow-Headers", "Content-Type,Authorization"
        )
        response.headers.add(
            "Access-Control-Allow-Methods", "GET,PUT,POST,DELETE,OPTIONS"
        )
        return response

    try:
        print(f"📊 [FALLBACK] Received request for service {service_id}")

        # Get data
        data = {}
        if request.is_json:
            data = request.get_json()
        elif request.form:
            data = dict(request.form)

        click_type = data.get("type", "unknown")

        print(
            f"📊 Legacy endpoint: Click logged - Service: {service_id}, Type: {click_type}"
        )

        # Try to log to database too
        try:
            service = MarketplaceService.query.get(service_id)
            if service:
                click = MarketplaceClick(
                    service_id=service_id,
                    user_id=current_user.id if current_user.is_authenticated else None,
                    click_type=click_type,
                    ip_address=request.remote_addr,
                    user_agent=request.user_agent.string,
                )
                db.session.add(click)
                db.session.commit()
        except Exception as db_error:
            print(f"⚠️ Could not save to database in fallback: {db_error}")

        response = jsonify(
            {
                "success": True,
                "message": "Click logged via fallback",
                "service_id": service_id,
                "endpoint": "fallback",
            }
        )
        response.headers.add("Access-Control-Allow-Origin", "*")

        return response

    except Exception as e:
        print(f"❌ Error in fallback: {e}")

        # Always return success to not break UI
        response = jsonify(
            {
                "success": True,
                "message": "Logged",
                "service_id": service_id,
                "endpoint": "fallback_error",
            }
        )
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 200


@market.route("/debug-log-click/<int:service_id>", methods=["GET", "POST"])
def debug_log_click(service_id):
    """Debug the log click endpoint"""
    _require_debug_access()
    print(f"🔍 DEBUG - Request to log-click for service {service_id}")
    print(f"Method: {request.method}")
    print(f"Headers: {dict(request.headers)}")
    print(f"Content-Type: {request.content_type}")

    if request.method == "POST":
        try:
            if request.is_json:
                data = request.get_json()
                print(f"JSON data: {data}")
            else:
                print(f"Raw data: {request.get_data()}")
                print(f"Form data: {request.form}")
        except Exception as e:
            print(f"Error reading data: {e}")

    return jsonify(
        {
            "debug": True,
            "service_id": service_id,
            "method": request.method,
            "content_type": request.content_type,
            "has_json": request.is_json,
        }
    )


@market.route("/api/seller/<int:seller_id>/stats", methods=["GET"])
@login_required
def seller_stats(seller_id):
    """Get seller statistics"""
    if current_user.id != seller_id:
        return jsonify({"success": False, "error": "Permission denied"}), 403

    try:
        # Get total services
        total_services = MarketplaceService.query.filter_by(seller_id=seller_id).count()

        # Get active services
        active_services = MarketplaceService.query.filter_by(
            seller_id=seller_id, status="active"
        ).count()

        # Get total views
        total_views = (
            db.session.query(func.sum(MarketplaceService.views))
            .filter_by(seller_id=seller_id)
            .scalar()
            or 0
        )

        # Get total clicks
        total_clicks = (
            db.session.query(func.sum(MarketplaceService.clicks))
            .filter_by(seller_id=seller_id)
            .scalar()
            or 0
        )

        # Get revenue (in tokens)
        total_revenue = (
            db.session.query(func.sum(MarketplaceService.price))
            .filter_by(seller_id=seller_id)
            .scalar()
            or 0
        )

        # Get monthly stats
        now = utcnow()
        month_start = datetime(now.year, now.month, 1)

        monthly_views = (
            db.session.query(func.sum(MarketplaceService.views))
            .filter(
                MarketplaceService.seller_id == seller_id,
                MarketplaceService.updated_at >= month_start,
            )
            .scalar()
            or 0
        )

        monthly_clicks = (
            db.session.query(func.sum(MarketplaceService.clicks))
            .filter(
                MarketplaceService.seller_id == seller_id,
                MarketplaceService.updated_at >= month_start,
            )
            .scalar()
            or 0
        )

        return jsonify(
            {
                "success": True,
                "stats": {
                    "total_services": total_services,
                    "active_services": active_services,
                    "total_views": total_views,
                    "total_clicks": total_clicks,
                    "total_revenue": total_revenue,
                    "monthly_views": monthly_views,
                    "monthly_clicks": monthly_clicks,
                },
            }
        )

    except Exception as e:
        print(f"Seller stats error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== ADMIN ROUTES ====================


@market.route("/admin/services", methods=["GET"])
@login_required
def admin_services():
    """Admin view of all services"""
    if not current_user.is_super_admin:
        flash("Admin access required", "danger")
        return redirect(url_for("market.main_market"))

    page = request.args.get("page", 1, type=int)
    per_page = 20

    status = request.args.get("status", "pending")

    query = MarketplaceService.query
    if status != "all":
        query = query.filter_by(status=status)

    services = query.order_by(desc(MarketplaceService.created_at)).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template(
        "admin/services.html",
        services=services,
        status=status,
        format_price=format_price,
    )


# @market.route("/admin/service/<int:service_id>/approve", methods=["POST"])
# @login_required
# def admin_approve_service(service_id):
#     """Approve a service"""
#     if not current_user.is_super_admin:
#         return jsonify({'success': False, 'error': 'Admin access required'}), 403

#     service = MarketplaceService.query.get_or_404(service_id)

#     try:
#         service.status = 'active'
#         service.published_at = utcnow()
#         db.session.commit()

#         # TODO: Send email notification to seller

#         return jsonify({'success': True})

#     except Exception as e:
#         db.session.rollback()
#         print(f"Approve service error: {e}")
#         return jsonify({'success': False, 'error': str(e)}), 500


# @market.route("/admin/service/<int:service_id>/reject", methods=["POST"])
# @login_required
# def admin_reject_service(service_id):
#     """Reject a service"""
#     if not current_user.is_super_admin:
#         return jsonify({'success': False, 'error': 'Admin access required'}), 403

#     service = MarketplaceService.query.get_or_404(service_id)
#     reason = request.json.get('reason', '')

#     try:
#         service.status = 'rejected'
#         service.rejection_reason = reason
#         db.session.commit()

#         # TODO: Send email notification to seller

#         return jsonify({'success': True})

#     except Exception as e:
#         db.session.rollback()
#         print(f"Reject service error: {e}")
#         return jsonify({'success': False, 'error': str(e)}), 500


@market.route("/admin/featured", methods=["GET", "POST"])
@login_required
def manage_featured():
    """Manage featured services"""
    if not current_user.is_super_admin:
        flash("Admin access required", "danger")
        return redirect(url_for("market.main_market"))

    if request.method == "POST":
        service_id = request.form.get("service_id")
        action = request.form.get("action")

        service = MarketplaceService.query.get_or_404(service_id)

        if action == "feature":
            service.is_featured = True
            message = "Service featured successfully"
        else:
            service.is_featured = False
            message = "Service unfeatured successfully"

        db.session.commit()
        flash(message, "success")
        return redirect(url_for("market.manage_featured"))

    # GET: Show featured services
    featured_services = MarketplaceService.query.filter_by(is_featured=True).all()
    non_featured_services = (
        MarketplaceService.query.filter_by(status="active", is_featured=False)
        .order_by(desc(MarketplaceService.created_at))
        .limit(50)
        .all()
    )

    return render_template(
        "admin/featured.html",
        featured_services=featured_services,
        non_featured_services=non_featured_services,
        format_price=format_price,
    )


# ==================== DATA INITIALIZATION ====================

DEFAULT_MARKETPLACE_CATEGORIES = [
    {
        "name": "Fashion",
        "slug": "fashion",
        "icon": "bi-bag-heart-fill",
        "subcategories": [
            {"name": "Clothing", "slug": "clothing"},
            {"name": "Underwear & Lingerie", "slug": "underwear-lingerie"},
            {"name": "Sportswear / Activewear", "slug": "sportswear-activewear"},
            {"name": "Footwear", "slug": "footwear"},
            {"name": "Bags", "slug": "bags"},
            {"name": "Jewellery", "slug": "jewellery"},
            {"name": "Accessories", "slug": "accessories"},
        ],
    },
    {
        "name": "Entertainment",
        "slug": "entertainment",
        "icon": "bi-mic-fill",
        "subcategories": [
            {"name": "DJs", "slug": "djs"},
            {"name": "Live Bands", "slug": "live-bands"},
            {"name": "MC / Event Hosts", "slug": "mc-event-hosts"},
            {"name": "Comedians", "slug": "comedians"},
            {"name": "Performers", "slug": "performers"},
            {"name": "Entertainment Booking", "slug": "entertainment-booking"},
        ],
    },
    {
        "name": "Beauty & Personal Care",
        "slug": "beauty-personal-care",
        "icon": "bi-droplet-fill",
        "subcategories": [
            {"name": "Skincare Products", "slug": "skincare-products"},
            {"name": "Makeup", "slug": "makeup"},
            {"name": "Hair Care", "slug": "hair-care"},
            {"name": "Grooming Products", "slug": "grooming-products"},
            {"name": "Hair Styling", "slug": "hair-styling-products"},
            {"name": "Nail Care", "slug": "nail-care-products"},
        ],
    },
    {
        "name": "Electronics & Gadgets",
        "slug": "electronics-gadgets",
        "icon": "bi-cpu-fill",
        "subcategories": [
            {"name": "Mobile Phones", "slug": "mobile-phones"},
            {"name": "Laptops & Computers", "slug": "laptops-computers"},
            {"name": "Tablets", "slug": "tablets"},
            {"name": "Smart Watches", "slug": "smart-watches"},
            {"name": "Headphones & Earbuds", "slug": "headphones-earbuds"},
            {"name": "Cameras", "slug": "cameras"},
            {"name": "Gaming Consoles", "slug": "gaming-consoles"},
            {"name": "Phone Accessories", "slug": "phone-accessories"},
            {"name": "Computer Accessories", "slug": "computer-accessories"},
            {"name": "Smart Home Devices", "slug": "smart-home-devices"},
        ],
    },
    {
        "name": "Home & Living",
        "slug": "home-living",
        "icon": "bi-house-heart-fill",
        "subcategories": [
            {"name": "Home Decor", "slug": "home-decor"},
            {"name": "Furniture", "slug": "furniture"},
            {"name": "Kitchen Products", "slug": "kitchen-products"},
            {"name": "Home Appliances", "slug": "home-appliances"},
            {"name": "Household Essentials", "slug": "household-essentials"},
            {"name": "Cleaning Supplies", "slug": "cleaning-supplies"},
        ],
    },
    {
        "name": "Garden & Outdoor",
        "slug": "garden-outdoor",
        "icon": "bi-flower1",
        "subcategories": [
            {"name": "Gardening Tools", "slug": "gardening-tools"},
            {"name": "Plants & Seeds", "slug": "plants-seeds"},
            {"name": "Outdoor Furniture", "slug": "outdoor-furniture"},
            {"name": "Outdoor Decor", "slug": "outdoor-decor"},
            {"name": "Landscaping Supplies", "slug": "landscaping-supplies"},
        ],
    },
    {
        "name": "Sports & Fitness",
        "slug": "sports-fitness",
        "icon": "bi-trophy-fill",
        "subcategories": [
            {"name": "Sports Equipment", "slug": "sports-equipment"},
            {"name": "Gym Equipment", "slug": "gym-equipment"},
            {"name": "Fitness Accessories", "slug": "fitness-accessories"},
            {"name": "Yoga & Pilates Gear", "slug": "yoga-pilates-gear"},
            {"name": "Running Gear", "slug": "running-gear"},
            {"name": "Cycling Equipment", "slug": "cycling-equipment"},
            {"name": "Sports Coaching", "slug": "sports-coaching"},
            {"name": "Personal Training", "slug": "personal-training"},
        ],
    },
    {
        "name": "Books & Learning",
        "slug": "books-learning",
        "icon": "bi-book-half",
        "subcategories": [
            {"name": "Books", "slug": "books"},
            {"name": "Educational Materials", "slug": "educational-materials"},
            {"name": "Study Guides", "slug": "study-guides"},
            {"name": "Training Manuals", "slug": "training-manuals"},
            {"name": "Online Courses", "slug": "online-courses"},
        ],
    },
    {
        "name": "Art, Crafts & Handmade Goods",
        "slug": "art-crafts-handmade-goods",
        "icon": "bi-brush-fill",
        "subcategories": [
            {"name": "Artwork", "slug": "artwork"},
            {"name": "Crafts", "slug": "crafts"},
            {"name": "Handmade Decor", "slug": "handmade-decor"},
            {"name": "Custom Gifts", "slug": "custom-gifts"},
            {"name": "Custom Art", "slug": "custom-art"},
        ],
    },
    {
        "name": "Kids & Baby",
        "slug": "kids-baby",
        "icon": "bi-emoji-smile",
        "subcategories": [
            {"name": "Baby Clothing", "slug": "baby-clothing"},
            {"name": "Kids Clothing", "slug": "kids-clothing"},
            {"name": "Baby Products", "slug": "baby-products"},
            {"name": "Toys & Games", "slug": "toys-games"},
            {"name": "Baby Care Products", "slug": "baby-care-products"},
            {"name": "Kids Learning Materials", "slug": "kids-learning-materials"},
        ],
    },
    {
        "name": "Domestic & Household Help",
        "slug": "domestic-household-help",
        "icon": "bi-house-check",
        "subcategories": [
            {"name": "House Help / Home Help", "slug": "house-help-home-help"},
            {"name": "Nannies", "slug": "nannies"},
            {"name": "Caregivers", "slug": "caregivers"},
            {"name": "Elderly Care", "slug": "elderly-care"},
            {"name": "Babysitting", "slug": "babysitting"},
        ],
    },
    {
        "name": "Automotive",
        "slug": "automotive",
        "icon": "bi-car-front-fill",
        "subcategories": [
            {"name": "Cars for Sale", "slug": "cars-for-sale"},
            {"name": "Car Accessories", "slug": "car-accessories"},
            {"name": "Car Care Products", "slug": "car-care-products"},
            {"name": "Car Parts", "slug": "car-parts"},
            {"name": "Car Electronics", "slug": "car-electronics"},
            {"name": "Auto Repair", "slug": "auto-repair"},
            {"name": "Car Detailing", "slug": "car-detailing"},
            {"name": "Vehicle Maintenance", "slug": "vehicle-maintenance"},
            {"name": "Car Inspection", "slug": "car-inspection"},
        ],
    },
    {
        "name": "Food & Groceries",
        "slug": "food-groceries",
        "icon": "bi-basket-fill",
        "subcategories": [
            {"name": "Raw Food / Fresh Produce", "slug": "raw-food-fresh-produce"},
            {"name": "Spices, Herbs & Seasonings", "slug": "spices-herbs-seasonings"},
            {"name": "Packaged Foods", "slug": "packaged-foods"},
            {"name": "Homemade Foods", "slug": "homemade-foods"},
            {"name": "Snacks", "slug": "snacks"},
            {"name": "Beverages", "slug": "beverages"},
        ],
    },
    {
        "name": "Health & Wellness",
        "slug": "health-wellness",
        "icon": "bi-heart-pulse-fill",
        "subcategories": [
            {"name": "Health Supplements", "slug": "health-supplements"},
            {"name": "Herbal Medicine", "slug": "herbal-medicine"},
            {"name": "Personal Hygiene Products", "slug": "personal-hygiene-products"},
            {"name": "Wellness Products", "slug": "wellness-products"},
            {"name": "Nutrition Coaching", "slug": "nutrition-coaching"},
            {"name": "Wellness Programs", "slug": "wellness-programs"},
            {"name": "Fitness Plans", "slug": "fitness-plans"},
        ],
    },
    {
        "name": "Mentoring & Coaching",
        "slug": "mentoring-coaching",
        "icon": "bi-people-fill",
        "subcategories": [
            {"name": "Life Coaching", "slug": "life-coaching"},
            {"name": "Leadership Coaching", "slug": "leadership-coaching"},
            {"name": "Relationship Coaching", "slug": "relationship-coaching"},
            {"name": "Personal Growth Coaching", "slug": "personal-growth-coaching"},
        ],
    },
    {
        "name": "Counselling & Therapy",
        "slug": "counselling-therapy",
        "icon": "bi-chat-heart-fill",
        "subcategories": [
            {"name": "Relationship Counselling", "slug": "relationship-counselling"},
            {"name": "Family Counselling", "slug": "family-counselling"},
            {"name": "Mental Wellness Support", "slug": "mental-wellness-support"},
            {"name": "Emotional Support Coaching", "slug": "emotional-support-coaching"},
            {"name": "Stress Management", "slug": "stress-management"},
            {"name": "Personal Development Therapy", "slug": "personal-development-therapy"},
            {"name": "Sex & Intimacy Therapy", "slug": "sex-intimacy-therapy"},
        ],
    },
    {
        "name": "Education & Tutoring",
        "slug": "education-tutoring",
        "icon": "bi-mortarboard-fill",
        "subcategories": [
            {"name": "Academic Tutoring", "slug": "academic-tutoring"},
            {"name": "Language Learning", "slug": "language-learning"},
            {"name": "Professional Certifications", "slug": "professional-certifications"},
            {"name": "Online Courses", "slug": "education-online-courses"},
            {"name": "Skill Development", "slug": "skill-development"},
            {"name": "Exam Preparation", "slug": "exam-preparation"},
        ],
    },
    {
        "name": "Professional Services",
        "slug": "professional-services",
        "icon": "bi-briefcase-fill",
        "subcategories": [
            {"name": "HR Consulting", "slug": "hr-consulting"},
            {"name": "Project Management", "slug": "project-management"},
            {"name": "Operations Consulting", "slug": "operations-consulting"},
            {"name": "Administrative Services", "slug": "administrative-services"},
            {"name": "Virtual Assistance", "slug": "virtual-assistance"},
            {"name": "Document Preparation", "slug": "document-preparation"},
            {"name": "Customer Support Services", "slug": "customer-support-services"},
            {"name": "Call Center Services", "slug": "call-center-services"},
            {"name": "Career & Employment Services", "slug": "career-employment-services"},
            {"name": "Business & Entrepreneurship Services", "slug": "business-entrepreneurship-services"},
            {"name": "Personal Development Coaching", "slug": "professional-personal-development-coaching"},
            {"name": "Other Business Services", "slug": "other-business-services"},
        ],
    },
    {
        "name": "Legal Services",
        "slug": "legal-services",
        "icon": "bi-shield-check",
        "subcategories": [
            {"name": "Legal Consultation", "slug": "legal-consultation"},
            {"name": "Contract Drafting", "slug": "contract-drafting"},
            {"name": "Business Registration Guidance", "slug": "business-registration-guidance"},
            {"name": "Compliance Support", "slug": "compliance-support"},
            {"name": "Legal Advisory", "slug": "legal-advisory"},
        ],
    },
    {
        "name": "Finance & Investment",
        "slug": "finance-investment",
        "icon": "bi-graph-up-arrow",
        "subcategories": [
            {"name": "Financial Planning", "slug": "financial-planning"},
            {"name": "Investment Education", "slug": "investment-education"},
            {"name": "Budgeting & Money Management", "slug": "budgeting-money-management"},
            {"name": "Tax Guidance", "slug": "tax-guidance"},
            {"name": "Wealth Building Strategies", "slug": "wealth-building-strategies"},
        ],
    },
    {
        "name": "Technology & Digital Services",
        "slug": "technology-digital-services",
        "icon": "bi-laptop-fill",
        "subcategories": [
            {"name": "Website Development", "slug": "website-development"},
            {"name": "Mobile App Development", "slug": "mobile-app-development"},
            {"name": "Software Development", "slug": "software-development"},
            {"name": "IT Support", "slug": "it-support"},
            {"name": "Cybersecurity Services", "slug": "cybersecurity-services"},
        ],
    },
    {
        "name": "Faith & Spiritual Guidance",
        "slug": "faith-spiritual-guidance",
        "icon": "bi-star-fill",
        "subcategories": [
            {"name": "Faith Coaching", "slug": "faith-coaching"},
            {"name": "Spiritual Counselling", "slug": "spiritual-counselling"},
            {"name": "Prayer & Support Sessions", "slug": "prayer-support-sessions"},
            {"name": "Religious Study Groups", "slug": "religious-study-groups"},
        ],
    },
    {
        "name": "Beauty Services",
        "slug": "beauty-services",
        "icon": "bi-scissors",
        "subcategories": [
            {"name": "Hair Styling", "slug": "hair-styling-services"},
            {"name": "Makeup Services", "slug": "makeup-services"},
            {"name": "Skincare Treatments", "slug": "skincare-treatments"},
            {"name": "Barbering / Grooming", "slug": "barbering-grooming"},
            {"name": "Nail Care Services", "slug": "nail-care-services"},
            {"name": "Beauty Consultations", "slug": "beauty-consultations"},
        ],
    },
    {
        "name": "Home Services",
        "slug": "home-services",
        "icon": "bi-house-gear",
        "subcategories": [
            {"name": "Interior Design", "slug": "interior-design"},
            {"name": "Home Decoration Services", "slug": "home-decoration-services"},
            {"name": "Furniture Assembly", "slug": "furniture-assembly"},
            {"name": "Home Organization", "slug": "home-organization"},
            {"name": "Home Maintenance", "slug": "home-maintenance"},
            {"name": "Cleaning Services", "slug": "cleaning-services"},
        ],
    },
    {
        "name": "Events & Celebrations",
        "slug": "events-celebrations",
        "icon": "bi-calendar-event",
        "subcategories": [
            {"name": "Event Planning", "slug": "event-planning"},
            {"name": "Wedding Planning", "slug": "wedding-planning"},
            {"name": "Event Decoration", "slug": "event-decoration"},
            {"name": "Photography", "slug": "photography"},
            {"name": "Event Hosting", "slug": "event-hosting"},
        ],
    },
    {
        "name": "Travel & Experiences",
        "slug": "travel-experiences",
        "icon": "bi-airplane-fill",
        "subcategories": [
            {"name": "Travel Planning", "slug": "travel-planning"},
            {"name": "Guided Tours", "slug": "guided-tours"},
            {"name": "Retreats", "slug": "retreats"},
            {"name": "Adventure Experiences", "slug": "adventure-experiences"},
            {"name": "Cultural Experiences", "slug": "cultural-experiences"},
        ],
    },
    {
        "name": "Office & Business Supplies",
        "slug": "office-business-supplies",
        "icon": "bi-printer-fill",
        "subcategories": [
            {"name": "Office Supplies", "slug": "office-supplies"},
            {"name": "Stationery", "slug": "stationery"},
            {"name": "Business Equipment", "slug": "business-equipment"},
            {"name": "Printers & Ink", "slug": "printers-ink"},
            {"name": "Office Furniture", "slug": "office-furniture"},
        ],
    },
    {
        "name": "Pet Products & Services",
        "slug": "pet-products-services",
        "icon": "bi-paw-fill",
        "subcategories": [
            {"name": "Pet Food", "slug": "pet-food"},
            {"name": "Pet Accessories", "slug": "pet-accessories"},
            {"name": "Pet Toys", "slug": "pet-toys"},
            {"name": "Pet Grooming", "slug": "pet-grooming"},
            {"name": "Pet Care", "slug": "pet-care"},
        ],
    },
    {
        "name": "Music & Musical Instruments",
        "slug": "music-musical-instruments",
        "icon": "bi-music-note-beamed",
        "subcategories": [
            {"name": "Musical Instruments", "slug": "musical-instruments"},
            {"name": "Music Accessories", "slug": "music-accessories"},
            {"name": "Audio Equipment", "slug": "audio-equipment"},
        ],
    },
    {
        "name": "Digital Products",
        "slug": "digital-products",
        "icon": "bi-cloud-download",
        "subcategories": [
            {"name": "E-book", "slug": "e-book"},
            {"name": "Online Templates", "slug": "online-templates"},
            {"name": "Digital Courses", "slug": "digital-courses"},
            {"name": "Software Tools", "slug": "software-tools"},
            {"name": "Digital Guides", "slug": "digital-guides"},
        ],
    },
    {
        "name": "Other / Uncategorized",
        "slug": "other-uncategorized",
        "icon": "bi-tags-fill",
        "subcategories": [
            {"name": "Miscellaneous Products", "slug": "miscellaneous-products"},
            {"name": "Miscellaneous Services", "slug": "miscellaneous-services"},
        ],
    },
]


def ensure_marketplace_categories():
    """Ensure default marketplace categories and subcategories exist."""
    created = False
    allowed_slugs = set()

    def upsert_category(data, parent_id=None, sort_order=0):
        nonlocal created
        category = MarketplaceCategory.query.filter_by(slug=data["slug"]).first()
        if not category:
            category = MarketplaceCategory(
                name=data["name"],
                slug=data["slug"],
                icon=data.get("icon"),
                description=f"{data['name']} services on Kimbela Marketplace",
                is_active=True,
                parent_id=parent_id,
                sort_order=sort_order,
            )
            db.session.add(category)
            created = True
        else:
            category.name = data["name"]
            category.icon = data.get("icon")
            category.is_active = True
            category.parent_id = parent_id
            category.sort_order = sort_order
        return category

    for parent_index, parent in enumerate(DEFAULT_MARKETPLACE_CATEGORIES, start=1):
        allowed_slugs.add(parent["slug"])
        parent_category = upsert_category(parent, parent_id=None, sort_order=parent_index)
        db.session.flush()
        for child_index, child in enumerate(parent.get("subcategories", []), start=1):
            allowed_slugs.add(child["slug"])
            upsert_category(child, parent_id=parent_category.id, sort_order=child_index)

    # Deactivate categories not in the current list
    inactive = (
        MarketplaceCategory.query.filter(
            MarketplaceCategory.slug.notin_(allowed_slugs)
        ).all()
        if allowed_slugs
        else []
    )
    for category in inactive:
        if category.is_active:
            category.is_active = False
            created = True

    if created:
        db.session.commit()


def ensure_marketplace_subscriptions():
    """Create default seller subscription plans if none exist."""
    existing_count = MarketplaceSubscription.query.count()
    if existing_count > 0:
        return

    subscriptions = [
        {
            "name": "Starter",
            "slug": "starter",
            "description": "Perfect for beginners",
            "price_tokens": 200,
            "price_usd": 2.00,
            "max_services": 3,
            "max_images": 5,
            "is_featured": False,
            "can_add_video": False,
            "can_add_digital": True,
            "support_level": "basic",
            "badge_color": "gray",
            "is_popular": False,
            "sort_order": 1,
        },
        {
            "name": "Basic",
            "slug": "basic",
            "description": "Great for growing sellers",
            "price_tokens": 500,
            "price_usd": 5.00,
            "max_services": 10,
            "max_images": 10,
            "is_featured": False,
            "can_add_video": False,
            "can_add_digital": True,
            "support_level": "priority",
            "badge_color": "blue",
            "is_popular": False,
            "sort_order": 2,
        },
        {
            "name": "Pro",
            "slug": "pro",
            "description": "Best for established sellers",
            "price_tokens": 1000,
            "price_usd": 10.00,
            "max_services": 20,
            "max_images": 20,
            "is_featured": True,
            "can_add_video": True,
            "can_add_digital": True,
            "support_level": "priority",
            "badge_color": "purple",
            "is_popular": True,
            "sort_order": 3,
        },
        {
            "name": "Premium",
            "slug": "premium",
            "description": "For power sellers",
            "price_tokens": 1500,
            "price_usd": 15.00,
            "max_services": 0,
            "max_images": 0,
            "is_featured": True,
            "can_add_video": True,
            "can_add_digital": True,
            "support_level": "premium",
            "badge_color": "gold",
            "is_popular": False,
            "sort_order": 4,
        },
    ]

    for sub_data in subscriptions:
        db.session.add(MarketplaceSubscription(**sub_data))

    db.session.commit()


@market.route("/init-data", methods=["GET"])
def init_marketplace_data():
    """Initialize marketplace data (run once)"""
    if not current_user or not current_user.is_super_admin:
        return "Admin access required", 403

    try:
        # Create categories
        ensure_marketplace_categories()
        ensure_marketplace_subscriptions()
        return "Marketplace data initialized successfully with 4 subscription plans!"

    except Exception as e:
        db.session.rollback()
        print(f"Init data error: {e}")
        return f"Error: {e}", 500


# Add these to your marketplace routes


@market.route("/api/categories", methods=["GET"])
def api_categories():
    """Get all marketplace categories"""
    try:
        ensure_marketplace_categories()
        categories = (
            MarketplaceCategory.query.filter_by(is_active=True)
            .order_by("sort_order")
            .all()
        )

        result = []
        for category in categories:
            service_count = MarketplaceService.query.filter_by(
                category_id=category.id, status="active"
            ).count()

            result.append(
                {
                    "id": category.id,
                    "name": category.name,
                    "slug": category.slug,
                    "icon": category.icon,
                    "description": category.description,
                    "service_count": service_count,
                }
            )

        return jsonify({"success": True, "categories": result, "total": len(result)})

    except Exception as e:
        print(f"API categories error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@market.route("/api/featured-sellers", methods=["GET"])
def api_featured_sellers():
    """Get featured sellers"""
    try:
        # Get sellers with featured services
        featured_sellers = get_featured_sellers(6)

        result = []
        for seller in featured_sellers:
            # Get seller stats
            total_services = MarketplaceService.query.filter_by(
                seller_id=seller.id, status="active"
            ).count()

            total_reviews = (
                db.session.query(func.count(MarketplaceReview.id))
                .join(MarketplaceService)
                .filter(MarketplaceService.seller_id == seller.id)
                .scalar()
                or 0
            )

            avg_rating = (
                db.session.query(func.avg(MarketplaceReview.rating))
                .join(MarketplaceService)
                .filter(MarketplaceService.seller_id == seller.id)
                .scalar()
                or 0
            )

            result.append(
                {
                    "id": seller.id,
                    "name": seller.full_name,
                    "first_name": seller.first_name,
                    "avatar": seller.profile_pic
                    or url_for("static", filename="assets/img/default-avatar.png"),
                    "title": seller.occupation or "Professional Seller",
                    "rating": float(avg_rating),
                    "review_count": total_reviews,
                    "total_services": total_services,
                    "is_online": seller.is_online,
                    "bio": (
                        seller.bio[:100] + "..."
                        if seller.bio and len(seller.bio) > 100
                        else seller.bio
                    ),
                }
            )

        return jsonify({"success": True, "sellers": result})

    except Exception as e:
        print(f"API featured sellers error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@market.route("/api/service/<slug>", methods=["GET"])
def api_service_detail(slug):
    """Get service details by slug"""
    try:
        service = MarketplaceService.query.filter_by(slug=slug).first_or_404()

        # Check if service is active
        if not service.is_active and (
            not current_user.is_authenticated or current_user.id != service.seller_id
        ):
            return jsonify({"success": False, "error": "Service not available"}), 404

        # Increment views
        service.views += 1
        db.session.commit()

        # Get seller info
        seller = service.seller

        # Format data
        result = {
            "id": service.id,
            "title": service.title,
            "slug": service.slug,
            "description": service.description,
            "short_description": service.short_description,
            "price": service.price,
            "formatted_price": format_price(service.price),
            "is_free": service.is_free,
            "is_featured": service.is_featured,
            "cover_image": service.cover_image
            or url_for("static", filename="assets/img/default-service.jpg"),
            "service_type": service.service_type,
            "duration": service.duration,
            "availability": service.availability,
            "average_rating": float(service.average_rating),
            "review_count": service.review_count,
            "views": service.views,
            "clicks": service.clicks,
            "created_at": service.created_at.isoformat(),
            "created_at_formatted": service.created_at.strftime("%b %d, %Y"),
            "contact_methods": service.contact_methods_list,
            "gallery_images": service.gallery_images_list,
            "features": service.features_list,
            "whatsapp_number": service.whatsapp_number,
            "whatsapp_link": service.whatsapp_link,
            "phone_number": service.phone_number,
            "email": service.email,
            "category": service.category.name if service.category else "Uncategorized",
            "seller": {
                "id": seller.id,
                "name": seller.full_name,
                "first_name": seller.first_name,
                "avatar": seller.profile_pic
                or url_for("static", filename="assets/img/default-avatar.png"),
                "description": seller.bio
                or f"Professional seller on Kimbela Marketplace",
                "rating": (
                    float(seller.avg_rating) if hasattr(seller, "avg_rating") else 4.5
                ),
                "service_count": MarketplaceService.query.filter_by(
                    seller_id=seller.id, status="active"
                ).count(),
                "phone": seller.phone_number,
            },
        }

        return jsonify({"success": True, "service": result})

    except Exception as e:
        print(f"API service detail error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@market.route("/api/seller/<int:seller_id>", methods=["GET"])
def api_seller_detail(seller_id):
    """Get seller details"""
    try:
        seller = User.query.get_or_404(seller_id)

        # Get seller stats
        total_services = MarketplaceService.query.filter_by(
            seller_id=seller_id, status="active"
        ).count()

        total_reviews = (
            db.session.query(func.count(MarketplaceReview.id))
            .join(MarketplaceService)
            .filter(MarketplaceService.seller_id == seller_id)
            .scalar()
            or 0
        )

        avg_rating = (
            db.session.query(func.avg(MarketplaceReview.rating))
            .join(MarketplaceService)
            .filter(MarketplaceService.seller_id == seller_id)
            .scalar()
            or 0
        )

        total_views = (
            db.session.query(func.sum(MarketplaceService.views))
            .filter_by(seller_id=seller_id)
            .scalar()
            or 0
        )

        # Get seller's other services
        other_services = (
            MarketplaceService.query.filter_by(seller_id=seller_id, status="active")
            .order_by(desc(MarketplaceService.created_at))
            .limit(4)
            .all()
        )

        services_data = []
        for service in other_services:
            services_data.append(
                {
                    "id": service.id,
                    "title": service.title,
                    "slug": service.slug,
                    "cover_image": service.cover_image
                    or url_for("static", filename="assets/img/default-service.jpg"),
                    "average_rating": float(service.average_rating),
                    "review_count": service.review_count,
                    "price": service.price,
                    "formatted_price": format_price(service.price),
                    "is_free": service.is_free,
                }
            )

        result = {
            "id": seller.id,
            "name": seller.full_name,
            "first_name": seller.first_name,
            "avatar": seller.profile_pic
            or url_for("static", filename="assets/img/default-avatar.png"),
            "title": seller.occupation or "Professional Seller",
            "bio": seller.bio,
            "rating": float(avg_rating),
            "review_count": total_reviews,
            "total_services": total_services,
            "total_views": total_views,
            "member_since": seller.created_at.strftime("%b %Y"),
            "phone": seller.phone_number,
            "email": seller.email,
            "services": services_data,
        }

        return jsonify({"success": True, "seller": result})

    except Exception as e:
        print(f"API seller detail error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== SELLER SETTINGS ROUTES ====================


@market.route("/settings", methods=["GET", "POST"])
@login_required
def seller_settings():
    """Seller settings dashboard"""
    if request.method == "GET":
        # Get subscription plans
        subscription_plans = (
            MarketplaceSubscription.query.filter_by(is_active=True)
            .order_by("sort_order")
            .all()
        )

        # Get current subscription
        current_subscription = None
        subscription_expires = None
        for service in current_user.marketplace_services:
            if service.subscription:
                current_subscription = service.subscription
                subscription_expires = service.subscription_expires
                break

        # Get payment history (last 10 payments)
        payment_history = (
            MarketplacePayment.query.filter_by(user_id=current_user.id)
            .order_by(desc(MarketplacePayment.created_at))
            .limit(10)
            .all()
        )

        # Get API keys
        api_keys = current_user.api_keys

        # Get login history (last 20 logins)
        login_history = (
            LoginHistory.query.filter_by(user_id=current_user.id)
            .order_by(desc(LoginHistory.created_at))
            .limit(20)
            .all()
        )

        # Get active sessions
        active_sessions = current_user.active_sessions

        return render_template(
            "seller_settings.html",
            current_subscription=current_subscription,
            subscription_expires=subscription_expires,
            subscription_plans=subscription_plans,
            payment_history=payment_history,
            api_keys=api_keys,
            login_history=login_history,
            active_sessions=active_sessions,
            now=utcnow(),
        )

    # POST: Handle settings updates
    # (Implement based on which form was submitted)


@market.route("/update-profile", methods=["POST"])
@login_required
def update_profile():
    """Update seller profile"""
    try:
        current_user.first_name = request.form.get(
            "first_name", current_user.first_name
        )
        current_user.last_name = request.form.get("last_name", current_user.last_name)
        current_user.phone_number = request.form.get("phone_number")
        current_user.occupation = request.form.get("occupation")
        current_user.location = request.form.get("location")
        current_user.bio = request.form.get("bio")
        current_user.website = request.form.get("website")
        current_user.linkedin_url = request.form.get("linkedin")
        current_user.twitter_url = request.form.get("twitter")
        current_user.facebook_url = request.form.get("facebook")
        current_user.availability = request.form.get("availability")
        current_user.response_time = request.form.get("response_time")

        # Handle profile picture upload
        if "profile_pic" in request.files:
            file = request.files["profile_pic"]
            if file and allowed_file(file.filename):
                image_url = upload_to_cloudinary(file, "profiles")
                if image_url:
                    current_user.profile_pic = image_url

        db.session.commit()
        flash("Profile updated successfully!", "success")

    except Exception as e:
        db.session.rollback()
        print(f"Update profile error: {e}")
        flash("Error updating profile", "danger")

    return redirect(url_for("market.seller_settings") + "#profile")


@market.route("/change-password", methods=["POST"])
@login_required
def change_password():
    """Change password"""
    current_password = request.form.get("current_password")
    new_password = request.form.get("new_password")
    confirm_password = request.form.get("confirm_password")

    if not current_user.check_password(current_password):
        flash("Current password is incorrect", "danger")
    elif new_password != confirm_password:
        flash("New passwords do not match", "danger")
    elif len(new_password) < 8:
        flash("Password must be at least 8 characters", "danger")
    else:
        current_user.set_password(new_password)
        db.session.commit()
        flash("Password changed successfully", "success")

    return redirect(url_for("market.seller_settings") + "#security")


@market.route("/api/generate-api-key", methods=["POST"])
@login_required
def generate_api_key():
    """Generate new API key"""
    try:
        name = request.json.get("name", "API Key")

        # Generate random API key
        import secrets

        api_key = f"kimbela_sk_{secrets.token_urlsafe(32)}"

        # Save to database
        key = ApiKey(user_id=current_user.id, name=name, key=api_key)
        db.session.add(key)
        db.session.commit()

        return jsonify({"success": True, "key": api_key, "id": key.id})

    except Exception as e:
        db.session.rollback()
        print(f"Generate API key error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@market.route("/edit-profile", methods=["GET", "POST"])
@login_required
def edit_seller_profile():
    """Edit seller profile"""
    if request.method == "POST":
        # Handle profile update
        current_user.bio = request.form.get("bio")
        current_user.occupation = request.form.get("occupation")
        current_user.location = request.form.get("location")
        current_user.website = request.form.get("website")

        # Handle profile picture upload
        if "profile_pic" in request.files:
            file = request.files["profile_pic"]
            if file and allowed_file(file.filename):
                image_url = upload_to_cloudinary(file, "profiles")
                if image_url:
                    current_user.profile_pic = image_url

        db.session.commit()
        flash("Profile updated successfully!", "success")
        return redirect(url_for("market.seller_profile", seller_id=current_user.id))

    return render_template("edit_seller_profile.html", now=utcnow())


@market.route("/seller/<int:seller_id>", methods=["GET"])
def seller_profile(seller_id):
    """View seller profile"""
    seller = User.query.get_or_404(seller_id)

    # Get seller's services with pagination
    page = request.args.get("page", 1, type=int)
    per_page = 12

    services_query = MarketplaceService.query.filter_by(
        seller_id=seller_id, status="active"
    ).order_by(desc(MarketplaceService.created_at))

    services = services_query.paginate(page=page, per_page=per_page, error_out=False)

    # Get seller stats
    total_services = services_query.count()

    total_reviews = (
        MarketplaceReview.query.join(MarketplaceService)
        .filter(
            MarketplaceService.seller_id == seller_id,
            MarketplaceReview.status == "approved",
        )
        .count()
    )

    # Calculate average rating
    avg_rating = (
        db.session.query(func.avg(MarketplaceReview.rating))
        .join(MarketplaceService)
        .filter(
            MarketplaceService.seller_id == seller_id,
            MarketplaceReview.status == "approved",
        )
        .scalar()
        or 0
    )

    # Get total views
    total_views = (
        db.session.query(func.sum(MarketplaceService.views))
        .filter_by(seller_id=seller_id)
        .scalar()
        or 0
    )

    # Get recent reviews
    reviews = (
        MarketplaceReview.query.join(MarketplaceService)
        .filter(
            MarketplaceService.seller_id == seller_id,
            MarketplaceReview.status == "approved",
        )
        .order_by(desc(MarketplaceReview.created_at))
        .limit(5)
        .all()
    )

    # Currency symbols for display
    currency_symbols = {
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "KES": "KSh",
        "NGN": "₦",
        "GHS": "GH₵",
        "ZAR": "R",
    }

    return render_template(
        "seller_profile.html",
        seller=seller,
        services=services,
        total_services=total_services,
        total_reviews=total_reviews,
        avg_rating=round(avg_rating, 1),
        total_views=total_views,
        reviews=reviews,
        currency_symbols=currency_symbols,
        now=utcnow(),
    )


@market.route("/remove-profile-picture", methods=["POST"])
@login_required
def remove_profile_picture():
    """Remove profile picture"""
    try:
        current_user.profile_pic = None
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== API ENDPOINTS FOR DASHBOARD ====================
# ==================== API ENDPOINTS FOR DASHBOARD ====================
@market.route("/api/dashboard/stats", methods=["GET"])
@login_required
@cache_response(timeout=300, key_prefix="dashboard_stats_")
def get_dashboard_stats():
    """Get real-time dashboard statistics"""
    try:
        # Get time range filters
        time_filter = request.args.get("time_filter", "all")  # week, month, year, all

        # Calculate time range
        now = utcnow()
        if time_filter == "week":
            start_date = now - timedelta(days=7)
        elif time_filter == "month":
            start_date = now - timedelta(days=30)
        elif time_filter == "year":
            start_date = now - timedelta(days=365)
        else:
            start_date = None

        # Base query
        base_filter = MarketplaceService.seller_id == current_user.id

        # Total services
        total_services = MarketplaceService.query.filter(base_filter).count()

        # Active services
        active_services = MarketplaceService.query.filter(
            base_filter, MarketplaceService.status == "active"
        ).count()

        # Views this period
        views_query = db.session.query(func.sum(MarketplaceService.views))
        if start_date:
            views_query = views_query.filter(
                MarketplaceService.updated_at >= start_date
            )
        total_views = views_query.filter(base_filter).scalar() or 0

        # Clicks this period (count clicks from MarketplaceClick)
        clicks_query = db.session.query(func.count(MarketplaceClick.id))
        if start_date:
            clicks_query = clicks_query.filter(
                MarketplaceClick.created_at >= start_date
            )
        total_clicks = (
            clicks_query.join(
                MarketplaceService, MarketplaceClick.service_id == MarketplaceService.id
            )
            .filter(base_filter)
            .scalar()
            or 0
        )

        # Earnings this period
        earnings_query = db.session.query(func.sum(MarketplaceService.earnings))
        if start_date:
            earnings_query = earnings_query.filter(
                MarketplaceService.updated_at >= start_date
            )
        total_earnings = earnings_query.filter(base_filter).scalar() or 0

        # Average rating
        avg_rating = (
            db.session.query(func.avg(MarketplaceReview.rating))
            .join(MarketplaceService)
            .filter(
                MarketplaceService.seller_id == current_user.id,
                MarketplaceReview.status == "approved",
            )
            .scalar()
            or 0
        )

        # Total reviews
        total_reviews = (
            db.session.query(func.count(MarketplaceReview.id))
            .join(MarketplaceService)
            .filter(
                MarketplaceService.seller_id == current_user.id,
                MarketplaceReview.status == "approved",
            )
            .scalar()
            or 0
        )

        # Chart data (last 30 days)
        chart_days = 30
        chart_data = []
        for i in range(chart_days):
            date = now - timedelta(days=chart_days - i - 1)
            date_start = datetime(date.year, date.month, date.day, 0, 0, 0)
            date_end = datetime(date.year, date.month, date.day, 23, 59, 59)

            # Views for this day
            day_views = (
                db.session.query(func.sum(MarketplaceService.views))
                .filter(
                    base_filter,
                    MarketplaceService.updated_at.between(date_start, date_end),
                )
                .scalar()
                or 0
            )

            # Earnings for this day
            day_earnings = (
                db.session.query(func.sum(MarketplaceService.earnings))
                .filter(
                    base_filter,
                    MarketplaceService.updated_at.between(date_start, date_end),
                )
                .scalar()
                or 0
            )

            # Clicks for this day
            day_clicks = (
                db.session.query(func.count(MarketplaceClick.id))
                .join(MarketplaceService)
                .filter(
                    base_filter,
                    MarketplaceClick.created_at.between(date_start, date_end),
                )
                .scalar()
                or 0
            )

            chart_data.append(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "views": int(day_views),
                    "clicks": int(day_clicks),
                    "earnings": float(day_earnings),
                }
            )

        # Service status breakdown
        service_stats = {}
        statuses = ["active", "pending", "draft", "paused"]
        for status in statuses:
            count = MarketplaceService.query.filter(
                base_filter, MarketplaceService.status == status
            ).count()
            service_stats[status] = count

        return jsonify(
            {
                "success": True,
                "stats": {
                    "total_services": total_services,
                    "active_services": active_services,
                    "total_views": int(total_views),
                    "total_clicks": int(total_clicks),
                    "total_earnings": float(total_earnings),
                    "average_rating": round(float(avg_rating), 1),
                    "total_reviews": int(total_reviews),
                },
                "service_stats": service_stats,
                "chart_data": chart_data,
                "time_filter": time_filter,
            }
        )

    except Exception as e:
        current_app.logger.error(f"Dashboard stats error: {str(e)}")
        return jsonify({"success": False, "error": "Failed to load statistics"}), 500


@market.route("/api/dashboard/services", methods=["GET"])
@login_required
@cache_response(timeout=180, key_prefix="dashboard_services_")
def get_dashboard_services():
    """Get paginated services for dashboard"""
    try:
        page = request.args.get("page", 1, type=int)
        per_page = 10
        status_filter = request.args.get("status", "all")
        search_query = request.args.get("search", "")

        # Build query
        query = MarketplaceService.query.filter_by(seller_id=current_user.id)

        # Apply filters
        if status_filter != "all":
            query = query.filter_by(status=status_filter)

        if search_query:
            query = query.filter(
                or_(
                    MarketplaceService.title.ilike(f"%{search_query}%"),
                    MarketplaceService.description.ilike(f"%{search_query}%"),
                    MarketplaceService.short_description.ilike(f"%{search_query}%"),
                )
            )

        # Order by created date
        query = query.order_by(desc(MarketplaceService.created_at))

        # Paginate
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        # Prepare response
        services_data = []
        for service in pagination.items:
            services_data.append(
                {
                    "id": service.id,
                    "title": service.title,
                    "slug": service.slug,
                    "short_description": service.short_description,
                    "price": float(service.price) if service.price else 0,
                    "currency": service.currency or "KES",
                    "is_free": service.is_free,
                    "status": service.status,
                    "views": service.views or 0,
                    "clicks": service.clicks or 0,
                    "earnings": float(service.earnings) if service.earnings else 0,
                    "average_rating": (
                        float(service.average_rating) if service.average_rating else 0
                    ),
                    "review_count": service.review_count or 0,
                    "cover_image": service.cover_image
                    or url_for("static", filename="assets/img/default-service.jpg"),
                    "created_at": service.created_at.strftime("%Y-%m-%d"),
                    "updated_at": (
                        service.updated_at.strftime("%Y-%m-%d")
                        if service.updated_at
                        else ""
                    ),
                    "category": (
                        service.category.name if service.category else "Uncategorized"
                    ),
                }
            )

        return jsonify(
            {
                "success": True,
                "services": services_data,
                "pagination": {
                    "page": pagination.page,
                    "pages": pagination.pages,
                    "total": pagination.total,
                    "has_next": pagination.has_next,
                    "has_prev": pagination.has_prev,
                },
            }
        )

    except Exception as e:
        current_app.logger.error(f"Dashboard services error: {str(e)}")
        return jsonify({"success": False, "error": "Failed to load services"}), 500


@market.route("/api/dashboard/reviews", methods=["GET"])
@login_required
@cache_response(timeout=120, key_prefix="dashboard_reviews_")
def get_dashboard_reviews():
    """Get seller reviews"""
    try:
        page = request.args.get("page", 1, type=int)
        per_page = 5

        reviews_query = (
            MarketplaceReview.query.join(MarketplaceService)
            .filter(
                MarketplaceService.seller_id == current_user.id,
                MarketplaceReview.status == "approved",
            )
            .order_by(desc(MarketplaceReview.created_at))
        )

        pagination = reviews_query.paginate(
            page=page, per_page=per_page, error_out=False
        )

        reviews_data = []
        for review in pagination.items:
            customer = review.customer
            reviews_data.append(
                {
                    "id": review.id,
                    "rating": float(review.rating),
                    "comment": review.comment,
                    "created_at": review.created_at.strftime("%b %d, %Y"),
                    "customer_name": customer.full_name if customer else "Anonymous",
                    "customer_avatar": (
                        customer.profile_pic
                        if customer and customer.profile_pic
                        else url_for("static", filename="assets/img/default-avatar.png")
                    ),
                    "service_title": (
                        review.service.title if review.service else "Unknown Service"
                    ),
                    "service_slug": review.service.slug if review.service else "",
                }
            )

        return jsonify(
            {
                "success": True,
                "reviews": reviews_data,
                "pagination": {
                    "page": pagination.page,
                    "pages": pagination.pages,
                    "total": pagination.total,
                },
            }
        )

    except Exception as e:
        current_app.logger.error(f"Dashboard reviews error: {str(e)}")
        return jsonify({"success": False, "error": "Failed to load reviews"}), 500


@market.route("/api/services/<int:service_id>/download")
def download_service_file(service_id):
    """Simple redirect to Cloudinary file"""
    try:
        service = MarketplaceService.query.get_or_404(service_id)

        if not service.digital_file:
            flash("No digital file available", "warning")
            return redirect(url_for("market.service_detail", slug=service.slug))

        # Check if it's a preview request
        is_preview = request.args.get("preview") == "true"

        # Increment download count for actual downloads
        if not is_preview:
            service.download_count = (service.download_count or 0) + 1
            db.session.commit()

        # Simply redirect to the Cloudinary URL
        # Let the browser handle the download
        return redirect(service.digital_file)

    except Exception as e:
        print(f"Download error: {str(e)}")
        flash("Error downloading file", "error")
        return redirect(url_for("market.service_detail", slug=service.slug))


import cloudinary.uploader


def upload_service_file(file, service_id, folder="marketplace/services"):
    """Upload a file to Cloudinary for a marketplace service"""
    try:
        # Upload to Cloudinary
        result = cloudinary.uploader.upload(
            file,
            folder=folder,
            resource_type="auto",  # Auto-detect type
            public_id=f"service_{service_id}",
            overwrite=True,
            # Additional options for security
            type="upload",
            access_mode="authenticated",  # Make files private
        )

        # Store in database
        service = MarketplaceService.query.get(service_id)
        if service:
            service.digital_file = result["secure_url"]
            service.cloudinary_public_id = result["public_id"]
            service.file_name = file.filename if hasattr(file, "filename") else "file"
            service.file_size = result.get("bytes", 0)
            service.file_type = result.get("resource_type", "raw")
            db.session.commit()

        return result

    except Exception as e:
        print(f"Upload error: {e}")
        return None


@market.route("/download/<int:service_id>")
def download_file(service_id):
    """WORKING download route for both free and paid files"""
    try:
        service = MarketplaceService.query.get_or_404(service_id)

        if not service.digital_file:
            flash("No file available for download", "warning")
            return redirect(url_for("market.service_detail", slug=service.slug))

        # Check if service is free
        if service.price and service.price > 0 and not service.is_free:
            # Paid service - check if user has purchased
            if not current_user.is_authenticated:
                flash("Please login to download this file", "warning")
                return redirect(url_for("auth.login", next=request.url))

            # TODO: Add purchase verification logic here
            # For now, we'll allow download but you should implement this
            # if not has_purchased(current_user, service):
            #     flash("Please purchase this service to download the file", "warning")
            #     return redirect(url_for('market.service_detail', slug=service.slug))

        url = service.digital_file
        print(f"Downloading from URL: {url}")

        # Check if it's a Cloudinary URL
        if "cloudinary.com" in url:
            # Parse the Cloudinary URL
            parsed = parse_cloudinary_url(url)
            if parsed:
                print(f"Parsed Cloudinary info: {parsed}")

                # For PDF files, we need to use raw resource type
                if ".pdf" in url.lower():
                    # Extract filename
                    filename = (
                        service.file_name or parsed.get("filename") or "document.pdf"
                    )

                    # Build the correct URL for PDF download
                    # Cloudinary PDFs should use raw/upload, not image/upload
                    if "/image/upload/" in url:
                        # Fix: Change to raw resource type for PDFs
                        cloud_name = (
                            parsed["cloud_name"] or cloudinary.config().cloud_name
                        )
                        public_id = parsed["public_id"]

                        # For PDFs, remove fl_attachment parameter - it causes 401 errors
                        # Build direct download URL
                        download_url = f"https://res.cloudinary.com/{cloud_name}/raw/upload/{public_id}"

                        print(f"PDF download URL: {download_url}")

                        # Test the URL first
                        try:
                            test_response = requests.head(download_url, timeout=5)
                            if test_response.status_code == 200:
                                url = download_url
                                print(f"✅ Using corrected PDF URL: {download_url}")
                            else:
                                print(
                                    f"⚠️ Corrected URL returned {test_response.status_code}, using original"
                                )
                        except Exception as e:
                            print(f"⚠️ Error testing corrected URL: {e}, using original")

                    # For PDFs, use simple redirect without fl_attachment
                    # This should work for publicly accessible files

                    # Increment download count
                    service.download_count = (service.download_count or 0) + 1
                    db.session.commit()

                    # Simply redirect to the URL
                    # Browser will handle PDF display/download
                    return redirect(url)

        # For non-PDF files or if PDF download failed
        # Extract filename
        filename = service.file_name or url.split("/")[-1].split("?")[0]

        # Increment download count
        service.download_count = (service.download_count or 0) + 1
        db.session.commit()

        # For non-PDF files, use direct redirect
        return redirect(url)

    except Exception as e:
        print(f"Download error: {str(e)}")
        traceback.print_exc()
        flash("Error downloading file. Please try again.", "error")
        return redirect(url_for("market.service_detail", slug=service.slug))


# Add these routes to market.py


@market.route("/check-subscription", methods=["GET"])
@login_required
def check_subscription():
    """Check user's subscription status"""
    try:
        payments_enabled = marketplace_payments_enabled()
        # Check if user has an active subscription
        has_subscription = (
            current_user.has_active_marketplace_subscription if payments_enabled else True
        )
        is_featured = current_user.is_marketplace_featured

        # Check if user's services need attention
        services = MarketplaceService.query.filter_by(seller_id=current_user.id).all()
        has_services = len(services) > 0

        # Determine if we should show subscription modal
        show_modal = False
        reason = None

        if payments_enabled and not has_subscription:
            if has_services:
                show_modal = True
                reason = "no_subscription"
            else:
                show_modal = False
        elif payments_enabled and (
            current_user.marketplace_subscription_expires
            and current_user.marketplace_subscription_expires - utcnow()
            < timedelta(days=7)
        ):
            show_modal = True
            reason = "expiring_soon"

        return jsonify(
            {
                "success": True,
                "has_subscription": has_subscription,
                "payments_enabled": payments_enabled,
                "is_featured": is_featured,
                "subscription_tier": current_user.marketplace_subscription_tier,
                "expires_at": (
                    current_user.marketplace_subscription_expires.isoformat()
                    if current_user.marketplace_subscription_expires
                    else None
                ),
                "show_modal": show_modal,
                "reason": reason,
                "has_services": has_services,
            }
        )

    except Exception as e:
        print(f"Error checking subscription: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@market.route("/subscription-plans", methods=["GET"])
@login_required
def subscription_plans():
    """Get available subscription plans"""
    try:
        plans = (
            MarketplaceSubscriptionPlan.query.filter_by(is_active=True)
            .order_by("sort_order")
            .all()
        )

        plans_data = []
        for plan in plans:
            plans_data.append(
                {
                    "id": plan.id,
                    "name": plan.name,
                    "slug": plan.slug,
                    "description": plan.description,
                    "price_usd": plan.price,
                    "price_ngn": plan.price_ngn,
                    "duration_days": plan.duration_days,
                    "features": plan.features_list,
                    "is_featured": plan.is_featured,
                    "max_services": plan.max_services,
                }
            )

        return jsonify({"success": True, "plans": plans_data})

    except Exception as e:
        print(f"Error getting plans: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@market.route("/subscribe", methods=["GET", "POST"])
@login_required
def subscribe():
    """Subscribe to a marketplace plan"""
    if request.method == "GET":
        ensure_marketplace_subscriptions()
        # Get all active plans
        plans = (
            MarketplaceSubscription.query.filter_by(is_active=True)
            .order_by("sort_order")
            .all()
        )

        # Get user's current subscription
        current_plan = None
        if current_user.marketplace_subscription_id:
            current_plan = MarketplaceSubscription.query.get(
                current_user.marketplace_subscription_id
            )

        return render_template(
            "subscribe.html",
            plans=plans,
            current_plan=current_plan,
            current_user=current_user,
            now=utcnow(),
        )

    # POST: Process subscription
    try:
        plan_id = request.form.get("plan_id")
        payment_method = request.form.get("payment_method", "flutterwave")

        # Validate plan
        plan = MarketplaceSubscriptionPlan.query.get_or_404(plan_id)
        if not plan.is_active:
            flash("This plan is not available", "danger")
            return redirect(url_for("market.subscribe"))

        # Check if user already has this plan
        if (
            current_user.marketplace_subscription_id == plan.id
            and current_user.has_active_marketplace_subscription
        ):
            flash("You already have an active subscription to this plan", "info")
            return redirect(url_for("market.seller_dashboard"))

        # Calculate expiration date
        expires_at = utcnow() + timedelta(days=plan.duration_days)

        # Store subscription info in session for payment processing
        session["subscription_data"] = {
            "plan_id": plan.id,
            "plan_name": plan.name,
            "price_usd": plan.price,
            "price_ngn": plan.price_ngn,
            "duration_days": plan.duration_days,
            "expires_at": expires_at.isoformat(),
            "user_id": current_user.id,
        }

        # Redirect to payment
        return redirect(url_for("market.subscription_payment"))

    except Exception as e:
        print(f"Error subscribing: {e}")
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for("market.subscribe"))


@market.route("/subscription-payment", methods=["GET", "POST"])
@login_required
def subscription_payment():
    """Handle subscription payment"""
    if "subscription_data" not in session:
        flash("No subscription selected", "warning")
        return redirect(url_for("market.subscribe"))

    subscription_data = session["subscription_data"]

    if request.method == "GET":
        return render_template(
            "subscription_payment.html",
            subscription_data=subscription_data,
            current_user=current_user,
        )

    # POST: Process payment
    try:
        # Generate payment reference
        tx_ref = f"KIMBELA-SUB-{int(time.time())}-{current_user.id}"

        # Create payment record
        payment = MarketplacePayment(
            user_id=current_user.id,
            amount=subscription_data["price_usd"],
            currency="USD",
            gateway="flutterwave",
            gateway_reference=tx_ref,
            status="pending",
            description=f"Marketplace subscription: {subscription_data['plan_name']} for {subscription_data['duration_days']} days",
        )
        db.session.add(payment)
        db.session.commit()

        # Prepare Flutterwave payment data
        payment_data = {
            "tx_ref": tx_ref,
            "amount": str(subscription_data["price_usd"]),
            "currency": "USD",
            "redirect_url": url_for("market.subscription_callback", _external=True),
            "customer": {
                "email": current_user.email,
                "name": current_user.full_name,
                "phone_number": current_user.phone_number,
            },
            "customizations": {
                "title": "Kimbela Marketplace Subscription",
                "description": f"Subscription: {subscription_data['plan_name']}",
                "logo": url_for(
                    "static", filename="assets/img/kim.png", _external=True
                ),
            },
            "meta": {
                "plan_id": subscription_data["plan_id"],
                "user_id": current_user.id,
                "payment_id": payment.id,
                "type": "subscription",
            },
        }

        return jsonify(
            {
                "success": True,
                "payment_data": payment_data,
                "flutterwave_public_key": current_app.config.get(
                    "FLUTTERWAVE_PUBLIC_KEY"
                ),
            }
        )

    except Exception as e:
        db.session.rollback()
        print(f"Error initiating subscription payment: {e}")
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for("market.subscription_payment"))


@market.route("/init-subscription-plans", methods=["GET"])
def init_subscription_plans():
    """Initialize marketplace subscription plans"""
    try:
        # Check if user is admin
        if not current_user.is_authenticated or not current_user.is_super_admin:
            return "Admin access required", 403

        # Check if plans already exist
        existing_plans = MarketplaceSubscriptionPlan.query.count()
        if existing_plans > 0:
            # Optional: Delete existing plans to recreate
            # MarketplaceSubscriptionPlan.query.delete()
            # db.session.commit()
            # print("Deleted existing plans")
            return f"Plans already exist ({existing_plans} plans found).", 200

        # Create subscription plans
        plans = [
            {
                "name": "Basic Plan",
                "slug": "basic",
                "description": "Perfect for beginners",
                "price": 9.99,
                "price_ngn": 5000.00,
                "duration_days": 30,
                "max_services": 3,
                "priority_visibility": False,
                "features": json.dumps(
                    ["3 service listings", "5 images per service", "Email support"]
                ),
                "is_featured": False,
                "is_active": True,
                "sort_order": 1,
            },
            {
                "name": "Pro Plan",
                "slug": "pro",
                "description": "Best for growing businesses",
                "price": 19.99,
                "price_ngn": 10000.00,
                "duration_days": 30,
                "max_services": 10,
                "priority_visibility": True,
                "features": json.dumps(
                    [
                        "10 service listings",
                        "10 images per service",
                        "Featured listing priority",
                        "Video uploads enabled",
                        "Priority support",
                    ]
                ),
                "is_featured": True,
                "is_active": True,
                "sort_order": 2,
            },
            {
                "name": "Enterprise Plan",
                "slug": "enterprise",
                "description": "For professional sellers",
                "price": 39.99,
                "price_ngn": 20000.00,
                "duration_days": 30,
                "max_services": 0,  # 0 means unlimited
                "priority_visibility": True,
                "features": json.dumps(
                    [
                        "Unlimited service listings",
                        "20 images per service",
                        "Premium featured priority",
                        "Video uploads enabled",
                        "Digital product sales",
                        "24/7 Premium support",
                    ]
                ),
                "is_featured": True,
                "is_active": True,
                "sort_order": 3,
            },
        ]

        created_count = 0
        for plan_data in plans:
            plan = MarketplaceSubscriptionPlan(**plan_data)
            db.session.add(plan)
            created_count += 1

        db.session.commit()

        return f"✅ Successfully created {created_count} subscription plans!", 200

    except Exception as e:
        db.session.rollback()
        print(f"❌ Error creating plans: {e}")
        import traceback

        print(traceback.format_exc())
        return f"Error: {e}", 500


# Add to your market.py routes (temporarily for debugging)


@market.route("/debug-payment", methods=["GET"])
@login_required
def debug_payment():
    """Debug payment service initialization"""
    _require_debug_access()
    try:
        result = {}

        # Check if payment_service exists on current_app
        if hasattr(current_app, "payment_service"):
            service = current_app.payment_service
            result["payment_service_available"] = "✅ Available"
            result["payment_service_type"] = type(service).__name__

            # Check the child services
            if hasattr(service, "matchmaking_service"):
                result["matchmaking_service"] = "✅ Available"
                if hasattr(service.matchmaking_service, "flutterwave_public_key"):
                    result["matchmaking_public_key"] = (
                        service.matchmaking_service.flutterwave_public_key is not None
                    )
                    if service.matchmaking_service.flutterwave_public_key:
                        result["matchmaking_public_key_preview"] = (
                            service.matchmaking_service.flutterwave_public_key[:20]
                            + "..."
                        )

            if hasattr(service, "marketplace_service"):
                result["marketplace_service"] = "✅ Available"
                if hasattr(service.marketplace_service, "flutterwave_public_key"):
                    result["marketplace_public_key"] = (
                        service.marketplace_service.flutterwave_public_key is not None
                    )
                    if service.marketplace_service.flutterwave_public_key:
                        result["marketplace_public_key_preview"] = (
                            service.marketplace_service.flutterwave_public_key[:20]
                            + "..."
                        )

            if hasattr(service, "ad_service"):
                result["ad_service"] = "✅ Available"
        else:
            result["payment_service_available"] = "❌ Not available"

        # Direct import check
        from payments.payment_service import PaymentService

        direct_service = PaymentService()
        result["direct_import"] = "✅ Available"
        result["direct_service_type"] = type(direct_service).__name__

        # Check child services on direct import
        if hasattr(direct_service, "marketplace_service"):
            if hasattr(direct_service.marketplace_service, "flutterwave_public_key"):
                result["direct_marketplace_public_key"] = (
                    direct_service.marketplace_service.flutterwave_public_key
                    is not None
                )

        return jsonify(
            {
                "success": True,
                "debug_info": result,
                "env_vars": {
                    "FLW_PUBLIC_KEY_set": os.getenv("FLW_PUBLIC_KEY") is not None,
                    "FLW_SECRET_KEY_set": os.getenv("FLW_SECRET_KEY") is not None,
                    "PUBLIC_KEY_set": os.getenv("PUBLIC_KEY") is not None,
                    "SECRET_KEY_set": os.getenv("SECRET_KEY") is not None,
                },
            }
        )

    except Exception as e:
        return (
            jsonify(
                {"success": False, "error": str(e), "traceback": traceback.format_exc()}
            ),
            500,
        )


@market.route("/become-seller", methods=["POST"])
@login_required
def become_seller():
    """Handle subscription payment"""
    try:
        print(f"🟡 [BECOME-SELLER] POST request received")

        # Validate request
        if not request.is_json:
            return jsonify({"success": False, "error": "Request must be JSON"}), 400

        data = request.get_json()
        plan_id = data.get("plan_id")

        if not plan_id:
            return jsonify({"success": False, "error": "No plan selected"}), 400

        # Get plan
        plan = MarketplaceSubscription.query.get(plan_id)
        if not plan:
            print(f"🔴 [BECOME-SELLER] Plan not found: {plan_id}")
            return jsonify({"success": False, "error": "Invalid plan selected"}), 404

        print(f"🟡 [BECOME-SELLER] Found plan: {plan.name}, Price: ${plan.price_usd}")

        # Check if user already has subscription
        if current_user.marketplace_subscription_status == "active":
            print(f"🔴 [BECOME-SELLER] User already has active subscription")
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "You already have an active subscription",
                    }
                ),
                400,
            )

        # Get marketplace service
        from payments.payment_service import MarketplacePaymentService

        marketplace_service = MarketplacePaymentService()

        # Check if keys are set
        if not marketplace_service.flutterwave_secret_key:
            print(f"🔴 [BECOME-SELLER] Flutterwave secret key is not set")
            return (
                jsonify(
                    {"success": False, "error": "Payment gateway configuration error"}
                ),
                500,
            )

        print(f"🟡 [BECOME-SELLER] Creating payment with Flutterwave...")
        print(
            f"🟡 [BECOME-SELLER] Secret Key preview: {marketplace_service.flutterwave_secret_key[:20]}..."
        )

        # Create payment
        result = marketplace_service.create_marketplace_payment(
            user=current_user, plan=plan, currency="USD"
        )

        print(f"🟡 [BECOME-SELLER] Payment result: {result}")

        if result.get("success"):
            return jsonify(
                {
                    "success": True,
                    "payment_url": result["payment_url"],
                    "payment_id": result.get(
                        "payment_id"
                    ),  # Now returns marketplace_payment.id
                    "gateway_reference": result.get("gateway_reference"),
                    "message": result.get("message", "Payment initiated successfully"),
                }
            )
        else:
            error_msg = result.get("error", "Payment initiation failed")
            print(f"🔴 [BECOME-SELLER] Payment failed: {error_msg}")
            return jsonify({"success": False, "error": error_msg}), 400

    except Exception as e:
        print(f"🔴 [BECOME-SELLER] Unhandled exception: {str(e)}")
        import traceback

        print(f"🔴 [BECOME-SELLER] Traceback:\n{traceback.format_exc()}")

        return (
            jsonify({"success": False, "error": f"Internal server error: {str(e)}"}),
            500,
        )


def create_default_plans():
    """Create default subscription plans if none exist"""
    try:
        plans = [
            MarketplaceSubscriptionPlan(
                name="Basic Plan",
                slug="basic",
                description="Perfect for beginners",
                price=9.99,
                price_ngn=5000.00,
                duration_days=30,
                max_services=3,
                priority_visibility=False,
                features=json.dumps(
                    ["3 service listings", "5 images per service", "Email support"]
                ),
                is_featured=False,
                is_active=True,
                sort_order=1,
            ),
            MarketplaceSubscriptionPlan(
                name="Pro Plan",
                slug="pro",
                description="Best for growing businesses",
                price=19.99,
                price_ngn=10000.00,
                duration_days=30,
                max_services=10,
                priority_visibility=True,
                features=json.dumps(
                    [
                        "10 service listings",
                        "10 images per service",
                        "Featured listing priority",
                        "Video uploads enabled",
                        "Priority support",
                    ]
                ),
                is_featured=True,
                is_active=True,
                sort_order=2,
            ),
            MarketplaceSubscriptionPlan(
                name="Enterprise Plan",
                slug="enterprise",
                description="For professional sellers",
                price=39.99,
                price_ngn=20000.00,
                duration_days=30,
                max_services=0,  # Unlimited
                priority_visibility=True,
                features=json.dumps(
                    [
                        "Unlimited service listings",
                        "20 images per service",
                        "Premium featured priority",
                        "Video uploads enabled",
                        "Digital product sales",
                        "24/7 Premium support",
                    ]
                ),
                is_featured=True,
                is_active=True,
                sort_order=3,
            ),
        ]

        for plan in plans:
            db.session.add(plan)

        db.session.commit()
        print(f"✅ Created {len(plans)} default subscription plans")

    except Exception as e:
        db.session.rollback()
        print(f"❌ Error creating default plans: {e}")


# Add this callback route for Flutterwave webhook:
@market.route("/marketplace-payment-callback", methods=["POST"])
def marketplace_payment_callback():
    """Handle Flutterwave webhook for marketplace payments"""
    try:
        # Get the webhook data
        webhook_data = request.get_json()

        print(
            f"🟡 [MARKETPLACE WEBHOOK] Received: {json.dumps(webhook_data, indent=2)}"
        )

        # Verify the event is from Flutterwave
        if request.headers.get("verif-hash"):
            # Verify the webhook signature
            # You should implement this based on your Flutterwave dashboard settings
            pass

        # Get transaction details
        event_type = webhook_data.get("event")
        data = webhook_data.get("data", {})

        if event_type == "charge.completed":
            # Payment was successful
            tx_ref = data.get("tx_ref")
            transaction_id = data.get("id")

            # Find the transaction
            transaction = PaymentTransaction.query.filter_by(
                gateway_reference=tx_ref
            ).first()

            if (
                transaction
                and transaction.transaction_type == "marketplace_subscription"
            ):
                # Verify the payment with Flutterwave
                verification = (
                    payment_service.marketplace_service.verify_flutterwave_payment(
                        transaction_id
                    )
                )

                if verification["success"]:
                    # Handle successful payment
                    payment_service.handle_marketplace_payment_success(
                        transaction.id, verification["data"]
                    )

                    return jsonify({"status": "success"}), 200

        return jsonify({"status": "ignored"}), 200

    except Exception as e:
        print(f"🔴 [MARKETPLACE WEBHOOK] Error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


# Update the subscription_callback route:


@market.route("/subscription-callback", methods=["GET"])
@login_required
def subscription_callback():
    """Handle Flutterwave payment callback for subscriptions"""
    try:
        tx_ref = request.args.get("tx_ref")
        transaction_id = request.args.get("transaction_id")
        status = request.args.get("status")

        print(f"🟡 [SUBSCRIPTION CALLBACK] Processing callback")

        if not tx_ref:
            flash("Invalid callback parameters", "danger")
            return redirect(url_for("market.become_seller"))

        # Find the marketplace payment
        marketplace_payment = MarketplacePayment.query.filter_by(
            gateway_reference=tx_ref
        ).first()

        if not marketplace_payment:
            flash("Payment record not found", "danger")
            return redirect(url_for("market.become_seller"))

        if marketplace_payment.user_id != current_user.id:
            flash("Unauthorized access", "danger")
            return redirect(url_for("market.seller_dashboard"))

        # Get payment service
        from payments.payment_service import MarketplacePaymentService

        payment_service = MarketplacePaymentService()

        if status == "successful" and transaction_id:
            print(f"🟡 [CALLBACK] Payment successful, verifying...")

            # Verify the payment
            verification = payment_service.verify_flutterwave_payment(transaction_id)

            if verification["success"]:
                print(f"✅ [CALLBACK] Payment verified")

                # Handle successful payment
                success = payment_service.handle_marketplace_payment_success(
                    marketplace_payment, verification["data"]
                )

                if success:
                    flash(
                        "🎉 Subscription activated successfully! Check your email for confirmation.",
                        "success",
                    )
                else:
                    flash(
                        "Subscription activated but there was an issue sending confirmation email.",
                        "warning",
                    )
            else:
                # Handle verification failure
                payment_service.handle_marketplace_payment_failure(
                    marketplace_payment,
                    verification.get("data", {"message": "Verification failed"}),
                )
                flash("Payment verification failed. Please contact support.", "danger")
        else:
            # Handle payment failure
            error_data = {
                "status": status or "cancelled",
                "message": "Payment was not completed",
            }
            payment_service.handle_marketplace_payment_failure(
                marketplace_payment, error_data
            )
            flash(
                "Payment was not completed. Please try again. Check your email for details.",
                "warning",
            )

        return redirect(url_for("market.seller_dashboard"))

    except Exception as e:
        print(f"🔴 [CALLBACK] Error: {str(e)}")
        flash("An error occurred processing your payment", "danger")
        return redirect(url_for("market.seller_dashboard"))


@market.route("/test-marketplace-payment-db", methods=["GET"])
@login_required
def test_marketplace_payment_db():
    """Test marketplace payment database operations"""
    try:
        # Get a plan
        plan = MarketplaceSubscriptionPlan.query.first()

        # Create a test marketplace payment
        test_payment = MarketplacePayment(
            user_id=current_user.id,
            subscription_id=plan.id if plan else 1,
            amount=9.99,
            currency="USD",
            tokens_paid=999,
            gateway="test",
            gateway_reference=f"TEST_{int(time.time())}",
            gateway_status="test",
            status="completed",
            description="Test payment",
            start_date=utcnow(),
            end_date=utcnow() + timedelta(days=30),
        )

        db.session.add(test_payment)
        db.session.commit()

        return jsonify(
            {
                "success": True,
                "message": "MarketplacePayment created successfully",
                "payment_id": test_payment.id,
            }
        )

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@market.route("/debug-subscription-status", methods=["GET"])
@login_required
def debug_subscription_status():
    """Debug subscription status for current user"""
    _require_debug_access()
    try:
        user = current_user

        # Get all subscription-related fields
        subscription_info = {
            "user_id": user.id,
            "email": user.email,
            "marketplace_subscription_status": user.marketplace_subscription_status,
            "marketplace_subscription_id": user.marketplace_subscription_id,
            "marketplace_subscription_expires": (
                user.marketplace_subscription_expires.isoformat()
                if user.marketplace_subscription_expires
                else None
            ),
            "marketplace_featured_until": (
                user.marketplace_featured_until.isoformat()
                if user.marketplace_featured_until
                else None
            ),
            "marketplace_subscription_tier": user.marketplace_subscription_tier,
            "now": utcnow().isoformat(),
        }

        # Check if subscription is active
        is_active = user.marketplace_subscription_status == "active"
        is_expired = False

        if user.marketplace_subscription_expires:
            is_expired = utcnow() > user.marketplace_subscription_expires

        subscription_info["is_active_bool"] = is_active
        subscription_info["is_expired"] = is_expired
        subscription_info["has_active_subscription"] = is_active and not is_expired

        # Check property
        subscription_info["has_active_marketplace_subscription_property"] = (
            user.has_active_marketplace_subscription
        )

        # Get marketplace payments
        payments = MarketplacePayment.query.filter_by(user_id=user.id).all()
        subscription_info["payments"] = [
            {
                "id": p.id,
                "status": p.status,
                "gateway_status": p.gateway_status,
                "amount": p.amount,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in payments
        ]

        return jsonify({"success": True, "subscription_info": subscription_info})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@market.route("/test-whatsapp/<phone>")
def test_whatsapp(phone):
    """Test WhatsApp link format with detailed debugging"""
    import re
    from urllib.parse import quote

    # Test different cleaning methods
    phone_str = str(phone).strip()
    digits_only = re.sub(r"\D", "", phone_str)

    # Method 1: Simple cleaning
    cleaned_simple = digits_only

    # Method 2: With country code logic
    if digits_only.startswith("0") and len(digits_only) == 11:
        cleaned_with_cc = "234" + digits_only[1:]
    elif digits_only.startswith("234") and len(digits_only) == 13:
        cleaned_with_cc = digits_only
    elif len(digits_only) == 10:
        cleaned_with_cc = "234" + digits_only
    else:
        cleaned_with_cc = digits_only

    # Remove any non-digits that might remain
    cleaned_with_cc = re.sub(r"\D", "", cleaned_with_cc)

    message = "Hi! I'm interested in your service: Test Service"
    encoded_message = quote(message)

    whatsapp_url_simple = f"https://wa.me/{cleaned_simple}?text={encoded_message}"
    whatsapp_url_with_cc = f"https://wa.me/{cleaned_with_cc}?text={encoded_message}"

    return f"""
    <h1>WhatsApp Link Test</h1>
    <p><strong>Original:</strong> {phone}</p>
    <p><strong>Digits only:</strong> {digits_only}</p>
    <p><strong>Length:</strong> {len(digits_only)}</p>
    
    <h2>Method 1: Simple (no country code)</h2>
    <p>Number: {cleaned_simple}</p>
    <p>URL: <a href="{whatsapp_url_simple}" target="_blank">{whatsapp_url_simple}</a></p>
    
    <h2>Method 2: With country code logic</h2>
    <p>Number: {cleaned_with_cc}</p>
    <p>URL: <a href="{whatsapp_url_with_cc}" target="_blank">{whatsapp_url_with_cc}</a></p>
    
    <hr>
    <p><strong>Test Links:</strong></p>
    <p><a href="{whatsapp_url_simple}" target="_blank">Test Simple Link</a></p>
    <p><a href="{whatsapp_url_with_cc}" target="_blank">Test With Country Code Link</a></p>
    
    <hr>
    <p><strong>Debug Info:</strong></p>
    <p>Starts with 0: {digits_only.startswith('0')}</p>
    <p>Starts with 234: {digits_only.startswith('234')}</p>
    <p>Expected WhatsApp format: 234XXXXXXXXXX (13 digits)</p>
    """


# Add these routes to market.py


@market.route("/service/<slug>/reviews", methods=["GET"])
def service_reviews(slug):
    """View all reviews for a service"""
    service = MarketplaceService.query.filter_by(slug=slug).first_or_404()

    # Get sort parameter
    sort_by = request.args.get("sort", "newest")
    page = request.args.get("page", 1, type=int)
    per_page = 10

    # Get reviews with pagination
    query = MarketplaceReview.query.filter_by(service_id=service.id, status="approved")

    # Apply sorting
    if sort_by == "helpful":
        query = query.order_by(MarketplaceReview.helpful_count.desc())
    elif sort_by == "highest":
        query = query.order_by(MarketplaceReview.rating.desc())
    elif sort_by == "lowest":
        query = query.order_by(MarketplaceReview.rating.asc())
    else:  # newest
        query = query.order_by(MarketplaceReview.created_at.desc())

    reviews = query.paginate(page=page, per_page=per_page, error_out=False)

    # Get rating breakdown
    rating_stats = {
        5: MarketplaceReview.query.filter_by(
            service_id=service.id, rating=5, status="approved"
        ).count(),
        4: MarketplaceReview.query.filter_by(
            service_id=service.id, rating=4, status="approved"
        ).count(),
        3: MarketplaceReview.query.filter_by(
            service_id=service.id, rating=3, status="approved"
        ).count(),
        2: MarketplaceReview.query.filter_by(
            service_id=service.id, rating=2, status="approved"
        ).count(),
        1: MarketplaceReview.query.filter_by(
            service_id=service.id, rating=1, status="approved"
        ).count(),
    }

    total_reviews = sum(rating_stats.values())

    # Calculate percentages
    for star in rating_stats:
        if total_reviews > 0:
            rating_stats[star] = {
                "count": rating_stats[star],
                "percentage": round((rating_stats[star] / total_reviews) * 100, 1),
            }
        else:
            rating_stats[star] = {"count": 0, "percentage": 0}

    return render_template(
        "service_reviews.html",
        service=service,
        reviews=reviews,
        sort_by=sort_by,
        rating_stats=rating_stats,
        total_reviews=total_reviews,
        average_rating=service.average_rating,
        now=utcnow(),
    )


@market.route("/seller/<int:seller_id>/reviews", methods=["GET"])
def seller_reviews(seller_id):
    """View all reviews for a seller"""
    seller = User.query.get_or_404(seller_id)

    # Get sort parameter
    sort_by = request.args.get("sort", "newest")
    page = request.args.get("page", 1, type=int)
    per_page = 10

    # Get reviews with pagination
    query = MarketplaceReview.query.filter_by(seller_id=seller_id, status="approved")

    # Apply sorting
    if sort_by == "helpful":
        query = query.order_by(MarketplaceReview.helpful_count.desc())
    elif sort_by == "highest":
        query = query.order_by(MarketplaceReview.rating.desc())
    elif sort_by == "lowest":
        query = query.order_by(MarketplaceReview.rating.asc())
    else:  # newest
        query = query.order_by(MarketplaceReview.created_at.desc())

    reviews = query.paginate(page=page, per_page=per_page, error_out=False)

    # Get seller rating stats
    seller_rating = SellerRating.query.filter_by(seller_id=seller_id).first()
    if not seller_rating:
        # Create if doesn't exist
        seller_rating = SellerRating(seller_id=seller_id)
        seller_rating.update_stats()

    rating_stats = {
        5: seller_rating.rating_5,
        4: seller_rating.rating_4,
        3: seller_rating.rating_3,
        2: seller_rating.rating_2,
        1: seller_rating.rating_1,
    }

    # Calculate percentages
    for star in rating_stats:
        if seller_rating.total_reviews > 0:
            rating_stats[star] = {
                "count": rating_stats[star],
                "percentage": seller_rating.get_rating_percentage(star),
            }
        else:
            rating_stats[star] = {"count": 0, "percentage": 0}

    return render_template(
        "seller_reviews.html",
        seller=seller,
        reviews=reviews,
        sort_by=sort_by,
        rating_stats=rating_stats,
        total_reviews=seller_rating.total_reviews,
        average_rating=seller_rating.average_rating,
        now=utcnow(),
    )


@market.route("/submit-review", methods=["POST"])
@login_required
def submit_review():
    """Submit a review for service or seller"""
    try:
        # Get form data
        review_type = request.form.get("review_type", "service")
        rating = request.form.get("rating", type=int)
        comment = request.form.get("comment", "").strip()
        title = request.form.get("title", "").strip()
        service_id = request.form.get("service_id", type=int)
        seller_id = request.form.get("seller_id", type=int)

        print(f"DEBUG - Received review submission:")
        print(f"  review_type: {review_type}")
        print(f"  rating: {rating}")
        print(f"  service_id: {service_id}")
        print(f"  seller_id: {seller_id}")

        if not rating or rating < 1 or rating > 5:
            return jsonify(
                {
                    "success": False,
                    "error": "Please select a rating between 1 and 5 stars",
                }
            )

        if not comment or len(comment) < 10:
            return jsonify(
                {
                    "success": False,
                    "error": "Review comment must be at least 10 characters",
                }
            )

        review = None

        if review_type == "service":
            if not service_id:
                return jsonify({"success": False, "error": "Service ID required"})

            service = MarketplaceService.query.get_or_404(service_id)

            # Get seller_id from the service
            seller_id = service.seller_id

            print(f"  Found service: {service.title}")
            print(f"  Service seller_id: {seller_id}")

            # Check if user is trying to review their own service
            if current_user.id == seller_id:
                return jsonify(
                    {"success": False, "error": "You cannot review your own service"}
                )

            # Check if user already reviewed this service
            existing_review = MarketplaceReview.query.filter_by(
                buyer_id=current_user.id, service_id=service_id
            ).first()

            if existing_review:
                return jsonify(
                    {
                        "success": False,
                        "error": "You have already reviewed this service",
                    }
                )

            # Create service review - USE is_verified NOT is_verified_purchase
            review = MarketplaceReview(
                service_id=service_id,
                seller_id=seller_id,
                buyer_id=current_user.id,
                rating=rating,
                title=title,
                comment=comment,
                review_type="service",  # Make sure this field exists in model
                is_verified=True,  # Use is_verified, not is_verified_purchase
                status="approved",
            )

        else:  # seller review
            if not seller_id:
                return jsonify({"success": False, "error": "Seller ID required"})

            seller = User.query.get_or_404(seller_id)

            if current_user.id == seller_id:
                return jsonify(
                    {"success": False, "error": "You cannot review yourself"}
                )

            # Check if user already reviewed this seller
            existing_review = MarketplaceReview.query.filter_by(
                buyer_id=current_user.id, seller_id=seller_id, review_type="seller"
            ).first()

            if existing_review:
                return jsonify(
                    {"success": False, "error": "You have already reviewed this seller"}
                )

            # Create seller review - USE is_verified NOT is_verified_purchase
            review = MarketplaceReview(
                seller_id=seller_id,
                buyer_id=current_user.id,
                rating=rating,
                title=title,
                comment=comment,
                review_type="seller",  # Make sure this field exists in model
                is_verified=True,  # Use is_verified, not is_verified_purchase
                status="approved",
            )

        # Handle review images
        review_images = []
        if "review_images" in request.files:
            files = request.files.getlist("review_images")
            for file in files[:3]:  # Limit to 3 images
                if file and file.filename != "" and allowed_file(file.filename):
                    print(f"  Uploading image: {file.filename}")
                    image_url = upload_to_cloudinary(file, "reviews")
                    if image_url:
                        review_images.append(image_url)

        if review_images:
            review.review_images = json.dumps(review_images)

        print(f"  Creating review with data:")
        print(f"    service_id: {review.service_id}")
        print(f"    seller_id: {review.seller_id}")
        print(f"    buyer_id: {review.buyer_id}")
        print(f"    review_type: {review.review_type}")

        db.session.add(review)
        db.session.commit()

        print(f"  ✅ Review created with ID: {review.id}")

        # Update service statistics if it's a service review
        if review.service_id:
            service = MarketplaceService.query.get(review.service_id)
            if service:
                # Calculate new average rating
                if service.review_count is None:
                    service.review_count = 0
                    service.average_rating = 0.0

                new_total_rating = (
                    service.average_rating * service.review_count
                ) + review.rating
                service.review_count += 1
                service.average_rating = new_total_rating / service.review_count

                db.session.commit()
                print(
                    f"  ✅ Updated service stats: average_rating={service.average_rating}, review_count={service.review_count}"
                )

        return jsonify(
            {
                "success": True,
                "message": "Review submitted successfully!",
                "review_id": review.id,
                "review_type": review.review_type,
            }
        )

    except Exception as e:
        db.session.rollback()
        print(f"❌ Error submitting review: {str(e)}")
        import traceback

        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500


@market.route("/api/review-helpful", methods=["POST"])
@login_required
def review_helpful():
    """Mark review as helpful or not helpful"""
    try:
        # Get JSON data
        if not request.is_json:
            return jsonify({"success": False, "error": "Request must be JSON"}), 400

        data = request.get_json()
        review_id = data.get("review_id", type=int)
        is_helpful = data.get("is_helpful", type=bool)

        if not review_id:
            return jsonify({"success": False, "error": "Review ID required"})

        if is_helpful is None:
            return jsonify({"success": False, "error": "is_helpful value required"})

        review = MarketplaceReview.query.get_or_404(review_id)

        # Check if ReviewHelpfulVote model exists
        try:
            from models import ReviewHelpfulVote
        except ImportError:
            # Create ReviewHelpfulVote model if it doesn't exist
            class ReviewHelpfulVote(db.Model):
                __tablename__ = "review_helpful_votes"
                id = db.Column(db.Integer, primary_key=True)
                review_id = db.Column(
                    db.Integer,
                    db.ForeignKey("marketplace_reviews.id", ondelete="CASCADE"),
                    nullable=False,
                )
                user_id = db.Column(
                    db.Integer,
                    db.ForeignKey("users.id", ondelete="CASCADE"),
                    nullable=False,
                )
                is_helpful = db.Column(db.Boolean, nullable=False)
                created_at = db.Column(db.DateTime, default=datetime.utcnow)

            db.create_all()  # This will create the table if it doesn't exist

        # Check if user already voted
        existing_vote = ReviewHelpfulVote.query.filter_by(
            review_id=review_id, user_id=current_user.id
        ).first()

        if existing_vote:
            # Update existing vote
            if existing_vote.is_helpful != is_helpful:
                # Update counts
                if existing_vote.is_helpful:
                    review.helpful_count = max(0, review.helpful_count - 1)
                else:
                    review.not_helpful_count = max(0, review.not_helpful_count - 1)

                if is_helpful:
                    review.helpful_count += 1
                else:
                    review.not_helpful_count += 1

                existing_vote.is_helpful = is_helpful
                existing_vote.created_at = utcnow()
        else:
            # Create new vote
            vote = ReviewHelpfulVote(
                review_id=review_id, user_id=current_user.id, is_helpful=is_helpful
            )
            db.session.add(vote)

            if is_helpful:
                review.helpful_count = (review.helpful_count or 0) + 1
            else:
                review.not_helpful_count = (review.not_helpful_count or 0) + 1

        db.session.commit()

        return jsonify(
            {
                "success": True,
                "helpful_count": review.helpful_count or 0,
                "not_helpful_count": review.not_helpful_count or 0,
                "user_vote": "helpful" if is_helpful else "not_helpful",
            }
        )

    except Exception as e:
        db.session.rollback()
        print(f"Error in review_helpful: {str(e)}")
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@market.route("/api/review-reply", methods=["POST"])
@login_required
def review_reply():
    """Seller reply to a review"""
    try:
        review_id = request.json.get("review_id", type=int)
        reply_text = request.json.get("reply", "").strip()

        if not review_id:
            return jsonify({"success": False, "error": "Review ID required"})

        if not reply_text or len(reply_text) < 5:
            return jsonify(
                {"success": False, "error": "Reply must be at least 5 characters"}
            )

        review = MarketplaceReview.query.get_or_404(review_id)

        # Check if user is the seller
        if current_user.id != review.seller_id and not current_user.is_super_admin:
            return jsonify(
                {"success": False, "error": "Only the seller can reply to reviews"}
            )

        # Check if already replied
        if review.seller_response:
            return jsonify(
                {"success": False, "error": "You have already replied to this review"}
            )

        review.seller_response = reply_text
        review.seller_response_at = utcnow()

        # Notify the buyer
        buyer = User.query.get(review.buyer_id)
        if buyer:
            buyer.create_notification(
                actor=current_user,
                notification_type="review_reply",
                entity_id=review.id,
                entity_type="review",
                custom_message=f"{current_user.full_name} replied to your review",
            )

        db.session.commit()

        return jsonify(
            {
                "success": True,
                "message": "Reply submitted successfully",
                "reply": reply_text,
                "reply_date": review.seller_response_at.isoformat(),
            }
        )

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@market.route("/api/user-reviews", methods=["GET"])
@login_required
def get_user_reviews():
    """Get reviews written by current user"""
    try:
        page = request.args.get("page", 1, type=int)
        per_page = 10
        review_type = request.args.get("type", "all")  # all, service, seller

        query = MarketplaceReview.query.filter_by(buyer_id=current_user.id)

        if review_type != "all":
            query = query.filter_by(review_type=review_type)

        query = query.order_by(MarketplaceReview.created_at.desc())

        reviews = query.paginate(page=page, per_page=per_page, error_out=False)

        reviews_data = []
        for review in reviews.items:
            review_data = {
                "id": review.id,
                "rating": review.rating,
                "title": review.title,
                "comment": review.comment,
                "review_type": review.review_type,
                "status": review.status,
                "is_verified": review.is_verified_purchase,
                "created_at": review.created_at.isoformat(),
                "seller_response": review.seller_response,
                "seller_response_at": (
                    review.seller_response_at.isoformat()
                    if review.seller_response_at
                    else None
                ),
                "helpful_count": review.helpful_count,
                "not_helpful_count": review.not_helpful_count,
                "review_images": review.review_images_list,
            }

            if review.service_id:
                review_data["service"] = {
                    "id": review.service.id,
                    "title": review.service.title,
                    "slug": review.service.slug,
                    "cover_image": review.service.cover_image,
                }

            review_data["seller"] = {
                "id": review.seller.id,
                "name": review.seller.full_name,
                "avatar": review.seller.profile_pic,
            }

            reviews_data.append(review_data)

        return jsonify(
            {
                "success": True,
                "reviews": reviews_data,
                "pagination": {
                    "page": reviews.page,
                    "pages": reviews.pages,
                    "total": reviews.total,
                    "has_next": reviews.has_next,
                    "has_prev": reviews.has_prev,
                },
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@market.route("/api/review/<int:review_id>", methods=["DELETE"])
@login_required
def delete_review(review_id):
    """Delete a review (only by author or admin)"""
    try:
        review = MarketplaceReview.query.get_or_404(review_id)

        # Check permissions
        if review.buyer_id != current_user.id and not current_user.is_super_admin:
            return jsonify({"success": False, "error": "Permission denied"}), 403

        # Store info before deletion
        seller_id = review.seller_id
        service_id = review.service_id

        db.session.delete(review)
        db.session.commit()

        # Update service statistics
        if service_id:
            service = MarketplaceService.query.get(service_id)
            if service:
                service.update_review_stats()

        # FIXED: Remove SellerRating reference since it doesn't exist
        # Update seller stats on User model instead
        try:
            seller = User.query.get(seller_id)
            if seller:
                # Update seller's average rating if you have that field
                # You could add this to your User model if needed
                pass
        except Exception as e:
            # Log error but don't fail the whole operation
            print(f"Error updating seller stats: {str(e)}")

        return jsonify({"success": True, "message": "Review deleted successfully"})

    except Exception as e:
        db.session.rollback()
        print(f"Error deleting review: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500
