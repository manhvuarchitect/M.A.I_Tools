"""
M.A.I Tools — Docker Container Protection Switch Entities
Tạo động một Switch entity cho mỗi Docker container trên host.

Entity format:
  Name:      Bảo vệ Container {name} _manhhome
  Unique ID: protect_container_{name}_manhhome
  Icon:      mdi:shield-lock (ON) / mdi:shield-off (OFF)
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DockerContainerCoordinator
from .container_manager import _set_protect_label

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """
    Thiết lập switch entities từ dữ liệu coordinator.

    Sử dụng pattern dynamic entity discovery:
    - Lấy danh sách containers từ coordinator
    - Đăng ký listener để thêm entity mới khi phát hiện container mới
    """
    coordinator: DockerContainerCoordinator = hass.data[DOMAIN]["coordinator"]

    # Theo dõi các container đã tạo entity (tránh tạo trùng)
    known_container_ids: set[str] = set()

    @callback
    def _add_new_entities() -> None:
        """Thêm switch entity cho container mới được phát hiện."""
        if not coordinator.data:
            return

        new_entities = []
        for container in coordinator.data:
            cid = container["id"]
            if cid not in known_container_ids:
                known_container_ids.add(cid)
                new_entities.append(DockerProtectSwitch(coordinator, container))

        if new_entities:
            _LOGGER.info(
                "[M.A.I Tools] Thêm %d switch entity mới cho containers",
                len(new_entities),
            )
            async_add_entities(new_entities)

    # Đăng ký listener — được gọi mỗi khi coordinator cập nhật data
    entry.async_on_unload(
        coordinator.async_add_listener(_add_new_entities)
    )

    # Tạo entities ngay lần đầu
    _add_new_entities()


class DockerProtectSwitch(CoordinatorEntity[DockerContainerCoordinator], SwitchEntity):
    """
    Switch entity đại diện cho trạng thái bảo vệ của một Docker container.

    Kế thừa CoordinatorEntity để tự động cập nhật khi coordinator refresh.
    """

    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: DockerContainerCoordinator,
        container_data: dict[str, Any],
    ) -> None:
        """Khởi tạo switch từ dữ liệu container."""
        super().__init__(coordinator)

        self._container_id = container_data["id"]
        self._container_name = container_data["name"]

        # Tên sạch cho unique_id (chỉ giữ ký tự an toàn)
        safe_name = self._container_name.lower().replace("-", "_").replace(".", "_")

        self._attr_name = f"Bảo vệ Container {self._container_name} _manhhome"
        self._attr_unique_id = f"protect_container_{safe_name}_manhhome"

    @property
    def _container_current_data(self) -> dict[str, Any] | None:
        """Lấy data hiện tại của container từ coordinator."""
        if not self.coordinator.data:
            return None
        for c in self.coordinator.data:
            if c["id"] == self._container_id:
                return c
        return None

    @property
    def is_on(self) -> bool:
        """Trả về True nếu container đang được bảo vệ (protect=true)."""
        data = self._container_current_data
        if data is None:
            return False
        return bool(data.get("protected", False))

    @property
    def icon(self) -> str:
        """Icon thay đổi theo trạng thái bảo vệ."""
        return "mdi:shield-lock" if self.is_on else "mdi:shield-off"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Thuộc tính bổ sung hiển thị trong HA Developer Tools."""
        data = self._container_current_data
        if not data:
            return {}
        return {
            "container_id": self._container_id,
            "container_name": self._container_name,
            "status": data.get("status", "unknown"),
            "state": data.get("state", "unknown"),
            "image": data.get("image", ""),
            "running": data.get("running", False),
        }

    @property
    def available(self) -> bool:
        """Entity available nếu coordinator có data và container vẫn tồn tại."""
        return (
            self.coordinator.last_update_success
            and self._container_current_data is not None
        )

    @property
    def device_info(self) -> dict[str, Any]:
        """Gắn entity vào virtual device M.A.I Tools."""
        return {
            "identifiers": {(DOMAIN, "mai_tools_arbox")},
            "name": "M.A.I Tools",
            "manufacturer": "manhvuarchitect",
            "model": "M.A.I Tools Integration",
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """
        Bật bảo vệ: Gán nhãn protect=true cho container.

        Nếu container đang RUNNING: Stop → Edit label → Start lại.
        """
        _LOGGER.info(
            "[M.A.I Tools] Switch BẬT bảo vệ container: %s", self._container_name
        )
        result = await self.hass.async_add_executor_job(
            _set_protect_label, self._container_id, True
        )
        if result["success"]:
            _LOGGER.info(
                "[M.A.I Tools] ✅ Đã BẬT bảo vệ container %s. %s",
                self._container_name,
                result.get("message", ""),
            )
        else:
            _LOGGER.error(
                "[M.A.I Tools] ❌ Thất bại khi BẬT bảo vệ container %s: %s",
                self._container_name,
                result.get("error"),
            )
        # Refresh coordinator để cập nhật trạng thái entity
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """
        Tắt bảo vệ: Gỡ nhãn protect khỏi container.

        Nếu container đang RUNNING: Stop → Edit label → Start lại.
        """
        _LOGGER.info(
            "[M.A.I Tools] Switch TẮT bảo vệ container: %s", self._container_name
        )
        result = await self.hass.async_add_executor_job(
            _set_protect_label, self._container_id, False
        )
        if result["success"]:
            _LOGGER.info(
                "[M.A.I Tools] ✅ Đã TẮT bảo vệ container %s. %s",
                self._container_name,
                result.get("message", ""),
            )
        else:
            _LOGGER.error(
                "[M.A.I Tools] ❌ Thất bại khi TẮT bảo vệ container %s: %s",
                self._container_name,
                result.get("error"),
            )
        # Refresh coordinator để cập nhật trạng thái entity
        await self.coordinator.async_request_refresh()
