"""Export logic — Entity Migrator module of M.A.I Tools."""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er, area_registry as ar
from ..const import BACKUP_FILE_VERSION

_LOGGER = logging.getLogger(__name__)


def get_all_devices(hass: HomeAssistant) -> list[dict[str, Any]]:
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    area_reg = ar.async_get(hass)
    devices = []
    for device in dev_reg.devices.values():
        entities = er.async_entries_for_device(ent_reg, device.id)
        if not entities:
            continue
        area = area_reg.async_get_area(device.area_id) if device.area_id else None
        devices.append({
            "device_id": device.id,
            "name": device.name_by_user or device.name or "Unknown",
            "model": device.model,
            "manufacturer": device.manufacturer,
            "area_id": device.area_id,
            "area_name": area.name if area else None,
            "entity_count": len(entities),
        })
    devices.sort(key=lambda d: (d["area_name"] or "zzz", d["name"].lower()))
    return devices


def _export_device_entities(hass: HomeAssistant, device_id: str) -> list[dict]:
    ent_reg = er.async_get(hass)
    entries = er.async_entries_for_device(ent_reg, device_id)
    result = []
    for entry in sorted(entries, key=lambda e: e.entity_id):
        result.append({
            "entity_id": entry.entity_id,
            "unique_id": entry.unique_id,
            "original_name": entry.original_name,
            "name": entry.name,
            "platform": entry.platform,
            "domain": entry.domain,
            "device_class": entry.device_class or entry.original_device_class,
            "icon": entry.icon or entry.original_icon,
            "unit_of_measurement": entry.unit_of_measurement,
            "disabled_by": str(entry.disabled_by) if entry.disabled_by else None,
            "hidden_by": str(entry.hidden_by) if entry.hidden_by else None,
            "area_id": entry.area_id,
        })
    return result


def export_devices(hass: HomeAssistant, device_ids: list[str]) -> dict[str, Any]:
    """Export multiple devices to a single backup dict."""
    dev_reg = dr.async_get(hass)
    area_reg = ar.async_get(hass)
    devices_out = []
    for device_id in device_ids:
        device = dev_reg.devices.get(device_id)
        if not device:
            continue
        area = area_reg.async_get_area(device.area_id) if device.area_id else None
        entities = _export_device_entities(hass, device_id)
        devices_out.append({
            "device_id": device.id,
            "name": device.name_by_user or device.name or "Unknown",
            "model": device.model,
            "manufacturer": device.manufacturer,
            "area_id": device.area_id,
            "area_name": area.name if area else None,
            "entities": entities,
        })
    return {
        "mai_backup_version": BACKUP_FILE_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "device_count": len(devices_out),
        "devices": devices_out,
    }


def export_devices_to_json(hass: HomeAssistant, device_ids: list[str]) -> str:
    return json.dumps(export_devices(hass, device_ids), ensure_ascii=False, indent=2)
