from decimal import Decimal


# Kimbela currently prices both matchmaking products at the same fixed USD
# amount. Keep the product-specific names so call sites remain explicit while
# deriving them from one authoritative value.
MATCHMAKING_PRODUCT_PRICE_USD = Decimal("3.00")
MATCHMAKING_ACCESS_PRICE_USD = MATCHMAKING_PRODUCT_PRICE_USD
PROFILE_BOOST_PRICE_USD = MATCHMAKING_PRODUCT_PRICE_USD


def format_usd(amount):
    """Return a stable two-decimal display value without using float math."""
    return format(Decimal(amount).quantize(Decimal("0.01")), ".2f")
