import pytest

from app.config import get_settings
from app.llm import client
from app.services import pii, resume_parser


# ---------- sensitive identifiers ----------

@pytest.mark.parametrize(
    "text,label",
    [
        ("My Aadhaar is 2345 6789 0123.", "AADHAAR"),
        ("PAN: ABCDE1234F", "PAN"),
        ("card 4111 1111 1111 1111 expires soon", "CARD_NUMBER"),
        ("IFSC SBIN0001234", "IFSC"),
        ("A/c no: 123456789012", "BANK_ACCOUNT"),
        ("DOB: 12/05/2002", "DATE_OF_BIRTH"),
        ("SSN 123-45-6789", "SSN"),
        ("passport K1234567", "PASSPORT"),
    ],
)
def test_sensitive_identifiers_are_masked(text, label):
    out, counts = pii.redact_sensitive(text)
    assert f"[REDACTED_{label}]" in out and counts.get(label) == 1


def test_ordinary_numbers_are_left_alone():
    text = "Stipend 20000-30000 per month, 2019-2023, CGPA 8.4, 3 months, version 1.2.3, 12 weeks"
    assert pii.redact_sensitive(text) == (text, {})
    assert pii.redact_all(text) == text


def test_a_random_16_digit_number_is_not_a_card():
    text = "order 1234 1234 1234 1234"  # fails the Luhn check
    assert pii.redact_sensitive(text)[0] == text


def test_labels_are_kept_for_account_and_dob():
    out, _ = pii.redact_sensitive("Bank account number: 123456789012 and date of birth 1 May 2002")
    assert out.startswith("Bank account number: [REDACTED_BANK_ACCOUNT]") and "date of birth [REDACTED_DATE_OF_BIRTH]" in out


# ---------- contact details ----------

def test_contacts_are_replaced_and_can_be_restored():
    text = "Reach me on +91 98765 43210 or 98765-43210, asha@example.com"
    masked, mapping = pii.redact_contacts(text)
    assert "asha@example.com" not in masked and "98765" not in masked
    assert set(mapping) == {"[EMAIL_1]", "[PHONE_1]", "[PHONE_2]"}
    assert pii.restore(masked, mapping) == text


def test_same_value_gets_the_same_placeholder():
    masked, mapping = pii.redact_contacts("a@example.com and again a@example.com")
    assert masked == "[EMAIL_1] and again [EMAIL_1]" and len(mapping) == 1


def test_redact_all_masks_everything_for_good():
    out = pii.redact_all("Call +91 98765 43210, mail asha@example.com, PAN ABCDE1234F")
    assert out == "Call [PHONE], mail [EMAIL], PAN [REDACTED_PAN]"


def test_restore_walks_models_lists_and_dicts():
    data = resume_parser.ResumeData()
    data.personal.email = "[EMAIL_1]"
    data.achievements = ["Reach [EMAIL_1]"]
    pii.restore(data, {"[EMAIL_1]": "a@example.com"})
    assert data.personal.email == "a@example.com" and data.achievements == ["Reach a@example.com"]
    assert pii.restore({"k": ["[EMAIL_1]"]}, {"[EMAIL_1]": "x"}) == {"k": ["x"]}


# ---------- applied at the boundaries ----------

def test_every_prompt_is_masked_before_it_reaches_a_provider(monkeypatch):
    seen = {}

    def fake_provider(prompt, schema, system, temperature, thinking, attempts):
        seen["prompt"], seen["system"] = prompt, system
        return "ok"

    s = get_settings()
    monkeypatch.setattr(s, "gemini_api_key", "k")
    monkeypatch.setattr(s, "llm_providers", "gemini")
    monkeypatch.setitem(client._PROVIDERS, "gemini", (lambda: "k", fake_provider))
    client.generate_text("my pan is ABCDE1234F and card 4111 1111 1111 1111", system="aadhaar 2345 6789 0123")
    assert "ABCDE1234F" not in seen["prompt"] and "4111" not in seen["prompt"] and "[REDACTED_PAN]" in seen["prompt"]
    assert "6789" not in seen["system"]


def test_masking_can_be_switched_off(monkeypatch):
    seen = {}
    s = get_settings()
    monkeypatch.setattr(s, "pii_redaction", False)
    monkeypatch.setattr(s, "llm_providers", "gemini")
    monkeypatch.setitem(client._PROVIDERS, "gemini", (lambda: "k", lambda p, *a: seen.setdefault("p", p) or "ok"))
    client.generate_text("PAN ABCDE1234F")
    assert seen["p"] == "PAN ABCDE1234F"


def test_resume_parsing_never_shows_the_provider_the_real_contacts(monkeypatch):
    seen = {}

    def fake(prompt, schema, **kw):
        seen["prompt"], seen["system"] = prompt, kw.get("system", "")
        d = resume_parser.ResumeData()
        d.personal.name = "Asha Verma"
        d.personal.email = "[EMAIL_1]"
        d.personal.phone = "[PHONE_1]"
        d.skills.technical = ["Python"]
        return d

    monkeypatch.setattr(resume_parser, "generate_structured", fake)
    text = "Asha Verma\nasha.verma@example.com | +91 98765 43210\nSkills: Python"
    result = resume_parser.parse_resume(text)
    assert "asha.verma@example.com" not in seen["prompt"] and "98765" not in seen["prompt"]
    assert "[EMAIL_1]" in seen["prompt"] and "placeholders" in seen["system"]
    assert result.data.personal.email == "asha.verma@example.com" and result.data.personal.phone == "+91 98765 43210"
    assert result.method == "llm" and result.data.skills.technical == ["Python"]
