import qrcode
from io import BytesIO
import base64


def generate_qr_code(data):
    img = qrcode.make(data)
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()
