"""Discovery/confirmation split for match sets, as fixed in ANALYSIS_PLAN.md section 4.

Do not change this rule: the confirmation set is only trustworthy if it was fixed before data
was seen. Any change must be logged under Deviations in ANALYSIS_PLAN.md.
"""
import hashlib

SALT = "nyc-building-risk:"
CONFIRMATION_PCT = 35

def normalize_bbl(bbl) -> str:
    """10-digit BBL string from int, float-like text ('1000010010.00000000') or padded text."""
    s = str(bbl).strip()
    if "." in s:
        s = s.split(".", 1)[0]
    if not s.isdigit() or len(s) > 10:
        raise ValueError(f"not a BBL: {bbl!r}")
    return s.zfill(10)

def split_for(case_bbl) -> str:
    """'confirmation' or 'discovery' for the match set identified by its case BBL."""
    h = int(hashlib.sha256((SALT + normalize_bbl(case_bbl)).encode()).hexdigest(), 16)
    return "confirmation" if h % 100 < CONFIRMATION_PCT else "discovery"
