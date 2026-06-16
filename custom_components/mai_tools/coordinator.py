"""
DataUpdateCoordinator for Docker containers (v0.0.7 - Docker API Socket mode).
"""

import asyncio
import logging
from datetime import timedelta
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, COORDINATOR_UPDATE_INTERVAL
from .docker_api import docker_api

_LOGGER = logging.getLogger(__name__)


class DockerContainerCoordinator(DataUpdateCoordinator):
    """Lấy danh sách container định kỳ qua Docker API Socket."""

    def __init__(self, hass: HomeAssistant):
        """Khởi tạo coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_docker_containers",
            update_interval=timedelta(seconds=COORDINATOR_UPDATE_INTERVAL),
        )

    async def _async_update_data(self):
        """Fetch dữ liệu từ Docker API Socket."""
        try:
            containers = await docker_api.list_containers()
            results = {}

            for c in containers:
                container_id = c.get("Id")
                name = c.get("Names", [""])[0].lstrip("/")
                state = c.get("State", "unknown")
                labels = c.get("Labels", {})
                
                is_protected = labels.get("protect") == "true"

                results[container_id] = {
                    "id": container_id,
                    "name": name,
                    "state": state,
                    "protected": is_protected,
                }

            return results
        except Exception as e:
            _LOGGER.error(f"Lỗi khi fetch danh sách docker containers: {e}")
            raise UpdateFailed(f"Lỗi Docker API: {e}")
