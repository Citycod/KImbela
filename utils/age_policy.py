"""Centralized age eligibility and validation policy for Kimbela.

Approved Policy Rules:
- Account eligibility minimum age: 18.
- Maximum account age: None (all adults supported).
- Earliest plausible date of birth: 1900-01-01.
- Preferred matchmaking age range: 18 to 120.
- Ad targeting range: 18 to 120.

Date calculations:
- Uses calendar arithmetic (not 365-day approximations).
- A user born on February 29 in a leap year turns 18 on March 1 in non-leap years.
"""

from datetime import date
import re
from typing import Optional, Tuple
from time_utils import utcnow

MIN_ACCOUNT_AGE = 18
MIN_PLAUSIBLE_DOB = date(1900, 1, 1)
MAX_PREFERENCE_AGE = 120
MIN_AD_TARGET_AGE = 18
MAX_AD_TARGET_AGE = 120


def calculate_age(dob: Optional[date], today: Optional[date] = None) -> Optional[int]:
    """Calculate exact integer age from date of birth.

    Returns None if dob is None.
    Handles leap years: if born on Feb 29, the user reaches their next year
    on March 1 in non-leap years.
    """
    if not dob:
        return None
    if today is None:
        today = utcnow().date()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def adult_cutoff(today: Optional[date] = None, years: int = MIN_ACCOUNT_AGE) -> date:
    """Return the latest date of birth that qualifies as an adult today.

    A user whose DOB is <= adult_cutoff(today) has reached the required age.
    Handles leap-day edge cases:
      - If today is Feb 29 (leap year) and target year has no Feb 29,
        falls back to Feb 28.
    """
    if today is None:
        today = utcnow().date()
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(year=today.year - years, month=2, day=28)


def validate_account_dob(
    dob: Optional[date], today: Optional[date] = None
) -> Tuple[bool, Optional[str]]:
    """Validate that a date of birth satisfies Kimbela's account eligibility policy.

    Rules:
    - Must be a valid date object.
    - Cannot be in the future.
    - Cannot be earlier than MIN_PLAUSIBLE_DOB (1900-01-01).
    - Must establish that the account holder is at least 18 years old.

    Returns (is_valid, error_message).
    """
    if not dob or not isinstance(dob, date):
        return False, "Date of birth is required."

    if today is None:
        today = utcnow().date()

    if dob > today:
        return False, "Date of birth cannot be in the future."

    if dob < MIN_PLAUSIBLE_DOB:
        return False, f"Date of birth cannot be earlier than {MIN_PLAUSIBLE_DOB.strftime('%Y-%m-%d')}."

    cutoff = adult_cutoff(today, MIN_ACCOUNT_AGE)
    if dob > cutoff:
        return False, f"You must be at least {MIN_ACCOUNT_AGE} years old to use Kimbela."

    return True, None


def validate_preferred_age_range(
    min_age_input, max_age_input
) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    """Validate a preferred partner or browse age range.

    Rules:
    - Both min_age and max_age must be whole numbers.
    - min_age must be >= 18.
    - min_age and max_age must be <= 120.
    - max_age must be >= min_age.

    Returns (min_age, max_age, error_message).
    """
    values = []
    for raw_value in (min_age_input, max_age_input):
        if isinstance(raw_value, bool) or raw_value in (None, ""):
            return None, None, "Please enter a valid whole-number age."
        if isinstance(raw_value, int):
            values.append(raw_value)
        elif isinstance(raw_value, str) and re.fullmatch(r"[+-]?\d+", raw_value.strip()):
            values.append(int(raw_value.strip()))
        else:
            return None, None, "Please enter a valid whole-number age."

    min_age, max_age = values

    if min_age < MIN_ACCOUNT_AGE:
        return None, None, f"Minimum age must be at least {MIN_ACCOUNT_AGE}."
    if min_age > MAX_PREFERENCE_AGE or max_age > MAX_PREFERENCE_AGE:
        return None, None, f"Maximum age cannot be greater than {MAX_PREFERENCE_AGE}."
    if max_age < min_age:
        return None, None, "Maximum age must be greater than or equal to minimum age."

    return min_age, max_age, None

