---
name: review-me
description: Review các thay đổi CHƯA COMMIT theo checklist bug/bảo mật/quy ước của repo, mỗi lỗi kèm bài học để lần sau tự tránh. Dùng khi người dùng gõ /review-me, nói "review giúp tôi", "tôi sửa xong rồi kiểm tra hộ", hoặc trước khi commit.
allowed-tools: Task, Bash, Read, Grep, Glob
---
<!-- SINH TỰ ĐỘNG — ĐỪNG sửa file này.
     Sửa `claude-kit/core/skills/review-me/SKILL.md` (chung 7 app) hoặc `claude-kit/overlay/ketoan/skills/review-me/SKILL.md` (riêng app này),
     rồi chạy: cd d:\PapaSanIT\claude-kit && python sync.py -->

# /review-me — soi thay đổi chưa commit

Giao việc cho subagent **`code-reviewer`** (`.claude/agents/code-reviewer.md`).
Checklist và mẫu báo cáo nằm trong định nghĩa subagent — **đừng chép lại**.

## Bước 1 — gom phạm vi trước khi gọi subagent

```bash
git status --short
git diff --stat
```

- **Không có thay đổi nào** → nói thẳng "không có gì để review" và dừng.
  Đừng tự đi review code cũ.
- **Có tham số kèm lệnh** (tên file/thư mục) → thu hẹp đúng phạm vi đó.
- **Diff quá lớn** (trên ~800 dòng) → báo người dùng, đề xuất chia theo file
  và hỏi review phần nào trước. Review một cục quá to sẽ ra báo cáo hời hợt.

## Bước 2 — giao cho `code-reviewer`

Đưa kèm: danh sách file thay đổi, và nhắc rõ đây là repo mà **pytest không chạy
được** nên không được kết luận "chạy test là biết" — mọi khẳng định phải dựa
trên đọc code hoặc gọi API thật.

## Bước 3 — trình bày lại cho người đang học

Giữ nguyên nội dung kỹ thuật, nhưng **sắp xếp lại theo hành động**:

```
🔴 PHẢI SỬA TRƯỚC KHI COMMIT   <các mục NẶNG>
🟡 NÊN SỬA                      <các mục VỪA>
⚪ TUỲ BẠN                      <các mục NHẸ>

🎓 BÀI HỌC HÔM NAY
<gộp các dòng "Lần sau" của mọi phát hiện thành 1-3 nguyên tắc ngắn,
 diễn đạt thành quy tắc tự kiểm — vd "khi đổi tên key trong dict trả về,
 luôn grep templates/ trước".>
```

Sau đó hỏi đúng một câu: **"Bạn muốn tự sửa hay tôi sửa?"**

- "Tôi tự sửa" / "để tôi tự làm" → **không Edit, không Write, không dán code
  hoàn chỉnh**. Chỉ nêu vị trí và hướng. Sửa xong nhờ kiểm thì chạy lại
  `/review-me`.
- "Bạn sửa" → sửa **các mục NẶNG trước**, mỗi lần sửa nói rõ đang sửa mục nào,
  không gộp lẫn với việc dọn dẹp ngoài phạm vi.

## Không làm

- Không tự `git add`, không tự `git commit` sau khi review. Commit là việc của
  `/commit` và luôn phải do người dùng khởi động.
- Không báo "sạch hoàn toàn" nếu chưa thật sự kiểm hết — nói rõ đã kiểm những
  gì và bỏ qua những gì.
