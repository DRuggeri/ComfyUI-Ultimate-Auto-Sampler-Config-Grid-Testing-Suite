"""Tests for LTX cache key generation."""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generation_orchestrator import get_model_cache_key, _ltx_sort_components


def _ltx_conf():
    return {
        "model_type": "ltx_video",
        "model": "ltx_model.safetensors",
        "clip_models": ["c1.safetensors", "c2.safetensors"],
        "vae_video": "vv.safetensors",
        "vae_audio": "va.safetensors",
        "latent_upscaler": "lup.safetensors",
    }


def test_ltx_key_includes_all_files():
    conf = _ltx_conf()
    key = get_model_cache_key(conf)
    assert "ltx" in key
    assert "ltx_model.safetensors" in key
    assert "c1.safetensors" in key
    assert "c2.safetensors" in key
    assert "vv.safetensors" in key
    assert "va.safetensors" in key
    assert "lup.safetensors" in key


def test_ltx_two_identical_configs_have_same_key():
    a = _ltx_conf()
    b = _ltx_conf()
    assert get_model_cache_key(a) == get_model_cache_key(b)


def test_ltx_different_upscaler_different_key():
    a = _ltx_conf()
    b = _ltx_conf()
    b["latent_upscaler"] = "different_upscaler.safetensors"
    assert get_model_cache_key(a) != get_model_cache_key(b)


def test_ltx_different_video_vae_different_key():
    a = _ltx_conf()
    b = _ltx_conf()
    b["vae_video"] = "other_vae.safetensors"
    assert get_model_cache_key(a) != get_model_cache_key(b)


def test_ltx_different_clip_different_key():
    a = _ltx_conf()
    b = _ltx_conf()
    b["clip_models"] = ["c1.safetensors", "alt_c2.safetensors"]
    assert get_model_cache_key(a) != get_model_cache_key(b)


def test_ltx_sigma_change_does_not_change_key():
    """Sweeping sigmas should NOT trigger a model reload."""
    a = _ltx_conf()
    b = _ltx_conf()
    a["sigmas_stage2"] = "0.85, 0.4, 0.0"
    b["sigmas_stage2"] = "0.9, 0.5, 0.0"
    assert get_model_cache_key(a) == get_model_cache_key(b)


def test_ltx_seed_change_does_not_change_key():
    a = _ltx_conf()
    b = _ltx_conf()
    a["seed"] = 42
    b["seed"] = 100
    assert get_model_cache_key(a) == get_model_cache_key(b)


def test_checkpoint_key_unchanged():
    """Existing checkpoint behavior must not regress."""
    conf = {"model_type": "checkpoint", "model": "sdxl.safetensors"}
    assert get_model_cache_key(conf) == "sdxl.safetensors"


def test_diffusion_model_key_unchanged():
    """Existing non-checkpoint (diffusion_model/gguf) behavior must not regress."""
    conf = {
        "model_type": "diffusion_model",
        "model": "flux.safetensors",
        "text_encoders": ["t5.safetensors", "clip_l.safetensors"],
    }
    key = get_model_cache_key(conf)
    assert "flux.safetensors" in key
    assert "diffusion_model" in key
    assert "t5.safetensors" in key
    assert "clip_l.safetensors" in key


def test_ltx_sort_components_imports():
    assert _ltx_sort_components({"model_type": "checkpoint"}) == (None, None, None, None)
    ltx = {
        "model_type": "ltx_video",
        "clip_models": ["c1", "c2"],
        "vae_video": "vv",
        "vae_audio": "va",
        "latent_upscaler": "lup",
    }
    assert _ltx_sort_components(ltx) == (("c1", "c2"), "vv", "va", "lup")


def test_build_ltx_manifest_entry_imports():
    """Smoke test: _build_ltx_manifest_entry produces a valid manifest dict."""
    from generation_orchestrator import _build_ltx_manifest_entry

    conf = {
        "model_type": "ltx_video",
        "model": "ltx.safetensors",
        "clip_models": ["c1.safetensors", "c2.safetensors"],
        "vae_video": "vv.safetensors",
        "vae_audio": "va.safetensors",
        "latent_upscaler": "lup.safetensors",
        "sampler_stage1": "euler_ancestral_cfg_pp",
        "sigmas_stage1": "1.0, 0.5, 0.0",
        "sampler_stage2": "euler_cfg_pp",
        "sigmas_stage2": "0.85, 0.4, 0.0",
        "cfg": 1.0,
        "seed": 42,
        "positive": "a video",
        "negative": "ugly",
        "lora": "None",
        "audio_mode": "on",
    }
    gen_result = {
        "video_path": "/tmp/gen.mp4",
        "preview_path": "/tmp/gen.preview.png",
        "frames": 126,
        "fps": 25,
        "duration_seconds": 5,
        "width": 446,
        "height": 576,
        "duration": 47.3,
    }
    entry = _build_ltx_manifest_entry(conf, gen_result, "myfile_seed42")
    assert entry["media_type"] == "video"
    assert entry["video_path"] == "/tmp/gen.mp4"
    # image_path mirrors video_path so the dashboard's existing image-loader picks
    # up video items through the same code path.
    assert entry["image_path"] == entry["video_path"]
    assert entry["preview_path"] == "/tmp/gen.preview.png"
    assert entry["clip_models"] == ["c1.safetensors", "c2.safetensors"]
    assert entry["sampler_stage2"] == "euler_cfg_pp"
    assert entry["audio_mode"] == "on"
    assert entry["favorited"] is False
    assert entry["rejected"] is False
    assert entry["note"] == ""
