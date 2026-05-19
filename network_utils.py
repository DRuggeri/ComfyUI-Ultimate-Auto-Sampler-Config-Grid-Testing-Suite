# ==============================================================================
# NETWORK UTILS - Outbound network requests centralized here.
#
# External services contacted:
#   1. CivitAI API (civitai.com/api/v1) - model/LoRA metadata lookup
#
# (HuggingFace Remote VAE was moved to the ComfyUI-USCG-RemoteVAE companion
#  plugin in 2026-05-19. See remote_vae.py for the facade.
#  Distribution system was moved to the ComfyUI-USCG-Distributed companion
#  plugin in 2026-05-19. See distribution.py for the facade.)
# ==============================================================================

import json
import os
import urllib.request
import urllib.error
import urllib.parse


# =============================================================================
# 1. CIVITAI API — Model/LoRA metadata lookup
#    Target: civitai.com/api/v1 (ONLY)
# =============================================================================

CIVITAI_API_BASE = "https://civitai.com/api/v1"
CIVITAI_TIMEOUT = 10  # seconds
CIVITAI_USER_AGENT = "ComfyUI-ConfigBuilder"


def civitai_fetch_by_hash(hash_value):
    """
    Fetch model version info from CivitAI API using a file hash.

    Network call: GET https://civitai.com/api/v1/model-versions/by-hash/{hash}
    Timeout: 10 seconds
    Returns: Parsed JSON dict on success, None on any error.
    """
    api_url = f"{CIVITAI_API_BASE}/model-versions/by-hash/{hash_value}"
    try:
        req = urllib.request.Request(
            api_url,
            headers={"User-Agent": CIVITAI_USER_AGENT}
        )
        with urllib.request.urlopen(req, timeout=CIVITAI_TIMEOUT) as response:
            if response.status == 200:
                return json.loads(response.read().decode("utf-8"))
            else:
                return None
    except urllib.error.HTTPError:
        return None
    except Exception as e:
        print(f"[NetworkUtils] ⚠️ CivitAI lookup failed: {e}")
        return None

