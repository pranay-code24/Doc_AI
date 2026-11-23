import re
from typing import Any


# 1. Prompt Injection / Jailbreak patterns
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|rules|prompts)",
    r"disregard\s+(all\s+)?(previous|prior|system)",
    r"reveal\s+(your\s+)?(system\s+prompt|instructions|hidden\s+prompt)",
    r"pretend\s+(you\s+are|to\s+be)",
    r"\b(jailbreak|dan\s+mode|developer\s+mode|bypass\s+guardrails)\b",
    r"forget\s+(everything|all\s+rules|your\s+instructions)",
    r"override\s+(verification|safety|rules|policy)",
]
INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)

# 2. Pure General Math (e.g. "2+2", "what is 2 + 2?", "15 * 4")
PURE_MATH_RE = re.compile(
    r"^\s*(?:what\s+is|whats|calculate|solve|evaluate|kitna\s+hota\s+hai|kitna\s+hai)?\s*"
    r"[\d.,\s+\-*/×÷^()%]+=\s*\??\s*$"
    r"|^\s*(?:what\s+is|whats|calculate|solve|evaluate)?\s*\d+(?:\.\d+)?\s*[+\-*/×÷^]\s*\d+(?:\.\d+)?(?:\s*[+\-*/×÷^]\s*\d+(?:\.\d+)?)*\s*\??\s*$",
    re.IGNORECASE,
)

# 3. Greetings / Chit-chat / General Knowledge outside documents
CHITCHAT_RE = re.compile(
    r"^\s*(hi|hello|hey|namaste|namaskar|good\s+morning|good\s+evening|how\s+are\s+you|"
    r"who\s+are\s+you|tell\s+me\s+a\s+joke|write\s+a\s+poem|thanks|thank\s+you)\s*[!?.]*\s*$",
    re.IGNORECASE,
)

# Document-domain keywords (if present, NEVER block as pure math/chitchat)
DOMAIN_KEYWORDS_RE = re.compile(
    r"\b(loan|emi|interest|rate|fee|fees|penalty|policy|clause|section|tenure|age|income|"
    r"document|pdf|circular|addendum|foreclosure|processing|bounce|grace|bank|rupees|inr|"
    r"byaj|karz|mahine|saal|overdue|principal|borrower|applicant)\b"
    r"|(ब्याज|लोन|किस्त|पेनल्टी|शुल्क|आय|उम्र|अवधि|व्याज|कर्ज|தவணை|வட்டி|వడ్డీ|সুদ)",
    re.IGNORECASE,
)

# 4. PII Patterns (Indian Banking Privacy Protection)
PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
AADHAAR_RE = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


LOCALIZED_MESSAGES = {
    "math_out_of_scope": {
        "en": (
            "I cannot answer general math like '{q}' because this is a strict Zero-Guessing Document AI "
            "that only uses proof from your uploaded PDFs—not outside knowledge. "
            "If you want a calculation based on your document's rules (like EMI, late penalty, or processing fee), "
            "please mention the loan/policy term (e.g., 'Calculate penalty on INR 20,000 overdue EMI for 2 months')."
        ),
        "hi": (
            "मैं '{q}' जैसे सामान्य गणित का जवाब नहीं दे सकता क्योंकि यह Zero-Guessing Document AI "
            "सिर्फ आपके अपलोड किए गए दस्तावेज़ों के सबूत से ही जवाब देता है, बाहर की जानकारी से नहीं। "
            "अगर आप दस्तावेज़ के नियम के हिसाब से EMI, लेट पेनल्टी या प्रोसेसिंग फीस निकालना चाहते हैं, "
            "तो कृपया लोन या पॉलिसी का ज़िक्र करें (जैसे: '20,000 रुपये की EMI 2 महीने लेट होने पर पेनल्टी कितनी लगेगी?')।"
        ),
        "mr": (
            "मी '{q}' सारख्या सामान्य गणिताचे उत्तर देऊ शकत नाही कारण हे Zero-Guessing Document AI "
            "फक्त तुमच्या अपलोड केलेल्या कागदपत्रांमधील पुराव्यावरूनच उत्तर देते. "
            "जर तुम्हाला कागदपत्रांतील नियमांनुसार EMI किंवा लेट पेनल्टी काढायची असेल, तर कृपया कर्ज/पॉलिसीचा उल्लेख करा."
        ),
    },
    "chitchat": {
        "en": (
            "Hello! I am a Zero-Guessing Document Verification Assistant. I only answer questions backed by exact "
            "proof in your uploaded PDFs. Please ask a question about your documents (for example: interest rate, "
            "fees, eligibility, tenure, or EMI calculation)."
        ),
        "hi": (
            "नमस्ते! मैं एक Zero-Guessing Document AI सहायक हूँ। मैं सिर्फ आपके अपलोड किए गए कागज़ात के "
            "पक्के सबूत के आधार पर ही जवाब देता हूँ। कृपया अपने दस्तावेज़ से जुड़ा सवाल पूछें "
            "(जैसे: ब्याज दर, फीस, उम्र की शर्त, या EMI की गणना)।"
        ),
        "mr": (
            "नमस्कार! मी Zero-Guessing Document AI सहाय्यक आहे. मी फक्त तुमच्या अपलोड केलेल्या कागदपत्रांतील "
            "पुराव्यावरूनच उत्तरे देतो. कृपया तुमच्या दस्तऐवजाशी संबंधित प्रश्न विचारा."
        ),
    },
    "injection": {
        "en": (
            "Request blocked by Prompt Injection Guardrail. Attempting to override verification rules, "
            "system prompts, or grounding policies is not permitted."
        ),
        "hi": (
            "सुरक्षा गार्डरेल (Prompt Injection Guard) द्वारा यह अनुरोध रोक दिया गया है। "
            "सत्यापन नियमों (verification rules) को बदलने की अनुमति नहीं है।"
        ),
    },
}


def _pick_msg(category: str, language: str, q: str = "") -> str:
    bucket = LOCALIZED_MESSAGES[category]
    lang = language if language in bucket else ("hi" if language in ("mr", "gu", "pa") and "hi" in bucket else "en")
    if language in bucket:
        lang = language
    return bucket[lang].format(q=q)


def check_input_guardrails(question: str, language: str = "auto") -> dict[str, Any]:
    """
    Runs 4 deterministic < 5ms Input Guardrails BEFORE touching any LLM:
      1. Length & Empty Check
      2. Prompt Injection / Jailbreak Detection
      3. PII Masking (PAN / Aadhaar / Email redaction)
      4. Closed-Book Scope Check (blocks '2+2' general math & chit-chat)
    """
    raw_q = (question or "").strip()
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []

    # Check 1: Empty / Length
    if not raw_q or len(raw_q) > 1500:
        checks.append({"name": "Input Length Guard", "status": "BLOCKED", "detail": "Empty or >1500 chars"})
        return {
            "allowed": False,
            "block_type": "invalid_length",
            "sanitized_question": raw_q,
            "message": "Please enter a valid question between 1 and 1500 characters.",
            "warnings": warnings,
            "checks": checks,
        }
    checks.append({"name": "Input Length Guard", "status": "PASSED", "detail": f"{len(raw_q)} chars"})

    # Check 2: Prompt Injection Guard
    if INJECTION_RE.search(raw_q):
        checks.append({
            "name": "Prompt Injection Guard",
            "status": "BLOCKED",
            "detail": "Detected instruction override / jailbreak attempt",
        })
        return {
            "allowed": False,
            "block_type": "prompt_injection",
            "sanitized_question": raw_q,
            "message": _pick_msg("injection", language),
            "warnings": warnings,
            "checks": checks,
        }
    checks.append({"name": "Prompt Injection Guard", "status": "PASSED", "detail": "No injection pattern"})

    # Check 3: PII Redaction Guard
    sanitized = raw_q
    pii_found: list[str] = []
    if PAN_RE.search(sanitized):
        sanitized = PAN_RE.sub("[REDACTED_PAN]", sanitized)
        pii_found.append("PAN")
    if AADHAAR_RE.search(sanitized):
        sanitized = AADHAAR_RE.sub("[REDACTED_AADHAAR]", sanitized)
        pii_found.append("Aadhaar/12-digit ID")
    if EMAIL_RE.search(sanitized):
        sanitized = EMAIL_RE.sub("[REDACTED_EMAIL]", sanitized)
        pii_found.append("Email")

    if pii_found:
        w = f"Privacy Guard redacted sensitive PII ({', '.join(pii_found)}) before processing."
        warnings.append(w)
        checks.append({"name": "PII Privacy Guard", "status": "REDACTED", "detail": ", ".join(pii_found)})
    else:
        checks.append({"name": "PII Privacy Guard", "status": "PASSED", "detail": "No personal IDs exposed"})

    # Check 4: Closed-Book Scope Guard (General Math like '2+2' & Chit-Chat)
    has_domain_context = bool(DOMAIN_KEYWORDS_RE.search(sanitized))
    if not has_domain_context and PURE_MATH_RE.match(sanitized):
        checks.append({
            "name": "Closed-Book Scope Guard",
            "status": "BLOCKED",
            "detail": "General arithmetic outside uploaded documents (Zero-Guessing rule enforced)",
        })
        return {
            "allowed": False,
            "block_type": "general_math_out_of_scope",
            "sanitized_question": sanitized,
            "message": _pick_msg("math_out_of_scope", language, q=sanitized),
            "warnings": warnings,
            "checks": checks,
        }

    if not has_domain_context and CHITCHAT_RE.match(sanitized):
        checks.append({
            "name": "Closed-Book Scope Guard",
            "status": "BLOCKED",
            "detail": "Chit-chat / non-document query redirected",
        })
        return {
            "allowed": False,
            "block_type": "chitchat_out_of_scope",
            "sanitized_question": sanitized,
            "message": _pick_msg("chitchat", language),
            "warnings": warnings,
            "checks": checks,
        }

    checks.append({"name": "Closed-Book Scope Guard", "status": "PASSED", "detail": "Valid document query"})
    return {
        "allowed": True,
        "block_type": None,
        "sanitized_question": sanitized,
        "message": "",
        "warnings": warnings,
        "checks": checks,
    }


def validate_pdf_upload(filename: str, content: bytes, max_mb: int = 25) -> tuple[bool, str]:
    """Upload Security Guard: verifies extension, file size, and actual %PDF- magic bytes."""
    if not filename or not filename.lower().endswith(".pdf"):
        return False, f"Only .pdf files are allowed: {filename}"
    if len(content) > max_mb * 1024 * 1024:
        return False, f"File exceeds {max_mb}MB limit: {filename}"
    if not content[:5].startswith(b"%PDF-"):
        return False, f"Security Guard blocked '{filename}': invalid PDF header (not a real PDF)."
    return True, "OK"