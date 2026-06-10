"""REST API views for M.A.I Tools v2.0.3."""
from __future__ import annotations
import logging
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from .const import DOMAIN
from .modules.entity_migrator_export import export_devices_to_json, get_all_devices
from .modules.entity_migrator_migrate import (
    apply_pairs, get_pending_pairs, get_target_device_entities,
    parse_backup_file, store_pending_pairs,
)
from .modules.conflict import check_conflicts
from .modules.history import (
    load_history, save_snapshot, delete_snapshot,
    clear_all_history, rollback_snapshot,
)

_LOGGER = logging.getLogger(__name__)


class MAIDeviceListView(HomeAssistantView):
    url = f"/api/{DOMAIN}/devices"
    name = f"api:{DOMAIN}:devices"
    requires_auth = True
    async def get(self, request: web.Request) -> web.Response:
        return self.json(get_all_devices(request.app["hass"]))


class MAIExportView(HomeAssistantView):
    url = f"/api/{DOMAIN}/export"
    name = f"api:{DOMAIN}:export"
    requires_auth = True
    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        try:
            body = await request.json()
        except Exception:
            return self.json({"error": "Body phải là JSON"}, status_code=400)
        device_ids = body.get("device_ids", [])
        if not device_ids:
            return self.json({"error": "Thiếu device_ids"}, status_code=400)
        json_str = export_devices_to_json(hass, device_ids)
        from datetime import datetime
        fname = f"mai_backup_{datetime.now().strftime('%Y%m%d')}.json"
        return web.Response(
            body=json_str.encode("utf-8"),
            content_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )


class MAITargetEntitiesView(HomeAssistantView):
    url = f"/api/{DOMAIN}/target_entities"
    name = f"api:{DOMAIN}:target_entities"
    requires_auth = True
    async def get(self, request: web.Request) -> web.Response:
        device_id = request.rel_url.query.get("device_id")
        if not device_id:
            return self.json({"error": "Thiếu device_id"}, status_code=400)
        return self.json(get_target_device_entities(request.app["hass"], device_id))


class MAICheckConflictsView(HomeAssistantView):
    """POST /api/mai_tools/check_conflicts  body: {pairs: [...]}"""
    url = f"/api/{DOMAIN}/check_conflicts"
    name = f"api:{DOMAIN}:check_conflicts"
    requires_auth = True
    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        try:
            body = await request.json()
        except Exception:
            return self.json({"error": "Body phải là JSON"}, status_code=400)
        pairs = body.get("pairs", [])
        if not pairs:
            return self.json({"conflicts": []})
        conflicts = check_conflicts(hass, pairs)
        return self.json({"conflicts": conflicts})


class MAIStorePairsView(HomeAssistantView):
    url = f"/api/{DOMAIN}/store_pairs"
    name = f"api:{DOMAIN}:store_pairs"
    requires_auth = True
    async def post(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return self.json({"error": "Body phải là JSON"}, status_code=400)
        pairs = body.get("pairs", [])
        store_pending_pairs(pairs)
        return self.json({"stored": len(pairs)})


class MAIApplyView(HomeAssistantView):
    url = f"/api/{DOMAIN}/apply"
    name = f"api:{DOMAIN}:apply"
    requires_auth = True
    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        pairs = get_pending_pairs()
        if not pairs:
            return self.json({"error": "Không có cặp nào. Hãy ghép trước."}, status_code=400)
        # Save snapshot BEFORE apply (for rollback)
        result = apply_pairs(hass)
        if result["applied"]:
            snapshot_id = await save_snapshot(hass, pairs, result["applied"])
            result["snapshot_id"] = snapshot_id
        return self.json(result)


# ── HISTORY / ROLLBACK ──────────────────────────────────────

class MAIHistoryView(HomeAssistantView):
    """GET /api/mai_tools/history"""
    url = f"/api/{DOMAIN}/history"
    name = f"api:{DOMAIN}:history"
    requires_auth = True
    async def get(self, request: web.Request) -> web.Response:
        entries = await load_history(request.app["hass"])
        return self.json({"entries": list(reversed(entries))})  # newest first


class MAIRollbackView(HomeAssistantView):
    """POST /api/mai_tools/rollback  body: {snapshot_id: "..."}"""
    url = f"/api/{DOMAIN}/rollback"
    name = f"api:{DOMAIN}:rollback"
    requires_auth = True
    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        try:
            body = await request.json()
        except Exception:
            return self.json({"error": "Body phải là JSON"}, status_code=400)
        snapshot_id = body.get("snapshot_id")
        if not snapshot_id:
            return self.json({"error": "Thiếu snapshot_id"}, status_code=400)
        result = await rollback_snapshot(hass, snapshot_id)
        return self.json(result)


class MAIDeleteSnapshotView(HomeAssistantView):
    """DELETE /api/mai_tools/history/{snapshot_id}"""
    url = f"/api/{DOMAIN}/history/{{snapshot_id}}"
    name = f"api:{DOMAIN}:delete_snapshot"
    requires_auth = True
    async def delete(self, request: web.Request) -> web.Response:
        snapshot_id = request.match_info["snapshot_id"]
        ok = await delete_snapshot(request.app["hass"], snapshot_id)
        return self.json({"deleted": ok})


class MAIClearHistoryView(HomeAssistantView):
    """DELETE /api/mai_tools/history"""
    url = f"/api/{DOMAIN}/history"
    name = f"api:{DOMAIN}:clear_history"
    requires_auth = True
    async def delete(self, request: web.Request) -> web.Response:
        await clear_all_history(request.app["hass"])
        return self.json({"cleared": True})
