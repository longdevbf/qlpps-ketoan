---
name: learn-log
description: Ghi nhật ký học qua dự án vào docs/LEARNING.md — hôm nay làm gì, khái niệm mới nào xuất hiện, câu hỏi nên tự tìm hiểu. Dùng khi người dùng gõ /learn-log, thường vào cuối một buổi làm việc hoặc sau khi xong một task đáng kể.
allowed-tools: Bash, Read, Write, Edit, Grep, Glob
---
<!-- SINH TỰ ĐỘNG — ĐỪNG sửa file này.
     Sửa `claude-kit/core/skills/learn-log/SKILL.md` (chung 7 app) hoặc `claude-kit/overlay/ketoan/skills/learn-log/SKILL.md` (riêng app này),
     rồi chạy: cd d:\PapaSanIT\claude-kit && python sync.py -->

# /learn-log — nhật ký học qua dự án

Đây **không phải** changelog và **không phải** báo cáo công việc. Người đọc duy
nhất là chính người dùng, 3 tháng sau, khi quên gần hết. Viết cho người đó.

## Bước 1 — thu thập nguyên liệu

```bash
git status --short
git diff --stat
git diff
git log --oneline -5
```

Cộng thêm **hội thoại trong phiên này**: người dùng đã hỏi gì, vướng ở đâu, đã
chọn phương án nào, đã hiểu sai điều gì rồi được đính chính. Phần này quan
trọng hơn `git diff` — diff nói *cái gì đổi*, hội thoại nói *người dùng đã học gì*.

Không có thay đổi **và** không có gì đáng kể trong hội thoại → nói thẳng
"hôm nay chưa có gì để ghi" và dừng. Đừng viết mục rỗng cho có.

## Bước 2 — ghi vào `docs/LEARNING.md`

Chưa có file thì tạo (`docs/` chưa có thì tạo luôn), mở đầu bằng:

```markdown
# Nhật ký học — qlpps-ketoan

Ghi bằng `/learn-log`. Mục mới nhất ở TRÊN CÙNG.
```

**Luôn chèn mục mới lên đầu**, ngay dưới dòng giới thiệu — không append xuống
cuối. Ngày lấy từ hệ thống, định dạng `dd/mm/yyyy`.

```markdown
---

## 01/08/2026

### Đã làm
- <việc 1 — một dòng, nói kết quả chứ không kể thao tác>
- <việc 2>

### Khái niệm mới gặp
- **<tên khái niệm>** — <1-2 câu giải thích> · gặp ở `<file:dòng>`

### Bẫy đã dính (hoặc suýt dính)
- <triệu chứng thấy được> → <nguyên nhân thật> → <cách nhận biết lần sau>

### Câu hỏi nên tự tìm hiểu
- [ ] <câu hỏi cụ thể, trả lời được trong 15 phút>

### Đọng lại
<Một câu. Nếu chỉ nhớ được một điều từ hôm nay thì nhớ điều này.>
```

## Quy tắc viết

- **Chỉ ghi khái niệm THỰC SỰ xuất hiện hôm nay.** Không liệt kê thứ hay ho mà
  người dùng chưa chạm vào — nhật ký phồng lên là nhật ký không ai đọc lại.
- **Luôn kèm `file:dòng`.** Nhật ký không dẫn được về code thật thì vô dụng.
- **Câu hỏi phải cụ thể và trả lời được.** "Học thêm về SQLAlchemy" là câu hỏi
  hỏng; "vì sao `selectinload` tránh được N+1 mà `joinedload` thì không?" là được.
- Mục "Bẫy" là mục giá trị nhất. Đủ ba phần: *triệu chứng nhìn thấy* →
  *nguyên nhân thật* → *dấu hiệu nhận biết lần sau*. Chỉ có nguyên nhân mà
  không có triệu chứng thì lần sau không nhận ra được.
- Tiếng Việt, ngắn. Mỗi mục 1-2 dòng.
- **Không sửa các mục ngày cũ.** Hôm nay phát hiện hôm qua hiểu sai thì ghi vào
  mục hôm nay: "hôm qua tôi tưởng X, thật ra là Y". Đó chính là dấu vết tiến bộ.

## Bước 3 — báo lại

In ra phần vừa ghi và một dòng:

```
Đã ghi vào docs/LEARNING.md — <n> khái niệm mới, <n> câu hỏi mở.
Câu hỏi cũ chưa đánh dấu xong: <n>  (xem các dòng [ ] trong file)
```

**Không tự commit** `docs/LEARNING.md`. Muốn commit thì người dùng gọi `/commit`.
