"""
Container Manager (v0.0.7).
Quản lý bảo vệ container bằng cách dùng Docker API (Unix Socket).
Recreate container thay vì sửa file config json (Vì API không hỗ trợ sửa label trực tiếp).
"""

import logging
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .docker_api import docker_api
from .coordinator import DockerContainerCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class DockerContainerListView(HomeAssistantView):
    """API trả về danh sách container cho Frontend."""
    url = "/api/mai_tools/docker_containers"
    name = "api:mai_tools:docker_containers"
    requires_auth = True

    async def get(self, request):
        """GET /api/mai_tools/docker_containers"""
        try:
            coordinator: DockerContainerCoordinator = request.app["hass"].data[DOMAIN]["coordinator"]
            
            # Buộc cập nhật dữ liệu mới nhất nếu cần
            await coordinator.async_request_refresh()
            data = coordinator.data or {}
            
            # Map dữ liệu coordinator -> danh sách mảng cho UI
            containers_list = []
            for cid, info in data.items():
                containers_list.append({
                    "id": cid[:12],  # UI chỉ cần short ID
                    "full_id": cid,
                    "name": info["name"],
                    "state": info["state"],
                    "protected": info["protected"]
                })
            
            # Sort by name
            containers_list.sort(key=lambda x: x["name"])

            return web.json_response({
                "success": True,
                "containers": containers_list
            })
        except Exception as e:
            _LOGGER.error(f"[M.A.I Tools] Lỗi khi lấy danh sách container: {e}")
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)


class DockerProtectView(HomeAssistantView):
    """API nhận lệnh bật/tắt bảo vệ container từ Frontend."""
    url = "/api/mai_tools/docker_protect"
    name = "api:mai_tools:docker_protect"
    requires_auth = True

    async def post(self, request):
        """POST /api/mai_tools/docker_protect"""
        try:
            body = await request.json()
            container_id = body.get("container_id")
            is_protected = bool(body.get("protected", False))

            if not container_id:
                return web.json_response({"success": False, "error": "Missing container_id"}, status=400)

            _LOGGER.info(f"[M.A.I Tools] Yêu cầu {'BẬT' if is_protected else 'TẮT'} bảo vệ cho container {container_id}")

            # Thực thi gán nhãn qua API (Recreate container)
            new_id = await docker_api.recreate_container(container_id, set_protect=is_protected)

            # Làm mới coordinator data
            coordinator: DockerContainerCoordinator = request.app["hass"].data[DOMAIN]["coordinator"]
            await coordinator.async_request_refresh()

            return web.json_response({
                "success": True,
                "message": f"Đã {'BẬT' if is_protected else 'TẮT'} bảo vệ thành công.",
                "new_id": new_id
            })

        except Exception as e:
            _LOGGER.error(f"[M.A.I Tools] Lỗi khi cấu hình bảo vệ: {e}")
            return web.json_response({
                "success": False,
                "error": str(e),
                "message": "Không thể cấu hình bảo vệ qua Docker API."
            }, status=500)
