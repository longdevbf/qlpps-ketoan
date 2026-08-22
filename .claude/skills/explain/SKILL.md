---
name: explain
description: Giải thích một file, một hàm, một endpoint hay một khái niệm ở mức người MỚI học, dùng ví dụ lấy từ chính codebase này. Dùng khi người dùng gõ /explain kèm tên file hoặc chủ đề, hoặc khi hỏi "cái này là gì", "file này làm gì", "vì sao lại viết thế này".
allowed-tools: Task, Read, Grep, Glob
---
<!-- SINH TỰ ĐỘNG — ĐỪNG sửa file này.
     Sửa `claude-kit/core/skills/explain/SKILL.md` (chung 7 app) hoặc `claude-kit/overlay/ketoan/skills/explain/SKILL.md` (riêng app này),
     rồi chạy: cd d:\PapaSanIT\claude-kit && python sync.py -->

# /explain — nhờ mentor giải thích

Giao việc cho subagent **`mentor`** (`.claude/agents/mentor.md`). Toàn bộ cách
giải thích nằm trong định nghĩa subagent đó — **đừng chép lại vào đây**, bản
chép sẽ lệch dần khỏi bản gốc.

## Cách xử lý tham số

Người dùng đưa kèm lệnh một trong các dạng sau:

| Dạng | Ví dụ | Giao cho mentor |
|---|---|---|
| Đường dẫn file | `app/routers/leads.py` | Giải thích file đó: nhiệm vụ, các endpoint chính, luồng dữ liệu |
| File:dòng | `app/routers/pages.py:82` | Giải thích đúng đoạn quanh dòng đó, kèm bối cảnh |
| Tên hàm/biến | `_render`, `PAGE_PERMS` | Grep tìm định nghĩa trước, rồi giải thích cả nơi dùng |
| Endpoint | `/api/ads-plan` | Truy về router → schema → template gọi nó |
| Trang | `/cong-no`, `bao_cao` | Truy route → template → API mà template gọi |
| Khái niệm | `Depends`, `JSONB`, `session` | Giải thích khái niệm **bằng ví dụ có thật trong repo** |

**Không có tham số** → hỏi lại người dùng muốn hiểu gì. Đừng tự chọn một file
ngẫu nhiên để giảng.

## Sau khi mentor trả kết quả

Chuyển nguyên văn cho người dùng. Chỉ thêm khi thật sự cần:

- Nếu mentor đánh dấu chỗ nào **chưa kiểm chứng**, và bạn kiểm được bằng cách
  chạy lệnh đọc (mentor không có quyền chạy lệnh) → chạy rồi bổ sung.
- Nếu người dùng có vẻ muốn **sửa** chứ không chỉ muốn hiểu → hỏi lại:
  "Bạn muốn tôi sửa luôn, hay bạn tự làm và tôi chỉ góp ý?"

Nếu người dùng trả lời **"để tôi tự làm"**: từ đó cho tới hết task, không Edit,
không Write, không dán code hoàn chỉnh. Chỉ chỉ vị trí và hướng đi
(xem `CLAUDE.md`, mục "CHẾ ĐỘ MENTOR" quy tắc 4).
