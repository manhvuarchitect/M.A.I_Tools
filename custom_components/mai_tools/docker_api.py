import asyncio
import json
import logging
import os
import aiohttp

_LOGGER = logging.getLogger(__name__)

class DockerAPI:
    def __init__(self, socket_path="/var/run/docker.sock"):
        self.socket_path = socket_path
        self._connector = None
        self._session = None

    async def _get_session(self):
        if not os.path.exists(self.socket_path):
            raise FileNotFoundError(f"Không tìm thấy socket Docker tại {self.socket_path}. Hãy mount volume này vào container HA.")
        if self._session is None or self._session.closed:
            self._connector = aiohttp.UnixConnector(path=self.socket_path)
            self._session = aiohttp.ClientSession(connector=self._connector)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(self, method, path, **kwargs):
        session = await self._get_session()
        url = f"http://localhost/v1.41{path}"
        try:
            async with session.request(method, url, **kwargs) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise Exception(f"Docker API Error {resp.status}: {text}")
                if resp.content_type == "application/json":
                    return await resp.json()
                return await resp.text()
        except Exception as e:
            _LOGGER.error(f"Lỗi gọi Docker API {method} {path}: {e}")
            raise e

    async def list_containers(self):
        """Lấy danh sách tất cả containers"""
        return await self._request("GET", "/containers/json?all=1")

    async def inspect_container(self, container_id):
        """Lấy chi tiết container"""
        return await self._request("GET", f"/containers/{container_id}/json")

    async def stop_container(self, container_id):
        """Dừng container"""
        await self._request("POST", f"/containers/{container_id}/stop")

    async def start_container(self, container_id):
        """Khởi động container"""
        await self._request("POST", f"/containers/{container_id}/start")

    async def kill_container(self, container_id, signal="SIGHUP"):
        """Gửi signal tới container (dùng cho dockerd reload config)"""
        await self._request("POST", f"/containers/{container_id}/kill?signal={signal}")

    async def recreate_container(self, container_id, set_protect=True):
        """Recreate container to update labels (since Docker API doesn't support direct label update)"""
        # 1. Inspect
        info = await self.inspect_container(container_id)
        name = info["Name"].lstrip("/")
        was_running = info["State"]["Running"]
        
        # 2. Build payload from Config
        payload = info["Config"].copy()
        payload["HostConfig"] = info["HostConfig"]
        if "Networks" in info["NetworkSettings"]:
            endpoints = info["NetworkSettings"]["Networks"].copy()
            for net in endpoints.values():
                net.pop("MacAddress", None)
                net.pop("EndpointID", None)
                net.pop("NetworkID", None)
                net.pop("GlobalIPv6Address", None)
            payload["NetworkingConfig"] = {"EndpointsConfig": endpoints}
        
        # Update Labels
        labels = payload.get("Labels", {})
        if labels is None: labels = {}
        if set_protect:
            labels["protect"] = "true"
        else:
            labels.pop("protect", None)
        payload["Labels"] = labels

        # Remove hostname if network mode is network (avoid conflicts)
        if payload["HostConfig"].get("NetworkMode", "") != "default":
             payload.pop("Hostname", None)

        # 3. Stop and Rename Old
        if was_running:
            await self.stop_container(container_id)
        await self._request("POST", f"/containers/{container_id}/rename?name={name}_old_mai")

        # 4. Create New
        try:
            res = await self._request("POST", f"/containers/create?name={name}", json=payload)
            new_id = res["Id"]
            
            # 5. Start New (if it was running)
            if was_running:
                await self.start_container(new_id)
                
            # 6. Delete Old
            await self._request("DELETE", f"/containers/{container_id}?v=1")
            return new_id
        except Exception as e:
            # Rollback
            _LOGGER.error(f"Lỗi recreate, rollback: {e}")
            await self._request("POST", f"/containers/{container_id}/rename?name={name}")
            if was_running:
                await self.start_container(container_id)
            raise e

    async def prune_system(self):
        """Thực thi dọn dẹp hệ thống qua API"""
        filters = json.dumps({"label": ["protect!=true"]})
        reclaimed = 0
        output_logs = []

        # 1. Containers prune
        try:
            c_prune = await self._request("POST", "/containers/prune", params={"filters": filters})
            del_count = len(c_prune.get('ContainersDeleted') or [])
            output_logs.append(f"Xóa containers: {del_count} mục")
            reclaimed += c_prune.get('SpaceReclaimed', 0)
        except Exception as e: output_logs.append(f"Lỗi xóa containers: {e}")

        # 2. Images prune
        try:
            i_prune = await self._request("POST", "/images/prune", params={"filters": filters})
            del_count = len(i_prune.get('ImagesDeleted') or [])
            output_logs.append(f"Xóa images: {del_count} mục")
            reclaimed += i_prune.get('SpaceReclaimed', 0)
        except Exception as e: output_logs.append(f"Lỗi xóa images: {e}")

        # 3. Networks prune
        try:
            n_prune = await self._request("POST", "/networks/prune", params={"filters": filters})
            del_count = len(n_prune.get('NetworksDeleted') or [])
            output_logs.append(f"Xóa networks: {del_count} mục")
        except Exception as e: output_logs.append(f"Lỗi xóa networks: {e}")

        # 4. Volumes prune
        try:
            v_prune = await self._request("POST", "/volumes/prune", params={"filters": filters})
            del_count = len(v_prune.get('VolumesDeleted') or [])
            output_logs.append(f"Xóa volumes: {del_count} mục")
            reclaimed += v_prune.get('SpaceReclaimed', 0)
        except Exception as e: output_logs.append(f"Lỗi xóa volumes: {e}")

        # 5. Build cache prune
        try:
            b_prune = await self._request("POST", "/build/prune", params={"all": "1", "filters": filters})
            del_count = len(b_prune.get('CachesDeleted') or [])
            output_logs.append(f"Xóa build cache: {del_count} mục")
            reclaimed += b_prune.get('SpaceReclaimed', 0)
        except Exception as e: output_logs.append(f"Lỗi xóa build cache: {e}")

        def format_size(size):
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if size < 1024: return f"{size:.2f} {unit}"
                size /= 1024
            return f"{size:.2f} PB"

        output_logs.append(f"\nTổng dung lượng giải phóng: {format_size(reclaimed)}")
        return "\n".join(output_logs), format_size(reclaimed)

# Khởi tạo singleton API
docker_api = DockerAPI()
