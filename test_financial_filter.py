import re

FINANCIAL_PATTERNS = [
    # Explicit bank/payment details matching (account numbers, app handles with numbers)
    r"\b(?:acct|account)\s*(?:no|num|number)?\s*[:#-]?\s*\d{8,12}\b",
    r"\b\d{10}\b.*\b(?:opay|palmpay|kuda|moniepoint|gtb|zenith|access|uba|first bank)\b",
    r"\b(?:opay|palmpay|kuda|moniepoint|gtb|zenith|access|uba|first bank)\b.*\b\d{10}\b",
    
    # Direct loan/money requests
    r"\b(?:send|transfer|lend|borrow|give)\s+(?:me|us|some|it|the)\s+(?:money|cash|funds|naira|dollars|k|\d+[k]?)\b",
    r"\b(?:need|seeking)\s+(?:a\s+)?(?:loan|financial assistance|funds)\b",
    
    # Soft/Indirect hardship language indicating money
    r"\b(?:help me out|things are tight|i am broke|no money|stranded|pay.*rent|school fees)\b",
    
    # Currency with urgency/begging
    r"\b(?:need|urgent|please|help|send|transfer)\b.*?(?:₦|naira|\$|\b\d+k\b)",
    r"(?:₦|naira|\$|\b\d+k\b).*?\b(?:need|urgent|please|help|send|transfer)\b"
]

compiled_patterns = [re.compile(p, re.IGNORECASE) for p in FINANCIAL_PATTERNS]

def is_financial_request(text: str) -> bool:
    for pattern in compiled_patterns:
        if pattern.search(text):
            return True
    return False

test_cases = [
    # Obvious requests
    ("Please send me money I am stranded", True),
    ("I urgently need a loan of 500k Naira", True),
    ("Can you transfer 50k to my opay?", True),
    
    # Numbers / Accounts
    ("My account number is 0123456789 GTB", True),
    ("Send it to 9012345678 palmpay", True),
    ("acct num: 1234567890", True),
    
    # Soft / Indirect phrasing
    ("can you help me out, things are tight right now", True),
    ("I have no money for food today", True),
    ("Need to pay my rent by tomorrow, any assistance?", True),
    
    # False positives check (Should be False)
    ("I went to GTB today to get a new ATM card", False),
    ("Opay's new update is really cool", False),
    ("I bought this shoe for 50k naira, isn't it nice?", False), 
    ("The ceiling fan makes a weird noise", False),
]

for text, expected in test_cases:
    result = is_financial_request(text)
    match = "PASS" if result == expected else "FAIL"
    print(f"[{match}] Text: '{text}' -> Got: {result} (Expected: {expected})")
