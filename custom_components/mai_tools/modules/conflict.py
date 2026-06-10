"""Conflict detection — scan automations/scripts for entity_id references."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def _entity_in_obj(entity_id: str, obj: Any) -> bool:
    """Recursively check if entity_id string appears anywhere in a dict/list/str."""
    if isinstance(obj, str):
        return entity_id in obj
    if isinstance(obj, dict):
        return any(_entity_in_obj(entity_id, v) for v in obj.values())
    if isinstance(obj, list):
        return any(_entity_in_obj(entity_id, item) for item in obj)
    return False


def check_conflicts(
    hass: HomeAssistant,
    pairs: list[dict],
) -> list[dict]:
    """
    For each pair, check if source_entity_id (the new id we want to assign)
    is already referenced in automations or scripts.

    Returns list of conflict dicts:
    {
        entity_id: str,          # the desired new entity_id
        target_entity_id: str,   # current entity being renamed
        usages: [                # where it's referenced
            {type: "automation"|"script", name: str, entity_id: str}
        ]
    }
    """
    conflicts = []

    # Collect all automation + script states
    candidates = []
    for state in hass.states.async_all():
        domain = state.entity_id.split(".")[0]
        if domain in ("automation", "script"):
            candidates.append(
                {
                    "type": domain,
                    "name": state.attributes.get("friendly_name") or state.entity_id,
                    "entity_id": state.entity_id,
                    "attributes": dict(state.attributes),
                }
            )

    for pair in pairs:
        desired_id = pair["source_entity_id"]   # the entity_id we want to rename TO
        current_id = pair["target_entity_id"]   # the entity_id we're renaming FROM

        usages = []
        for cand in candidates:
            # Check if the DESIRED id is already referenced somewhere
            # (means renaming to it might break existing references)
            if _entity_in_obj(desired_id, cand["attributes"]):
                usages.append(
                    {
                        "type": cand["type"],
                        "name": cand["name"],
                        "entity_id": cand["entity_id"],
                    }
                )

        if usages:
            conflicts.append(
                {
                    "entity_id": desired_id,
                    "target_entity_id": current_id,
                    "usages": usages,
                }
            )

    return conflicts
