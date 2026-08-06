---
name: learn-log
description: Ghi nhật ký học tập vào docs/LEARNING.md từ git diff và hội thoại gần đây — hôm nay làm gì, khái niệm mới nào xuất hiện, câu hỏi nào nên tự tìm hiểu. Dùng khi người dùng gõ /learn-log, thường vào cuối buổi làm việc.
argument-hint: (không cần tham số)
---

# /learn-log — nhật ký học qua dự án

Đây là **nhật ký học tập cá nhân** của người dùng, không phải changelog kỹ thuật. Viết cho họ đọc
lại sau 3 tháng và vẫn hiểu mình đã học được gì.

## Cách thực hiện

**Bước 1 — thu thập dữ liệu thật.** Chạy:
```bash
git status --short
git diff --stat
git diff
git log --oneline -5
```
Nếu không có thay đổi nào chưa commit, xem commit gần nhất trong ngày (`git log --since=midnight`).
Không có gì cả thì nói thẳng "hôm nay chưa có thay đổi nào để ghi" và dừng — **đừng bịa nội dung**.

**Bước 2 — soi lại hội thoại phiên này**, tìm:
- Khái niệm/thuật ngữ đã xuất hiện (dependency injection, idempotency, N+1, migration head,
  fail-soft, `Decimal` vs `float`, partial index...).
- Chỗ người dùng hỏi lại, hiểu nhầm, hoặc bạn phải giải thích thêm → đó chính là chỗ đáng ghi nhất.
- Lỗi đã gặp và cách xử lý.

**Bước 3 — tạo/nối vào `docs/LEARNING.md`.**
- Thư mục `docs/` chưa có thì tạo.
- File chưa có thì tạo với tiêu đề `# Nhật ký học — Kế Toán V2`.
- **Luôn THÊM mục mới lên ĐẦU** (sau tiêu đề), không ghi đè, không xoá mục cũ.
- Ngày lấy từ `git log -1 --format=%ad --date=short` hoặc hỏi người dùng — **không tự bịa ngày**.

## Khuôn một mục

```markdown
## YYYY-MM-DD

### Hôm nay làm gì
- <việc 1 — kèm file đã sửa, viết theo kiểu kể lại, không phải liệt kê diff>
- <việc 2>

### Khái niệm mới gặp
- **<tên khái niệm>** — <giải thích 1-2 câu bằng lời của người học>.
  Gặp ở: `file.py:dòng`.

### Vướng ở đâu
- <lỗi/hiểu nhầm cụ thể> → <nguyên nhân thật> → <cách xử lý>.
  (Bỏ mục này nếu hôm nay không vướng gì.)

### Câu hỏi tự tìm hiểu
- [ ] <câu hỏi cụ thể, tra được — không phải "học thêm SQLAlchemy">
- [ ] <câu hỏi 2>

### Một điều nhớ nhất
<một câu duy nhất>
```

## Quy tắc

- **Tiếng Việt**, giọng kể lại cho chính mình, không phải báo cáo cho sếp.
- Mục "Câu hỏi tự tìm hiểu" dùng `- [ ]` để lần sau tick được. Câu hỏi phải **cụ thể**:
  ✅ "Vì sao `flush()` lấy được id mà chưa commit?"
  ❌ "Tìm hiểu thêm về transaction."
- Tối đa **5 gạch đầu dòng mỗi mục con** — dài quá thì không ai đọc lại.
- Chỉ ghi những gì **thật sự xảy ra trong phiên này**. Không suy diễn, không thêm khái niệm chưa
  từng xuất hiện chỉ để mục cho đầy đặn.
- Ghi xong báo lại: đã thêm mục ngày nào, và nhắc còn bao nhiêu câu hỏi chưa tick trong cả file.
