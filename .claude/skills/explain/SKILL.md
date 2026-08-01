---
name: explain
description: Giải thích một file, hàm, hoặc khái niệm ở mức người mới học FastAPI/SQLAlchemy, lấy ví dụ từ chính codebase Kế Toán V2. Dùng khi người dùng gõ /explain hoặc hỏi "giải thích X", "X là gì", "tại sao code này viết vậy".
argument-hint: <đường-dẫn-file | tên-hàm | khái-niệm>
---

# /explain — nhờ mentor giải thích

Người dùng muốn **hiểu**, không muốn bạn sửa gì.

## Cách thực hiện

**Bước 1 — xác định đối tượng.** `$ARGUMENTS` có thể là:
- Đường dẫn file (`app/services/so_quy_auto.py`) → giải thích file đó.
- Tên hàm/class (`sync_so_quy`, `SoQuy`) → `Grep` tìm định nghĩa trước.
- Khái niệm (`dependency injection`, `idempotency`, `N+1`, `migration`) → tìm chỗ repo dùng nó
  thật rồi giải thích qua ví dụ đó.
- **Rỗng** → hỏi lại đúng một câu: muốn giải thích file nào hay khái niệm nào.

**Bước 2 — gọi subagent `mentor`.** Dùng Agent tool với `subagent_type: "mentor"`, chạy đồng bộ
(`run_in_background: false`) vì người dùng đang chờ đọc câu trả lời.

Prompt gửi cho mentor phải nêu rõ:
- Đối tượng cần giải thích (kèm đường dẫn file đã xác định ở bước 1).
- Người đọc là **lập trình viên mới bắt đầu thật sự** với FastAPI/SQLAlchemy.
- Yêu cầu dùng ví dụ code **từ chính repo này**, kèm `file:dòng`.
- Yêu cầu trả lời theo đúng khuôn trong `.claude/agents/mentor.md`.

**Bước 3 — trình bày lại nguyên văn** phần giải thích của mentor cho người dùng. Đừng tóm tắt
ngắn lại — họ cần bản đầy đủ để học. Bạn chỉ thêm 1-2 câu nối nếu cần.

## Lưu ý

- Mentor **chỉ đọc**. Nếu trong lúc giải thích phát hiện bug, chỉ **nêu ra**, không tự sửa —
  hỏi người dùng có muốn sửa không.
- File `templates/index.html` nặng **564 KB**: tuyệt đối không đọc cả file, phải `Grep` theo tên
  hàm/id rồi chỉ đọc quanh đó.
- Không kết thúc bằng "bạn có muốn tôi implement không?" — mục đích của lệnh này là học, không
  phải chuyển sang code.
