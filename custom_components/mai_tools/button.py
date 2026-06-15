"""
M.A.I Tools — Docker Cleanup Button Entity
Button entity để kích hoạt lệnh dọn dẹp Docker ARBox từ Lovelace Dashboard.

Entity ID:  button.don_dep_docker_arbox_manhhome
Unique ID:  clean_docker_arbox_manhhome
Service:    mai_tools.clean_docker_arbox
"""

from __future__ import annotations

import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Đăng ký button entity khi integration được setup."""
    async_add_entities([DockerCleanupButton(hass)], update_before_add=False)


class DockerCleanupButton(ButtonEntity):
    """
    Button entity: Dọn dẹp Docker ARBox _manhhome

    Khi nhấn, button sẽ gọi service mai_tools.clean_docker_arbox
    để thực thi lệnh docker system prune với bộ lọc bảo vệ.
    """

    # ── Thuộc tính Entity chuẩn HA ────────────────────────────────────────────

    _attr_name = "Dọn dẹp Docker ARBox _manhhome"
    _attr_unique_id = "clean_docker_arbox_manhhome"
    _attr_icon = "mdi:docker"

    # Không cần polling — button chỉ phản hồi khi nhấn
    _attr_should_poll = False

    # Đặt has_entity_name = False để dùng tên đầy đủ như đã khai báo
    _attr_has_entity_name = False

    def __init__(self, hass: HomeAssistant) -> None:
        """Khởi tạo button entity."""
        self.hass = hass

    @property
    def device_info(self) -> dict:
        """Gắn entity vào virtual device M.A.I Tools."""
        return {
            "identifiers": {(DOMAIN, "mai_tools_arbox")},
            "name": "M.A.I Tools",
            "manufacturer": "manhvuarchitect",
            "model": "M.A.I Tools Integration",
        }

    async def async_press(self) -> None:
        """
        Xử lý sự kiện nhấn nút.

        Gọi service mai_tools.clean_docker_arbox để thực thi
        docker system prune bất đồng bộ. Button sẽ trở về trạng thái
        bình thường ngay sau khi lệnh bắt đầu thực thi (không bị kẹt).
        """
        _LOGGER.info(
            "[M.A.I Tools] Button 'Dọn dẹp Docker ARBox' được nhấn — "
            "kích hoạt service mai_tools.clean_docker_arbox"
        )
        await self.hass.services.async_call(
            domain=DOMAIN,
            service="clean_docker_arbox",
            blocking=False,  # Non-blocking: button trả về ngay, prune chạy ngầm
        )
