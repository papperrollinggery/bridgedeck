#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MODELS_CACHE_PATH = Path.home() / ".codex" / "models_cache.json"
DEFAULT_MODEL_ID = "gpt-6-astra"
CATALOG_STALE_SECS = 48 * 60 * 60
REASONING_EFFORT_ORDER = ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")
REASONING_LEVEL_DESCRIPTIONS = {
    "none": "No deliberate reasoning",
    "minimal": "Minimal reasoning",
    "low": "Fast responses with lighter reasoning",
    "medium": "Balances speed and reasoning depth for everyday tasks",
    "high": "Greater reasoning depth for complex problems",
    "xhigh": "Extra high reasoning depth for complex problems",
    "max": "Maximum reasoning depth for the hardest problems",
    "ultra": "Maximum reasoning with automatic task delegation",
}


_FALLBACK_MODELS: tuple[dict[str, Any], ...] = (
    {
        "id": DEFAULT_MODEL_ID,
        "name": "GPT-6 Astra",
        # Codex's default window, not the public API's 1,050,000-token window.
        "context_tokens": 272_000,
        "max_context_tokens": 872_000,
        "max_output_tokens": 128_000,
        "thinking_levels": ("low", "medium", "high", "xhigh", "max", "ultra"),
        "default_reasoning_level": "medium",
    },
    {
        "id": "gpt-5.6-sol",
        "name": "GPT-5.6 Sol",
        "context_tokens": 372_000,
        "max_output_tokens": 128_000,
        "thinking_levels": ("low", "medium", "high", "xhigh", "max", "ultra"),
        "default_reasoning_level": "medium",
    },
    {
        "id": "gpt-5.6-terra",
        "name": "GPT-5.6 Terra",
        "context_tokens": 372_000,
        "max_output_tokens": 128_000,
        "thinking_levels": ("low", "medium", "high", "xhigh", "max", "ultra"),
        "default_reasoning_level": "medium",
    },
    {
        "id": "gpt-5.6-luna",
        "name": "GPT-5.6 Luna",
        "context_tokens": 372_000,
        "max_output_tokens": 128_000,
        "thinking_levels": ("low", "medium", "high", "xhigh", "max"),
        "default_reasoning_level": "medium",
    },
    {
        "id": "gpt-5.5",
        "name": "GPT-5.5",
        "context_tokens": 272_000,
        "max_output_tokens": 128_000,
        "thinking_levels": ("low", "medium", "high", "xhigh"),
        "default_reasoning_level": "medium",
    },
    {
        "id": "gpt-5.4",
        "name": "GPT-5.4",
        "context_tokens": 220_000,
        "thinking_levels": ("low", "medium", "high", "xhigh"),
        "default_reasoning_level": "medium",
    },
    {
        "id": "gpt-5.4-mini",
        "name": "GPT-5.4 Mini",
        "context_tokens": 220_000,
        "thinking_levels": ("low", "medium", "high", "xhigh"),
        "default_reasoning_level": "medium",
    },
    {"id": "gpt-5.3-codex", "name": "GPT-5.3 Codex", "context_tokens": 220_000, "thinking_levels": ()},
    {"id": "gpt-5.3-codex-spark", "name": "GPT-5.3 Codex Spark", "context_tokens": 220_000, "thinking_levels": ()},
)


def normalize_model_id(value: Any) -> str:
    model = str(value or "").strip().lower()
    return "gpt-5.6-sol" if model == "gpt-5.6" else model


def _positive_int(value: Any) -> int | None:
    return value if type(value) is int and 0 < value <= 2_000_000 else None


def _cache_model(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    model_id = normalize_model_id(item.get("slug") or item.get("id"))
    if not re.fullmatch(r"gpt-\d[0-9a-z]*(?:[.-][0-9a-z]+)*", model_id):
        return None
    levels: list[str] = []
    raw_levels = item.get("supported_reasoning_levels")
    for raw in raw_levels if isinstance(raw_levels, list) else []:
        effort = raw.get("effort") if isinstance(raw, dict) else raw
        effort = str(effort or "").strip().lower()
        if effort in REASONING_EFFORT_ORDER and effort not in levels:
            levels.append(effort)
    context = _positive_int(item.get("context_window")) or _positive_int(item.get("max_context_window"))
    return {
        "id": model_id,
        "name": str(item.get("display_name") or model_id),
        "context_tokens": context,
        "max_context_tokens": _positive_int(item.get("max_context_window")),
        "max_output_tokens": _positive_int(item.get("max_output_tokens")) or _positive_int(item.get("max_completion_tokens")),
        "thinking_levels": tuple(levels),
        "default_reasoning_level": str(item.get("default_reasoning_level") or "").strip().lower(),
    }


def load_model_catalog(path: Path | None = None) -> dict[str, Any]:
    target = path or MODELS_CACHE_PATH
    cache_models: dict[str, dict[str, Any]] = {}
    fetched_at = ""
    source = "fallback"
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("models"), list):
            fetched_at = str(raw.get("fetched_at") or "")
            for item in raw["models"]:
                parsed = _cache_model(item)
                if parsed:
                    cache_models[parsed["id"]] = parsed
            if cache_models:
                source = "codex_models_cache"
    except (OSError, ValueError, TypeError):
        pass

    models: list[dict[str, Any]] = []
    seen: set[str] = set()
    for fallback in _FALLBACK_MODELS:
        model = dict(fallback)
        cached = cache_models.get(model["id"])
        if cached:
            # Current Codex metadata wins; fallbacks fill missing cache fields.
            model.update(
                {
                    key: value
                    for key, value in cached.items()
                    if value not in (None, (), "")
                }
            )
        models.append(model)
        seen.add(model["id"])
    for model_id, model in sorted(cache_models.items()):
        if model_id not in seen:
            models.append(dict(model))
    for model in models:
        levels = model.get("thinking_levels") or ()
        if model.get("default_reasoning_level") not in levels:
            model["default_reasoning_level"] = "medium" if "medium" in levels or not levels else levels[0]
        context = model.get("context_tokens")
        if context and (model.get("max_context_tokens") or 0) < context:
            model["max_context_tokens"] = context

    try:
        age_secs = max(0.0, time.time() - target.stat().st_mtime)
    except OSError:
        age_secs = None
    if fetched_at:
        try:
            fetched = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
            fetched = fetched if fetched.tzinfo else fetched.replace(tzinfo=timezone.utc)
            age_secs = max(0.0, time.time() - fetched.timestamp())
        except (ValueError, OverflowError, OSError):
            age_secs = None
    return {
        "source": source,
        "path": str(target),
        "fetched_at": fetched_at,
        "stale": source == "fallback" or age_secs is None or age_secs > CATALOG_STALE_SECS,
        "age_seconds": round(age_secs, 3) if age_secs is not None else None,
        "models": models,
    }


def model_options(path: Path | None = None) -> tuple[dict[str, Any], ...]:
    return tuple(load_model_catalog(path)["models"])


def model_by_id(model_id: Any, path: Path | None = None) -> dict[str, Any] | None:
    normalized = normalize_model_id(model_id)
    return next((model for model in model_options(path) if model["id"] == normalized), None)


def normalize_reasoning_effort(model_id: Any, requested: Any, path: Path | None = None) -> dict[str, Any]:
    effort = str(requested or "").strip().lower()
    if effort not in REASONING_EFFORT_ORDER:
        raise ValueError(f"unsupported reasoning effort: {requested}")
    model = model_by_id(model_id, path)
    if model is None or not model.get("thinking_levels"):
        return {"requested": effort, "effective": effort, "clamped": False, "model_known": model is not None}
    supported = tuple(model["thinking_levels"])
    if effort in supported:
        effective = effort
    else:
        requested_rank = REASONING_EFFORT_ORDER.index(effort)
        ranked = sorted((REASONING_EFFORT_ORDER.index(level), level) for level in supported)
        below = [entry for entry in ranked if entry[0] <= requested_rank]
        effective = (below[-1] if below else ranked[0])[1]
    return {
        "requested": effort,
        "effective": effective,
        "clamped": effective != effort,
        "model_known": True,
        "supported": list(supported),
    }


def public_catalog(path: Path | None = None) -> dict[str, Any]:
    catalog = load_model_catalog(path)
    public_models = []
    for model in catalog["models"]:
        public_models.append(
            {
                "id": model["id"],
                "name": model["name"],
                "context_tokens": model.get("context_tokens"),
                "max_context_tokens": model.get("max_context_tokens"),
                "max_output_tokens": model.get("max_output_tokens"),
                "thinking_levels": list(model.get("thinking_levels") or ()),
                "default_reasoning_level": model.get("default_reasoning_level") or "medium",
            }
        )
    return {**{key: catalog[key] for key in ("source", "fetched_at", "stale", "age_seconds")}, "models": public_models}
