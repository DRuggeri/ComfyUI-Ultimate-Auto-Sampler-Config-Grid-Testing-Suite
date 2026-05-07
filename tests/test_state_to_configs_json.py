"""Golden tests for UltimateConfigBuilder.state_to_configs_json.

This is the single transformer that both the runtime (generate_config) and
the preview endpoint (/configbuilder/preview) call. Drift between preview
and runtime is impossible by construction because both call this function.
"""
import json
import pytest
from config_builder_node import UltimateConfigBuilder


def make_state(loras=None, lora_weight_arrays=None, lora_bypass_states=None,
               models=None, samplers=None, schedulers=None, steps="20", cfg="7.0",
               extra_array_fields=None):
    """Build a minimal valid state with one config_array for tests."""
    arr = {
        "name": "Test",
        "samplers": samplers or ["euler"],
        "schedulers": schedulers or ["normal"],
        "steps": steps,
        "cfg": cfg,
        "models": models or ["None"],
        "vaes": ["None"],
        "text_encoders": [],
        "clip_type": "stable_diffusion",
        "gguf_options": {},
        "loras": loras if loras is not None else ["None"],
        "lora_omit_triggers": [],
        "lora_triggerwords_append_settings": {},
        "lora_bypass_states": lora_bypass_states or {},
        "lora_strength_lock": {},
        "lora_weight_arrays": lora_weight_arrays or {},
        "model_bypass_states": {},
        "vae_bypass_states": {},
        "te_bypass_states": {},
        "combine": False,
        "positive_prompt_groups": [],
        "negative_prompt": "",
        "use_custom_prompts": False,
        "model_prompt_prefix": "",
        "model_prompt_suffix": "",
        "attention_modes": ["default"],
    }
    if extra_array_fields:
        arr.update(extra_array_fields)
    return {
        "session_name": "test_session",
        "include_none": False,
        "global_positive_groups": [],
        "global_negative": "",
        "config_arrays": [arr],
    }


def test_lora_strength_arrays_render_as_brackets():
    """REGRESSION: Compare Strengths arrays must reach configs_json as bracket form.

    Bug history (2026-04-28): convertStateToConfigs (JS) emitted brackets but
    process_lora_array (Python) emitted scalar 1.00:1.00 because Python ignored
    the lora_weight_arrays side-channel. Result: preview disagreed with runtime.
    """
    state = make_state(
        loras=["Sexy-IL-v11/:1.00:1.00"],
        lora_weight_arrays={
            "Sexy-IL-v11/_model": [0, 1, 2, 5, 10],
            "Sexy-IL-v11/_clip": [0, 1, 2, 5, 10],
        },
    )
    json_str = UltimateConfigBuilder.state_to_configs_json(state)
    parsed = json.loads(json_str)
    loras = [c["lora"] for c in parsed["configs"]]
    bracketed = [l for l in loras if isinstance(l, str) and "[0, 1, 2, 5, 10]" in l]
    assert bracketed, f"No bracketed lora strings in output. Got: {loras}"
    assert "Sexy-IL-v11/" in bracketed[0]
