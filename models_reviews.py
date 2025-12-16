# models_reviews.py
from extensions import db
from datetime import datetime
import json


class MarketplaceReview(db.Model):
    """Reviews for marketplace services"""
    __tablename__ = "marketplace_reviews"

    __table_args__ = (
        db.Index('idx_reviews_service_id', 'service_id'),
        db.Index('idx_reviews_seller_id', 'seller_id'),
        db.Index('idx_reviews_buyer_id', 'buyer_id'),
        db.Index('idx_reviews_rating', 'rating'),
        db.Index('idx_reviews_status', 'status'),
        db.Index('idx_reviews_created_at', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)

    # Review can be for service OR seller (or both)
    service_id = db.Column(db.Integer, db.ForeignKey('marketplace_services.id', ondelete='CASCADE'), nullable=True)
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)

    # Review details
    rating = db.Column(db.Integer, nullable=False)  # 1-5 stars
    title = db.Column(db.String(200))
    comment = db.Column(db.Text, nullable=False)

    # Type of review (service or seller)
    review_type = db.Column(db.String(20), default='service')  # 'service' or 'seller'

    # Verified purchase check
    is_verified_purchase = db.Column(db.Boolean, default=False)

    # Seller response
    seller_response = db.Column(db.Text)
    seller_response_at = db.Column(db.DateTime)

    # Status
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected, flagged
    is_featured = db.Column(db.Boolean, default=False)

    # Helpfulness tracking
    helpful_count = db.Column(db.Integer, default=0)
    not_helpful_count = db.Column(db.Integer, default=0)

    # Media (optional - images for reviews)
    review_images = db.Column(db.Text)  # JSON list of image URLs

    # Dates
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships (these will be set up separately to avoid circular imports)

    def __repr__(self):
        return f'<MarketplaceReview {self.id} - {self.rating} stars>'

    @property
    def review_images_list(self):
        """Get review images as list"""
        if self.review_images:
            try:
                return json.loads(self.review_images)
            except:
                return []
        return []

    @property
    def average_rating(self):
        """Get average rating (for consistency)"""
        return float(self.rating)

    @property
    def is_verified(self):
        """Check if review is from verified purchase"""
        return self.is_verified_purchase


class ReviewHelpfulVote(db.Model):
    """Track helpful votes for reviews"""
    __tablename__ = "review_helpful_votes"

    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey('marketplace_reviews.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    is_helpful = db.Column(db.Boolean, nullable=False)  # True = helpful, False = not helpful
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('review_id', 'user_id', name='unique_review_vote'),
    )


class SellerRating(db.Model):
    """Aggregate seller ratings (updated when new reviews are added)"""
    __tablename__ = "seller_ratings"

    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True)

    # Aggregate stats
    average_rating = db.Column(db.Float, default=0.0)
    total_reviews = db.Column(db.Integer, default=0)
    rating_1 = db.Column(db.Integer, default=0)  # Count of 1-star ratings
    rating_2 = db.Column(db.Integer, default=0)  # Count of 2-star ratings
    rating_3 = db.Column(db.Integer, default=0)  # Count of 3-star ratings
    rating_4 = db.Column(db.Integer, default=0)  # Count of 4-star ratings
    rating_5 = db.Column(db.Integer, default=0)  # Count of 5-star ratings

    # Communication rating (if applicable)
    communication_rating = db.Column(db.Float, default=0.0)

    # Last updated
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def update_stats(self):
        """Update aggregate stats from reviews"""
        from models import MarketplaceReview  # Import here to avoid circular import

        reviews = MarketplaceReview.query.filter_by(
            seller_id=self.seller_id,
            status='approved'
        ).all()

        self.total_reviews = len(reviews)

        if reviews:
            total_rating = sum([r.rating for r in reviews])
            self.average_rating = round(total_rating / self.total_reviews, 1)

            # Reset counts
            self.rating_1 = 0
            self.rating_2 = 0
            self.rating_3 = 0
            self.rating_4 = 0
            self.rating_5 = 0

            # Count ratings
            for review in reviews:
                if review.rating == 1:
                    self.rating_1 += 1
                elif review.rating == 2:
                    self.rating_2 += 1
                elif review.rating == 3:
                    self.rating_3 += 1
                elif review.rating == 4:
                    self.rating_4 += 1
                elif review.rating == 5:
                    self.rating_5 += 1

        db.session.commit()

    def get_rating_percentage(self, star):
        """Get percentage for specific star rating"""
        if self.total_reviews == 0:
            return 0
        count = getattr(self, f'rating_{star}', 0)
        return round((count / self.total_reviews) * 100, 1)