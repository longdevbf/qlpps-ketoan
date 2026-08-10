---
name: review-me
description: Review các thay đổi chưa commit bằng subagent code-reviewer, trả về danh sách lỗi kèm bài học rút ra. Dùng khi người dùng gõ /review-me, thường trước khi commit.
argument-hint: (không cần tham số — mặc định review thay đổi chưa commit)
---

# /review-me — review thay đổi của tôi

## Cách thực hiện

**Bước 1 — xác định phạm vi.** Chạy:
```bash
git status --short
git diff --stat
git diff --staged --stat
```

- Có thay đổi chưa commit → review đúng phần đó (cả staged lẫn unstaged).
- Không có gì → hỏi người dùng muốn review gì: commit gần nhất, hay một file cụ thể. **Không tự
  ý đi review cả repo** — vô ích và tốn thời gian.
- `$ARGUMENTS` có đường dẫn file → chỉ review file đó.

**Bước 2 — gọi subagent `code-reviewer`.** Agent tool với `subagent_type: "code-reviewer"`,
chạy đồng bộ (`run_in_background: false`).

Prompt gửi cho reviewer phải nêu:
- Phạm vi cụ thể (danh sách file đã đổi từ `git diff --stat`).
- Người viết code là **lập trình viên đang học** — mỗi lỗi bắt buộc giải thích **tại sao** sai và
  **cách nghĩ để lần sau tự tránh**, theo đúng khuôn trong `.claude/agents/code-reviewer.md`.
- Nhắc chạy checklist đầy đủ: bug, bảo mật, quy ước dự án.

**Bước 3 — trình bày nguyên văn** báo cáo của reviewer. Giữ nguyên phân mức NẶNG/VỪA/NHẸ và
phần "Cách nghĩ để lần sau tự tránh" — đó là phần có giá trị học nhất, đừng cắt.

**Bước 4 — hỏi, đừng tự sửa.** Kết thúc bằng câu hỏi: muốn tự sửa lỗi nào, muốn Claude sửa lỗi
nào? **Không tự động sửa** — người dùng đang học, tự sửa mới nhớ được.

## Lưu ý

- Reviewer có thể chạy `py_compile` để kiểm chứng:
  `source /c/PapasanIT/App_qlpps/ketoan-devrun/env.sh && "$PY" -m py_compile <file>`
- Không tìm thấy lỗi thì nói thẳng, kèm phạm vi đã review. Đừng bịa lỗi nhẹ cho có.
- **Không commit sau khi review**, kể cả khi mọi thứ sạch — commit là việc của người dùng
  (`/commit`).
