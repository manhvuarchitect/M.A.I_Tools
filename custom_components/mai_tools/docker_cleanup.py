"""
Module thực thi lệnh dọn dẹp Docker an toàn (Docker system prune).
Bắt buộc áp dụng bộ lọc: --filter "label!=protect=true"
"""

import logging
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .docker_api import docker_api

_LOGGER = logging.getLogger(__name__)


async def async_setup_docker_cleanup(hass: HomeAssistant):
    """Thiết lập tính năng Docker Cleanup."""

    async def async_clean_docker(call: ServiceCall):
        """Execute docker prune via API."""
        try:
            output, reclaimed = await docker_api.prune_system()
            _LOGGER.info(f"Dọn dẹp Docker thành công. Đã giải phóng: {reclaimed}")
            _LOGGER.debug(f"Kết quả:\n{output}")
        except Exception as e:
            _LOGGER.error(f"Lỗi khi dọn dẹp Docker: {e}")
            raise HomeAssistantError(f"Dọn dẹp thất bại: {e}")

    hass.services.async_register(
        DOMAIN,
        "clean_docker_arbox",
        async_clean_docker,
    )


class DockerCleanupView(HomeAssistantView):
    """HTTP API View để kích hoạt Docker Cleanup từ Frontend."""
    url = "/api/mai_tools/docker_cleanup"
    name = "api:mai_tools:docker_cleanup"
    requires_auth = True

    async def post(self, request):
        """Xử lý yêu cầu dọn dẹp từ giao diện (POST /api/mai_tools/docker_cleanup)."""
        _LOGGER.info("[M.A.I Tools] Nhận yêu cầu dọn dẹp Docker từ giao diện.")

        try:
            # Chạy logic dọn dẹp qua API
            output, reclaimed = await docker_api.prune_system()
            _LOGGER.info(f"Dọn dẹp Docker thành công. Đã giải phóng: {reclaimed}")
            
            return web.json_response(
                {
                    "success": True,
                    "reclaimed_space": reclaimed,
                    "output": output,
                    "error": None,
                }
            )
        except Exception as err:
            _LOGGER.error("[M.A.I Tools] API trả về lỗi dọn dẹp Docker: %s", err)
            return web.json_response(
                {
                    "success": False,
                    "reclaimed_space": None,
                    "output": "Đã xảy ra lỗi trong quá trình dọn dẹp.",
                    "error": str(err),
                },
                status=500,
            )
