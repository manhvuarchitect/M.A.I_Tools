"""M.A.I Tools — HACS Integration v2.0.6."""
from __future__ import annotations
import logging, os, shutil
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.components.frontend import async_register_built_in_panel
from .supervisor_backup import register_views as register_backup_views
from .api import (
    MAIDeviceListView, MAIExportView, MAITargetEntitiesView,
    MAICheckConflictsView, MAIStorePairsView, MAIApplyView,
    MAIHistoryView, MAIRollbackView, MAIDeleteSnapshotView, MAIClearHistoryView,
)
from .docker_cleanup import DockerCleanupView, async_clean_docker_arbox
from .container_manager import DockerContainerListView, DockerContainerProtectView
from .coordinator import DockerContainerCoordinator
from .const import DOMAIN, SERVICE_CLEAN_DOCKER

_LOGGER = logging.getLogger(__name__)

# Platforms được đăng ký (button + switch)
_PLATFORMS = ["button", "switch"]


async def async_setup(hass, config): return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.info("[M.A.I Tools] Setting up v0.0.6")

    # ── Khởi tạo hass.data cho domain ─────────────────────────────────────
    hass.data.setdefault(DOMAIN, {})

    # ── Khởi tạo Coordinator và fetch data lần đầu ────────────────────────
    coordinator = DockerContainerCoordinator(hass)
    hass.data[DOMAIN]["coordinator"] = coordinator
    # Fetch lần đầu (không raise nếu Docker chưa sẵn sàng)
    await coordinator.async_config_entry_first_refresh()

    # ── Đăng ký các REST API View ──────────────────────────────────────────
    for view in [
        MAIDeviceListView, MAIExportView, MAITargetEntitiesView,
        MAICheckConflictsView, MAIStorePairsView, MAIApplyView,
        MAIHistoryView, MAIRollbackView, MAIDeleteSnapshotView, MAIClearHistoryView,
        DockerCleanupView,          # POST /api/mai_tools/docker_cleanup
        DockerContainerListView,    # GET  /api/mai_tools/docker_containers
        DockerContainerProtectView, # POST /api/mai_tools/docker_protect
    ]:
        hass.http.register_view(view)

    # ── Copy frontend assets ───────────────────────────────────────────────
    await hass.async_add_executor_job(_copy_frontend, hass)

    # ── Đăng ký Supervisor Backup views ───────────────────────────────────
    register_backup_views(hass)

    # ── Đăng ký Button + Switch platforms ─────────────────────────────────
    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

    # ── Đăng ký Service: mai_tools.clean_docker_arbox ─────────────────────
    hass.services.async_register(
        domain=DOMAIN,
        service=SERVICE_CLEAN_DOCKER,
        service_func=lambda call: hass.async_create_task(
            async_clean_docker_arbox(hass, call)
        ),
        schema=vol.Schema({}),
    )
    _LOGGER.info(
        "[M.A.I Tools] Đã đăng ký service: %s.%s", DOMAIN, SERVICE_CLEAN_DOCKER
    )

    # ── Đăng ký panel sidebar ─────────────────────────────────────────────
    async_register_built_in_panel(
        hass, component_name="iframe", sidebar_title="M.A.I Tools",
        sidebar_icon="mdi:swap-horizontal", frontend_url_path="mai-tools",
        config={"url": "/local/mai_tools/index.html?v=0.0.7"}, require_admin=True,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Gỡ bỏ integration và unload tất cả platform đã đăng ký."""
    # Hủy đăng ký service
    hass.services.async_remove(DOMAIN, SERVICE_CLEAN_DOCKER)
    # Xóa domain data
    hass.data.pop(DOMAIN, None)
    # Unload tất cả platforms
    return await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)


def _copy_frontend(hass):
    src = os.path.join(os.path.dirname(__file__), "frontend")
    dst = hass.config.path("www", "mai_tools")
    os.makedirs(dst, exist_ok=True)
    for f in os.listdir(src):
        shutil.copy2(os.path.join(src, f), os.path.join(dst, f))
