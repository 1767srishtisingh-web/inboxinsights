# modules/pdf_generator.py
"""
Generates a clean, structured, per-user PDF report.
Uses fpdf2 — 100% free, no external services, no subscriptions.
"""

import os
from datetime import datetime
from fpdf import FPDF
from config.settings import OUTPUT_DIR

PRIORITY_COLOR = {
    "High": (180, 0, 0),
    "Medium": (180, 120, 0),
    "Low": (0, 120, 60),
}
CATEGORY_COLOR = {
    "Work": (0, 82, 165),
    "Personal": (0, 140, 70),
    "Finance": (180, 80, 0),
}


def _safe(text) -> str:
    """
    Core PDF fonts (Helvetica) only support latin-1. Real email subjects,
    senders, and AI summaries can contain arbitrary unicode (smart quotes,
    em dashes, emoji, non-Latin scripts) which would otherwise crash PDF
    generation entirely. Replace anything unsupported instead of failing.
    """
    if text is None:
        return ""
    return str(text).encode("latin-1", errors="replace").decode("latin-1")


class EmailReportPDF(FPDF):
    """Custom FPDF subclass with branded header/footer."""

    def __init__(self, user_name: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_name = user_name

    def header(self):
        self.set_font("Helvetica", "B", 12)
        self.set_fill_color(30, 30, 60)
        self.set_text_color(255, 255, 255)
        self.cell(0, 10, _safe(f"  Inbox Insights - {self.user_name}"), fill=True, ln=True)
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(130, 130, 130)
        self.cell(0, 10, f"Page {self.page_no()} | Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}", align="C")

    def section_title(self, title: str, color=(30, 30, 60)):
        self.set_fill_color(*color)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 7, _safe(f"  {title}"), fill=True, ln=True)
        self.set_text_color(0, 0, 0)
        self.ln(1)

    def kv_row(self, key: str, value: str):
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "B", 9)
        self.cell(35, 6, _safe(key) + ":", ln=False)
        self.set_font("Helvetica", "", 9)
        self.multi_cell(0, 6, _safe(value))
        self.set_x(self.l_margin)

    def bullet(self, text: str, indent: int = 8):
        self.set_font("Helvetica", "", 9)
        self.set_x(self.l_margin + indent)
        self.cell(5, 5, chr(149), ln=False)
        self.multi_cell(0, 5, _safe(text))
        self.set_x(self.l_margin)


def generate_pdf(user_name: str, gmail_accounts: list, emails: list, filename: str = None) -> str:
    """
    Build a PDF report for ONE user from their (already summarized) emails.

    Args:
        user_name:      Display name for the report header.
        gmail_accounts: List of account dicts used to produce this report
                         (for the "Gmail accounts used" line).
        emails:         List of email dicts, each with an 'ai' key from
                         ai_summarizer.summarize_all().
        filename:       Optional explicit output path.

    Returns:
        Path to the saved PDF file.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if not filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() else "_" for c in user_name)
        filename = os.path.join(OUTPUT_DIR, f"{safe_name}_report_{ts}.pdf")

    pdf = EmailReportPDF(user_name=user_name, orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # ── Cover summary ─────────────────────────────
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, f"Email Summary  -  {datetime.now().strftime('%A, %d %B %Y')}", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, _safe(f"User: {user_name}"), ln=True)
    pdf.cell(0, 6, f"Total emails processed: {len(emails)}", ln=True)

    account_labels = ", ".join(a.get("label", a["alias"]) for a in gmail_accounts) or "None"
    pdf.multi_cell(0, 6, _safe(f"Gmail accounts used: {account_labels}"))

    # Count by category and priority
    cats, priorities = {}, {"High": 0, "Medium": 0, "Low": 0}
    for e in emails:
        cats[e.get("category", "General")] = cats.get(e.get("category", "General"), 0) + 1
        p = e.get("ai", {}).get("priority", "Medium")
        priorities[p] = priorities.get(p, 0) + 1

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5, "By category:", ln=True)
    pdf.set_font("Helvetica", "", 9)
    for cat, count in cats.items():
        pdf.set_x(pdf.l_margin + 6)
        pdf.cell(0, 5, f"- {cat}: {count}", ln=True)

    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5, "By priority:", ln=True)
    pdf.set_font("Helvetica", "", 9)
    for p in ("High", "Medium", "Low"):
        pdf.set_x(pdf.l_margin + 6)
        pdf.cell(0, 5, f"- {p}: {priorities[p]}", ln=True)
    pdf.ln(4)

    # ── Per-email sections ────────────────────────
    for idx, email in enumerate(emails, 1):
        ai = email.get("ai", {})
        cat = email.get("category", "General")
        priority = ai.get("priority", "Medium")

        pdf.section_title(
            f"{idx}. [{cat}] [{priority}]  {email['subject'][:60]}",
            color=CATEGORY_COLOR.get(cat, (80, 80, 80)),
        )

        pdf.kv_row("From", email.get("sender", "")[:80])
        pdf.kv_row("Date", email.get("date", "")[:60])
        pdf.kv_row("Account", email.get("account", ""))
        pdf.ln(1)

        if ai.get("summary"):
            pdf.set_font("Helvetica", "BI", 9)
            pdf.cell(0, 5, "Summary:", ln=True)
            pdf.set_font("Helvetica", "", 9)
            pdf.multi_cell(0, 5, _safe(ai["summary"]))
            pdf.ln(1)

        if ai.get("tasks"):
            pdf.set_font("Helvetica", "BI", 9)
            pdf.cell(0, 5, "Action Items:", ln=True)
            for t in ai["tasks"]:
                pdf.bullet(t)
            pdf.ln(1)

        if ai.get("deadlines"):
            pdf.set_font("Helvetica", "BI", 9)
            pdf.set_text_color(*PRIORITY_COLOR["High"])
            pdf.cell(0, 5, "Deadlines:", ln=True)
            pdf.set_text_color(0, 0, 0)
            for d in ai["deadlines"]:
                pdf.bullet(d)
            pdf.ln(1)

        if ai.get("key_points"):
            pdf.set_font("Helvetica", "BI", 9)
            pdf.cell(0, 5, "Key Points:", ln=True)
            for p in ai["key_points"]:
                pdf.bullet(p)

        pdf.ln(5)

    pdf.output(filename)
    return filename
