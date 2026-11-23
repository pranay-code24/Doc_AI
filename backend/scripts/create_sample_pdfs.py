from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)

# Output folder set karo: zero-guessing-doc-ai/sample_docs
BASE_DIR = Path(__file__).resolve().parent.parent.parent
SAMPLE_DIR = BASE_DIR / "sample_docs"
SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

styles = getSampleStyleSheet()
TITLE = styles["Title"]
H2 = styles["Heading2"]
BODY = styles["Normal"]


def make_table(data, col_widths):
    table = Table(data, colWidths=col_widths)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F9FAFB")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def build_doc_a():
    path = SAMPLE_DIR / "DocA_Loan_Policy_2023.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    story = [
        Paragraph("Apex National Bank - Retail Personal Loan Policy", TITLE),
        Paragraph("<b>Document ID:</b> POL-2023-01 | <b>Effective Date:</b> 2023-04-01", BODY),
        Spacer(1, 12),

        Paragraph("Section 1: Scope and Definitions", H2),
        Paragraph(
            "This master policy governs all retail unsecured personal loans issued by Apex National Bank "
            "across India starting April 1, 2023. All branches must strictly adhere to the eligibility "
            "criteria, interest schedules, and penalty clauses specified below.",
            BODY,
        ),
        Spacer(1, 10),

        Paragraph("Clause 3.1: Applicant Eligibility", H2),
        Paragraph(
            "To qualify for a Retail Personal Loan, the primary applicant must be a resident Indian citizen "
            "with a minimum age of 21 years at the time of application and a maximum age of 60 years at loan "
            "maturity. The applicant must have a minimum net monthly income of INR 30,000.",
            BODY,
        ),
        Spacer(1, 10),

        Paragraph("Clause 4.2: Base Interest Rate", H2),
        Paragraph(
            "The standard annual interest rate applicable on all approved Retail Personal Loans shall be "
            "9.50% per annum on a reducing balance basis.",
            BODY,
        ),
        Spacer(1, 10),

        Paragraph("Clause 5.1: Late Payment Penalty", H2),
        Paragraph(
            "If an EMI remains unpaid beyond the 5-day grace period from the due date, a late payment "
            "penalty of 2.0% per month shall be levied on the overdue EMI amount.",
            BODY,
        ),
        Spacer(1, 12),

        # Page 2 start (multi-page retrieval test karne ke liye)
        PageBreak(),

        Paragraph("Clause 6.1: Loan Amount and Repayment Tenure", H2),
        Paragraph(
            "Eligible applicants may borrow between INR 50,000 and INR 15,00,000. The maximum repayment "
            "tenure allowed under this policy is 60 months from the date of disbursement.",
            BODY,
        ),
        Spacer(1, 12),

        Paragraph("Clause 7.1: Schedule of Standard Fees and Charges", H2),
        Spacer(1, 6),
        make_table(
            [
                ["Fee Type", "Applicable Rate / Amount", "Remarks"],
                ["Processing Fee", "1.5% of Loan Amount", "Minimum INR 1,500"],
                ["Bounce Charge", "INR 500 per instance", "For dishonoured NACH/ECS"],
                ["Foreclosure Fee", "3.0% of Principal Outstanding", "Allowed after 12 EMIs"],
                ["Statement Copy Fee", "INR 250", "Physical branch copy"],
            ],
            col_widths=[140, 170, 170],
        ),
        Spacer(1, 12),
        Paragraph(
            "Note: Policy terms may be revised periodically via official numbered bank circulars.",
            BODY,
        ),
    ]
    doc.build(story)
    print(f"Created: {path.name}")


def build_doc_b():
    path = SAMPLE_DIR / "DocB_Circular_2024.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    story = [
        Paragraph("Apex National Bank - Regulatory Circular (First Amendment)", TITLE),
        Paragraph(
            "<b>Document ID:</b> CIRC-2024-07 | <b>Effective Date:</b> 2024-04-01 | "
            "<b>Amends:</b> POL-2023-01 (DocA_Loan_Policy_2023.pdf)",
            BODY,
        ),
        Spacer(1, 12),

        Paragraph("Subject: Revision of Interest Rate and Late Payment Penalty", H2),
        Paragraph(
            "Pursuant to revised funding costs, this circular formally amends Document ID POL-2023-01 "
            "(Retail Personal Loan Policy dated 2023-04-01) with effect from April 1, 2024.",
            BODY,
        ),
        Spacer(1, 10),

        Paragraph("Amendment to Clause 4.2 (Base Interest Rate)", H2),
        Paragraph(
            "Clause 4.2 of POL-2023-01 is hereby superseded. Effective April 1, 2024, the standard annual "
            "interest rate applicable on all Retail Personal Loans is revised from 9.50% per annum to "
            "10.50% per annum on a reducing balance basis.",
            BODY,
        ),
        Spacer(1, 10),

        Paragraph("Amendment to Clause 5.1 (Late Payment Penalty)", H2),
        Paragraph(
            "Clause 5.1 of POL-2023-01 is hereby superseded. Effective April 1, 2024, the late payment "
            "penalty for overdue EMIs beyond the 5-day grace period is increased from 2.0% per month to "
            "3.0% per month on the overdue EMI amount.",
            BODY,
        ),
        Spacer(1, 10),

        Paragraph("Unchanged Provisions", H2),
        Paragraph(
            "All other clauses of POL-2023-01, including eligibility and fee schedules, remain unchanged "
            "unless modified by a subsequent circular.",
            BODY,
        ),
    ]
    doc.build(story)
    print(f"Created: {path.name}")


def build_doc_c():
    path = SAMPLE_DIR / "DocC_Circular_2025.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    story = [
        Paragraph("Apex National Bank - Regulatory Circular (Second Amendment)", TITLE),
        Paragraph(
            "<b>Document ID:</b> CIRC-2025-12 | <b>Effective Date:</b> 2025-04-01 | "
            "<b>Amends:</b> CIRC-2024-07 (DocB_Circular_2024.pdf)",
            BODY,
        ),
        Spacer(1, 12),

        Paragraph("Subject: Further Revision of Retail Personal Loan Interest Rate", H2),
        Paragraph(
            "This circular formally amends Document ID CIRC-2024-07 (First Amendment dated 2024-04-01), "
            "which had previously amended POL-2023-01. The changes below take effect on April 1, 2025.",
            BODY,
        ),
        Spacer(1, 10),

        Paragraph("Amendment to Clause 4.2 (Base Interest Rate)", H2),
        Paragraph(
            "Clause 4.2 as amended by CIRC-2024-07 is hereby superseded. Effective April 1, 2025, the "
            "currently applicable standard annual interest rate on Retail Personal Loans shall be "
            "11.25% per annum on a reducing balance basis.",
            BODY,
        ),
        Spacer(1, 10),

        Paragraph("Retention of Late Payment Penalty", H2),
        Paragraph(
            "The late payment penalty of 3.0% per month established under CIRC-2024-07 remains active "
            "and unchanged.",
            BODY,
        ),
    ]
    doc.build(story)
    print(f"Created: {path.name}")


def build_doc_d():
    path = SAMPLE_DIR / "DocD_Partner_Addendum_2025.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    story = [
        Paragraph("Apex National Bank - Digital Sourcing Partner Addendum", TITLE),
        Paragraph("<b>Document ID:</b> ADD-2025-03 | <b>Effective Date:</b> 2025-05-01", BODY),
        Spacer(1, 12),

        Paragraph("Section 1: Digital Loan Origination Terms", H2),
        Paragraph(
            "This addendum defines operational guidelines for Retail Personal Loans sourced through "
            "authorized digital lending partners.",
            BODY,
        ),
        Spacer(1, 10),

        # Deliberate Contradiction #1: Age (Doc A says 21, Doc D says 25 without superseding!)
        Paragraph("Clause 2.1: Borrower Age Requirement", H2),
        Paragraph(
            "Every applicant applying for a Retail Personal Loan must have a minimum age of 25 years "
            "at the time of application. Applications from individuals below 25 years shall be rejected.",
            BODY,
        ),
        Spacer(1, 10),

        # Deliberate Contradiction #2: Max Tenure (Doc A says 60 months, Doc D says 48 months!)
        Paragraph("Clause 2.2: Maximum Loan Repayment Tenure", H2),
        Paragraph(
            "The maximum repayment tenure permitted for any Retail Personal Loan shall not exceed "
            "48 months from the date of disbursement.",
            BODY,
        ),
        Spacer(1, 10),

        # Extra Fee Table (for calculation tests)
        Paragraph("Clause 3.1: Digital Convenience and Late Fee Cap", H2),
        Spacer(1, 6),
        make_table(
            [
                ["Parameter", "Rule / Value"],
                ["Digital Onboarding Fee", "INR 750 flat"],
                ["Minimum Monthly Income", "INR 30,000"],
                ["Grace Period for EMI", "5 calendar days"],
            ],
            col_widths=[200, 280],
        ),
    ]
    doc.build(story)
    print(f"Created: {path.name}")


if __name__ == "__main__":
    build_doc_a()
    build_doc_b()
    build_doc_c()
    build_doc_d()
    print(f"\nAll 4 sample PDFs saved inside: {SAMPLE_DIR}")