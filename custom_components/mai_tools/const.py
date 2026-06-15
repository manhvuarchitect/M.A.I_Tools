"""Constants for M.A.I Tools."""
from pathlib import Path

DOMAIN = "mai_tools"
VERSION = "0.0.6"
BACKUP_FILE_VERSION = "1.0"
HISTORY_STORAGE_KEY = "mai_tools_history"
MAX_HISTORY = None  # None = unlimited, user deletes manually

# Docker Cleanup Service
SERVICE_CLEAN_DOCKER = "clean_docker_arbox"

# Docker Container Coordinator
COORDINATOR_UPDATE_INTERVAL = 30  # giây — tần suất poll danh sách containers

# Docker filesystem paths (dùng cho config.v2.json editing)
DOCKER_ROOT = Path("/var/lib/docker/containers")
DOCKER_PID_FILE = Path("/var/run/docker.pid")

