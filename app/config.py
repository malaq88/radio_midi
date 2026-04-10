"""
Configuração central: pasta de música e mapeamento dispositivo → playlist.

A pasta pode ser alterada via variável de ambiente MUSIC_DIR (Pydantic usa o nome do campo em maiúsculas).
"""

from pathlib import Path
from typing import Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raiz do repositório (pasta que contém `app/`). Caminhos MUSIC_DIR relativos são resolvidos daqui.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Mapeamento exemplo: cada device_id recebe músicas da subpasta com este nome em music_dir.
# Ex.: esp32_sala → apenas arquivos em music_dir/rock/
DEVICE_PLAYLIST_MAP: dict[str, str] = {
    "esp32_sala": "rock",
    "esp32_quarto": "chill",
}


class Settings(BaseSettings):
    """Carrega configuração de ambiente com defaults seguros para desenvolvimento local."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Absoluto no sistema de ficheiros, ou relativo à raiz do projeto (PROJECT_ROOT), não ao cwd do uvicorn.
    music_dir: Path = Field(
        default=Path("music"),
        description="Pasta raiz com .mp3; relativo = a partir da raiz do projeto.",
    )

    @field_validator("music_dir", mode="after")
    @classmethod
    def resolve_music_dir(cls, v: Path) -> Path:
        if v.is_absolute():
            return v.resolve()
        return (PROJECT_ROOT / v).resolve()

    # Leitura em disco (blocos pequenos mantêm I/O assíncrono fluido).
    stream_chunk_size: int = Field(
        default=4096,
        ge=1024,
        le=65536,
        description="Bytes lidos por read() ao ler cada ficheiro MP3.",
    )

    # Tamanho mínimo dos blocos enviados ao cliente HTTP (agregação = menos yields e TCP mais estável).
    stream_emit_chunk_size: int = Field(
        default=8192,
        ge=2048,
        le=131072,
        description="Bytes por yield após agregação; deve ser >= stream_chunk_size.",
    )

    # Quantos blocos já emitidos podem estar em fila à frente do envio (amortiza picos de disco/rede).
    stream_queue_max_chunks: int = Field(
        default=32,
        ge=4,
        le=256,
        description="Profundidade da fila asyncio.Queue por cliente; backpressure quando cheia.",
    )

    # Ficheiro opcional (MP3 curto) injetado entre faixas; relativo à raiz do projeto se não for absoluto.
    stream_transition_gap_file: Path | None = Field(
        default=None,
        description="Silêncio entre músicas; None desativa.",
    )

    @model_validator(mode="after")
    def stream_chunk_order(self) -> Self:
        if self.stream_emit_chunk_size < self.stream_chunk_size:
            raise ValueError(
                "stream_emit_chunk_size deve ser >= stream_chunk_size "
                "(caso contrário a agregação não cobre uma leitura completa)."
            )
        return self

    @field_validator("stream_transition_gap_file", mode="before")
    @classmethod
    def empty_gap_means_none(cls, v: object) -> object:
        if v == "" or v is None:
            return None
        return v

    @field_validator("stream_transition_gap_file", mode="after")
    @classmethod
    def resolve_gap_file(cls, v: Path | None) -> Path | None:
        if v is None:
            return None
        if v.is_absolute():
            return v.resolve()
        return (PROJECT_ROOT / v).resolve()

    # Upload (desativado se vazio — ver `require_upload_api_key`).
    # Padrão alinhado com .env de desenvolvimento; em produção defina UPLOAD_API_KEY forte no ambiente.
    upload_api_key: str | None = Field(
        default="radio_midi_dev",
        description="Segredo para X-API-Key / Bearer (POST /upload).",
    )
    upload_max_mp3_bytes: int = Field(
        default=20 * 1024 * 1024,
        ge=1024 * 1024,
        le=200 * 1024 * 1024,
        description="Tamanho máximo de um único .mp3 (bytes).",
    )
    upload_max_zip_bytes: int = Field(
        default=512 * 1024 * 1024,
        ge=5 * 1024 * 1024,
        le=2 * 1024 * 1024 * 1024,
        description="Tamanho máximo do ficheiro .zip enviado (bytes).",
    )
    upload_max_zip_uncompressed_bytes: int = Field(
        default=2 * 1024 * 1024 * 1024,
        ge=50 * 1024 * 1024,
        le=2 * 1024 * 1024 * 1024,
        description="Limite de bytes descomprimidos no total (anti-ZIP bomb).",
    )

    @field_validator("upload_api_key", mode="before")
    @classmethod
    def empty_upload_key_is_none(cls, v: object) -> object:
        if v == "":
            return None
        return v

    # Rádio 24/7 (FFmpeg): processo separado em app.services.radio_generator
    radio_live_bind_host: str = Field(
        default="127.0.0.1",
        description="Host do mini-servidor HTTP do gerador (só escutar em 0.0.0.0 se souber o que faz).",
    )
    radio_live_bind_port: int = Field(
        default=9000,
        ge=1,
        le=65535,
        description="Porta do gerador de rádio contínua (FFmpeg → HTTP).",
    )
    radio_live_stream_url: str = Field(
        default="http://127.0.0.1:9000/stream",
        description="URL que o FastAPI usa para proxy em GET /radio/live.",
    )
    radio_live_status_url: str = Field(
        default="http://127.0.0.1:9000/status",
        description="URL JSON de estado do gerador (GET /radio/live/status no API).",
    )
    radio_live_autostart: bool = Field(
        default=False,
        description="Se true, o lifespan arranca subprocess python -m app.services.radio_generator.",
    )


settings = Settings()
