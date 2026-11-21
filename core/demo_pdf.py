"""Примерные PDF-файлы для демо-версии: титульный лист документа с реквизитами.

Рисуем страницу через Pillow (уже в зависимостях) и сохраняем как PDF.
Нужен шрифт с кириллицей: берём DejaVu Sans / Liberation Sans из системы.
"""
import io
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = {
    False: ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/Library/Fonts/Arial Unicode.ttf", "C:/Windows/Fonts/arial.ttf"],
    True: ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
           "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
           "/Library/Fonts/Arial Unicode.ttf", "C:/Windows/Fonts/arialbd.ttf"],
}
NAVY, GRAY, ACCENT = (11, 31, 77), (110, 120, 140), (0, 160, 230)


def font(size, bold=False):
    for p in FONTS[bold]:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def document_pdf(company, title, kind, number="", date_text="", lines=(), signer=""):
    """Возвращает байты PDF (лист A4) с шапкой компании, названием и текстом."""
    W, H = 1240, 1754  # A4 при 150 dpi
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    m = 110
    d.rectangle([0, 0, W, 14], fill=NAVY)
    d.text((m, 70), company.name, font=font(30, True), fill=NAVY)
    sub = " · ".join(x for x in [f"БИН {company.bin}" if company.bin else "", company.legal_address] if x)
    d.text((m, 116), sub, font=font(20), fill=GRAY)
    d.line([m, 160, W - m, 160], fill=ACCENT, width=3)

    y = 230
    d.text((m, y), kind.upper(), font=font(24, True), fill=GRAY)
    y += 46
    head = " ".join(x for x in [f"№ {number}" if number else "", f"от {date_text}" if date_text else ""] if x)
    if head:
        d.text((m, y), head, font=font(24), fill=NAVY)
        y += 56
    for row in textwrap.wrap(title, 42):
        d.text((m, y), row, font=font(40, True), fill=NAVY)
        y += 54
    y += 30
    body = font(24)
    for para in lines:
        for row in textwrap.wrap(para, 68):
            d.text((m, y), row, font=body, fill=(40, 48, 66))
            y += 36
        y += 18

    y = max(y + 80, H - 420)
    if signer:
        d.text((m, y), signer, font=font(24), fill=NAVY)
        d.line([W - m - 360, y + 30, W - m, y + 30], fill=GRAY, width=2)
        d.text((W - m - 360, y + 40), "подпись", font=font(18), fill=GRAY)
    # Пометка, что это образец (демо-данные)
    d.rounded_rectangle([m, H - 200, W - m, H - 120], radius=14, outline=(230, 236, 245), width=3)
    d.text((W // 2, H - 160), "Образец документа · демо-версия Smart Building", font=font(22), fill=GRAY,
           anchor="mm")
    buf = io.BytesIO()
    img.save(buf, "PDF", resolution=150.0)
    return buf.getvalue()
