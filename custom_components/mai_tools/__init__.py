"""M.A.I Tools — HACS Integration v2.0.3."""
from __future__ import annotations
import logging, os, shutil
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.components.frontend import async_register_built_in_panel
from .supervisor_backup import register_views as register_backup_views
from .api import (
    MAIDeviceListView, MAIExportView, MAITargetEntitiesView,
    MAICheckConflictsView, MAIStorePairsView, MAIApplyView,
    MAIHistoryView, MAIRollbackView, MAIDeleteSnapshotView, MAIClearHistoryView,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass, config): return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.info("[M.A.I Tools] Setting up v0.0.4")
    for view in [
        MAIDeviceListView, MAIExportView, MAITargetEntitiesView,
        MAICheckConflictsView, MAIStorePairsView, MAIApplyView,
        MAIHistoryView, MAIRollbackView, MAIDeleteSnapshotView, MAIClearHistoryView,
    ]:
        hass.http.register_view(view)
    await hass.async_add_executor_job(_copy_frontend, hass)
    register_backup_views(hass)
    async_register_built_in_panel(
        hass, component_name="iframe", sidebar_title="M.A.I Tools",
        sidebar_icon="mdi:swap-horizontal", frontend_url_path="mai-tools",
        config={"url": "/local/mai_tools/index.html?v=0.0.4"}, require_admin=True,
    )
    return True

async def async_unload_entry(hass, entry): return True

def _copy_frontend(hass):
    src = os.path.join(os.path.dirname(__file__), "frontend")
    dst = hass.config.path("www", "mai_tools")
    os.makedirs(dst, exist_ok=True)
    for f in os.listdir(src):
        shutil.copy2(os.path.join(src, f), os.path.join(dst, f))
