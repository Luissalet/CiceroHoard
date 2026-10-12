"""Import existing local figures through the same asset store as UI uploads."""
from pathlib import Path

from . import decks
from .errors import CiceroError, Refused


def import_file(svc, deck_id: str, path: str):
    decks._deck_row(svc, deck_id)
    try:
        file = Path(path).expanduser().resolve(strict=True)
    except OSError:
        raise CiceroError(f'Image not found: {path}') from None
    if not file.is_file() or file.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
        raise CiceroError('Choose a PNG, JPEG or WEBP image file.')
    if svc.config.file_roots and not any(file.is_relative_to(root.resolve()) for root in svc.config.file_roots):
        raise Refused('Image is outside CICERO_FILE_ROOTS.')
    if file.stat().st_size > svc.config.max_image_bytes:
        raise CiceroError('Image exceeds the configured upload size.')
    return decks.add_asset(svc, deck_id, file.read_bytes(), file.name)
