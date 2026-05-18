"""Regression test: state_to_configs_json must preserve the florence2 sub-object
on an upscale step when mode is 'florence2_hires'.

This is currently a passthrough (config_builder_node.py L838 does
{**p, 'steps': active_steps}), but a future refactor could whitelist fields
and silently drop our new keys. This test catches that.
"""
import json

import pytest

from config_builder_node import UltimateConfigBuilder


def _base_state():
    return {
        "session_name": "test_session",
        "include_none": False,
        "global_positive_groups": [],
        "global_negative": "",
        "config_arrays": [{
            "name": "Config 1",
            "samplers": "euler",
            "schedulers": "simple",
            "steps": "20",
            "cfg": "7.0",
            "model": "ckpt.safetensors",
            "loras": ["None"],
            "lora_omit_triggers": [],
            "lora_triggerwords_append_settings": {},
            "combine": True,
            "positive_prompt_groups": [],
            "negative_prompt": "",
            "use_custom_prompts": False,
            "model_type": "checkpoint",
        }],
        "upscaling": {
            "enabled": True,
            "pipelines": [{
                "name": "Pipeline 1",
                "active": True,
                "steps": [{
                    "active": True,
                    "mode": "florence2_hires",
                    "florence2": {
                        "model": "microsoft/Florence-2-base",
                        "text_input": "face",
                        "target_megapixels": 1.0,
                        "crop_padding": 64,
                        "min_crop_resolution": 256,
                        "max_crop_resolution": 1536,
                        "grow_expand": 32,
                        "feather_left": 128, "feather_top": 128,
                        "feather_right": 128, "feather_bottom": 128,
                        "output_mask_select": "",
                        "model_source": "from_manifest",
                        "on_no_detection": "skip",
                    },
                    "hires_denoise": "0.45",
                    "hires_steps": 15,
                }]
            }]
        }
    }


def test_florence2_block_round_trips():
    state = _base_state()
    out = UltimateConfigBuilder.state_to_configs_json(state)
    parsed = json.loads(out)
    session = parsed.get("_session_settings", {})
    upscaling = session.get("upscaling", {})
    pipelines = upscaling.get("pipelines", [])
    assert len(pipelines) == 1
    steps = pipelines[0]["steps"]
    assert len(steps) == 1
    step = steps[0]
    assert step["mode"] == "florence2_hires"
    f2 = step.get("florence2")
    assert f2 is not None
    assert f2["model"] == "microsoft/Florence-2-base"
    assert f2["text_input"] == "face"
    assert f2["target_megapixels"] == 1.0
    assert f2["model_source"] == "from_manifest"
    # Sampling fields are at step level, not inside florence2
    assert step["hires_denoise"] == "0.45"
    assert step["hires_steps"] == 15


def test_florence2_step_with_active_false_filtered_out():
    """Active=false step is dropped, just like other modes."""
    state = _base_state()
    state["upscaling"]["pipelines"][0]["steps"][0]["active"] = False
    out = UltimateConfigBuilder.state_to_configs_json(state)
    parsed = json.loads(out)
    upscaling = parsed.get("_session_settings", {}).get("upscaling", {})
    # When all steps are inactive, the entire pipeline is filtered
    assert upscaling == {} or upscaling.get("pipelines", []) == []


def test_florence2_disabled_upscaling_omits_block():
    state = _base_state()
    state["upscaling"]["enabled"] = False
    out = UltimateConfigBuilder.state_to_configs_json(state)
    parsed = json.loads(out)
    assert "upscaling" not in parsed.get("_session_settings", {})
