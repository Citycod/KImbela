# scheduler.py - OPTIMIZED VERSION
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
import logging
import time
from flask import current_app
from extensions import db
from datetime import datetime, date
from models import User, BirthdayNotification, db
from apscheduler.schedulers.background import BackgroundScheduler


logger = logging.getLogger(__name__)
scheduler = None


def init_scheduler(app):
    """Initialize the background scheduler with optimized settings"""
    global scheduler

    # Check if scheduler already running
    if scheduler and scheduler.running:
        logger.info("Scheduler already running")
        return scheduler

    # Create scheduler with optimized settings
    scheduler = BackgroundScheduler(
        daemon=True,
        job_defaults={
            "coalesce": True,  # Combine multiple pending jobs
            "max_instances": 3,  # Limit concurrent jobs
            "misfire_grace_time": 300,  # 5 minutes grace period
        },
    )

    # ========== OPTIMIZED JOBS ==========

    # Campaign expiry check - every 6 hours (was every hour)
    @scheduler.scheduled_job("interval", hours=6, id="campaign_expiry_check")
    def check_expired_campaigns():
        """Check for expired campaigns every 6 hours"""
        with app.app_context():
            start_time = time.time()
            try:
                # Import here to avoid circular imports
                from campaign_service import CampaignService

                campaign_service = CampaignService()

                # Batch process expired campaigns
                expired_count = campaign_service.check_campaign_expiry()

                # Check for campaigns expiring soon (7 days, not 3)
                expiring_soon = campaign_service.get_expiring_soon_campaigns(days=7)
                for campaign in expiring_soon[:50]:  # Limit to 50 per run
                    if not getattr(campaign, "expiry_notification_sent", False):
                        campaign_service.send_expiry_reminder(campaign)
                        campaign.expiry_notification_sent = True

                if expired_count > 0 or expiring_soon:
                    db.session.commit()

                elapsed = time.time() - start_time
                if elapsed > 5:  # Log if took more than 5 seconds
                    logger.warning(f"Campaign expiry check took {elapsed:.2f}s")

            except Exception as e:
                logger.error(f"Error in campaign expiry check: {str(e)}")
                db.session.rollback()

    # Daily maintenance - 2 AM (off-peak hours)
    @scheduler.scheduled_job("cron", hour=2, minute=0, id="daily_maintenance")
    def daily_maintenance():
        """Daily maintenance tasks during off-peak hours"""
        with app.app_context():
            start_time = time.time()
            try:
                # Only update campaigns with recent activity
                from models import AdCampaign

                # Limit to campaigns with activity in last 7 days
                seven_days_ago = datetime.utcnow() - timedelta(days=7)
                campaigns = (
                    AdCampaign.query.filter(
                        AdCampaign.impressions > 0,
                        AdCampaign.updated_at >= seven_days_ago,
                    )
                    .limit(100)
                    .all()
                )  # Limit to 100 campaigns

                for campaign in campaigns:
                    if campaign.impressions > 0:
                        campaign.click_through_rate = (
                            campaign.clicks / campaign.impressions
                        ) * 100

                # Update marketplace stats in bulk
                update_marketplace_stats_bulk()

                db.session.commit()

                elapsed = time.time() - start_time
                logger.info(f"Daily maintenance completed in {elapsed:.2f}s")

            except Exception as e:
                logger.error(f"Error in daily maintenance: {str(e)}")
                db.session.rollback()

    # Marketplace subscription check - 10 AM (once per day)
    @scheduler.scheduled_job("cron", hour=10, minute=0, id="marketplace_subscriptions")
    def check_marketplace_subscriptions():
        """Check marketplace subscriptions - optimized"""
        with app.app_context():
            start_time = time.time()
            try:
                # Run checks in sequence with limits
                check_expiring_subscriptions_optimized()
                check_expired_subscriptions_optimized()

                elapsed = time.time() - start_time
                logger.info(f"Marketplace check completed in {elapsed:.2f}s")

            except Exception as e:
                logger.error(f"Error in marketplace subscription check: {str(e)}")

    # Matchmaking expiry - 11 AM (once per day)
    @scheduler.scheduled_job("cron", hour=11, minute=0, id="matchmaking_expiry")
    def check_matchmaking_expiry():
        """Check matchmaking expiry - optimized"""
        with app.app_context():
            start_time = time.time()
            try:
                # Use batch processing
                check_expired_matchmaking_batch()

                elapsed = time.time() - start_time
                logger.info(f"Matchmaking check completed in {elapsed:.2f}s")

            except Exception as e:
                logger.error(f"Error in matchmaking expiry check: {str(e)}")

    # Inactive sellers check - Wednesdays at 10 AM (once per week)
    @scheduler.scheduled_job(
        "cron", day_of_week="wed", hour=10, minute=0, id="inactive_sellers"
    )
    def check_inactive_sellers():
        """Check inactive sellers - weekly instead of daily"""
        with app.app_context():
            start_time = time.time()
            try:
                check_inactive_sellers_optimized()

                elapsed = time.time() - start_time
                logger.info(f"Inactive sellers check completed in {elapsed:.2f}s")

            except Exception as e:
                logger.error(f"Error checking inactive sellers: {str(e)}")

    # Weekly report - Monday at 3 AM (off-peak)
    @scheduler.scheduled_job(
        "cron", day_of_week="mon", hour=3, minute=0, id="weekly_report"
    )
    def weekly_performance_report():
        """Weekly report - optimized"""
        with app.app_context():
            start_time = time.time()
            try:
                generate_marketplace_report_optimized()

                elapsed = time.time() - start_time
                logger.info(f"Weekly report completed in {elapsed:.2f}s")

            except Exception as e:
                logger.error(f"Error in weekly performance report: {str(e)}")

    # Start the scheduler
    scheduler.start()
    logger.info("Optimized scheduler started successfully")

    # Add shutdown handler
    import atexit

    atexit.register(lambda: scheduler.shutdown() if scheduler else None)

    return scheduler


# ========== OPTIMIZED HELPER FUNCTIONS ==========


def check_expiring_subscriptions_optimized():
    """Optimized version - batch processing"""
    try:
        three_days_from_now = datetime.utcnow() + timedelta(days=3)
        now = datetime.utcnow()

        # Use direct SQL for efficiency
        from sqlalchemy import text

        # Find services expiring soon (limit 100)
        query = text(
            """
            SELECT DISTINCT ON (seller_id) 
                   id, seller_id, title, subscription_expires
            FROM marketplace_service 
            WHERE subscription_status = 'active'
              AND subscription_expires <= :expiry_date
              AND subscription_expires > :now
              AND status = 'active'
              AND (expiry_reminder_sent IS NULL OR expiry_reminder_sent = false)
            ORDER BY seller_id, subscription_expires ASC
            LIMIT 100
        """
        )

        result = db.session.execute(
            query, {"expiry_date": three_days_from_now, "now": now}
        ).fetchall()

        if result:
            from models import User, MarketplaceService

            seller_ids = [row[1] for row in result]

            # Fetch sellers in bulk
            sellers = User.query.filter(User.id.in_(seller_ids)).all()
            seller_dict = {seller.id: seller for seller in sellers}

            for row in result:
                seller = seller_dict.get(row[1])
                if seller:
                    service = MarketplaceService.query.get(row[0])
                    if service:
                        # Send reminder
                        send_subscription_reminder_optimized(
                            seller, "expiring_soon", service
                        )
                        service.expiry_reminder_sent = True

            db.session.commit()
            logger.info(f"Processed {len(result)} expiring subscriptions")

    except Exception as e:
        logger.error(f"Error checking expiring subscriptions: {str(e)}")
        db.session.rollback()


def check_expired_subscriptions_optimized():
    """Optimized version with batch update"""
    try:
        now = datetime.utcnow()

        # Update expired subscriptions in bulk
        from models import MarketplaceService

        expired_count = (
            db.session.query(MarketplaceService)
            .filter(
                MarketplaceService.subscription_status == "active",
                MarketplaceService.subscription_expires <= now,
                MarketplaceService.status == "active",
            )
            .update(
                {MarketplaceService.subscription_status: "expired"},
                synchronize_session=False,
            )
        )

        if expired_count > 0:
            db.session.commit()
            logger.info(f"Updated {expired_count} expired subscriptions")

            # Send notifications in background (optional)
            # Can be done async via task queue

    except Exception as e:
        logger.error(f"Error checking expired subscriptions: {str(e)}")
        db.session.rollback()


def check_expired_matchmaking_batch():
    """Batch process expired matchmaking requests"""
    try:
        from models import MatchmakingRequest

        now = datetime.utcnow()

        # Update in bulk
        expired_count = (
            db.session.query(MatchmakingRequest)
            .filter(
                MatchmakingRequest.status == "active",
                MatchmakingRequest.end_date <= now,
                MatchmakingRequest.payment_status == "paid",
            )
            .update(
                {
                    MatchmakingRequest.status: "expired",
                    MatchmakingRequest.updated_at: now,
                },
                synchronize_session=False,
            )
        )

        if expired_count > 0:
            db.session.commit()
            logger.info(f"Marked {expired_count} matchmaking requests as expired")

    except Exception as e:
        logger.error(f"Error checking expired matchmaking requests: {str(e)}")
        db.session.rollback()


def check_inactive_sellers_optimized():
    """Optimized check for inactive sellers"""
    try:
        from models import User, MarketplaceService

        # Find sellers with services but no active subscription
        # Using subquery for efficiency
        subquery = (
            db.session.query(MarketplaceService.seller_id)
            .filter(
                MarketplaceService.status == "active",
                MarketplaceService.subscription_status == "active",
                MarketplaceService.subscription_expires > datetime.utcnow(),
            )
            .distinct()
            .subquery()
        )

        # Get sellers not in the active subscription list
        sellers = (
            User.query.filter(
                User.marketplace_services.any(MarketplaceService.status == "active")
            )
            .filter(~User.id.in_(db.session.query(subquery.c.seller_id)))
            .limit(50)
            .all()
        )  # Limit to 50 per run

        # Send promotions in batch (optional)
        # Could be moved to task queue

        logger.info(f"Found {len(sellers)} sellers without active subscription")

    except Exception as e:
        logger.error(f"Error checking inactive sellers: {str(e)}")


def update_marketplace_stats_bulk():
    """Bulk update marketplace statistics"""
    try:
        from sqlalchemy import text

        # Use SQL for bulk update
        update_query = text(
            """
            UPDATE marketplace_service 
            SET ranking_score = (
                (views * 0.1) + 
                (clicks * 0.5) + 
                (COALESCE(average_rating, 0) * 20)
            ) * CASE 
                WHEN subscription_status = 'active' 
                     AND subscription_expires > CURRENT_TIMESTAMP 
                THEN 3 
                ELSE 1 
            END
            WHERE status = 'active'
              AND updated_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'
            LIMIT 200
        """
        )

        db.session.execute(update_query)
        logger.info("Updated marketplace stats in bulk")

    except Exception as e:
        logger.error(f"Error updating marketplace stats: {str(e)}")


def generate_marketplace_report_optimized():
    """Optimized weekly report"""
    try:
        from sqlalchemy import func

        week_ago = datetime.utcnow() - timedelta(days=7)

        # Single query for all stats
        stats = (
            db.session.query(
                func.count(MarketplaceService.id).label("total_services"),
                func.sum(MarketplaceService.views).label("total_views"),
                func.sum(
                    func.case((MarketplaceService.created_at >= week_ago, 1), else_=0)
                ).label("new_services"),
                func.sum(
                    func.case(
                        (MarketplaceService.subscription_status == "active", 1), else_=0
                    )
                ).label("subscribed_services"),
            )
            .filter(MarketplaceService.status == "active")
            .first()
        )

        if stats:
            total_services = stats.total_services or 0
            subscribed_services = stats.subscribed_services or 0
            subscription_rate = (
                (subscribed_services / total_services * 100)
                if total_services > 0
                else 0
            )

            logger.info(
                f"""
            Weekly Marketplace Report:
            - Total Active Services: {total_services}
            - New Services (7 days): {stats.new_services or 0}
            - Subscribed Services: {subscribed_services}
            - Total Views: {stats.total_views or 0}
            - Subscription Rate: {subscription_rate:.1f}%
            """
            )

    except Exception as e:
        logger.error(f"Error generating marketplace report: {str(e)}")


def send_subscription_reminder_optimized(user, reminder_type, service=None):
    """Optimized email sending with template caching"""
    try:
        # Import here to avoid circular imports
        from flask_mail import Message
        from extensions import mail

        # Use template caching
        templates = {
            "expiring_soon": {
                "subject": f"⏰ Your Kimbela Subscription Expires Soon!",
                "template": "email/expiring_soon.html",
            },
            "expired": {
                "subject": f"📉 Your Kimbela Subscription Has Expired",
                "template": "email/expired.html",
            },
            "welcome": {
                "subject": f"🎉 Welcome to Kimbela Marketplace!",
                "template": "email/welcome.html",
            },
        }

        if reminder_type not in templates:
            return

        template_info = templates[reminder_type]

        # Create message - actual email sending could be moved to task queue
        msg = Message(
            subject=template_info["subject"],
            recipients=[user.email],
            sender=current_app.config["MAIL_DEFAULT_SENDER"],
        )

        # For now, just log it (to avoid email spam during debugging)
        logger.info(f"Would send {reminder_type} email to {user.email}")

        # Uncomment to actually send emails:
        # msg.html = render_email_template(template_info["template"], user=user, service=service)
        # mail.send(msg)

    except Exception as e:
        logger.error(f"Error preparing {reminder_type} email: {str(e)}")


# ========== MANUAL TRIGGERS (FOR TESTING) ==========


def manual_trigger_all_checks():
    """Manually trigger all checks for testing"""
    try:
        from flask import current_app

        with current_app.app_context():
            logger.info("Starting manual trigger of all checks...")

            check_expired_campaigns()
            daily_maintenance()
            check_marketplace_subscriptions()
            check_matchmaking_expiry()
            check_inactive_sellers()
            weekly_performance_report()

            logger.info("Manual trigger completed")
            return True

    except Exception as e:
        logger.error(f"Error in manual trigger: {str(e)}")
        return False


def get_scheduler_status():
    """Get scheduler status"""
    global scheduler
    if scheduler:
        jobs = scheduler.get_jobs()
        return {
            "running": scheduler.running,
            "job_count": len(jobs),
            "jobs": [
                {"id": job.id, "next_run": str(job.next_run_time)} for job in jobs
            ],
        }
    return {"running": False, "job_count": 0, "jobs": []}


def pause_scheduler():
    """Pause scheduler"""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.pause()
        logger.info("Scheduler paused")
        return True
    return False


# Add this to your existing scheduler.py (at the end, before the last line)


def manual_trigger_matchmaking_expiry_check():
    """Manually trigger matchmaking expiry check (for testing)"""
    try:
        from flask import current_app

        with current_app.app_context():
            # Import EmailService inside the function to avoid circular imports
            from email_service import EmailService

            success = EmailService.check_and_send_expiry_reminders()
            logger.info(
                f"Manual matchmaking expiry check: {'Success' if success else 'Failed'}"
            )
            return success
    except Exception as e:
        logger.error(f"Error in manual matchmaking expiry check: {str(e)}")
        return False


def resume_scheduler():
    """Resume scheduler"""
    global scheduler
    if scheduler:
        scheduler.resume()
        logger.info("Scheduler resumed")
        return True
    return False


def check_and_create_birthday_notifications():
    """
    Run daily to check for upcoming birthdays
    """
    print("🎂 Checking for birthdays...")
    today = date.today()

    # Get all users who have friends
    users = User.query.all()

    for user in users:
        friends = user.friends.all()

        for friend in friends:
            if friend.dob:
                # Check if friend's birthday is today
                if friend.dob.month == today.month and friend.dob.day == today.day:
                    # Check if notification already exists
                    existing = BirthdayNotification.query.filter_by(
                        user_id=user.id, birthday_user_id=friend.id, birthday_date=today
                    ).first()

                    if not existing:
                        # Create birthday notification
                        notification = BirthdayNotification(
                            user_id=user.id,
                            birthday_user_id=friend.id,
                            birthday_date=today,
                            is_seen=False,
                            is_wished=False,
                        )
                        db.session.add(notification)

        db.session.commit()

    print(f"✅ Birthday check completed at {datetime.now()}")


def init_birthday_scheduler():
    """Initialize the birthday scheduler"""
    scheduler = BackgroundScheduler()

    # Run daily at 9 AM
    scheduler.add_job(check_and_create_birthday_notifications, "cron", hour=9, minute=0)

    scheduler.start()
