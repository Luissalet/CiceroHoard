"""Cicero mounts the family relay; Faustus owns its copilot infrastructure."""
import os
from ..hoard_link.config import LinkConfig
from ..hoard_link.copilot import make_copilot_router


def create_router(config):
    link = LinkConfig.load(path=config.backend_json_path, app="cicero")
    url = os.environ.get("CICERO_FAUSTUS_URL") or os.environ.get("HOARD_FAUSTUS_URL")
    return make_copilot_router("cicero", config.data_dir,
        faustus_urls=[url] if url else link.faustus_urls, token=link.faustus_token,
        app_name="Cicero's Hoard")
