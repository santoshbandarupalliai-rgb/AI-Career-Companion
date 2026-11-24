"""PII redaction for text that leaves the application (prompts sent to AI providers).

Pure functions, no I/O. Two levels:

1. SENSITIVE identifiers (national IDs, card and bank numbers, ...). The application never needs them, so they are
   always masked in every prompt (applied centrally in app/llm/client.py).
2. CONTACT details (email addresses, phone numbers). Masked in free text the student types (chat messages, interview
   answers). For resume parsing they are replaced by placeholders and put back into the result afterwards, so the
   contact fields still work but the AI provider never sees the real values.

Detection is pattern based, so it is a safety net and not a guarantee. It deliberately favours masking.
"""

import re
from collections import Counter

# ---------- sensitive identifiers ----------

_AADHAAR = re.compile(r"(?<!\d)[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?!\d)")
_PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
_IFSC = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
_PASSPORT = re.compile(r"\b[A-PR-WY][1-9]\d{5}[1-9]\b")
_SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_ACCOUNT = re.compile(r"(?i)\b((?:bank\s+)?(?:account|a/c|acct)\s*(?:no\.?|number|#)?\s*[:\-]?\s*)(\d{9,18})\b")
_DOB = re.compile(
    r"(?i)\b((?:dob|d\.o\.b\.?|date\s+of\s+birth|born\s+on)\s*[:\-]?\s*)"
    r"(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\.?,?\s+\d{4})"
)


def _luhn(digits: str) -> bool:
    total, flip = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if flip:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        flip = not flip
    return total % 10 == 0


def redact_sensitive(text: str) -> tuple[str, dict[str, int]]:
    """Mask sensitive identifiers. Returns (text, counts per kind)."""
    counts: Counter = Counter()

    def sub(pattern: re.Pattern, label: str, value: str, check=None, keep_prefix: bool = False) -> str:
        def repl(m: re.Match) -> str:
            if check and not check(m):
                return m.group(0)
            counts[label] += 1
            if keep_prefix:  # keep the words before the value ("Account no:"), mask only the value
                return m.group(1) + f"[REDACTED_{label}]"
            return f"[REDACTED_{label}]"

        return pattern.sub(repl, value)

    def card_ok(m: re.Match) -> bool:
        digits = re.sub(r"\D", "", m.group(0))
        return 13 <= len(digits) <= 19 and _luhn(digits)

    text = sub(_ACCOUNT, "BANK_ACCOUNT", text, keep_prefix=True)
    text = sub(_DOB, "DATE_OF_BIRTH", text, keep_prefix=True)
    text = sub(_CARD, "CARD_NUMBER", text, check=card_ok)
    text = sub(_AADHAAR, "AADHAAR", text)
    text = sub(_SSN, "SSN", text)
    text = sub(_PAN, "PAN", text)
    text = sub(_IFSC, "IFSC", text)
    text = sub(_PASSPORT, "PASSPORT", text)
    return text, dict(counts)


# ---------- contact details ----------

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?<![\w.])(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,5}\)?[\s.-]?)?\d{3,5}[\s.-]?\d{3,5}(?![\w])")


def _is_phone(candidate: str) -> bool:
    """A phone number, not a number range or an id: international (+) or a mobile number (starts with 6-9)."""
    digits = re.sub(r"\D", "", candidate)
    if candidate.strip().startswith("+"):
        return 10 <= len(digits) <= 15
    if len(digits) == 10:
        return digits[0] in "6789"
    if len(digits) == 11 and digits[0] == "0":
        return digits[1] in "6789"
    if len(digits) == 12 and digits.startswith("91"):
        return digits[2] in "6789"
    return False


def redact_contacts(text: str) -> tuple[str, dict[str, str]]:
    """Replace emails and phone numbers by placeholders ([EMAIL_1], [PHONE_1]). Returns (text, placeholder -> original)."""
    mapping: dict[str, str] = {}
    seen: dict[str, str] = {}

    def make(kind: str, value: str) -> str:
        if value in seen:
            return seen[value]
        n = sum(1 for k in mapping if k.startswith(f"[{kind}_")) + 1
        key = f"[{kind}_{n}]"
        mapping[key] = value
        seen[value] = key
        return key

    text = _EMAIL.sub(lambda m: make("EMAIL", m.group(0)), text)
    text = _PHONE.sub(lambda m: make("PHONE", m.group(0).strip()) if _is_phone(m.group(0)) else m.group(0), text)
    return text, mapping


def restore(value, mapping: dict[str, str]):
    """Put the originals back into a string, list, dict or pydantic model (models are changed in place)."""
    if not mapping:
        return value
    if isinstance(value, str):
        for key, original in mapping.items():
            value = value.replace(key, original)
        return value
    if isinstance(value, list):
        return [restore(v, mapping) for v in value]
    if isinstance(value, dict):
        return {k: restore(v, mapping) for k, v in value.items()}
    fields = getattr(type(value), "model_fields", None)
    if fields:
        for name in fields:
            setattr(value, name, restore(getattr(value, name), mapping))
    return value


def redact_all(text: str) -> str:
    """Free text the student typed: mask sensitive identifiers and contact details for good."""
    text, _ = redact_sensitive(text)
    text, mapping = redact_contacts(text)
    for key in mapping:
        text = text.replace(key, key.split("_")[0] + "]")  # [EMAIL_1] -> [EMAIL]
    return text
