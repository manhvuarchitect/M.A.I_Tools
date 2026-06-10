"""Migrate logic — Entity Migrator module of M.A.I Tools."""
from __future__ import annotations
import json
import logging
from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)
_pending_pairs: list[dict] = []  # [{source_entity_id, target_entity_id, source_meta}]


def parse_backup_file(content: str) -> dict[str, Any]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"File không hợp lệ: {e}") from e
    if "mai_backup_version" not in data:
        raise ValueError("Không phải file M.A.I Backup.")
    if "devices" not in data or not isinstance(data["devices"], list):
        raise ValueError("File thiếu danh sách devices.")
    return data


def get_target_device_entities(hass: HomeAssistant, device_id: str) -> list[dict]:
    ent_reg = er.async_get(hass)
    entries = er.async_entries_for_device(ent_reg, device_id)
    return [
        {
            "entity_id": e.entity_id,
            "name": e.name or e.original_name,
            "domain": e.domain,
            "device_class": e.device_class or e.original_device_class,
            "icon": e.icon or e.original_icon,
        }
        for e in sorted(entries, key=lambda e: e.entity_id)
    ]


def store_pending_pairs(pairs: list[dict]) -> None:
    global _pending_pairs
    _pending_pairs = pairs


def get_pending_pairs() -> list[dict]:
    return _pending_pairs


def apply_pairs(hass: HomeAssistant) -> dict:
    ent_reg = er.async_get(hass)
    applied, errors = [], []
    for pair in _pending_pairs:
        src_id = pair["source_entity_id"]
        tgt_id = pair["target_entity_id"]
        src_meta = pair.get("source_meta", {})
        try:
            existing = ent_reg.async_get(src_id)
            tgt_entry = ent_reg.async_get(tgt_id)
            if not tgt_entry:
                errors.append(f"{tgt_id}: không tìm thấy entity đích")
                continue
            if existing and existing.id != tgt_entry.id:
                errors.append(f"{tgt_id} → {src_id}: entity_id đã tồn tại")
                continue
            ent_reg.async_update_entity(
                tgt_id,
                new_entity_id=src_id,
                name=src_meta.get("name") or src_meta.get("original_name"),
                icon=src_meta.get("icon"),
            )
            applied.append(f"{tgt_id} → {src_id}")
            _LOGGER.info("[MAI Tools] Renamed %s → %s", tgt_id, src_id)
        except Exception as exc:
            errors.append(f"{tgt_id}: {exc}")
            _LOGGER.error("[MAI Tools] Error: %s", exc)
    _pending_pairs.clear()
    return {"applied": applied, "errors": errors}
