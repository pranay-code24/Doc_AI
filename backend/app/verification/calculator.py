import re
from typing import Any

from app.llm.ollama_client import call_ollama_json
from app.verification.quote_matcher import QuoteMatcher, extract_numbers


CALC_TRIGGER_RE = re.compile(
    r"\b(calculate|calculation|compute|emi|monthly\s+installment|total\s+penalty|late\s+payment\s+penalty|"
    r"how\s+much|processing\s+fee\s+for|foreclosure\s+fee\s+for|total\s+fee|kitna|kitni|penalty\s+for)\b",
    re.IGNORECASE,
)


CALC_SCHEMA = {
    "type": "object",
    "properties": {
        "needs_calculation": {"type": "boolean"},
        "operation": {
            "type": "string",
            "enum": ["late_penalty", "emi", "percentage_fee", "none"],
        },
        "principal_or_amount": {"type": "number"},
        "rate_percent": {"type": "number"},
        "months": {"type": "number"},
        "min_fee": {"type": "number"},
        "evidence_index": {"type": "integer"},
    },
    "required": [
        "needs_calculation",
        "operation",
        "principal_or_amount",
        "rate_percent",
        "months",
        "min_fee",
        "evidence_index",
    ],
}


CALC_SYSTEM_PROMPT = """You are a financial calculation parameter extractor.
ONLY extract parameters from the USER QUESTION and numbered ACTIVE EVIDENCE passages. NEVER invent rates.

Supported operations:
1. "late_penalty": User gives an overdue EMI amount and overdue months; evidence gives monthly late payment penalty %.
   - principal_or_amount = overdue EMI amount (e.g., 20000)
   - rate_percent = active monthly penalty % (e.g., 3.0)
   - months = overdue months (e.g., 2)
   - min_fee = 0
2. "emi": User asks for monthly EMI given a loan principal and tenure in months; evidence gives active annual interest rate %.
   - principal_or_amount = loan principal (e.g., 500000)
   - rate_percent = active annual interest rate % (e.g., 11.25)
   - months = tenure in months (e.g., 24)
   - min_fee = 0
3. "percentage_fee": User asks for processing fee or foreclosure fee on a given amount.
   - principal_or_amount = loan/principal amount
   - rate_percent = fee % from fee table (e.g., 1.5 or 3.0)
   - months = 0
   - min_fee = minimum fee if stated in table (e.g., 1500), else 0
4. "none": If no arithmetic calculation is needed.

Set "evidence_index" to the integer number (1, 2, 3...) of the ACTIVE EVIDENCE block that contains rate_percent.
"""


def looks_like_calculation(question: str) -> bool:
    has_number = bool(re.search(r"\d", question))
    has_trigger = bool(CALC_TRIGGER_RE.search(question))
    return has_number and has_trigger


class ClauseCalculator:
    def __init__(self, quote_matcher: QuoteMatcher):
        self.quote_matcher = quote_matcher

    def try_calculate(
        self,
        question: str,
        resolved_chunks: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not looks_like_calculation(question):
            return None

        active_chunks = [c for c in resolved_chunks if c.get("is_active", True)][:6]
        if not active_chunks:
            return None

        evidence_text = "\n\n".join(
            f"[EVIDENCE {idx} | {c['doc_name']} | Page {c['page_number']}]\n{c['text']}"
            for idx, c in enumerate(active_chunks, start=1)
        )

        params = call_ollama_json(
            system_prompt=CALC_SYSTEM_PROMPT,
            user_prompt=f"USER QUESTION:\n{question}\n\nACTIVE EVIDENCE:\n{evidence_text}",
            json_schema=CALC_SCHEMA,
        )

        op = params.get("operation", "none")
        if not params.get("needs_calculation") or op == "none":
            return None

        amount = float(params.get("principal_or_amount", 0.0))
        rate = float(params.get("rate_percent", 0.0))
        months = float(params.get("months", 0.0))
        min_fee = float(params.get("min_fee", 0.0))
        ev_idx = int(params.get("evidence_index", 1))

        if amount <= 0 or rate <= 0:
            return None

        # Pick the exact chunk from active_chunks & verify rate_percent exists inside it!
        chosen_chunk = None
        if 1 <= ev_idx <= len(active_chunks):
            cand = active_chunks[ev_idx - 1]
            nums = extract_numbers(cand["text"])
            if f"{rate:g}%" in nums or f"{rate:g}" in nums:
                chosen_chunk = cand

        # Fallback: scan active_chunks for the exact rate_percent
        if chosen_chunk is None:
            for cand in active_chunks:
                nums = extract_numbers(cand["text"])
                if f"{rate:g}%" in nums or f"{rate:g}" in nums:
                    chosen_chunk = cand
                    break

        if chosen_chunk is None:
            return None

        doc_name = chosen_chunk["doc_name"]
        page_num = int(chosen_chunk["page_number"])
        quote = chosen_chunk["text"]
        q_check = self.quote_matcher.verify_quote(doc_name, page_num, quote)

        citation = {
            "doc_name": doc_name,
            "page_number": page_num,
            "verbatim_quote": quote,
            "bboxes": chosen_chunk.get("bboxes") or q_check["bboxes"],
            "page_width": chosen_chunk.get("page_width") or q_check["page_width"],
            "page_height": chosen_chunk.get("page_height") or q_check["page_height"],
        }

        if op == "late_penalty":
            if months <= 0:
                months = 1.0
            penalty = round(amount * (rate / 100.0) * months, 2)
            return {
                "operation": "Late Payment Penalty",
                "formula": "Penalty = Overdue EMI × (Monthly Penalty Rate / 100) × Overdue Months",
                "inputs": {
                    "Overdue EMI Amount": f"INR {amount:,.2f} (from question)",
                    "Active Monthly Penalty Rate": f"{rate:g}% per month ({doc_name}, p.{page_num})",
                    "Overdue Duration": f"{months:g} month(s) (from question)",
                },
                "steps": [
                    f"1. Monthly penalty on INR {amount:,.2f} at {rate:g}% = INR {amount * (rate / 100.0):,.2f}",
                    f"2. Total penalty for {months:g} month(s) = INR {amount * (rate / 100.0):,.2f} × {months:g} = INR {penalty:,.2f}",
                ],
                "result": f"INR {penalty:,.2f}",
                "numeric_result": penalty,
                "citation": citation,
            }

        if op == "emi":
            if months <= 0:
                return None
            r = rate / (12.0 * 100.0)
            n = int(round(months))
            factor = (1.0 + r) ** n
            emi = round((amount * r * factor) / (factor - 1.0), 2)
            total_payment = round(emi * n, 2)
            total_interest = round(total_payment - amount, 2)
            return {
                "operation": "Monthly Loan EMI (Reducing Balance)",
                "formula": "EMI = [P × r × (1 + r)^n] / [(1 + r)^n - 1], where r = Annual Rate / (12 × 100)",
                "inputs": {
                    "Loan Principal (P)": f"INR {amount:,.2f} (from question)",
                    "Active Annual Interest Rate": f"{rate:g}% p.a. ({doc_name}, p.{page_num})",
                    "Tenure (n)": f"{n} months (from question)",
                },
                "steps": [
                    f"1. Monthly interest rate r = {rate:g}% / 12 = {r:.6f}",
                    f"2. Compound factor (1 + r)^{n} = {factor:.6f}",
                    f"3. Monthly EMI = ({amount:,.2f} × {r:.6f} × {factor:.6f}) / ({factor - 1.0:.6f}) = INR {emi:,.2f}",
                    f"4. Total Payable over {n} months = INR {total_payment:,.2f} (Total Interest = INR {total_interest:,.2f})",
                ],
                "result": f"INR {emi:,.2f} / month",
                "numeric_result": emi,
                "citation": citation,
            }

        if op == "percentage_fee":
            raw_fee = round(amount * (rate / 100.0), 2)
            final_fee = max(raw_fee, min_fee)
            steps = [
                f"1. Percentage fee = INR {amount:,.2f} × {rate:g}% = INR {raw_fee:,.2f}",
            ]
            if min_fee > 0:
                steps.append(
                    f"2. Apply minimum fee floor (INR {min_fee:,.2f}): max(INR {raw_fee:,.2f}, INR {min_fee:,.2f}) = INR {final_fee:,.2f}"
                )
            return {
                "operation": "Clause Percentage Fee",
                "formula": "Fee = max(Amount × Rate%, Minimum Fee)",
                "inputs": {
                    "Base Amount": f"INR {amount:,.2f} (from question)",
                    "Applicable Fee Rate": f"{rate:g}% ({doc_name}, p.{page_num})",
                    "Minimum Fee": f"INR {min_fee:,.2f}" if min_fee > 0 else "None",
                },
                "steps": steps,
                "result": f"INR {final_fee:,.2f}",
                "numeric_result": final_fee,
                "citation": citation,
            }

        return None