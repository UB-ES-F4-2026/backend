"""Gestió local dels fitxers multimèdia de les oportunitats."""
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

MEDIA_ROOT = Path("/app/media")
MAX_IMAGE_BYTES = 5 * 1024 * 1024
CHUNK_SIZE = 64 * 1024


class InvalidImage(Exception):
    """La imatge rebuda no compleix el contracte de pujada."""


@dataclass(frozen=True)
class StagedImage:
    """Fitxer validat que encara no s'ha associat a una oportunitat."""

    temporary_path: Path
    content_type: str
    extension: str


@dataclass(frozen=True)
class StoredImage:
    """Fitxer ja mogut a la seva ubicació definitiva."""

    storage_key: str
    content_type: str


async def stage_images(images: Iterable[UploadFile]) -> list[StagedImage]:
    """Valida les imatges i les desa temporalment abans de confirmar la BD."""
    staged_images: list[StagedImage] = []
    try:
        for image in images:
            staged_images.append(await stage_image(image))
    except Exception:
        delete_staged_images(staged_images)
        raise
    if not staged_images:
        raise InvalidImage("At least one image is required")
    return staged_images


async def stage_image(image: UploadFile) -> StagedImage:
    """Llegeix un fitxer per blocs i el deixa preparat per persistir-lo."""
    temporary_dir = MEDIA_ROOT / ".tmp"
    temporary_dir.mkdir(parents=True, exist_ok=True)
    temporary_path = temporary_dir / str(uuid4())
    header = bytearray()
    size = 0

    try:
        with temporary_path.open("xb") as destination:
            while chunk := await image.read(CHUNK_SIZE):
                size += len(chunk)
                if size > MAX_IMAGE_BYTES:
                    raise InvalidImage("Image exceeds the maximum size")
                if len(header) < 12:
                    header.extend(chunk[: 12 - len(header)])
                destination.write(chunk)

        content_type, extension = detect_image_type(bytes(header))
        if image.content_type not in {None, content_type}:
            raise InvalidImage("Image content type does not match its content")
        return StagedImage(
            temporary_path=temporary_path,
            content_type=content_type,
            extension=extension,
        )
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def detect_image_type(header: bytes) -> tuple[str, str]:
    """Identifica formats admesos a partir de la seva signatura binària."""
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp", "webp"
    raise InvalidImage("Unsupported image format")


def persist_staged_images(
    staged_images: Iterable[StagedImage], opportunity_id: int
) -> list[StoredImage]:
    """Mou les imatges validades a la galeria definitiva de l'oportunitat."""
    staged_list = list(staged_images)
    opportunity_directory = MEDIA_ROOT / "opportunities" / str(opportunity_id)
    opportunity_directory.mkdir(parents=True, exist_ok=True)
    stored_images: list[StoredImage] = []

    try:
        for staged_image in staged_list:
            filename = f"{uuid4()}.{staged_image.extension}"
            destination = opportunity_directory / filename
            staged_image.temporary_path.replace(destination)
            stored_images.append(
                StoredImage(
                    storage_key=str(destination.relative_to(MEDIA_ROOT)),
                    content_type=staged_image.content_type,
                )
            )
    except Exception:
        delete_stored_images(stored_images)
        delete_staged_images(staged_list)
        raise

    return stored_images


def delete_staged_images(staged_images: Iterable[StagedImage]) -> None:
    """Elimina fitxers temporals després d'un error de negoci o de base de dades."""
    for staged_image in staged_images:
        staged_image.temporary_path.unlink(missing_ok=True)


def delete_stored_images(stored_images: Iterable[StoredImage]) -> None:
    """Elimina fitxers definitius que no s'han pogut confirmar a la base de dades."""
    for stored_image in stored_images:
        (MEDIA_ROOT / stored_image.storage_key).unlink(missing_ok=True)
