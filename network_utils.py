# ==============================================================================
# NETWORK UTILS — All outbound network requests are centralized here.
#
# External services contacted:
#   1. CivitAI API (civitai.com/api/v1) — model/LoRA metadata lookup
#   2. HuggingFace Endpoints (*.huggingface.cloud) — Remote VAE decoding
#   3. Distribution System (user-configured LAN addresses) — worker coordination
#
# No other file in this project makes outbound network requests.
# All urllib usage is confined to this module.
# ==============================================================================

import json
import os
import urllib.request
import urllib.error
import urllib.parse

import torch
from safetensors.torch import _tobytes


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
# 2. HUGGINGFACE REMOTE VAE — Offload VAE decoding to HF endpoints
#    Target: *.huggingface.cloud (allowlisted endpoints ONLY)
# =============================================================================

HUGGINGFACE_VAE_ENDPOINTS = {
    "SD": "https://q1bj3bpq6kzilnsu.us-east-1.aws.endpoints.huggingface.cloud/",
    "SDXL": "https://x2dmsqunjd6k9prw.us-east-1.aws.endpoints.huggingface.cloud/",
    "Flux": "https://whhx50ex1aryqvw6.us-east-1.aws.endpoints.huggingface.cloud/",
    "HunyuanVideo": "https://o7ywnmrahorts457.us-east-1.aws.endpoints.huggingface.cloud/"
}
HUGGINGFACE_VAE_TIMEOUT = 60  # seconds


def huggingface_vae_decode(endpoint_url, tensor, height, width):
    """
    Send latent tensor to a HuggingFace Remote VAE endpoint for decoding.

    Network call: POST to an allowlisted *.huggingface.cloud endpoint
    Timeout: 60 seconds
    Validates endpoint_url against HUGGINGFACE_VAE_ENDPOINTS allowlist.

    Args:
        endpoint_url: Must be one of HUGGINGFACE_VAE_ENDPOINTS values
        tensor: Raw torch tensor (will be serialized internally)
        height: Image height
        width: Image width

    Returns:
        Tuple of (response_bytes, response_headers_dict) for caller to parse

    Raises:
        ValueError: If endpoint_url is not in the allowlist
        RuntimeError: If the remote endpoint returns non-200
    """
    # Validate endpoint against allowlist
    if endpoint_url not in HUGGINGFACE_VAE_ENDPOINTS.values():
        raise ValueError(
            f"HuggingFace VAE endpoint not in allowlist: {endpoint_url}\n"
            f"Allowed: {list(HUGGINGFACE_VAE_ENDPOINTS.values())}"
        )

    # Prepare tensor for transport
    tensor = tensor.cpu().contiguous()

    # Build query parameters
    shape_values = [int(dim) for dim in tensor.shape]
    query_parts = [
        ("do_scaling", "False"),
        ("output_type", "pt"),
        ("partial_postprocess", "False"),
        ("dtype", str(tensor.dtype).split(".")[-1]),
        ("height", str(int(height))),
        ("width", str(int(width))),
    ]
    for s in shape_values:
        query_parts.append(("shape", str(s)))

    query_string = urllib.parse.urlencode(query_parts)
    full_url = f"{endpoint_url}?{query_string}"

    # Serialize tensor to bytes
    tensor_data = _tobytes(tensor, "tensor")

    # Execute request
    req = urllib.request.Request(
        full_url,
        data=tensor_data,
        headers={
            "Content-Type": "tensor/binary",
            "Accept": "tensor/binary",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=HUGGINGFACE_VAE_TIMEOUT) as response:
        if response.status != 200:
            error_text = response.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Remote VAE decode failed: {error_text}")

        output_data = response.read()
        # Capture headers before response closes
        headers = {k: response.headers.get(k) for k in ["shape", "dtype"]}

    return output_data, headers
