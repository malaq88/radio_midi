"""Esquemas de resposta para endpoints de upload."""

from pydantic import BaseModel, Field


class SkippedItem(BaseModel):
    """Entrada ignorada (ZIP) com motivo."""

    path: str
    reason: str


class UploadResult(BaseModel):
    """Resultado de POST /upload ou POST /upload/zip."""

    success: bool
    message: str
    files: list[str] = Field(default_factory=list, description="Caminhos relativos a MUSIC_DIR dos ficheiros gravados.")
    skipped: list[SkippedItem] = Field(default_factory=list)
