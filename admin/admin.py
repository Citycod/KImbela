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
import json
from io import BytesIO
from models import (
    User,
    Group,
    ReportedContent,
    Post,
    Comment,
    SponsoredAd,
    AdCampaign,
    AdPackage,
    PaymentTransaction,
    MarketplacePayment,
    MatchmakingRequest,
    MatchmakingPayments,
    ActivityLog,
)

from time_utils import utcnow
# from sendgrid import SendGridAPIClient
# from sendgrid.helpers.mail import Mail, Content
from datetime import datetime, timedelta

from sqlalchemy.orm import joinedload
from sqlalchemy import func, desc
from decimal import Decimal


import bleach, os
from dotenv import load_dotenv
from extensions import mail
from flask_mail import Message
from email_utils import EmailService

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


def allowed_file(filename):
    """Check if file extension is allowed"""
    allowed_extensions = {"png", "jpg", "jpeg", "gif", "mp4", "mov", "avi"}
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


# Add this function to create a timeago filter
def timeago_filter(dt):
    if dt is None:
        return "Never"

    # Make sure dt is a datetime object
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except:
            return "Unknown"

    now = utcnow()
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
    today = utcnow().date()
    age = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age


def _admin_has_permission(permission):
    if current_user.is_super_admin:
        return True
    if not current_user.is_admin:
        return False
    return current_user.has_admin_permission(permission)


def _require_admin_permission(permission):
    if not _admin_has_permission(permission):
        flash("Access denied. Insufficient permissions.", "danger")
        return False
    return True


@admin.route("/admin_dashboard")
@login_required
def admin_dashboard():
    if not current_user.is_super_admin:
        flash("Access denied. Super admin privileges required.", "danger")
        return redirect(url_for("auth.user_dashboard"))

    # Get statistics for dashboard
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    pending_users = User.query.filter_by(is_active=False).count()
    total_groups = Group.query.count()
    active_groups = Group.query.filter_by(is_active=True).count()
    pending_reports = ReportedContent.query.filter_by(status="pending").count()
    active_ads = SponsoredAd.query.filter_by(status="active").count()
    total_posts = Post.query.count()
    total_comments = Comment.query.count()
    total_reports = ReportedContent.query.count()

    now = utcnow()
    day_start = datetime(now.year, now.month, now.day)
    month_start = datetime(now.year, now.month, 1)
    year_start = datetime(now.year, 1, 1)
    analytics_days = 14
    analytics_start = (now - timedelta(days=analytics_days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    def sum_completed_payment_transactions(start_date):
        total = (
            db.session.query(func.coalesce(func.sum(PaymentTransaction.amount), 0))
            .filter(
                PaymentTransaction.status == "completed",
                PaymentTransaction.created_at >= start_date,
            )
            .scalar()
        )
        return total if isinstance(total, Decimal) else Decimal(str(total or 0))

    def sum_completed_marketplace_payments(start_date):
        paid_at = func.coalesce(
            MarketplacePayment.paid_at, MarketplacePayment.created_at
        )
        total = (
            db.session.query(func.coalesce(func.sum(MarketplacePayment.amount), 0))
            .filter(MarketplacePayment.status == "completed", paid_at >= start_date)
            .scalar()
        )
        return total if isinstance(total, Decimal) else Decimal(str(total or 0))

    def sum_completed_payment_transactions_range(start_date, end_date):
        total = (
            db.session.query(func.coalesce(func.sum(PaymentTransaction.amount), 0))
            .filter(
                PaymentTransaction.status == "completed",
                PaymentTransaction.created_at >= start_date,
                PaymentTransaction.created_at < end_date,
            )
            .scalar()
        )
        return total if isinstance(total, Decimal) else Decimal(str(total or 0))

    def sum_completed_marketplace_payments_range(start_date, end_date):
        paid_at = func.coalesce(
            MarketplacePayment.paid_at, MarketplacePayment.created_at
        )
        total = (
            db.session.query(func.coalesce(func.sum(MarketplacePayment.amount), 0))
            .filter(
                MarketplacePayment.status == "completed",
                paid_at >= start_date,
                paid_at < end_date,
            )
            .scalar()
        )
        return total if isinstance(total, Decimal) else Decimal(str(total or 0))

    def sum_completed_ad_campaign_payments(start_date, end_date=None):
        query = db.session.query(func.coalesce(func.sum(PaymentTransaction.amount), 0))
        query = query.filter(
            PaymentTransaction.status == "completed",
            PaymentTransaction.transaction_type == "ad_campaign",
            PaymentTransaction.created_at >= start_date,
        )
        if end_date:
            query = query.filter(PaymentTransaction.created_at < end_date)
        total = query.scalar()
        return total if isinstance(total, Decimal) else Decimal(str(total or 0))

    def sum_completed_matchmaking_payments(start_date, end_date=None):
        query = db.session.query(func.coalesce(func.sum(MatchmakingPayments.amount), 0))
        query = query.filter(
            MatchmakingPayments.status == "completed",
            MatchmakingPayments.created_at >= start_date,
        )
        if end_date:
            query = query.filter(MatchmakingPayments.created_at < end_date)
        total = query.scalar()
        return total if isinstance(total, Decimal) else Decimal(str(total or 0))

    def sum_completed_payment_transactions_range(start_date, end_date):
        total = (
            db.session.query(func.coalesce(func.sum(PaymentTransaction.amount), 0))
            .filter(
                PaymentTransaction.status == "completed",
                PaymentTransaction.created_at >= start_date,
                PaymentTransaction.created_at < end_date,
            )
            .scalar()
        )
        return total if isinstance(total, Decimal) else Decimal(str(total or 0))

    def sum_completed_marketplace_payments_range(start_date, end_date):
        paid_at = func.coalesce(
            MarketplacePayment.paid_at, MarketplacePayment.created_at
        )
        total = (
            db.session.query(func.coalesce(func.sum(MarketplacePayment.amount), 0))
            .filter(
                MarketplacePayment.status == "completed",
                paid_at >= start_date,
                paid_at < end_date,
            )
            .scalar()
        )
        return total if isinstance(total, Decimal) else Decimal(str(total or 0))

    def sum_completed_ad_campaign_payments(start_date, end_date=None):
        query = db.session.query(func.coalesce(func.sum(PaymentTransaction.amount), 0))
        query = query.filter(
            PaymentTransaction.status == "completed",
            PaymentTransaction.transaction_type == "ad_campaign",
            PaymentTransaction.created_at >= start_date,
        )
        if end_date:
            query = query.filter(PaymentTransaction.created_at < end_date)
        total = query.scalar()
        return total if isinstance(total, Decimal) else Decimal(str(total or 0))

    def sum_completed_matchmaking_payments(start_date, end_date=None):
        query = db.session.query(func.coalesce(func.sum(MatchmakingPayments.amount), 0))
        query = query.filter(
            MatchmakingPayments.status == "completed",
            MatchmakingPayments.created_at >= start_date,
        )
        if end_date:
            query = query.filter(MatchmakingPayments.created_at < end_date)
        total = query.scalar()
        return total if isinstance(total, Decimal) else Decimal(str(total or 0))

    def sum_completed_payment_transactions_range(start_date, end_date):
        total = (
            db.session.query(func.coalesce(func.sum(PaymentTransaction.amount), 0))
            .filter(
                PaymentTransaction.status == "completed",
                PaymentTransaction.created_at >= start_date,
                PaymentTransaction.created_at < end_date,
            )
            .scalar()
        )
        return total if isinstance(total, Decimal) else Decimal(str(total or 0))

    def sum_completed_marketplace_payments_range(start_date, end_date):
        paid_at = func.coalesce(
            MarketplacePayment.paid_at, MarketplacePayment.created_at
        )
        total = (
            db.session.query(func.coalesce(func.sum(MarketplacePayment.amount), 0))
            .filter(
                MarketplacePayment.status == "completed",
                paid_at >= start_date,
                paid_at < end_date,
            )
            .scalar()
        )
        return total if isinstance(total, Decimal) else Decimal(str(total or 0))

    def sum_completed_ad_campaign_payments(start_date, end_date=None):
        query = db.session.query(func.coalesce(func.sum(PaymentTransaction.amount), 0))
        query = query.filter(
            PaymentTransaction.status == "completed",
            PaymentTransaction.transaction_type == "ad_campaign",
            PaymentTransaction.created_at >= start_date,
        )
        if end_date:
            query = query.filter(PaymentTransaction.created_at < end_date)
        total = query.scalar()
        return total if isinstance(total, Decimal) else Decimal(str(total or 0))

    def sum_completed_payment_transactions_range(start_date, end_date):
        total = (
            db.session.query(func.coalesce(func.sum(PaymentTransaction.amount), 0))
            .filter(
                PaymentTransaction.status == "completed",
                PaymentTransaction.created_at >= start_date,
                PaymentTransaction.created_at < end_date,
            )
            .scalar()
        )
        return total if isinstance(total, Decimal) else Decimal(str(total or 0))

    def sum_completed_marketplace_payments_range(start_date, end_date):
        paid_at = func.coalesce(
            MarketplacePayment.paid_at, MarketplacePayment.created_at
        )
        total = (
            db.session.query(func.coalesce(func.sum(MarketplacePayment.amount), 0))
            .filter(
                MarketplacePayment.status == "completed",
                paid_at >= start_date,
                paid_at < end_date,
            )
            .scalar()
        )
        return total if isinstance(total, Decimal) else Decimal(str(total or 0))

    daily_earnings = float(
        sum_completed_payment_transactions(day_start)
        + sum_completed_marketplace_payments(day_start)
    )
    monthly_earnings = float(
        sum_completed_payment_transactions(month_start)
        + sum_completed_marketplace_payments(month_start)
    )
    yearly_earnings = float(
        sum_completed_payment_transactions(year_start)
        + sum_completed_marketplace_payments(year_start)
    )
    epoch_start = datetime(1970, 1, 1)
    total_earnings = float(
        sum_completed_payment_transactions(epoch_start)
        + sum_completed_marketplace_payments(epoch_start)
    )
    marketplace_monthly_revenue = float(sum_completed_marketplace_payments(month_start))
    marketplace_total_revenue = float(sum_completed_marketplace_payments(epoch_start))
    ad_campaign_monthly_revenue = float(sum_completed_ad_campaign_payments(month_start))
    ad_campaign_total_revenue = float(sum_completed_ad_campaign_payments(epoch_start))
    matchmaking_monthly_revenue = float(sum_completed_matchmaking_payments(month_start))
    matchmaking_total_revenue = float(sum_completed_matchmaking_payments(epoch_start))

    earnings_labels = []
    earnings_series = []
    user_series = []
    for offset in range(6, -1, -1):
        bucket_start = day_start - timedelta(days=offset)
        bucket_end = bucket_start + timedelta(days=1)
        earnings = sum_completed_payment_transactions_range(
            bucket_start, bucket_end
        ) + sum_completed_marketplace_payments_range(bucket_start, bucket_end)
        earnings_labels.append(bucket_start.strftime("%b %d"))
        earnings_series.append(float(earnings))
        user_series.append(
            User.query.filter(
                User.created_at >= bucket_start, User.created_at < bucket_end
            ).count()
        )
    marketplace_monthly_revenue = float(sum_completed_marketplace_payments(month_start))
    marketplace_total_revenue = float(sum_completed_marketplace_payments(epoch_start))
    ad_campaign_monthly_revenue = float(sum_completed_ad_campaign_payments(month_start))
    ad_campaign_total_revenue = float(sum_completed_ad_campaign_payments(epoch_start))
    matchmaking_monthly_revenue = float(sum_completed_matchmaking_payments(month_start))
    matchmaking_total_revenue = float(sum_completed_matchmaking_payments(epoch_start))

    earnings_labels = []
    earnings_series = []
    user_series = []
    for offset in range(6, -1, -1):
        bucket_start = day_start - timedelta(days=offset)
        bucket_end = bucket_start + timedelta(days=1)
        earnings = sum_completed_payment_transactions_range(
            bucket_start, bucket_end
        ) + sum_completed_marketplace_payments_range(bucket_start, bucket_end)
        earnings_labels.append(bucket_start.strftime("%b %d"))
        earnings_series.append(float(earnings))
        user_series.append(
            User.query.filter(
                User.created_at >= bucket_start, User.created_at < bucket_end
            ).count()
        )
    marketplace_monthly_revenue = float(sum_completed_marketplace_payments(month_start))
    marketplace_total_revenue = float(sum_completed_marketplace_payments(epoch_start))
    ad_campaign_monthly_revenue = float(sum_completed_ad_campaign_payments(month_start))
    ad_campaign_total_revenue = float(sum_completed_ad_campaign_payments(epoch_start))
    matchmaking_monthly_revenue = float(sum_completed_matchmaking_payments(month_start))
    matchmaking_total_revenue = float(sum_completed_matchmaking_payments(epoch_start))

    earnings_labels = []
    earnings_series = []
    user_series = []
    for offset in range(6, -1, -1):
        bucket_start = day_start - timedelta(days=offset)
        bucket_end = bucket_start + timedelta(days=1)
        earnings = sum_completed_payment_transactions_range(
            bucket_start, bucket_end
        ) + sum_completed_marketplace_payments_range(bucket_start, bucket_end)
        earnings_labels.append(bucket_start.strftime("%b %d"))
        earnings_series.append(float(earnings))
        user_series.append(
            User.query.filter(
                User.created_at >= bucket_start, User.created_at < bucket_end
            ).count()
        )

    earnings_labels = []
    earnings_series = []
    user_series = []
    for offset in range(6, -1, -1):
        bucket_start = day_start - timedelta(days=offset)
        bucket_end = bucket_start + timedelta(days=1)
        earnings = sum_completed_payment_transactions_range(
            bucket_start, bucket_end
        ) + sum_completed_marketplace_payments_range(bucket_start, bucket_end)
        earnings_labels.append(bucket_start.strftime("%b %d"))
        earnings_series.append(float(earnings))
        user_series.append(
            User.query.filter(
                User.created_at >= bucket_start, User.created_at < bucket_end
            ).count()
        )

    # Recent activity
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    recent_reports = (
        ReportedContent.query.order_by(ReportedContent.created_at.desc()).limit(5).all()
    )

    reported_comment_reports = (
        ReportedContent.query.filter_by(content_type="comment", status="pending")
        .order_by(ReportedContent.created_at.desc())
        .limit(6)
        .all()
    )
    reported_comment_ids = [
        report.content_id for report in reported_comment_reports if report.content_id
    ]
    reported_comments = (
        Comment.query.filter(Comment.id.in_(reported_comment_ids)).all()
        if reported_comment_ids
        else []
    )
    reported_comments_map = {comment.id: comment for comment in reported_comments}
    reported_comments_data = [
        {"report": report, "comment": reported_comments_map.get(report.content_id)}
        for report in reported_comment_reports
    ]

    active_sponsored_ads = (
        SponsoredAd.query.filter_by(status="active")
        .order_by(SponsoredAd.end_date.asc())
        .limit(6)
        .all()
    )
    active_ad_campaigns = (
        AdCampaign.query.filter(
            AdCampaign.status == "active",
            db.or_(AdCampaign.end_date == None, AdCampaign.end_date >= now),
        )
        .order_by(AdCampaign.end_date.asc())
        .limit(6)
        .all()
    )
    sponsored_active_budget = (
        db.session.query(func.coalesce(func.sum(SponsoredAd.budget), 0))
        .filter(SponsoredAd.status == "active")
        .scalar()
        or 0
    )
    ad_campaign_active_budget = (
        db.session.query(func.coalesce(func.sum(AdCampaign.budget), 0))
        .filter(AdCampaign.status == "active")
        .scalar()
        or 0
    )
    matchmaking_active_requests = (
        MatchmakingRequest.query.filter(
            MatchmakingRequest.status == "active",
            MatchmakingRequest.end_date != None,
            MatchmakingRequest.end_date >= now,
        )
        .order_by(MatchmakingRequest.end_date.asc())
        .limit(6)
        .all()
    )
    matchmaking_recent_payments = (
        MatchmakingPayments.query.filter(MatchmakingPayments.status == "completed")
        .order_by(MatchmakingPayments.paid_at.desc())
        .limit(6)
        .all()
    )
    sponsored_active_budget = (
        db.session.query(func.coalesce(func.sum(SponsoredAd.budget), 0))
        .filter(SponsoredAd.status == "active")
        .scalar()
        or 0
    )
    ad_campaign_active_budget = (
        db.session.query(func.coalesce(func.sum(AdCampaign.budget), 0))
        .filter(AdCampaign.status == "active")
        .scalar()
        or 0
    )
    sponsored_active_budget = (
        db.session.query(func.coalesce(func.sum(SponsoredAd.budget), 0))
        .filter(SponsoredAd.status == "active")
        .scalar()
        or 0
    )
    ad_campaign_active_budget = (
        db.session.query(func.coalesce(func.sum(AdCampaign.budget), 0))
        .filter(AdCampaign.status == "active")
        .scalar()
        or 0
    )
    marketplace_active_payments = (
        MarketplacePayment.query.filter(
            MarketplacePayment.status == "completed",
            MarketplacePayment.end_date != None,
            MarketplacePayment.end_date >= now,
        )
        .order_by(MarketplacePayment.end_date.asc())
        .limit(6)
        .all()
    )
    marketplace_active_users = (
        User.query.filter(
            User.marketplace_subscription_expires != None,
            User.marketplace_subscription_expires >= now,
        )
        .order_by(User.marketplace_subscription_expires.asc())
        .limit(6)
        .all()
    )
    recent_groups = Group.query.order_by(Group.created_at.desc()).limit(6).all()
    pending_reports_list = (
        ReportedContent.query.filter_by(status="pending")
        .order_by(ReportedContent.created_at.desc())
        .limit(8)
        .all()
    )
    pending_post_ids = [
        report.content_id
        for report in pending_reports_list
        if report.content_type == "post" and report.content_id
    ]
    pending_comment_ids = [
        report.content_id
        for report in pending_reports_list
        if report.content_type == "comment" and report.content_id
    ]
    pending_posts = (
        Post.query.filter(Post.id.in_(pending_post_ids)).all()
        if pending_post_ids
        else []
    )
    pending_comments = (
        Comment.query.filter(Comment.id.in_(pending_comment_ids)).all()
        if pending_comment_ids
        else []
    )
    pending_post_map = {post.id: post for post in pending_posts}
    pending_comment_map = {comment.id: comment for comment in pending_comments}

    # ======== Activity Analytics ========
    visits_rows = (
        db.session.query(func.date(ActivityLog.created_at), func.count(ActivityLog.id))
        .filter(ActivityLog.created_at >= analytics_start)
        .group_by(func.date(ActivityLog.created_at))
        .all()
    )
    visits_map = {row[0]: row[1] for row in visits_rows}
    activity_labels = []
    visits_series = []
    for i in range(analytics_days):
        day = analytics_start + timedelta(days=i)
        key = day.date()
        activity_labels.append(day.strftime("%b %d"))
        visits_series.append(int(visits_map.get(key, 0)))

    top_pages_rows = (
        db.session.query(ActivityLog.path, func.count(ActivityLog.id))
        .filter(
            ActivityLog.created_at >= analytics_start,
            ActivityLog.event_type.in_(["page", "admin"]),
        )
        .group_by(ActivityLog.path)
        .order_by(desc(func.count(ActivityLog.id)))
        .limit(10)
        .all()
    )
    top_pages_labels = [row[0] for row in top_pages_rows]
    top_pages_series = [int(row[1]) for row in top_pages_rows]

    activity_type_rows = (
        db.session.query(ActivityLog.event_type, func.count(ActivityLog.id))
        .filter(ActivityLog.created_at >= analytics_start)
        .group_by(ActivityLog.event_type)
        .order_by(desc(func.count(ActivityLog.id)))
        .all()
    )
    activity_type_labels = [row[0] for row in activity_type_rows]
    activity_type_series = [int(row[1]) for row in activity_type_rows]

    recent_activity = (
        ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(50).all()
    )

    unique_visitors = (
        db.session.query(func.count(func.distinct(ActivityLog.ip_address)))
        .filter(ActivityLog.created_at >= day_start)
        .scalar()
        or 0
    )
    total_events = (
        db.session.query(func.count(ActivityLog.id))
        .filter(ActivityLog.created_at >= analytics_start)
        .scalar()
        or 0
    )
    pending_post_ids = [
        report.content_id
        for report in pending_reports_list
        if report.content_type == "post" and report.content_id
    ]
    pending_comment_ids = [
        report.content_id
        for report in pending_reports_list
        if report.content_type == "comment" and report.content_id
    ]
    pending_posts = (
        Post.query.filter(Post.id.in_(pending_post_ids)).all()
        if pending_post_ids
        else []
    )
    pending_comments = (
        Comment.query.filter(Comment.id.in_(pending_comment_ids)).all()
        if pending_comment_ids
        else []
    )
    pending_post_map = {post.id: post for post in pending_posts}
    pending_comment_map = {comment.id: comment for comment in pending_comments}

    return render_template(
        "admin_dashboard.html",
        total_users=total_users,
        active_users=active_users,
        pending_users=pending_users,
        total_groups=total_groups,
        active_groups=active_groups,
        pending_reports=pending_reports,
        active_ads=active_ads,
        total_posts=total_posts,
        total_comments=total_comments,
        total_reports=total_reports,
        daily_earnings=daily_earnings,
        monthly_earnings=monthly_earnings,
        yearly_earnings=yearly_earnings,
        total_earnings=total_earnings,
        marketplace_monthly_revenue=marketplace_monthly_revenue,
        marketplace_total_revenue=marketplace_total_revenue,
        ad_campaign_monthly_revenue=ad_campaign_monthly_revenue,
        ad_campaign_total_revenue=ad_campaign_total_revenue,
        matchmaking_monthly_revenue=matchmaking_monthly_revenue,
        matchmaking_total_revenue=matchmaking_total_revenue,
        earnings_labels=earnings_labels,
        earnings_series=earnings_series,
        user_series=user_series,
        recent_users=recent_users,
        recent_reports=recent_reports,
        reported_comments_data=reported_comments_data,
        active_sponsored_ads=active_sponsored_ads,
        active_ad_campaigns=active_ad_campaigns,
        marketplace_active_payments=marketplace_active_payments,
        marketplace_active_users=marketplace_active_users,
        recent_groups=recent_groups,
        pending_reports_list=pending_reports_list,
        pending_post_map=pending_post_map,
        pending_comment_map=pending_comment_map,
        matchmaking_active_requests=matchmaking_active_requests,
        matchmaking_recent_payments=matchmaking_recent_payments,
        sponsored_active_budget=float(sponsored_active_budget),
        ad_campaign_active_budget=float(ad_campaign_active_budget),
        activity_labels=activity_labels,
        visits_series=visits_series,
        top_pages_labels=top_pages_labels,
        top_pages_series=top_pages_series,
        activity_type_labels=activity_type_labels,
        activity_type_series=activity_type_series,
        recent_activity=recent_activity,
        unique_visitors=unique_visitors,
        total_events=total_events,
        analytics_days=analytics_days,
        now=now,
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
    if not current_user.is_super_admin:
        return jsonify({"success": False, "error": "Super admin required"}), 403

    user = User.query.get_or_404(user_id)
    if user.is_super_admin:
        return jsonify({"success": False, "error": "Cannot suspend super admin"}), 403
    if not user.is_admin:
        return jsonify({"success": False, "error": "Only sub admins can be suspended here"}), 403
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
    user.admin_role = "sub_admin"
    user.admin_permissions = json.dumps(["groups_manage", "reported_comments_delete"])
    db.session.commit()

    return jsonify({"success": True})


@admin.route("/admin/users/<int:user_id>/remove_admin", methods=["POST"])
@login_required
def admin_remove_admin(user_id):
    if not current_user.is_super_admin:
        return jsonify({"success": False, "error": "Super admin required"}), 403

    user = User.query.get_or_404(user_id)
    if user.is_super_admin:
        return jsonify({"success": False, "error": "Cannot remove super admin"}), 403
    user.is_admin = False
    user.admin_role = "moderator"
    user.admin_permissions = None
    db.session.commit()

    return jsonify({"success": True})


@admin.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@login_required
def admin_delete_user(user_id):
    if not current_user.is_super_admin:
        return jsonify({"success": False, "error": "Super admin required"}), 403

    user = User.query.get_or_404(user_id)
    if user.is_super_admin:
        return jsonify({"success": False, "error": "Cannot delete super admin"}), 403
    if not user.is_admin:
        return jsonify({"success": False, "error": "Only sub admins can be deleted here"}), 403
    if user.id == current_user.id:
        return jsonify({"success": False, "error": "Cannot delete yourself"}), 403

    db.session.delete(user)
    db.session.commit()

    return jsonify({"success": True})


@admin.route("/admin/change_password", methods=["POST"])
@login_required
def admin_change_password():
    if not current_user.is_super_admin:
        flash("Access denied. Super admin privileges required.", "danger")
        return redirect(url_for("admin.admin_users"))

    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not current_user.check_password(current_password):
        flash("Current password is incorrect.", "danger")
        return redirect(url_for("admin.admin_users"))

    if new_password != confirm_password:
        flash("New passwords do not match.", "danger")
        return redirect(url_for("admin.admin_users"))

    if not is_strong_password(new_password):
        flash(
            "Password must be at least 8 characters and include upper, lower, number, and symbol.",
            "danger",
        )
        return redirect(url_for("admin.admin_users"))

    current_user.set_password(new_password)
    db.session.commit()
    flash("Password updated successfully.", "success")
    return redirect(url_for("admin.admin_users"))


@admin.route("/admin/groups")
@login_required
def admin_groups():
    if not _require_admin_permission("groups_manage"):
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
    if not _require_admin_permission("groups_manage"):
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
    if not _require_admin_permission("groups_manage"):
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
    if not _require_admin_permission("groups_manage"):
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
    if not (current_user.is_super_admin or _admin_has_permission("groups_delete")):
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
    if not _require_admin_permission("reported_comments_delete"):
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

    post_ids = [
        report.content_id
        for report in reports.items
        if report.content_type == "post" and report.content_id
    ]
    comment_ids = [
        report.content_id
        for report in reports.items
        if report.content_type == "comment" and report.content_id
    ]
    posts = Post.query.filter(Post.id.in_(post_ids)).all() if post_ids else []
    comments = (
        Comment.query.filter(Comment.id.in_(comment_ids)).all() if comment_ids else []
    )
    post_map = {post.id: post for post in posts}
    comment_map = {comment.id: comment for comment in comments}

    return render_template(
        "admin_reports.html",
        reports=reports,
        status_filter=status_filter,
        type_filter=type_filter,
        post_map=post_map,
        comment_map=comment_map,
    )


@admin.route("/admin/reports/<int:report_id>/resolve", methods=["POST"])
@login_required
def admin_resolve_report(report_id):
    if not (current_user.is_super_admin or _admin_has_permission("reported_comments_delete")):
        return jsonify({"success": False, "error": "Access denied"}), 403

    report = ReportedContent.query.get_or_404(report_id)
    action = request.json.get(
        "action"
    )  # delete_content, warn_user, suspend_user, dismiss

    if not current_user.is_super_admin:
        if action != "delete_content" or report.content_type != "comment":
            return jsonify({"success": False, "error": "Access denied"}), 403

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
    report.resolved_at = utcnow()
    report.admin_notes = request.json.get("notes", "")

    db.session.commit()

    return jsonify({"success": True})


@admin.route("/admin/reports/<int:report_id>/dismiss", methods=["POST"])
@login_required
def admin_dismiss_report(report_id):
    if not current_user.is_super_admin:
        return jsonify({"success": False, "error": "Super admin required"}), 403

    report = ReportedContent.query.get_or_404(report_id)
    report.status = "dismissed"
    report.resolved_by = current_user.id
    report.resolved_at = utcnow()
    report.admin_notes = request.json.get("notes", "")

    db.session.commit()

    return jsonify({"success": True})


@admin.route("/admin/ads")
@login_required
def admin_ads():
    if not current_user.is_super_admin:
        return jsonify({"error": "Access denied"}), 403

    page = request.args.get("page", 1, type=int)
    status_filter = request.args.get("status", "all")

    query = SponsoredAd.query

    if status_filter != "all":
        query = query.filter_by(status=status_filter)

    ads = query.order_by(SponsoredAd.created_at.desc()).paginate(
        page=page, per_page=12, error_out=False
    )

    campaign_query = AdCampaign.query
    if status_filter != "all":
        campaign_query = campaign_query.filter_by(status=status_filter)
    campaigns = campaign_query.order_by(AdCampaign.created_at.desc()).limit(30).all()

    return render_template(
        "admin_ads.html",
        ads=ads,
        campaigns=campaigns,
        status_filter=status_filter,
    )


@admin.route("/admin/ads/create", methods=["POST"])
@login_required
def admin_create_ad():
    if not current_user.is_super_admin:
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
    if not current_user.is_super_admin:
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
    if not current_user.is_super_admin:
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
    if not current_user.is_super_admin:
        return jsonify({"success": False, "error": "Access denied"}), 403

    ad = SponsoredAd.query.get_or_404(ad_id)
    db.session.delete(ad)
    db.session.commit()

    return jsonify({"success": True})


@admin.route("/admin/stats")
@login_required
def admin_stats():
    if not current_user.is_super_admin:
        return jsonify({"error": "Access denied"}), 403

    # User growth (last 30 days)
    thirty_days_ago = utcnow() - timedelta(days=30)
    user_growth = User.query.filter(User.created_at >= thirty_days_ago).count()

    # Active users (last 7 days)
    seven_days_ago = utcnow() - timedelta(days=7)
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
    if not (current_user.is_super_admin or _admin_has_permission("reported_comments_delete")):
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
    if not current_user.is_super_admin:
        return jsonify({"error": "Access denied"}), 403

    # Get statistics for dashboard
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    pending_users = User.query.filter_by(is_active=False).count()
    total_groups = Group.query.count()
    active_groups = Group.query.filter_by(is_active=True).count()
    pending_reports = ReportedContent.query.filter_by(status="pending").count()
    active_ads = SponsoredAd.query.filter_by(status="active").count()
    total_posts = Post.query.count()
    total_comments = Comment.query.count()
    total_reports = ReportedContent.query.count()

    now = utcnow()
    day_start = datetime(now.year, now.month, now.day)
    month_start = datetime(now.year, now.month, 1)
    year_start = datetime(now.year, 1, 1)

    def sum_completed_payment_transactions(start_date):
        total = (
            db.session.query(func.coalesce(func.sum(PaymentTransaction.amount), 0))
            .filter(
                PaymentTransaction.status == "completed",
                PaymentTransaction.created_at >= start_date,
            )
            .scalar()
        )
        return total if isinstance(total, Decimal) else Decimal(str(total or 0))

    def sum_completed_marketplace_payments(start_date):
        paid_at = func.coalesce(
            MarketplacePayment.paid_at, MarketplacePayment.created_at
        )
        total = (
            db.session.query(func.coalesce(func.sum(MarketplacePayment.amount), 0))
            .filter(MarketplacePayment.status == "completed", paid_at >= start_date)
            .scalar()
        )
        return total if isinstance(total, Decimal) else Decimal(str(total or 0))

    daily_earnings = float(
        sum_completed_payment_transactions(day_start)
        + sum_completed_marketplace_payments(day_start)
    )
    monthly_earnings = float(
        sum_completed_payment_transactions(month_start)
        + sum_completed_marketplace_payments(month_start)
    )
    yearly_earnings = float(
        sum_completed_payment_transactions(year_start)
        + sum_completed_marketplace_payments(year_start)
    )
    epoch_start = datetime(1970, 1, 1)
    total_earnings = float(
        sum_completed_payment_transactions(epoch_start)
        + sum_completed_marketplace_payments(epoch_start)
    )

    # Recent activity
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    recent_reports = (
        ReportedContent.query.order_by(ReportedContent.created_at.desc()).limit(5).all()
    )

    reported_comment_reports = (
        ReportedContent.query.filter_by(content_type="comment", status="pending")
        .order_by(ReportedContent.created_at.desc())
        .limit(6)
        .all()
    )
    reported_comment_ids = [
        report.content_id for report in reported_comment_reports if report.content_id
    ]
    reported_comments = (
        Comment.query.filter(Comment.id.in_(reported_comment_ids)).all()
        if reported_comment_ids
        else []
    )
    reported_comments_map = {comment.id: comment for comment in reported_comments}
    reported_comments_data = [
        {"report": report, "comment": reported_comments_map.get(report.content_id)}
        for report in reported_comment_reports
    ]

    active_sponsored_ads = (
        SponsoredAd.query.filter_by(status="active")
        .order_by(SponsoredAd.end_date.asc())
        .limit(6)
        .all()
    )
    active_ad_campaigns = (
        AdCampaign.query.filter(
            AdCampaign.status == "active",
            db.or_(AdCampaign.end_date == None, AdCampaign.end_date >= now),
        )
        .order_by(AdCampaign.end_date.asc())
        .limit(6)
        .all()
    )
    matchmaking_active_requests = (
        MatchmakingRequest.query.filter(
            MatchmakingRequest.status == "active",
            MatchmakingRequest.end_date != None,
            MatchmakingRequest.end_date >= now,
        )
        .order_by(MatchmakingRequest.end_date.asc())
        .limit(6)
        .all()
    )
    matchmaking_recent_payments = (
        MatchmakingPayments.query.filter(MatchmakingPayments.status == "completed")
        .order_by(MatchmakingPayments.paid_at.desc())
        .limit(6)
        .all()
    )
    marketplace_active_payments = (
        MarketplacePayment.query.filter(
            MarketplacePayment.status == "completed",
            MarketplacePayment.end_date != None,
            MarketplacePayment.end_date >= now,
        )
        .order_by(MarketplacePayment.end_date.asc())
        .limit(6)
        .all()
    )
    marketplace_active_users = (
        User.query.filter(
            User.marketplace_subscription_expires != None,
            User.marketplace_subscription_expires >= now,
        )
        .order_by(User.marketplace_subscription_expires.asc())
        .limit(6)
        .all()
    )
    recent_groups = Group.query.order_by(Group.created_at.desc()).limit(6).all()
    pending_reports_list = (
        ReportedContent.query.filter_by(status="pending")
        .order_by(ReportedContent.created_at.desc())
        .limit(8)
        .all()
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
        total_posts=total_posts,
        total_comments=total_comments,
        total_reports=total_reports,
        daily_earnings=daily_earnings,
        monthly_earnings=monthly_earnings,
        yearly_earnings=yearly_earnings,
        total_earnings=total_earnings,
        marketplace_monthly_revenue=marketplace_monthly_revenue,
        marketplace_total_revenue=marketplace_total_revenue,
        ad_campaign_monthly_revenue=ad_campaign_monthly_revenue,
        ad_campaign_total_revenue=ad_campaign_total_revenue,
        matchmaking_monthly_revenue=matchmaking_monthly_revenue,
        matchmaking_total_revenue=matchmaking_total_revenue,
        earnings_labels=earnings_labels,
        earnings_series=earnings_series,
        user_series=user_series,
        recent_users=recent_users,
        recent_reports=recent_reports,
        reported_comments_data=reported_comments_data,
        active_sponsored_ads=active_sponsored_ads,
        active_ad_campaigns=active_ad_campaigns,
        marketplace_active_payments=marketplace_active_payments,
        marketplace_active_users=marketplace_active_users,
        recent_groups=recent_groups,
        pending_reports_list=pending_reports_list,
        pending_post_map=pending_post_map,
        pending_comment_map=pending_comment_map,
        matchmaking_active_requests=matchmaking_active_requests,
        matchmaking_recent_payments=matchmaking_recent_payments,
        sponsored_active_budget=float(sponsored_active_budget),
        ad_campaign_active_budget=float(ad_campaign_active_budget),
        now=now,
    )


@admin.route("/admin/users")
@login_required
def admin_users():
    if not current_user.is_super_admin:
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
        "admin_users_page.html",
        users=users,
        search=search,
        status_filter=status_filter,
        current_user=current_user,
    )


@admin.route("/admin/users/bulk_email", methods=["POST"])
@login_required
def admin_bulk_email():
    if not current_user.is_super_admin:
        return jsonify({"success": False, "error": "Access denied"}), 403

    data = request.get_json(silent=True) or {}
    subject = (data.get("subject") or "").strip()
    message = (data.get("message") or "").strip()
    user_ids = data.get("user_ids") or []
    send_all = bool(data.get("send_all"))
    search = data.get("search", "")
    status_filter = data.get("status", "all")

    if not subject or not message:
        return jsonify({"success": False, "error": "Subject and message are required"}), 400

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

    if send_all:
        users = query.all()
    else:
        if not user_ids:
            return jsonify({"success": False, "error": "No users selected"}), 400
        users = query.filter(User.id.in_(user_ids)).all()

    sent = 0
    failed = 0
    for user in users:
        if not user.email:
            failed += 1
            continue
        try:
            EmailService.send_email(
                to_email=user.email,
                subject=subject,
                html_content=f"<p>{message}</p>",
                text_content=message,
            )
            sent += 1
        except Exception:
            failed += 1

    return jsonify({"success": True, "sent": sent, "failed": failed})
