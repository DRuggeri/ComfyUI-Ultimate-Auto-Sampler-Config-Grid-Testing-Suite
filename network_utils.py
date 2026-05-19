# ==============================================================================
# NETWORK UTILS - Outbound network requests centralized here.
#
# External services contacted:
#   1. CivitAI API (civitai.com/api/v1) - model/LoRA metadata lookup
#   2. Distribution System (user-configured LAN addresses) - worker coordination
#
# (HuggingFace Remote VAE was moved to the ComfyUI-USCG-RemoteVAE companion
#  plugin in 2026-05-19. See remote_vae.py for the facade.)
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


# =============================================================================
# 3. DISTRIBUTION SYSTEM — LAN-only worker coordination
#    Target: User-configured LAN addresses (ComfyUI worker instances)
# =============================================================================

DISTRIBUTION_DEFAULT_TIMEOUT = 10  # seconds


def distribution_get(url, timeout=None):
    """
    LAN-only: GET request to a user-configured ComfyUI worker/master instance.

    Args:
        url: Full URL (caller constructs from master_url + endpoint)
        timeout: Request timeout in seconds (default: 10)

    Returns:
        Tuple of (status_code, response_bytes)

    Raises:
        urllib.error.HTTPError: On HTTP error responses
        urllib.error.URLError: On connection errors
    """
    t = timeout if timeout is not None else DISTRIBUTION_DEFAULT_TIMEOUT
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=t) as resp:
        return resp.status, resp.read()


def distribution_post_json(url, data_dict, timeout=None):
    """
    LAN-only: POST JSON to a user-configured ComfyUI worker/master instance.

    Args:
        url: Full URL (caller constructs from master_url + endpoint)
        data_dict: Dict to serialize as JSON body
        timeout: Request timeout in seconds (default: 10)

    Returns:
        Tuple of (status_code, response_bytes)

    Raises:
        urllib.error.HTTPError: On HTTP error responses
        urllib.error.URLError: On connection errors
    """
    t = timeout if timeout is not None else DISTRIBUTION_DEFAULT_TIMEOUT
    payload = json.dumps(data_dict).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=t) as resp:
        return resp.status, resp.read()


def distribution_post_multipart(url, content_type, body, timeout=60):
    """
    LAN-only: POST multipart/form-data to a user-configured ComfyUI instance.

    Caller is responsible for building the multipart body and boundary.
    This function handles only the HTTP transport.

    Args:
        url: Full URL
        content_type: Full Content-Type header value (including boundary)
        body: Pre-built multipart body bytes
        timeout: Request timeout in seconds (default: 60)

    Returns:
        Tuple of (status_code, response_bytes)

    Raises:
        urllib.error.HTTPError: On HTTP error responses
        urllib.error.URLError: On connection errors
    """
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": content_type},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


def distribution_stream_download(url, data_dict, target_path, timeout=3600,
                                  progress_callback=None):
    """
    LAN-only: POST JSON and stream response body to a file.
    Uses atomic write pattern (downloads to .downloading temp file, then renames).

    Args:
        url: Full URL
        data_dict: Dict to serialize as JSON body
        target_path: Final destination file path
        timeout: Request timeout in seconds (default: 3600 / 1 hour)
        progress_callback: Optional callable(downloaded_bytes, total_bytes)
                          called after each chunk for progress reporting

    Returns:
        total_bytes downloaded

    Raises:
        urllib.error.HTTPError: On HTTP error responses
        urllib.error.URLError: On connection errors
        OSError: On file system errors
    """
    payload = json.dumps(data_dict).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        total_size = int(resp.headers.get("Content-Length", 0))
        temp_path = target_path + ".downloading"
        downloaded = 0

        with open(temp_path, "wb") as f:
            while True:
                chunk = resp.read(8 * 1024 * 1024)  # 8 MB chunks
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, total_size)

    os.replace(temp_path, target_path)
    return downloaded
