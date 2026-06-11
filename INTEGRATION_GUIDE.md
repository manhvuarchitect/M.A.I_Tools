# Supervisor Backup Manager — Hướng dẫn tích hợp vào M.A.I_Tools

## Tổng quan

Tính năng này giải quyết lỗi **"Lỗi khi tải ứng dụng"** do token mismatch giữa Supervisor và HA container.

### Chức năng:
- ✅ **Backup** các file config critical của Supervisor
- ✅ **Restore** về bất kỳ snapshot nào với 1 click
- ✅ **Token mismatch detection** — tự động phát hiện và cảnh báo
- ✅ **Fix token** — hướng dẫn chạy script sửa tự động
- ✅ **Auto-prune** — giữ tối đa 10 snapshots gần nhất

---

## Các file được backup

| File | Mục đích |
|------|----------|
| `homeassistant.json` | Token, version, image của HA |
| `config.json` | Config tổng của Supervisor |
| `addons.json` | Danh sách và config các add-on |
| `dns.json`, `audio.json`, `cli.json`… | Config các service phụ trợ |

---

## Cách tích hợp vào repo

### Bước 1: Thêm file Python

Copy `supervisor_backup.py` vào:
```
custom_components/mai_tools/supervisor_backup.py
```

### Bước 2: Đăng ký views trong `__init__.py`

Thêm vào hàm `async_setup_entry` trong `__init__.py`:

```python
from .supervisor_backup import register_views as register_backup_views

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # ... code hiện có ...
    
    # Đăng ký Supervisor Backup Manager views
    register_backup_views(hass)
    
    return True
```

### Bước 3: Thêm panel HTML

Copy `supervisor_backup_panel.html` vào:
```
custom_components/mai_tools/www/supervisor_backup_panel.html
```

Hoặc tích hợp vào panel hiện có của mai_tools bằng cách thêm tab/section mới.

### Bước 4: Đăng ký static path (nếu cần)

Trong `__init__.py`, thêm static path cho panel HTML:

```python
hass.http.async_register_static_paths([
    StaticPathConfig(
        "/mai_tools/supervisor_backup",
        hass.config.path("custom_components/mai_tools/www"),
        False,
    )
])
```

---

## API Endpoints

| Method | URL | Mô tả |
|--------|-----|-------|
| GET | `/api/mai_tools/supervisor_backup/list` | Danh sách snapshots + status hiện tại |
| GET | `/api/mai_tools/supervisor_backup/status` | Chỉ lấy status token |
| POST | `/api/mai_tools/supervisor_backup/create` | Tạo backup mới |
| POST | `/api/mai_tools/supervisor_backup/restore` | Restore một snapshot |
| DELETE | `/api/mai_tools/supervisor_backup/delete` | Xóa một snapshot |

### POST /create body:
```json
{ "label": "Trước khi update HA 2026.6" }
```

### POST /restore body:
```json
{ "snapshot_id": "20260611_083000" }
```

---

## Vị trí lưu backup

Backups được lưu tại:
```
/config/.mai_supervisor_backups/
  └── 20260611_083000/
      ├── meta.json
      ├── homeassistant.json
      ├── config.json
      ├── addons.json
      ├── fix_token.sh   ← Script fix token tự động
      └── ...
```

Thư mục `/config/` là volume được mount vào HA container, nên **data sẽ tồn tại** kể cả khi recreate container.

---

## Script fix token

Mỗi snapshot tự động kèm file `fix_token.sh`. Khi gặp lỗi token mismatch, chạy:

```bash
# SSH vào máy, sau đó:
bash /config/.mai_supervisor_backups/<snapshot_id>/fix_token.sh
```

Hoặc dùng script đã lưu sẵn:
```bash
~/fix-ha-token.sh
```

---

## Gợi ý cho Roadmap

- [ ] **Auto-backup trigger**: Tự động tạo backup khi Supervisor hoặc HA được restart
- [ ] **Cron schedule**: Backup định kỳ (hàng ngày/tuần)
- [ ] **Google Drive sync**: Tích hợp với addon Google Drive Backup
- [ ] **Webhook notify**: Gửi thông báo khi token mismatch được phát hiện
