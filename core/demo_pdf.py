"""Примерные PDF-файлы для демо-версии: титульный лист документа с реквизитами.

Рисуем страницу через Pillow (уже в зависимостях) и сохраняем как PDF.
Шрифт документов — Arial. Если Arial в системе нет, берём Liberation Sans: у него те же размеры букв,
поэтому строки переносятся так же, как в Arial (DejaVu — только на крайний случай).
"""
import io
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = {
    False: ["C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    True: ["C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf",
           "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
           "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
           "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
           "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
}
PT12 = 25  # 12 pt при 150 dpi (страница A4 = 1240 × 1754 точек)
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
    d.text((m, 60), company.name, font=font(PT12, True), fill=NAVY)
    sub = " · ".join(x for x in [f"БИН {company.bin}" if company.bin else "", company.legal_address] if x)
    for i, row in enumerate(textwrap.wrap(sub, 78)[:2]):
        d.text((m, 98 + i * 34), row, font=font(PT12), fill=GRAY)
    d.line([m, 172, W - m, 172], fill=ACCENT, width=3)

    y = 230
    d.text((m, y), kind.upper(), font=font(PT12, True), fill=GRAY)
    y += 46
    head = " ".join(x for x in [f"№ {number}" if number else "", f"от {date_text}" if date_text else ""] if x)
    if head:
        d.text((m, y), head, font=font(PT12), fill=NAVY)
        y += 56
    for row in textwrap.wrap(title, 68):
        d.text((m, y), row, font=font(PT12, True), fill=NAVY)
        y += 38
    y += 30
    body = font(PT12)
    for para in lines:
        for row in textwrap.wrap(para, 72):
            d.text((m, y), row, font=body, fill=(40, 48, 66))
            y += 38
        y += 18

    y = max(y + 80, H - 420)
    if signer:
        d.text((m, y), signer, font=font(PT12), fill=NAVY)
        d.line([W - m - 360, y + 30, W - m, y + 30], fill=GRAY, width=2)
        d.text((W - m - 360, y + 40), "подпись", font=font(PT12), fill=GRAY)
    # Пометка, что это образец (демо-данные)
    d.rounded_rectangle([m, H - 200, W - m, H - 120], radius=14, outline=(230, 236, 245), width=3)
    d.text((W // 2, H - 160), "Образец документа · демо-версия Smart Building", font=font(PT12), fill=GRAY,
           anchor="mm")
    buf = io.BytesIO()
    img.save(buf, "PDF", resolution=150.0)
    return buf.getvalue()
