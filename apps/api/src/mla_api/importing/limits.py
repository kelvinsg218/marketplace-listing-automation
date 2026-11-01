"""File-type allow-lists shared by imports and photos (from desktop core/validation.py and services/files.py)."""

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_FILE_EXTENSIONS = {
    ".pdf", ".txt", ".csv", ".xlsx", ".xls", ".ods", ".docx", ".doc", ".odt", ".rtf",
    ".dxf", ".dwg", ".step", ".stp", ".stl", ".jpg", ".jpeg", ".png", ".webp",
}
