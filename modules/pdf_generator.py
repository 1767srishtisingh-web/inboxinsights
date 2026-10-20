"""
modules/pdf_generator.py — Clean, tabular, minimal PDF report for Inbox Insights.

Specification:
  - Mauve heading band (#A3807E) with torn-paper zigzag bottom edge
  - Date heading (e.g. "Tuesday, 20 October 2026")
  - Small line: "user name · N emails · N deadlines"
  - ONE table with exactly 3 columns:
      #        Subject                           Deadline
      1        Assignment 3 reminder             24 Oct 2026, 11:59 PM – submit assignment
      2        Team standup notes                —
  - Subject only — NO summaries, key points, sender, body text, or priority tags.
  - Rows appear in the exact order emails were received (oldest first).
  - Deadlines highlighted in raspberry (#9A3440); "—" in cocoa (#7A5650).
  - Long subjects wrap inside their cell.
  - Table header repeats on every page.
  - "Page X of Y" footer.
  - Strip emoji; support Hindi / Devanagari subjects with uharfbuzz text shaping.
  - Self-hosted Playfair Display, Jost, and Noto Sans Devanagari fonts.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Optional

from fpdf import FPDF

from config.settings import BASE_DIR
from modules.logger import get_logger

log = get_logger(__name__)

# ─── Color Palette ────────────────────────────────────────────────────────────

MAUVE        = (163, 128, 126)  # #A3807E
ESPRESSO     = (74,  42,  38)   # #4A2A26
CREAM        = (251, 247, 241)  # #FBF7F1
SOFT_ROSE    = (242, 208, 203)  # #F2D0CB
RASPBERRY    = (154, 52,  64)   # #9A3440
COCOA        = (122, 86,  80)   # #7A5650
WHITE        = (255, 255, 255)

# ─── Geometry Constants ───────────────────────────────────────────────────────

PAGE_W       = 210              # A4 width in mm
PAGE_H       = 297              # A4 height in mm
MARGIN       = 15               # Left/right margin
CONTENT_W    = PAGE_W - 2 * MARGIN  # 180 mm

HEADER_H     = 28               # Top band height in mm
TORN_H       = 5                # Height of torn-paper teeth
TOP_MARGIN   = HEADER_H + TORN_H + 8

COL_NO_W     = 12               # 12 mm for "#"
COL_DL_W     = 58               # 58 mm for "Deadline"
COL_SUBJ_W   = CONTENT_W - COL_NO_W - COL_DL_W  # 110 mm for "Subject"

HEADER_ROW_H = 8
LINE_HEIGHT  = 5

# ─── Emoji & Script Handling ──────────────────────────────────────────────────

# Regex to strip emoji and pictographic symbols
EMOJI_REGEX = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags (iOS)
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA70-\U0001FAFF"  # symbols and pictographs extended-a
    "\U00002600-\U000026FF"  # misc symbols
    "\U00002300-\U000023FF"  # misc technical
    "]+",
    flags=re.UNICODE,
)

DEVANAGARI_REGEX = re.compile(r"[\u0900-\u097F]")


def clean_text(text: Optional[str]) -> str:
    """Strip emoji, normalize whitespace, and trim."""
    if not text:
        return ""
    # Strip emojis
    cleaned = EMOJI_REGEX.sub("", str(text))
    # Replace multiple spaces with a single space
    cleaned = re.sub(r"[ \t]+", " ", cleaned).strip()
    return cleaned


def has_devanagari(text: str) -> bool:
    """Return True if text contains any Devanagari character."""
    return bool(DEVANAGARI_REGEX.search(text))


# ─── Custom PDF Class ─────────────────────────────────────────────────────────


class ReportPDF(FPDF):
    """FPDF subclass for Inbox Insights daily email report."""

    def __init__(
        self,
        user_name: str,
        report_date_str: str,
        email_count: int,
        deadline_count: int,
        *args,
        **kwargs,
    ):
        super().__init__(orientation="P", unit="mm", format="A4", *args, **kwargs)

        self.user_name = user_name
        self.report_date_str = report_date_str
        self.email_count = email_count
        self.deadline_count = deadline_count

        self.alias_nb_pages()
        self.set_margins(MARGIN, TOP_MARGIN, MARGIN)
        self.set_auto_page_break(auto=True, margin=15)

        # Flag indicating whether custom fonts loaded successfully
        self.has_custom_fonts = False
        self.has_devanagari_font = False
        self._load_fonts()

    def _load_fonts(self):
        """Register Playfair Display, Jost, and Noto Sans Devanagari."""
        fonts_dir = os.path.join(BASE_DIR, "static", "fonts")

        playfair_reg = os.path.join(fonts_dir, "PlayfairDisplay-Regular.ttf")
        playfair_bold = os.path.join(fonts_dir, "PlayfairDisplay-Bold.ttf")
        playfair_ital = os.path.join(fonts_dir, "PlayfairDisplay-Italic.ttf")
        jost_reg = os.path.join(fonts_dir, "Jost-Regular.ttf")
        jost_bold = os.path.join(fonts_dir, "Jost-Bold.ttf")
        noto_dev = os.path.join(fonts_dir, "NotoSansDevanagari-Regular.ttf")

        try:
            if os.path.exists(playfair_reg):
                self.add_font("Playfair", "", playfair_reg)
            if os.path.exists(playfair_bold):
                self.add_font("Playfair", "B", playfair_bold)
            if os.path.exists(playfair_ital):
                self.add_font("Playfair", "I", playfair_ital)
            if os.path.exists(jost_reg):
                self.add_font("Jost", "", jost_reg)
            if os.path.exists(jost_bold):
                self.add_font("Jost", "B", jost_bold)

            self.has_custom_fonts = True
        except Exception as exc:
            log.warning("Could not load custom Latin fonts (%s), falling back to Helvetica.", exc)
            self.has_custom_fonts = False

        try:
            if os.path.exists(noto_dev):
                self.add_font("NotoDevanagari", "", noto_dev)
                self.has_devanagari_font = True
        except Exception as exc:
            log.warning("Could not load Devanagari font (%s): %s", noto_dev, exc)
            self.has_devanagari_font = False

    # ── Font Helpers ──────────────────────────────────────────────────────────

    def font_serif(self, style: str = "", size: float = 10):
        if self.has_custom_fonts:
            self.set_font("Playfair", style, size)
        else:
            self.set_font("Helvetica", style, size)

    def font_sans(self, style: str = "", size: float = 9):
        if self.has_custom_fonts:
            self.set_font("Jost", style, size)
        else:
            self.set_font("Helvetica", style, size)

    def font_for_text(self, text: str, style: str = "", size: float = 9):
        if has_devanagari(text) and self.has_devanagari_font:
            self.set_font("NotoDevanagari", "", size)
        elif self.has_custom_fonts:
            self.set_font("Jost", style, size)
        else:
            self.set_font("Helvetica", style, size)

    # ── Page Header ───────────────────────────────────────────────────────────

    def header(self):
        """Draw the mauve heading band + torn paper zigzag on every page."""
        # Mauve solid rectangle at top
        self.set_fill_color(*MAUVE)
        self.rect(0, 0, PAGE_W, HEADER_H, style="F")

        # Parse date for heading: e.g. "Tuesday, 20 October 2026"
        try:
            dt = datetime.strptime(self.report_date_str, "%Y-%m-%d")
            date_heading = dt.strftime("%A, %d %B %Y")
        except Exception:
            date_heading = self.report_date_str

        # 1. Date heading in CREAM Playfair Display
        self.set_xy(0, 7)
        self.font_serif("B", 15)
        self.set_text_color(*CREAM)
        self.cell(PAGE_W, 8, date_heading, align="C", ln=True)

        # 2. Subtitle line: "user name · N emails · N deadlines"
        subtitle = (
            f"{self.user_name}  ·  "
            f"{self.email_count} email{'s' if self.email_count != 1 else ''}  ·  "
            f"{self.deadline_count} deadline{'s' if self.deadline_count != 1 else ''}"
        )
        self.font_sans("", 9)
        self.set_text_color(245, 237, 230)
        self.cell(PAGE_W, 6, subtitle, align="C", ln=True)

        # 3. Torn paper edge at bottom of mauve band
        self._draw_torn_edge()

        # Reset cursor position
        self.set_y(TOP_MARGIN)

    def _draw_torn_edge(self):
        """Draw triangular cream teeth at the bottom edge of the mauve band."""
        tooth_w = 5.0
        y_top = HEADER_H
        y_bottom = y_top + TORN_H
        num_teeth = int(PAGE_W / tooth_w) + 2

        self.set_fill_color(*CREAM)
        for i in range(num_teeth):
            x0 = i * tooth_w
            x_mid = x0 + tooth_w / 2
            x1 = x0 + tooth_w
            # Triangle pointing down into the page
            self.polygon(
                [(x0, y_top), (x_mid, y_bottom), (x1, y_top)],
                style="F",
            )

    # ── Page Footer ───────────────────────────────────────────────────────────

    def footer(self):
        """Minimal 'Page X of Y' footer."""
        self.set_y(-12)
        self.font_sans("", 8)
        self.set_text_color(*COCOA)
        self.cell(0, 6, f"Page {self.page_no()} of {{nb}}", align="C")

    # ── Table Header Row ──────────────────────────────────────────────────────

    def draw_table_header(self):
        """Header row: ESPRESSO background, CREAM bold text."""
        self.set_fill_color(*ESPRESSO)
        self.set_text_color(*CREAM)
        self.font_sans("B", 9)

        x = MARGIN
        y = self.get_y()
        self.set_xy(x, y)

        self.cell(COL_NO_W, HEADER_ROW_H, "#", border=0, fill=True, align="C")
        self.cell(COL_SUBJ_W, HEADER_ROW_H, "  Subject", border=0, fill=True, align="L")
        self.cell(COL_DL_W, HEADER_ROW_H, "Deadline", border=0, fill=True, align="L", ln=True)

    # ── Table Data Row ────────────────────────────────────────────────────────

    def draw_row(
        self,
        row_num: int,
        subject: str,
        deadline: Optional[str],
        is_odd_row: bool,
    ):
        """
        Draw a single data row.
        - Background: CREAM for odd rows, SOFT_ROSE for even rows.
        - Subject wraps inside its cell.
        - Deadline highlighted in RASPBERRY, or '—' in COCOA.
        """
        fill_color = CREAM if is_odd_row else SOFT_ROSE

        # Clean strings
        clean_subj = clean_text(subject) or "(No Subject)"
        clean_dl = clean_text(deadline) if deadline else None

        # Choose font for subject (handles Devanagari)
        self.font_for_text(clean_subj, "", 9)

        # Estimate line count for subject wrapping
        approx_chars_per_line = max(1, int((COL_SUBJ_W - 4) / 1.85))
        estimated_lines = max(1, -(-len(clean_subj) // approx_chars_per_line))
        row_height = max(7, estimated_lines * LINE_HEIGHT + 2)

        # Check page break
        x = MARGIN
        y = self.get_y()
        if y + row_height > self.page_break_trigger:
            self.add_page()
            self.draw_table_header()
            y = self.get_y()

        # 1. Fill background rectangle for the entire row
        self.set_fill_color(*fill_color)
        self.rect(x, y, CONTENT_W, row_height, style="F")

        # 2. Column 1: Row Number (#)
        self.set_xy(x, y)
        self.set_text_color(*ESPRESSO)
        self.font_sans("", 9)
        self.cell(COL_NO_W, row_height, str(row_num), border=0, align="C")

        # 3. Column 2: Subject (wrapped)
        subj_x = x + COL_NO_W + 1
        self.set_xy(subj_x, y + 1)
        self.set_text_color(*ESPRESSO)
        self.font_for_text(clean_subj, "", 9)

        # Safe multi_cell output
        try:
            self.multi_cell(
                COL_SUBJ_W - 2,
                LINE_HEIGHT,
                clean_subj,
                border=0,
                align="L",
                fill=False,
                max_line_height=LINE_HEIGHT,
            )
        except Exception as exc:
            # Fallback if unhandled characters occur
            log.warning("Subject rendering exception: %s. Using latin-1 sanitized text.", exc)
            safe_text = clean_subj.encode("latin-1", "replace").decode("latin-1")
            self.set_xy(subj_x, y + 1)
            self.set_font("Helvetica", "", 9)
            self.multi_cell(COL_SUBJ_W - 2, LINE_HEIGHT, safe_text, border=0, align="L")

        # 4. Column 3: Deadline
        dl_x = x + COL_NO_W + COL_SUBJ_W
        self.set_xy(dl_x, y)

        if clean_dl:
            self.set_text_color(*RASPBERRY)
            self.font_sans("B", 8.5)
            self.cell(COL_DL_W, row_height, clean_dl, border=0, align="L")
        else:
            self.set_text_color(*COCOA)
            self.font_sans("", 9)
            self.cell(COL_DL_W, row_height, "—", border=0, align="L")

        # Advance Y to bottom of this row
        self.set_y(y + row_height)


# ─── Public Interface ─────────────────────────────────────────────────────────


def generate_pdf(
    user_name: str,
    report_date: str,
    emails: list[dict],
    output_path: str,
) -> str:
    """
    Generate the tabular PDF report for a user's day of emails.

    Args:
        user_name: User display name (e.g. "Srishti")
        report_date: Date string in "YYYY-MM-DD"
        emails: List of dicts, each with {subject, deadline, internal_date_ms, ...}
                Pre-sorted oldest-first by internalDate.
        output_path: Destination path for the generated PDF.

    Returns:
        output_path
    """
    email_count = len(emails)
    deadline_count = sum(1 for e in emails if e.get("deadline"))

    pdf = ReportPDF(
        user_name=user_name,
        report_date_str=report_date,
        email_count=email_count,
        deadline_count=deadline_count,
    )

    pdf.add_page()
    pdf.draw_table_header()

    for idx, email in enumerate(emails, start=1):
        subject = email.get("subject", "")
        deadline = email.get("deadline")
        is_odd = (idx % 2 == 1)

        pdf.draw_row(
            row_num=idx,
            subject=subject,
            deadline=deadline,
            is_odd_row=is_odd,
        )

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    pdf.output(output_path)
    log.info("PDF generated successfully: %s (%d rows)", output_path, email_count)
    return output_path
