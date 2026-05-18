"""Tests for per-image checkpoint+lora resolution under 'from_manifest' mode."""
from unittest.mock import MagicMock


def test_from_manifest_uses_item_model_and_lora(monkeypatch):
    load_count = {"n": 0}

    def fake_load_checkpoint(target_model_name, ckpt_name, use_remote_vae=False):
        load_count["n"] += 1
        return (f"model:{ckpt_name}", f"clip:{ckpt_name}", f"vae:{ckpt_name}")

    def fake_load_loras(model, clip, lora_string):
        return (f"{model}+{lora_string}", f"{clip}+{lora_string}")

    import florence2_hires
    monkeypatch.setattr(florence2_hires, "_FH_CKPT_LOADER", fake_load_checkpoint)
    monkeypatch.setattr(florence2_hires, "_FH_LORA_LOADER", fake_load_loras)

    cache = {}
    item = {"model": "ckpt_A.safetensors", "lora_expanded": "loraX.safetensors:0.8:0.8"}
    fallback = ("fallback_model", "fallback_clip", "fallback_vae")

    model, clip, vae = florence2_hires._get_or_load_checkpoint_lora(
        item, fallback, model_source="from_manifest", cache=cache
    )

    assert model == "model:ckpt_A.safetensors+loraX.safetensors:0.8:0.8"
    assert clip == "clip:ckpt_A.safetensors+loraX.safetensors:0.8:0.8"
    assert vae == "vae:ckpt_A.safetensors"
    assert load_count["n"] == 1


def test_from_manifest_caches_by_combo(monkeypatch):
    load_count = {"n": 0}

    def fake_load_checkpoint(target_model_name, ckpt_name, use_remote_vae=False):
        load_count["n"] += 1
        return (f"model:{ckpt_name}", f"clip:{ckpt_name}", f"vae:{ckpt_name}")

    def fake_load_loras(model, clip, lora_string):
        return (model, clip)

    import florence2_hires
    monkeypatch.setattr(florence2_hires, "_FH_CKPT_LOADER", fake_load_checkpoint)
    monkeypatch.setattr(florence2_hires, "_FH_LORA_LOADER", fake_load_loras)

    cache = {}
    fallback = ("fallback_model", "fallback_clip", "fallback_vae")

    item1 = {"model": "ckpt_A.safetensors", "lora_expanded": "loraX:0.8:0.8"}
    item2 = {"model": "ckpt_A.safetensors", "lora_expanded": "loraX:0.8:0.8"}
    item3 = {"model": "ckpt_B.safetensors", "lora_expanded": "loraX:0.8:0.8"}

    florence2_hires._get_or_load_checkpoint_lora(item1, fallback, "from_manifest", cache)
    florence2_hires._get_or_load_checkpoint_lora(item2, fallback, "from_manifest", cache)
    florence2_hires._get_or_load_checkpoint_lora(item3, fallback, "from_manifest", cache)

    assert load_count["n"] == 2  # only ckpt_A and ckpt_B loaded once each


def test_from_builder_returns_fallback_unchanged(monkeypatch):
    """model_source=from_builder -> use the fallback handles, no per-item loading."""
    import florence2_hires
    cache = {}
    fallback = ("fallback_model", "fallback_clip", "fallback_vae")
    item = {"model": "ignored.safetensors"}

    model, clip, vae = florence2_hires._get_or_load_checkpoint_lora(
        item, fallback, model_source="from_builder", cache=cache
    )
    assert (model, clip, vae) == fallback


def test_from_manifest_missing_model_falls_back(monkeypatch):
    """Item has no 'model' key (legacy) -> use fallback, log once."""
    import florence2_hires
    cache = {}
    fallback = ("fallback_model", "fallback_clip", "fallback_vae")
    item = {}  # no model

    model, clip, vae = florence2_hires._get_or_load_checkpoint_lora(
        item, fallback, model_source="from_manifest", cache=cache
    )
    assert (model, clip, vae) == fallback


def test_from_manifest_empty_lora_loads_checkpoint_only(monkeypatch):
    load_count = {"ckpt": 0, "lora": 0}

    def fake_load_checkpoint(target_model_name, ckpt_name, use_remote_vae=False):
        load_count["ckpt"] += 1
        return (f"model:{ckpt_name}", f"clip:{ckpt_name}", f"vae:{ckpt_name}")

    def fake_load_loras(model, clip, lora_string):
        load_count["lora"] += 1
        return (model, clip)

    import florence2_hires
    monkeypatch.setattr(florence2_hires, "_FH_CKPT_LOADER", fake_load_checkpoint)
    monkeypatch.setattr(florence2_hires, "_FH_LORA_LOADER", fake_load_loras)

    cache = {}
    fallback = ("fallback_model", "fallback_clip", "fallback_vae")
    item = {"model": "ckpt_A.safetensors"}  # no lora_expanded

    model, clip, vae = florence2_hires._get_or_load_checkpoint_lora(
        item, fallback, model_source="from_manifest", cache=cache
    )
    assert load_count["ckpt"] == 1
    assert load_count["lora"] == 0
    assert model == "model:ckpt_A.safetensors"
