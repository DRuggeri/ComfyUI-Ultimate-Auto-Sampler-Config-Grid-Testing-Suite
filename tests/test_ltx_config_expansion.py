"""Tests for LTX field cartesian expansion."""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_utils import expand_configs


def _ltx_base():
    return {
        "model_type": "ltx_video",
        "model": "ltx_model.safetensors",
        "clip_models": ["c1.safetensors", "c2.safetensors"],
        "vae_video": "vv.safetensors",
        "vae_audio": "va.safetensors",
        "latent_upscaler": "lup.safetensors",
        "positive": "a video",
        "negative": "ugly",
        "width": 446,
        "height": 576,
        "duration_seconds": 5,
        "frame_rate": 25,
        "sampler_stage1": "euler_ancestral_cfg_pp",
        "sampler_stage2": "euler_cfg_pp",
        "sigmas_stage1": "1.0, 0.5, 0.0",
        "sigmas_stage2": "0.85, 0.4, 0.0",
        "cfg": 1.0,
        "seed": 42,
        "input_image": None,
        "image_strength_stage1": 0.8,
        "image_strength_stage2": 1.0,
        "img_compression": 18,
        "audio_mode": "on",
        "lora": "None",
    }


def _call(base):
    """Wrap expand_configs with the dummy outer args it needs for non-LTX paths."""
    return expand_configs(
        raw_configs=[base],
        pos_prompts=[base.get("positive", "")],
        neg_prompts=[base.get("negative", "")],
        denoise_values=[1.0],
        seed=base.get("seed", 0),
        extra_seeds=[],
        ckpt_name=None,
    )


def test_single_value_returns_one_config():
    result = _call(_ltx_base())
    assert len(result) == 1
    assert result[0]["model_type"] == "ltx_video"
    assert result[0]["model"] == "ltx_model.safetensors"


def test_sigmas_stage2_array_expands():
    base = _ltx_base()
    base["sigmas_stage2"] = ["0.85, 0.4, 0.0", "0.9, 0.5, 0.0"]
    result = _call(base)
    assert len(result) == 2
    sigmas_seen = sorted(c["sigmas_stage2"] for c in result)
    assert sigmas_seen == ["0.85, 0.4, 0.0", "0.9, 0.5, 0.0"]


def test_audio_mode_both_expands_to_on_off():
    base = _ltx_base()
    base["audio_mode"] = "both"
    result = _call(base)
    assert len(result) == 2
    modes_seen = sorted(c["audio_mode"] for c in result)
    assert modes_seen == ["off", "on"]


def test_audio_mode_array_accepted():
    base = _ltx_base()
    base["audio_mode"] = ["on", "off"]
    result = _call(base)
    assert len(result) == 2


def test_duration_array_expands():
    base = _ltx_base()
    base["duration_seconds"] = [5, 10]
    result = _call(base)
    assert len(result) == 2


def test_image_strength_arrays_cross_with_sigmas():
    base = _ltx_base()
    base["image_strength_stage1"] = [0.6, 0.8]
    base["sigmas_stage2"] = ["0.85, 0.4, 0.0", "0.9, 0.5, 0.0"]
    result = _call(base)
    assert len(result) == 4  # 2 x 2


def test_input_image_array_expands():
    base = _ltx_base()
    base["input_image"] = ["a.png", "b.png", "c.png"]
    result = _call(base)
    assert len(result) == 3


def test_clip_models_2tuple_does_not_expand():
    """clip_models is a [name1, name2] tuple, not 2 sweep values."""
    base = _ltx_base()
    base["clip_models"] = ["g.safetensors", "tp.safetensors"]
    result = _call(base)
    assert len(result) == 1
    assert result[0]["clip_models"] == ["g.safetensors", "tp.safetensors"]


def test_clip_models_list_of_lists_expands():
    """[[c1a, c2a], [c1b, c2b]] sweeps 2 CLIP pairs."""
    base = _ltx_base()
    base["clip_models"] = [["g.safetensors", "tp1.safetensors"], ["g.safetensors", "tp2.safetensors"]]
    result = _call(base)
    assert len(result) == 2
