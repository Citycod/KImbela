from flask import (
    Flask,
    render_template,
    Response,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    Blueprint,
    make_response,
)
from flask_wtf.csrf import generate_csrf
import uuid
from io import BytesIO

# from sendgrid import SendGridAPIClient
# from sendgrid.helpers.mail import Mail, Content
from datetime import datetime, timedelta

from sqlalchemy.orm import joinedload


import bleach, os
from dotenv import load_dotenv
from extensions import mail
from flask_mail import Message

from sqlalchemy.orm import joinedload

from datetime import timedelta, datetime

from sqlalchemy.orm import joinedload
from io import BytesIO
from datetime import datetime
from weasyprint import HTML
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from extensions import db
from flask_bcrypt import bcrypt
from werkzeug.security import generate_password_hash, check_password_hash
import os, re
import cloudinary.uploader
from dotenv import load_dotenv
import pytz
import logging
from flask import flash, redirect, url_for, render_template, request
from flask_login import login_user, current_user
from flask import (
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
    jsonify,
)
from flask_login import login_required, current_user
import logging
from sqlalchemy.sql import text
from flask import send_file, render_template_string
from io import BytesIO
import shutil
from flask import render_template
import re
from cloudinary.uploader import upload
import cloudinary


load_dotenv()

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path)



cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)


admin = Blueprint("admin", __name__)






# Add this function to create a timeago filter
def timeago_filter(dt):
    if dt is None:
        return "Never"
    
    # Make sure dt is a datetime object
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return "Unknown"
    
    now = datetime.utcnow()
    return humanize.naturaltime(now - dt)



def is_strong_password(password):
    if len(password) < 8:
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"\d", password):
        return False
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False
    return True


def calculate_age(birth_date):
    today = datetime.utcnow().date()
    age = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age






@admin.route("/admin_dashboard")
@login_required
def admin_dashboard():
    if not current_user.is_admin and not current_user.is_super_admin:
        flash("Access denied. Admin privileges required.", "danger")
        return redirect(url_for("auth.user_dashboard"))

    # Get statistics for dashboard
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    pending_users = User.query.filter_by(is_active=False).count()
    total_groups = Group.query.count()
    active_groups = Group.query.filter_by(is_active=True).count()
    pending_reports = ReportedContent.query.filter_by(status="pending").count()
    active_ads = SponsoredAd.query.filter_by(status="active").count()

    # Recent activity
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    recent_reports = (
        ReportedContent.query.order_by(ReportedContent.created_at.desc()).limit(5).all()
    )

    return render_template(
        "admin_dashboard.html",
        total_users=total_users,
        active_users=active_users,
        pending_users=pending_users,
        total_groups=total_groups,
        active_groups=active_groups,
        pending_reports=pending_reports,
        active_ads=active_ads,
        recent_users=recent_users,
        recent_reports=recent_reports,
    )


# @admin.route('/admin/users')
# @login_required
# def admin_users():
#     if not current_user.is_admin and not current_user.is_super_admin:
#         return jsonify({'error': 'Access denied'}), 403

#     page = request.args.get('page', 1, type=int)
#     search = request.args.get('search', '')
#     status_filter = request.args.get('status', 'all')

#     query = User.query

#     if search:
#         query = query.filter(
#             db.or_(
#                 User.first_name.ilike(f'%{search}%'),
#                 User.last_name.ilike(f'%{search}%'),
#                 User.email.ilike(f'%{search}%')
#             )
#         )

#     if status_filter == 'active':
#         query = query.filter_by(is_active=True)
#     elif status_filter == 'pending':
#         query = query.filter_by(is_active=False)
#     elif status_filter == 'admin':
#         query = query.filter(db.or_(User.is_admin == True, User.is_super_admin == True))

#     users = query.order_by(User.created_at.desc()).paginate(
#         page=page, per_page=20, error_out=False
#     )

#     return render_template('admin_users.html', users=users, search=search, status_filter=status_filter)


@admin.route("/admin/users/<int:user_id>/toggle_status", methods=["POST"])
@login_required
def admin_toggle_user_status(user_id):
    if not current_user.is_admin and not current_user.is_super_admin:
        return jsonify({"success": False, "error": "Access denied"}), 403

    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()

    return jsonify({"success": True, "is_active": user.is_active})


@admin.route("/admin/users/<int:user_id>/make_admin", methods=["POST"])
@login_required
def admin_make_admin(user_id):
    if not current_user.is_super_admin:
        return jsonify({"success": False, "error": "Super admin required"}), 403

    user = User.query.get_or_404(user_id)
    user.is_admin = True
    db.session.commit()

    return jsonify({"success": True})


@admin.route("/admin/users/<int:user_id>/remove_admin", methods=["POST"])
@login_required
def admin_remove_admin(user_id):
    if not current_user.is_super_admin:
        return jsonify({"success": False, "error": "Super admin required"}), 403

    user = User.query.get_or_404(user_id)
    user.is_admin = False
    db.session.commit()

    return jsonify({"success": True})


@admin.route("/admin/groups")
@login_required
def admin_groups():
    if not current_user.is_admin and not current_user.is_super_admin:
        return jsonify({"error": "Access denied"}), 403

    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "")

    query = Group.query

    if search:
        query = query.filter(
            db.or_(
                Group.name.ilike(f"%{search}%"), Group.description.ilike(f"%{search}%")
            )
        )

    groups = query.order_by(Group.created_at.desc()).paginate(
        page=page, per_page=12, error_out=False
    )

    return render_template("admin_groups.html", groups=groups, search=search)


@admin.route("/admin/groups/create", methods=["POST"])
@login_required
def admin_create_group():
    if not (current_user.is_admin or current_user.is_super_admin):
        return jsonify({"success": False, "error": "Access denied"}), 403

    # Force parsing of form data even when files are present
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    category = request.form.get("category", "social")
    is_private_str = request.form.get("is_private", "false")
    is_private = is_private_str == "true" or is_private_str == "True"

    if not name:
        return jsonify({"success": False, "error": "Group name is required"}), 400

    group = Group(
        name=name,
        description=description or None,
        category=category,
        is_private=is_private,
        created_by=current_user.id,
    )

    # Handle image
    if "image" in request.files:
        file = request.files["image"]
        if file and file.filename and allowed_file(file.filename):
            try:
                result = cloudinary.uploader.upload(
                    file,
                    folder="kimbela/groups",
                    transformation=[
                        {"width": 800, "height": 600, "crop": "limit"},
                        {"quality": "auto", "fetch_format": "auto"},
                    ],
                )
                group.image = result["secure_url"]
            except Exception as e:
                print("Image upload failed:", e)

    db.session.add(group)
    db.session.commit()

    return jsonify({"success": True, "group_id": group.id})


@admin.route("/admin/groups/<int:group_id>/edit")
@login_required
def admin_get_group_for_edit(group_id):
    if not current_user.is_admin and not current_user.is_super_admin:
        return jsonify({"success": False, "error": "Access denied"}), 403

    group = Group.query.get_or_404(group_id)

    return jsonify(
        {
            "success": True,
            "group": {
                "id": group.id,
                "name": group.name,
                "description": group.description,
                "category": group.category,
                "is_private": group.is_private,
            },
        }
    )


@admin.route("/admin/groups/<int:group_id>/update", methods=["POST"])
@login_required
def admin_update_group(group_id):
    if not current_user.is_admin and not current_user.is_super_admin:
        return jsonify({"success": False, "error": "Access denied"}), 403

    group = Group.query.get_or_404(group_id)

    group.name = request.form.get("name", group.name)
    group.description = request.form.get("description", group.description)
    group.category = request.form.get("category", group.category)
    group.is_private = request.form.get("is_private") == "true"

    # Handle group image update
    if "image" in request.files:
        file = request.files["image"]
        if file and file.filename != "" and allowed_file(file.filename):
            try:
                result = cloudinary.uploader.upload(
                    file,
                    folder="kimbela/groups",
                    transformation=[
                        {"width": 400, "height": 300, "crop": "fill"},
                        {"quality": "auto", "fetch_format": "auto"},
                    ],
                )
                group.image = result["secure_url"]
            except Exception as e:
                print(f"Group image upload error: {e}")

    db.session.commit()

    return jsonify({"success": True})


@admin.route("/admin/groups/<int:group_id>/delete", methods=["POST"])
@login_required
def admin_delete_group(group_id):
    if not (current_user.is_admin or current_user.is_super_admin):
        return jsonify({"success": False, "error": "Access denied"}), 403

    group = Group.query.get(group_id)
    if not group:
        return jsonify({"success": False, "error": "Group not found"}), 404

    try:
        # 1. Remove all members (clears group_members table)
        group.members.clear()  # This is clean and safe

        # 2. Delete Cloudinary image if exists
        if group.image and "res.cloudinary.com" in group.image:
            try:
                public_id = group.image.split("/")[-1].split(".")[0]
                cloudinary.uploader.destroy(f"kimbela/groups/{public_id}")
            except:
                pass  # Ignore image delete errors

        # 3. Delete the group — created_by becomes NULL automatically
        db.session.delete(group)
        db.session.commit()

        return jsonify({"success": True})

    except Exception as e:
        db.session.rollback()
        print("Group delete error:", str(e))
        return jsonify({"success": False, "error": "Delete failed"}), 500


@admin.route("/admin/reports")
@login_required
def admin_reports():
    if not current_user.is_admin and not current_user.is_super_admin:
        return jsonify({"error": "Access denied"}), 403

    page = request.args.get("page", 1, type=int)
    status_filter = request.args.get("status", "pending")
    type_filter = request.args.get("type", "all")

    query = ReportedContent.query

    if status_filter != "all":
        query = query.filter_by(status=status_filter)

    if type_filter != "all":
        query = query.filter_by(content_type=type_filter)

    reports = query.order_by(ReportedContent.created_at.desc()).paginate(
        page=page, per_page=10, error_out=False
    )

    return render_template(
        "admin_reports.html",
        reports=reports,
        status_filter=status_filter,
        type_filter=type_filter,
    )


@admin.route("/admin/reports/<int:report_id>/resolve", methods=["POST"])
@login_required
def admin_resolve_report(report_id):
    if not current_user.is_admin and not current_user.is_super_admin:
        return jsonify({"success": False, "error": "Access denied"}), 403

    report = ReportedContent.query.get_or_404(report_id)
    action = request.json.get(
        "action"
    )  # delete_content, warn_user, suspend_user, dismiss

    if action == "delete_content":
        # Delete the reported content based on type
        if report.content_type == "post":
            post = Post.query.get(report.content_id)
            if post:
                db.session.delete(post)
        elif report.content_type == "comment":
            comment = Comment.query.get(report.content_id)
            if comment:
                db.session.delete(comment)
    elif action == "suspend_user" and report.reported_user:
        report.reported_user.is_active = False

    report.status = "resolved"
    report.resolved_by = current_user.id
    report.resolved_at = datetime.utcnow()
    report.admin_notes = request.json.get("notes", "")

    db.session.commit()

    return jsonify({"success": True})


@admin.route("/admin/reports/<int:report_id>/dismiss", methods=["POST"])
@login_required
def admin_dismiss_report(report_id):
    if not current_user.is_admin and not current_user.is_super_admin:
        return jsonify({"success": False, "error": "Access denied"}), 403

    report = ReportedContent.query.get_or_404(report_id)
    report.status = "dismissed"
    report.resolved_by = current_user.id
    report.resolved_at = datetime.utcnow()
    report.admin_notes = request.json.get("notes", "")

    db.session.commit()

    return jsonify({"success": True})


@admin.route("/admin/ads")
@login_required
def admin_ads():
    if not current_user.is_admin and not current_user.is_super_admin:
        return jsonify({"error": "Access denied"}), 403

    page = request.args.get("page", 1, type=int)
    status_filter = request.args.get("status", "active")

    query = SponsoredAd.query

    if status_filter != "all":
        query = query.filter_by(status=status_filter)

    ads = query.order_by(SponsoredAd.created_at.desc()).paginate(
        page=page, per_page=12, error_out=False
    )

    return render_template("admin_ads.html", ads=ads, status_filter=status_filter)


@admin.route("/admin/ads/create", methods=["POST"])
@login_required
def admin_create_ad():
    if not current_user.is_admin and not current_user.is_super_admin:
        return jsonify({"success": False, "error": "Access denied"}), 403

    title = request.form.get("title")
    description = request.form.get("description")
    target_audience = request.form.get("target_audience", "all")
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    budget = request.form.get("budget", 0.0, type=float)

    if not all([title, start_date, end_date]):
        return jsonify({"success": False, "error": "Missing required fields"})

    try:
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
        end_date = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return jsonify({"success": False, "error": "Invalid date format"})

    ad = SponsoredAd(
        title=title,
        description=description,
        target_audience=target_audience,
        start_date=start_date,
        end_date=end_date,
        budget=budget,
        created_by=current_user.id,
    )

    # Handle ad image
    if "image" in request.files:
        file = request.files["image"]
        if file and file.filename != "" and allowed_file(file.filename):
            try:
                result = cloudinary.uploader.upload(
                    file,
                    folder="kimbela/ads",
                    transformation=[
                        {"width": 400, "height": 300, "crop": "fill"},
                        {"quality": "auto", "fetch_format": "auto"},
                    ],
                )
                ad.image = result["secure_url"]
            except Exception as e:
                print(f"Ad image upload error: {e}")

    db.session.add(ad)
    db.session.commit()

    return jsonify({"success": True, "ad_id": ad.id})


@admin.route("/admin/ads/<int:ad_id>/update", methods=["POST"])
@login_required
def admin_update_ad(ad_id):
    if not current_user.is_admin and not current_user.is_super_admin:
        return jsonify({"success": False, "error": "Access denied"}), 403

    ad = SponsoredAd.query.get_or_404(ad_id)

    ad.title = request.form.get("title", ad.title)
    ad.description = request.form.get("description", ad.description)
    ad.target_audience = request.form.get("target_audience", ad.target_audience)
    ad.budget = request.form.get("budget", ad.budget, type=float)

    # Handle dates
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    if start_date:
        ad.start_date = datetime.strptime(start_date, "%Y-%m-%d")
    if end_date:
        ad.end_date = datetime.strptime(end_date, "%Y-%m-%d")

    # Handle ad image update
    if "image" in request.files:
        file = request.files["image"]
        if file and file.filename != "" and allowed_file(file.filename):
            try:
                result = cloudinary.uploader.upload(
                    file,
                    folder="kimbela/ads",
                    transformation=[
                        {"width": 400, "height": 300, "crop": "fill"},
                        {"quality": "auto", "fetch_format": "auto"},
                    ],
                )
                ad.image = result["secure_url"]
            except Exception as e:
                print(f"Ad image upload error: {e}")

    db.session.commit()

    return jsonify({"success": True})


@admin.route("/admin/ads/<int:ad_id>/toggle_status", methods=["POST"])
@login_required
def admin_toggle_ad_status(ad_id):
    if not current_user.is_admin and not current_user.is_super_admin:
        return jsonify({"success": False, "error": "Access denied"}), 403

    ad = SponsoredAd.query.get_or_404(ad_id)

    if ad.status == "active":
        ad.status = "paused"
    else:
        ad.status = "active"

    db.session.commit()

    return jsonify({"success": True, "status": ad.status})


@admin.route("/admin/ads/<int:ad_id>/delete", methods=["POST"])
@login_required
def admin_delete_ad(ad_id):
    if not current_user.is_admin and not current_user.is_super_admin:
        return jsonify({"success": False, "error": "Access denied"}), 403

    ad = SponsoredAd.query.get_or_404(ad_id)
    db.session.delete(ad)
    db.session.commit()

    return jsonify({"success": True})


@admin.route("/admin/stats")
@login_required
def admin_stats():
    if not current_user.is_admin and not current_user.is_super_admin:
        return jsonify({"error": "Access denied"}), 403

    # User growth (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    user_growth = User.query.filter(User.created_at >= thirty_days_ago).count()

    # Active users (last 7 days)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    active_users = User.query.filter(User.last_seen >= seven_days_ago).count()

    # Group statistics
    total_groups = Group.query.count()
    active_groups = Group.query.filter_by(is_active=True).count()

    # Report statistics
    total_reports = ReportedContent.query.count()
    resolved_reports = ReportedContent.query.filter_by(status="resolved").count()

    # Ad statistics
    total_ads = SponsoredAd.query.count()
    active_ads = SponsoredAd.query.filter_by(status="active").count()
    total_ad_budget = db.session.query(db.func.sum(SponsoredAd.budget)).scalar() or 0

    return jsonify(
        {
            "user_growth": user_growth,
            "active_users": active_users,
            "total_groups": total_groups,
            "active_groups": active_groups,
            "total_reports": total_reports,
            "resolved_reports": resolved_reports,
            "total_ads": total_ads,
            "active_ads": active_ads,
            "total_ad_budget": float(total_ad_budget),
        }
    )


# Add this to handle user comments (for reported comments)
@admin.route("/admin/comments/<int:comment_id>/delete", methods=["POST"])
@login_required
def admin_delete_comment(comment_id):
    if not current_user.is_admin and not current_user.is_super_admin:
        return jsonify({"success": False, "error": "Access denied"}), 403

    comment = Comment.query.get_or_404(comment_id)
    db.session.delete(comment)
    db.session.commit()

    return jsonify({"success": True})


from flask import jsonify, request
from random import sample


# Add these routes to your admin blueprint


@admin.route("/admin/dashboard_content")
@login_required
def admin_dashboard_content():
    if not current_user.is_admin and not current_user.is_super_admin:
        return jsonify({"error": "Access denied"}), 403

    # Get statistics for dashboard
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    pending_users = User.query.filter_by(is_active=False).count()
    total_groups = Group.query.count() if "Group" in globals() else 0
    active_groups = (
        Group.query.filter_by(is_active=True).count() if "Group" in globals() else 0
    )
    pending_reports = (
        ReportedContent.query.filter_by(status="pending").count()
        if "ReportedContent" in globals()
        else 0
    )
    active_ads = (
        SponsoredAd.query.filter_by(status="active").count()
        if "SponsoredAd" in globals()
        else 0
    )

    # Recent activity
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    recent_reports = (
        ReportedContent.query.order_by(ReportedContent.created_at.desc()).limit(5).all()
        if "ReportedContent" in globals()
        else []
    )

    return render_template(
        "admin_dashboard_content.html",
        total_users=total_users,
        active_users=active_users,
        pending_users=pending_users,
        total_groups=total_groups,
        active_groups=active_groups,
        pending_reports=pending_reports,
        active_ads=active_ads,
        recent_users=recent_users,
        recent_reports=recent_reports,
    )


@admin.route("/admin/users")
@login_required
def admin_users():
    if not current_user.is_admin and not current_user.is_super_admin:
        return jsonify({"error": "Access denied"}), 403

    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "")
    status_filter = request.args.get("status", "all")
    partial = request.args.get("partial", 0, type=int)

    query = User.query

    if search:
        query = query.filter(
            db.or_(
                User.first_name.ilike(f"%{search}%"),
                User.last_name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
            )
        )

    if status_filter == "active":
        query = query.filter_by(is_active=True)
    elif status_filter == "pending":
        query = query.filter_by(is_active=False)
    elif status_filter == "admins":
        query = query.filter(db.or_(User.is_admin == True, User.is_super_admin == True))
    elif status_filter == "suspended":
        query = query.filter_by(is_active=False)

    # Set pagination to 10 per page
    users = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=10, error_out=False
    )

    if partial:
        return render_template(
            "admin_users.html",
            users=users,
            search=search,
            status_filter=status_filter,
            current_user=current_user,
        )

    return render_template(
        "admin_dashboard.html", users=users, search=search, status_filter=status_filter
    )


