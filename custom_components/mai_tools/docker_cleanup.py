"""
M.A.I Tools — Docker Cleanup Service
Thực thi lệnh docker system prune an toàn với bộ lọc nhãn bảo vệ.
Service: mai_tools.clean_docker_arbox
HTTP API: POST /api/mai_tools/docker_cleanup
"""

from __future__ import annotations

import logging
import re
import subprocess
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, ServiceCall

_LOGGER = logging.getLogger(__name__)

# ── Hằng số an toàn bắt buộc ────────────────────────────────────────────────
# Filter này KHÔNG được phép thay đổi hay ghi đè từ bên ngoài.
# Mục đích: bảo vệ các container/volume được đánh nhãn protect=true khỏi bị xóa.
_DOCKER_PRUNE_CMD = [
    "docker", "system", "prune",
    "-a",          # Xóa tất cả image không dùng (kể cả image đang dừng)
    "-f",          # Không hỏi xác nhận
    "--volumes",   # Bao gồm volume không dùng
    "--filter", "label!=protect=true",  # BỘ LỌC AN TOÀN TUYỆT ĐỐI
]

# Timeout tối đa cho lệnh docker prune (giây)
_PRUNE_TIMEOUT_SECONDS = 300  # 5 phút


def _parse_reclaimed_space(output: str) -> str | None:
    """Bóc tách thông tin dung lượng đã giải phóng từ output của docker prune."""
    match = re.search(
        r"Total reclaimed space:\s*([\d.]+\s*[A-Za-z]+)",
        output,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return None


def _run_docker_prune() -> dict[str, Any]:
    """
    Chạy lệnh docker system prune đồng bộ (được gọi qua executor_job).

    Hàm này PHẢI được gọi thông qua hass.async_add_executor_job()
    để không block Event Loop của Home Assistant.

    Returns:
        dict với các key: success, reclaimed_space, output, error
    """
    _LOGGER.info(
        "[M.A.I Tools] Docker cleanup started. Command: %s",
        " ".join(_DOCKER_PRUNE_CMD),
    )

    try:
        result = subprocess.run(
            _DOCKER_PRUNE_CMD,
            capture_output=True,
            text=True,
            timeout=_PRUNE_TIMEOUT_SECONDS,
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        combined_output = stdout + ("\n" + stderr if stderr else "")

        if result.returncode == 0:
            reclaimed = _parse_reclaimed_space(stdout)
            if reclaimed:
                _LOGGER.info(
                    "[M.A.I Tools] Docker cleanup hoàn thành. Đã giải phóng: %s",
                    reclaimed,
                )
            else:
                _LOGGER.info(
                    "[M.A.I Tools] Docker cleanup hoàn thành. (Không có tài nguyên nào cần dọn)"
                )
            return {
                "success": True,
                "reclaimed_space": reclaimed or "0 B",
                "output": combined_output,
                "error": None,
            }
        else:
            _LOGGER.error(
                "[M.A.I Tools] Docker cleanup thất bại (exit code %d): %s",
                result.returncode,
                stderr or stdout,
            )
            return {
                "success": False,
                "reclaimed_space": None,
                "output": combined_output,
                "error": f"Exit code {result.returncode}: {stderr or 'Unknown error'}",
            }

    except subprocess.TimeoutExpired:
        msg = f"Lệnh docker prune bị timeout sau {_PRUNE_TIMEOUT_SECONDS} giây."
        _LOGGER.error("[M.A.I Tools] %s", msg)
        return {
            "success": False,
            "reclaimed_space": None,
            "output": "",
            "error": msg,
        }
    except FileNotFoundError:
        msg = "Không tìm thấy lệnh 'docker'. Hãy đảm bảo Docker đã được cài đặt và có trong PATH."
        _LOGGER.error("[M.A.I Tools] %s", msg)
        return {
            "success": False,
            "reclaimed_space": None,
            "output": "",
            "error": msg,
        }
    except Exception as exc:  # noqa: BLE001
        msg = f"Lỗi không xác định khi chạy docker prune: {exc}"
        _LOGGER.exception("[M.A.I Tools] %s", msg)
        return {
            "success": False,
            "reclaimed_space": None,
            "output": "",
            "error": msg,
        }


async def async_clean_docker_arbox(hass: HomeAssistant, call: ServiceCall) -> None:
    """
    Service handler bất đồng bộ cho mai_tools.clean_docker_arbox.

    Được đăng ký tại __init__.py và có thể gọi từ:
    - Button entity (button.py)
    - Developer Tools > Services
    - Automations
    """
    _LOGGER.info("[M.A.I Tools] Service clean_docker_arbox được kích hoạt.")
    # Chạy lệnh blocking trong thread pool để không block Event Loop
    result = await hass.async_add_executor_job(_run_docker_prune)

    if result["success"]:
        _LOGGER.info(
            "[M.A.I Tools] Service hoàn thành. Dung lượng đã giải phóng: %s",
            result["reclaimed_space"],
        )
    else:
        _LOGGER.error(
            "[M.A.I Tools] Service thất bại: %s",
            result["error"],
        )


# ── HTTP API View ────────────────────────────────────────────────────────────

class DockerCleanupView(HomeAssistantView):
    """
    POST /api/mai_tools/docker_cleanup

    Được gọi từ frontend panel để thực thi lệnh docker prune
    và trả về kết quả JSON cho UI hiển thị.
    """

    url = "/api/mai_tools/docker_cleanup"
    name = "api:mai_tools:docker_cleanup"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        _LOGGER.info("[M.A.I Tools] HTTP API docker_cleanup được gọi từ frontend.")
        result = await hass.async_add_executor_job(_run_docker_prune)
        status_code = 200 if result["success"] else 500
        return self.json(result, status_code=status_code)
