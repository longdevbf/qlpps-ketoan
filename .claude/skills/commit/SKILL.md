---
name: commit
description: Tạo commit với message chuẩn theo quy ước dự án. CHỈ chạy khi người dùng gõ /commit.
argument-hint: (không cần tham số)
disable-model-invocation: true
---

# /commit — tạo commit

⚠️ Skill này có `disable-model-invocation: true`: **chỉ chạy khi người dùng tự gõ `/commit`.**
Claude không bao giờ được tự gọi. Ngoài lệnh này ra, `CLAUDE.md` cấm tự commit.

## Cách thực hiện

**Bước 1 — xem xét trước khi làm gì.** Chạy song song:
```bash
git status --short
git diff
git diff --staged
git log --oneline -10
```

**Bước 2 — kiểm tra an toàn (bắt buộc, không được bỏ):**
- **`.env` có nằm trong danh sách sắp commit không?** File này đang bị git theo dõi và chứa
  secret production thật. Nếu nó xuất hiện trong diff → **DỪNG LẠI**, báo người dùng, không commit.
- Có file `__pycache__/`, `.venv/`, `.pytest_cache/` lọt vào không? Có thì nhắc kiểm tra
  `.gitignore` trước.
- Có secret/token/mật khẩu hardcode trong diff không?
- Đang ở nhánh nào? Nếu là `main` → hỏi người dùng có muốn tạo nhánh mới trước không.

**Bước 3 — viết message.** Repo mới có 1 commit (`initial commit`) nên **chưa hình thành quy ước
lịch sử**. Dùng Conventional Commits, phần mô tả viết **tiếng Việt không dấu** cho khớp với quy
ước đặt tên của dự án:

```
<type>(<scope>): <mo ta ngan, khong dau, khong qua 72 ky tu>

<than bai: giai thich TAI SAO thay doi, khong lap lai CAI GI diff da noi ro>
```

- `type`: `feat` | `fix` | `refactor` | `docs` | `test` | `chore` | `perf`
- `scope`: tên module nghiệp vụ — `so_quy`, `cong_no`, `doanh_thu`, `chi_phi`, `bao_cao`,
  `tscd`, `models`, `alembic`, `shared`, `claude`
- Ví dụ: `fix(so_quy): them alembic revision cho cot ref_sepay`

**Bước 4 — trình message cho người dùng duyệt TRƯỚC KHI commit.** Chờ họ đồng ý mới chạy
`git add` + `git commit`. Đây là người đang học — họ cần thấy message trước để học cách viết.

**Bước 5 — commit**, rồi chạy `git status` xác nhận kết quả.

## Cấm

- **Không `git push`.** Kể cả sau khi commit thành công. Push là lệnh riêng người dùng phải tự gõ.
- Không `--amend` commit đã push.
- Không `--no-verify`.
- Không tự thêm file vào staging ngoài những gì người dùng muốn commit — không rõ thì hỏi.
- Không commit khi `.env` có trong diff.
