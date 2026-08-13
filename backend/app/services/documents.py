from pathlib import Path

from app.models.document import DocumentType


IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "tif", "tiff", "webp", "bmp"}
EXCEL_EXTENSIONS = {"xlsx", "xls"}


def detect_document_type(filename: str) -> DocumentType:
    ext = Path(filename).suffix.lower().lstrip(".")
    name = filename.lower()
    if ext == "pdf":
        return DocumentType.PDF
    if ext in EXCEL_EXTENSIONS:
        return DocumentType.EXCEL
    if ext == "csv":
        return DocumentType.CSV
    if ext in IMAGE_EXTENSIONS:
        return DocumentType.IMAGE
    if ext == "zip":
        return DocumentType.ZIP
    if ext == "dxf":
        return DocumentType.DXF
    if ext == "dwg":
        return DocumentType.DWG
    if ext == "landxml" or (ext == "xml" and "land" in name):
        return DocumentType.LANDXML
    if ext == "xml":
        return DocumentType.LANDXML
    if ext == "json" and ("civil" in name or "c3d" in name):
        return DocumentType.CIVIL3D
    if ext == "json":
        return DocumentType.CIVIL3D
    return DocumentType.OTHER


def guess_content_type(filename: str) -> str:
    ext = Path(filename).suffix.lower().lstrip(".")
    mapping = {
        "pdf": "application/pdf",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "csv": "text/csv",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "tif": "image/tiff",
        "tiff": "image/tiff",
        "zip": "application/zip",
        "dxf": "application/dxf",
        "dwg": "application/acad",
        "xml": "application/xml",
        "landxml": "application/xml",
        "json": "application/json",
    }
    return mapping.get(ext, "application/octet-stream")
