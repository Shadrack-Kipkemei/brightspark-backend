import os
import uuid

from PIL import Image
from flask import current_app
from werkzeug.utils import secure_filename


def allowed_image(filename):
    """
    Check whether the uploaded file has an allowed extension.
    """

    if not filename:
        return False

    if "." not in filename:
        return False

    extension = filename.rsplit(".", 1)[1].lower()

    return extension in current_app.config[
        "ALLOWED_IMAGE_EXTENSIONS"
    ]


def save_product_image(file):
    """
    Validate and save a product image.

    Returns the relative image URL.
    """

    if not file:
        raise ValueError("No image file was provided.")

    if not file.filename:
        raise ValueError("The uploaded image has no filename.")

    if not allowed_image(file.filename):
        raise ValueError(
            "Invalid image format. "
            "Allowed formats are JPG, JPEG, PNG and WEBP."
        )

    try:
        image = Image.open(file)

        image.verify()

    except Exception:
        raise ValueError(
            "The uploaded file is not a valid image."
        )

    # Re-open the file because verify() consumes the image stream.
    file.seek(0)

    image = Image.open(file)

    if image.width > 3000 or image.height > 3000:
        raise ValueError(
            "Image dimensions are too large. "
            "Maximum allowed dimensions are 3000 x 3000 pixels."
        )

    extension = (
        file.filename
        .rsplit(".", 1)[1]
        .lower()
    )

    filename = (
        f"{uuid.uuid4().hex}.{extension}"
    )

    upload_folder = os.path.join(
        current_app.config["UPLOAD_FOLDER"],
        "products"
    )

    os.makedirs(
        upload_folder,
        exist_ok=True
    )

    safe_filename = secure_filename(filename)

    file_path = os.path.join(
        upload_folder,
        safe_filename
    )

    file.save(file_path)

    return f"/uploads/products/{safe_filename}"