"""Generate QR code image from a vpn:// config URL."""
import io
from typing import Optional

import qrcode
from qrcode.image.pil import PilImage


def generate_qr(data: str) -> bytes:
    """Returns PNG bytes for the QR code."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img: PilImage = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
