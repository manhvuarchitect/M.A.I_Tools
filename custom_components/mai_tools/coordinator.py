"""
M.A.I Tools — Docker Container Coordinator
DataUpdateCoordinator: Poll danh sách Docker containers mỗi 30 giây.
Dữ liệu này được dùng bởi switch.py để tạo dynamic entities.
"""

from __future__ import annotations

import logging
import subprocess
import json
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, COORDINATOR_UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


def _list_containers() -> list[dict[str, Any]]:
    """
    Lấy danh sách tất cả Docker containers (kể cả stopped).
    Chạy đồng bộ — phải được gọi qua async_add_executor_job().

    Returns:
        List of dicts: [{id, short_id, name, status, image, protected, running}, ...]
    """
    try:
        # docker ps -a --format json trả về 1 JSON object mỗi dòng
        result = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{json .}}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            _LOGGER.warning(
                "[M.A.I Tools] docker ps thất bại: %s", result.stderr.strip()
            )
            return []

        containers = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                # Lấy tên container (bỏ dấu "/" đầu nếu có)
                name = entry.get("Names", "").lstrip("/")
                container_id = entry.get("ID", "")
                status = entry.get("Status", "")
                image = entry.get("Image", "")
                state = entry.get("State", "").lower()

                # Kiểm tra nhãn protect=true qua docker inspect
                protected = _check_protect_label(container_id)

                containers.append({
                    "id": container_id,
                    "name": name,
                    "status": status,
                    "state": state,      # "running", "exited", "paused", etc.
                    "image": image,
                    "protected": protected,
                    "running": state == "running",
                })
            except (json.JSONDecodeError, KeyError) as exc:
                _LOGGER.debug("[M.A.I Tools] Không parse được dòng: %s — %s", line, exc)

        _LOGGER.debug("[M.A.I Tools] Tìm thấy %d containers", len(containers))
        return containers

    except subprocess.TimeoutExpired:
        _LOGGER.error("[M.A.I Tools] docker ps timeout")
        return []
    except FileNotFoundError:
        _LOGGER.error("[M.A.I Tools] Không tìm thấy lệnh 'docker'")
        return []
    except Exception as exc:  # noqa: BLE001
        _LOGGER.exception("[M.A.I Tools] Lỗi khi list containers: %s", exc)
        return []


def _check_protect_label(container_id: str) -> bool:
    """
    Kiểm tra container có nhãn protect=true không.
    Dùng docker inspect để đọc labels hiện tại từ Docker daemon.
    """
    if not container_id:
        return False
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format",
             "{{index .Config.Labels \"protect\"}}", container_id],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            val = result.stdout.strip().lower()
            return val == "true"
    except Exception:  # noqa: BLE001
        pass
    return False


class DockerContainerCoordinator(DataUpdateCoordinator):
    """
    Coordinator quản lý dữ liệu danh sách Docker containers.

    Tự động poll mỗi COORDINATOR_UPDATE_INTERVAL giây.
    Switch entities đăng ký lắng nghe coordinator để cập nhật trạng thái.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Khởi tạo coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_docker_containers",
            update_interval=timedelta(seconds=COORDINATOR_UPDATE_INTERVAL),
        )

    async def _async_update_data(self) -> list[dict[str, Any]]:
        """
        Fetch dữ liệu mới từ Docker daemon.
        Được gọi tự động bởi DataUpdateCoordinator.
        """
        try:
            containers = await self.hass.async_add_executor_job(_list_containers)
            return containers
        except Exception as exc:
            raise UpdateFailed(f"Lỗi khi poll Docker containers: {exc}") from exc
