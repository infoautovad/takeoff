from typing import Annotated

from pydantic import AfterValidator

from app.services.csi_mapper import format_export_unit

PayUnit = Annotated[str, AfterValidator(format_export_unit)]
