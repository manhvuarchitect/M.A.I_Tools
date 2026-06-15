"""
M.A.I Tools — Docker Container Manager
Core logic gán/gỡ nhãn protect=true cho containers + HTTP API Views.

Chiến lược gán nhãn:
  - Container STOPPED: Edit config.v2.json trực tiếp + gửi SIGHUP dockerd
  - Container RUNNING: Stop → edit config.v2.json → Start lại (~vài giây downtime)

Fallback: Nếu /var/lib/docker không accessible, trả về lỗi rõ ràng.

HTTP API:
  GET  /api/mai_tools/docker_containers    → Danh sách containers
  POST /api/mai_tools/docker_protect       → Gán/gỡ nhãn bảo vệ
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOCKER_ROOT, DOCKER_PID_FILE, DOMAIN
from .coordinator import DockerContainerCoordinator, _list_containers

_LOGGER = logging.getLogger(__name__)

# Timeout cho các subprocess call ngắn
_CMD_TIMEOUT = 30


# ── Hàm helper đồng bộ (chạy trong executor thread) ─────────────────────────

def _get_full_container_id(short_id: str) -> str | None:
    """Lấy full 64-char container ID từ short ID qua docker inspect."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.Id}}", short_id],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return None


def _get_container_state(container_id: str) -> str:
    """Lấy trạng thái container: running, exited, paused, ..."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}}", container_id],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip().lower()
    except Exception:  # noqa: BLE001
        pass
    return "unknown"


def _edit_config_v2_label(full_id: str, protected: bool) -> dict[str, Any]:
    """
    Chỉnh sửa nhãn protect trong file config.v2.json của container.

    Args:
        full_id: Full 64-char container ID
        protected: True = thêm protect=true, False = xóa nhãn

    Returns:
        dict {success, error, note}
    """
    config_path = DOCKER_ROOT / full_id / "config.v2.json"

    # Kiểm tra Docker root có accessible không
    if not DOCKER_ROOT.exists():
        return {
            "success": False,
            "error": (
                f"Không truy cập được {DOCKER_ROOT}. "
                "Nếu HA chạy trong container, hãy mount: "
                "-v /var/lib/docker:/var/lib/docker:rw"
            ),
        }

    if not config_path.exists():
        return {
            "success": False,
            "error": f"Không tìm thấy config.v2.json cho container {full_id[:12]}",
        }

    try:
        # Đọc file hiện tại
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)

        # Cập nhật nhãn
        config.setdefault("Config", {})
        labels: dict = config["Config"].get("Labels") or {}
        if protected:
            labels["protect"] = "true"
        else:
            labels.pop("protect", None)
        config["Config"]["Labels"] = labels

        # Ghi lại file
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

        _LOGGER.info(
            "[M.A.I Tools] Đã %s nhãn protect cho container %s",
            "gán" if protected else "gỡ",
            full_id[:12],
        )

        # Gửi SIGHUP tới dockerd để reload metadata
        _signal_dockerd_reload()

        return {"success": True, "error": None}

    except PermissionError:
        # Thử với sudo
        _LOGGER.warning("[M.A.I Tools] PermissionError khi edit config.v2.json, thử sudo...")
        try:
            import tempfile, shutil
            # Tạo file tạm với nội dung mới
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
            labels = config["Config"].get("Labels") or {}
            if protected:
                labels["protect"] = "true"
            else:
                labels.pop("protect", None)
            config["Config"]["Labels"] = labels

            with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                             delete=False, encoding="utf-8") as tmp:
                json.dump(config, tmp, indent=2)
                tmp_path = tmp.name

            result = subprocess.run(
                ["sudo", "cp", tmp_path, str(config_path)],
                capture_output=True, text=True, timeout=10,
            )
            Path(tmp_path).unlink(missing_ok=True)

            if result.returncode != 0:
                return {"success": False, "error": f"sudo cp thất bại: {result.stderr.strip()}"}

            _signal_dockerd_reload()
            return {"success": True, "error": None}
        except Exception as exc2:
            return {"success": False, "error": f"Không thể ghi file (kể cả sudo): {exc2}"}

    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"Lỗi khi edit config.v2.json: {exc}"}


def _signal_dockerd_reload() -> None:
    """
    Gửi SIGHUP tới dockerd để reload metadata containers.
    SIGHUP chỉ reload config — KHÔNG restart containers.
    """
    try:
        # Cách 1: Đọc PID từ file
        if DOCKER_PID_FILE.exists():
            pid = DOCKER_PID_FILE.read_text().strip()
            result = subprocess.run(
                ["kill", "-HUP", pid],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                _LOGGER.info("[M.A.I Tools] Đã gửi SIGHUP tới dockerd (PID %s)", pid)
                return

        # Cách 2: pkill
        result = subprocess.run(
            ["pkill", "-HUP", "dockerd"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            _LOGGER.info("[M.A.I Tools] Đã gửi SIGHUP tới dockerd via pkill")
        else:
            _LOGGER.warning(
                "[M.A.I Tools] Không thể gửi SIGHUP tới dockerd. "
                "Label đã được ghi vào file nhưng Docker daemon chưa reload. "
                "Có thể cần restart dockerd thủ công hoặc chạy: "
                "kill -HUP $(pgrep dockerd)"
            )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("[M.A.I Tools] SIGHUP dockerd thất bại: %s", exc)


def _stop_container(container_id: str) -> dict[str, Any]:
    """Stop container gracefully (timeout 10s)."""
    try:
        result = subprocess.run(
            ["docker", "stop", "--time", "10", container_id],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode == 0:
            return {"success": True}
        return {"success": False, "error": result.stderr.strip()}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _start_container(container_id: str) -> dict[str, Any]:
    """Start container đã dừng."""
    try:
        result = subprocess.run(
            ["docker", "start", container_id],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return {"success": True}
        return {"success": False, "error": result.stderr.strip()}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _set_protect_label(container_id: str, protected: bool) -> dict[str, Any]:
    """
    Entry point chính để gán/gỡ nhãn bảo vệ.

    Chiến lược:
      1. Lấy full ID từ short ID
      2. Kiểm tra trạng thái container
      3. Nếu RUNNING: Stop → edit file → Start lại
      4. Nếu STOPPED: Chỉ edit file + SIGHUP
      5. Luôn thử edit file; fallback rõ ràng nếu thất bại

    Returns:
        dict {success, protected, container_id, message, error}
    """
    _LOGGER.info(
        "[M.A.I Tools] Yêu cầu %s bảo vệ cho container %s",
        "BẬT" if protected else "TẮT",
        container_id,
    )

    # Lấy full container ID
    full_id = _get_full_container_id(container_id)
    if not full_id:
        return {
            "success": False,
            "error": f"Không tìm thấy container: {container_id}",
        }

    state = _get_container_state(container_id)
    was_running = state == "running"
    notes = []

    # Nếu container đang chạy: cần stop trước
    if was_running:
        _LOGGER.info(
            "[M.A.I Tools] Container %s đang RUNNING — dừng tạm để cập nhật nhãn...",
            container_id,
        )
        stop_result = _stop_container(container_id)
        if not stop_result["success"]:
            return {
                "success": False,
                "error": f"Không thể dừng container: {stop_result.get('error')}",
            }
        notes.append("Container đã được dừng tạm để cập nhật nhãn.")

    # Edit config.v2.json
    edit_result = _edit_config_v2_label(full_id, protected)

    # Nếu container đang chạy: khởi động lại dù edit thành công hay thất bại
    if was_running:
        start_result = _start_container(container_id)
        if start_result["success"]:
            notes.append("Container đã được khởi động lại.")
        else:
            notes.append(
                f"⚠️ CẢNH BÁO: Không thể khởi động lại container: "
                f"{start_result.get('error')}. Cần start thủ công!"
            )
            _LOGGER.error(
                "[M.A.I Tools] Không thể start lại container %s: %s",
                container_id, start_result.get("error"),
            )

    if edit_result["success"]:
        action = "BẬT" if protected else "TẮT"
        _LOGGER.info("[M.A.I Tools] Đã %s bảo vệ container %s", action, container_id)
        return {
            "success": True,
            "protected": protected,
            "container_id": container_id,
            "message": f"Đã {'bật' if protected else 'tắt'} bảo vệ. " + " ".join(notes),
            "error": None,
        }
    else:
        # Edit thất bại nhưng container đã được start lại (nếu có)
        return {
            "success": False,
            "container_id": container_id,
            "error": edit_result.get("error"),
            "message": " ".join(notes),
        }


# ── HTTP API Views ────────────────────────────────────────────────────────────

class DockerContainerListView(HomeAssistantView):
    """
    GET /api/mai_tools/docker_containers
    Trả về danh sách tất cả Docker containers với trạng thái bảo vệ.
    """

    url = "/api/mai_tools/docker_containers"
    name = "api:mai_tools:docker_containers"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]

        # Ưu tiên dùng data từ coordinator nếu có (tránh gọi subprocess thêm)
        coordinator: DockerContainerCoordinator | None = (
            hass.data.get(DOMAIN, {}).get("coordinator")
        )
        if coordinator and coordinator.data is not None:
            return self.json({"containers": coordinator.data})

        # Fallback: gọi trực tiếp
        containers = await hass.async_add_executor_job(_list_containers)
        return self.json({"containers": containers})


class DockerContainerProtectView(HomeAssistantView):
    """
    POST /api/mai_tools/docker_protect
    Body: {"container_id": "...", "protected": true/false}
    Gán hoặc gỡ nhãn protect=true cho container chỉ định.
    """

    url = "/api/mai_tools/docker_protect"
    name = "api:mai_tools:docker_protect"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]

        try:
            body = await request.json()
        except Exception:
            return self.json({"success": False, "error": "Body phải là JSON"}, status_code=400)

        container_id = body.get("container_id", "").strip()
        protected = bool(body.get("protected", False))

        if not container_id:
            return self.json({"success": False, "error": "Thiếu container_id"}, status_code=400)

        result = await hass.async_add_executor_job(_set_protect_label, container_id, protected)

        # Sau khi thay đổi, request coordinator refresh để sync switch entities
        coordinator: DockerContainerCoordinator | None = (
            hass.data.get(DOMAIN, {}).get("coordinator")
        )
        if coordinator:
            await coordinator.async_request_refresh()

        status_code = 200 if result["success"] else 500
        return self.json(result, status_code=status_code)
