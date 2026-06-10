# M.A.I Tools

**HACS Integration** — Bộ công cụ quản lý Home Assistant.

Tác giả: [@manhvuarchitect](https://github.com/manhvuarchitect) · [midar.vn](https://midar.vn)

---

## Tính năng nổi bật (v0.0.3)

### 📤 Entity Export — 3 chế độ
| Chế độ | Mô tả |
|---|---|
| Theo thiết bị | Tick chọn từng device trong danh sách |
| Theo phòng/Area | Tick theo Room, tự chọn hết device trong phòng |
| Tất cả | 1 click export toàn bộ hệ thống |

Tất cả 3 chế độ tạo ra **1 file `.json` duy nhất** chứa nhiều thiết bị.

### 🔗 Entity Import — Tick-to-pair
- Upload file backup → danh sách thiết bị nguồn hiện ra ngay
- **Tick 1 entity nguồn** (cột trái) + **tick 1 entity đích** (cột phải) → nhấn **Ghép**
- Ghép nhiều cặp tùy ý (kể cả từ các thiết bị khác nhau trong file)
- Ví dụ: lấy 2 entity từ công tắc 4 nút → gắn vào 2 entity của công tắc 2 nút
- Preview toàn bộ danh sách cặp → **Áp dụng** 1 lần

### ⚠️ Conflict Detection (Phát hiện xung đột)
- Trước khi đổi tên `entity_id`, hệ thống tự động quét xem entity đích có đang được tham chiếu trong bất kỳ **Automation** hoặc **Script** nào không.
- Hiển thị Modal cảnh báo chi tiết giúp bạn tránh việc làm hỏng tự động hóa, với tùy chọn "Vẫn tiếp tục" nếu muốn ép buộc đổi.

### 🕐 History & Rollback (Lịch sử & Hoàn tác)
- Mỗi lần Apply thành công, hệ thống tự động lưu lại một **Snapshot** của trạng thái cũ.
- Trong tab Lịch sử, bạn có thể xem lại các lần thay đổi, hoặc click **Rollback** để phục hồi toàn bộ `entity_id` về trạng thái ban đầu một cách an toàn.

## Roadmap

| Tool | Status |
|---|---|
| Entity Migrator (Export + Import) | ✅ v0.0.3 |
| Backup Manager (schedule, version) | 🔜 Coming soon |
| Entity Inspector | 🔜 Coming soon |
| Automation Audit | 🔜 Coming soon |

## Cài đặt

### Thủ công (trước khi publish HACS)
1. Copy `custom_components/mai_tools/` → `/config/custom_components/`
2. Restart Home Assistant
3. Settings → Integrations → Add Integration → **M.A.I Tools**

### Qua HACS
1. HACS → Integrations → ➕ → tìm **M.A.I Tools**
2. Tải về → Restart → Add Integration

## Format file backup v2.0

```json
{
  "mai_backup_version": "2.0",
  "exported_at": "2026-06-10T10:00:00+00:00",
  "device_count": 3,
  "devices": [
    {
      "device_id": "...",
      "name": "Công tắc phòng khách",
      "model": "TS0044",
      "manufacturer": "TuYa",
      "area_name": "Phòng khách",
      "entities": [
        {
          "entity_id": "switch.cong_tac_pk_1",
          "name": "Đèn chính",
          "platform": "tuya",
          ...
        }
      ]
    }
  ]
}
```
