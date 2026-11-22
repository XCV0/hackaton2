"""Shared styling for project documents (reportlab, Cyrillic-capable system fonts)."""
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, Table, TableStyle

F = "/System/Library/Fonts/Supplemental/"
pdfmetrics.registerFont(TTFont("Arial", F + "Arial.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Bold", F + "Arial Bold.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Italic", F + "Arial Italic.ttf"))
pdfmetrics.registerFont(TTFont("Mono", F + "Courier New.ttf"))
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold", italic="Arial-Italic", boldItalic="Arial-Bold")

INK = colors.HexColor("#13294b")
TEAL = colors.HexColor("#237f7c")
AMBER = colors.HexColor("#9a5b00")
LINE = colors.HexColor("#cfd6df")
BG = colors.HexColor("#f2f5f8")
TEALBG = colors.HexColor("#e5f3f2")
AMBERBG = colors.HexColor("#fdf3e1")

ss = {
    "title": ParagraphStyle("title", fontName="Arial-Bold", fontSize=24, leading=29, textColor=INK, spaceAfter=8),
    "sub": ParagraphStyle("sub", fontName="Arial", fontSize=12.5, leading=17, textColor=colors.HexColor("#33496b")),
    "h1": ParagraphStyle("h1", fontName="Arial-Bold", fontSize=17, leading=21, textColor=INK, spaceBefore=6, spaceAfter=8),
    "h2": ParagraphStyle("h2", fontName="Arial-Bold", fontSize=12.5, leading=16, textColor=INK, spaceBefore=9, spaceAfter=4),
    "h3": ParagraphStyle("h3", fontName="Arial-Bold", fontSize=10.5, leading=14, textColor=TEAL, spaceBefore=6, spaceAfter=2),
    "p": ParagraphStyle("p", fontName="Arial", fontSize=9.6, leading=13.6, textColor=colors.HexColor("#1d2b40"), spaceAfter=4),
    "li": ParagraphStyle("li", fontName="Arial", fontSize=9.6, leading=13.4, leftIndent=12, bulletIndent=2, spaceAfter=1.5),
    "step": ParagraphStyle("step", fontName="Arial", fontSize=9.6, leading=13.4, leftIndent=16, bulletIndent=2, spaceAfter=2),
    "small": ParagraphStyle("small", fontName="Arial", fontSize=8.2, leading=11, textColor=colors.HexColor("#5d6b80")),
    "cell": ParagraphStyle("cell", fontName="Arial", fontSize=8.4, leading=10.8),
    "cellb": ParagraphStyle("cellb", fontName="Arial-Bold", fontSize=8.4, leading=10.8, textColor=INK),
    "code": ParagraphStyle("code", fontName="Mono", fontSize=7.9, leading=10.2, backColor=BG, borderPadding=5, leftIndent=4,
                           rightIndent=4, spaceBefore=3, spaceAfter=6),
    "box": ParagraphStyle("box", fontName="Arial", fontSize=9.4, leading=13, backColor=TEALBG, borderPadding=7, borderColor=TEAL,
                          borderWidth=0.6, spaceBefore=4, spaceAfter=8, leftIndent=6, rightIndent=6),
    "warn": ParagraphStyle("warn", fontName="Arial", fontSize=9.4, leading=13, backColor=AMBERBG, borderPadding=7,
                           borderColor=AMBER, borderWidth=0.6, spaceBefore=4, spaceAfter=8, leftIndent=6, rightIndent=6),
}


from fontTools.ttLib import TTFont as _FT

_CMAP = {"Arial": set(_FT(F + "Arial.ttf").getBestCmap()), "Mono": set(_FT(F + "Courier New.ttf").getBestCmap())}
_REPL = {"↗": "", "☰": "", "✅": "[OK]", "⚠": "[частично]", "❌": "[пропуск]", "🐞": "[ложное]", "✓": "", "✎": "", "✕": "", "⇪": "↑",
         "≈": "~", "∼": "~", "−": "-", "→": "->", "≤": "<=", "≥": ">=", "≠": "!=", "·": "*", "×": "x", "—": "-", "–": "-",
         "«": '"', "»": '"', "²": "2", "±": "+/-", "…": "..."}


def clean(text: str, font: str = "Arial") -> str:
    """Replace characters the font cannot draw (they would render as boxes)."""
    cmap = _CMAP[font]
    out = []
    for ch in text:
        if ord(ch) < 128 or ord(ch) in cmap:
            out.append(ch)
        else:
            out.append(_REPL.get(ch, "?"))
    return "".join(out).replace("  ", " ")


def P(t, s="p"):
    return Paragraph(clean(t, "Mono" if s == "code" else "Arial"), ss[s])


def LI(items, style="li"):
    return [Paragraph(clean(t), ss[style], bulletText="•") for t in items]


def STEPS(items):
    return [Paragraph(clean(t), ss["step"], bulletText=f"{i}.") for i, t in enumerate(items, 1)]


def T(rows, widths, head=True):
    data = [[P(str(c), "cellb" if (head and i == 0) else "cell") for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if head else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LEFTPADDING", (0, 0), (-1, -1), 4)]
    if head:
        st.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6ebf2")))
    for i in range(1 if head else 0, len(rows)):
        if i % 2 == 0:
            st.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#fafbfc")))
    t.setStyle(TableStyle(st))
    return t


def code(text):
    """Monospace block; keeps line breaks and escapes markup."""
    esc = clean(text, "Mono").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace(" ", "&nbsp;").replace("\n", "<br/>")
    return Paragraph(esc, ss["code"])


def footer(title):
    def on_page(c, doc):
        c.saveState()
        c.setFont("Arial", 7.5)
        c.setFillColor(colors.HexColor("#8a96a8"))
        c.drawString(18 * mm, 10 * mm, title)
        c.drawRightString(A4[0] - 18 * mm, 10 * mm, str(doc.page))
        c.restoreState()
    return on_page
