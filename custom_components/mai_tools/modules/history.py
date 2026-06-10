"""Apply history & rollback — M.A.I Tools."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from ..const import DOMAIN, HISTORY_STORAGE_KEY

_LOGGER = logging.getLogger(__name__)
_STORE_VERSION = 1


def _get_store(hass: HomeAssistant) -> Store:
    return Store(hass, _STORE_VERSION, f"{DOMAIN}.{HISTORY_STORAGE_KEY}")


async def load_history(hass: HomeAssistant) -> list[dict]:
    store = _get_store(hass)
    data = await store.async_load()
    if not data or "entries" not in data:
        return []
    return data["entries"]


async def save_snapshot(
    hass: HomeAssistant,
    pairs: list[dict],
    applied: list[str],
) -> str:
    """
    Save a snapshot BEFORE applying pairs so we can rollback.
    Snapshot stores the PREVIOUS entity_id for each pair (i.e. target_entity_id
    before rename), so rollback renames back.

    Returns snapshot id (timestamp string).
    """
    store = _get_store(hass)
    data = await store.async_load() or {"entries": []}

    snapshot_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")

    # Build rollback map: after apply, entity lives at source_entity_id.
    # To rollback: rename source_entity_id → target_entity_id (the old id).
    rollback_pairs = [
        {
            "from_entity_id": p["source_entity_id"],   # current id after apply
            "to_entity_id": p["target_entity_id"],     # original id before apply
            "label": p.get("source_meta", {}).get("name")
                     or p.get("source_meta", {}).get("original_name")
                     or p["source_entity_id"],
        }
        for p in pairs
        if p["source_entity_id"] in " ".join(applied)
    ]

    entry = {
        "id": snapshot_id,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "pair_count": len(rollback_pairs),
        "applied_summary": applied,
        "rollback_pairs": rollback_pairs,
        "rolled_back": False,
    }

    data["entries"].append(entry)
    await store.async_save(data)
    _LOGGER.info("[MAI Tools] Snapshot saved: %s (%d pairs)", snapshot_id, len(rollback_pairs))
    return snapshot_id


async def delete_snapshot(hass: HomeAssistant, snapshot_id: str) -> bool:
    store = _get_store(hass)
    data = await store.async_load() or {"entries": []}
    before = len(data["entries"])
    data["entries"] = [e for e in data["entries"] if e["id"] != snapshot_id]
    if len(data["entries"]) < before:
        await store.async_save(data)
        return True
    return False


async def clear_all_history(hass: HomeAssistant) -> None:
    store = _get_store(hass)
    await store.async_save({"entries": []})


async def rollback_snapshot(hass: HomeAssistant, snapshot_id: str) -> dict:
    """Perform rollback for a snapshot. Returns {applied, errors}."""
    store = _get_store(hass)
    data = await store.async_load() or {"entries": []}

    entry = next((e for e in data["entries"] if e["id"] == snapshot_id), None)
    if not entry:
        return {"applied": [], "errors": [f"Snapshot {snapshot_id} không tìm thấy"]}
    if entry.get("rolled_back"):
        return {"applied": [], "errors": ["Snapshot này đã được rollback rồi"]}

    ent_reg = er.async_get(hass)
    applied, errors = [], []

    for rp in entry["rollback_pairs"]:
        from_id = rp["from_entity_id"]
        to_id = rp["to_entity_id"]
        try:
            current_entry = ent_reg.async_get(from_id)
            if not current_entry:
                errors.append(f"{from_id}: entity không còn tồn tại")
                continue
            conflict = ent_reg.async_get(to_id)
            if conflict and conflict.id != current_entry.id:
                errors.append(f"{from_id} → {to_id}: entity_id đích đã tồn tại")
                continue
            ent_reg.async_update_entity(from_id, new_entity_id=to_id)
            applied.append(f"{from_id} → {to_id}")
            _LOGGER.info("[MAI Tools] Rollback: %s → %s", from_id, to_id)
        except Exception as exc:
            errors.append(f"{from_id}: {exc}")

    # Mark as rolled back
    entry["rolled_back"] = True
    entry["rolled_back_at"] = datetime.now(timezone.utc).isoformat()
    await store.async_save(data)

    return {"applied": applied, "errors": errors}
