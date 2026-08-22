---
name: commit
description: Tạo commit theo đúng quy ước của repo này. CHỈ chạy khi người dùng tự gõ /commit.
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob
---
<!-- SINH TỰ ĐỘNG — ĐỪNG sửa file này.
     Sửa `claude-kit/core/skills/commit/SKILL.md` (chung 7 app) hoặc `claude-kit/overlay/ketoan/skills/commit/SKILL.md` (riêng app này),
     rồi chạy: cd d:\PapaSanIT\claude-kit && python sync.py -->

# /commit — tạo commit chuẩn

> `disable-model-invocation: true` — skill này **chỉ chạy khi người dùng tự gõ
> `/commit`**. Không bao giờ tự gọi sau khi sửa code xong.

## Quy ước commit của repo — rút từ `git log` thật

```
876b3af  chore: go .venv khoi git
0093d30  theme: doi bang mau giao dien sang tong cam Papasan
c822ba2  chore: them .gitignore, go .env va __pycache__ khoi git
5b7fec5  fix frontend, form
78a2c1e  initial commit
```

Quy ước rút ra — **giữ nguyên, đừng "nâng cấp" sang chuẩn khác**:

- Dạng `<type>: <mô tả>`, tất cả **chữ thường**.
- Mô tả bằng **tiếng Việt KHÔNG DẤU** (`go .venv khoi git`, không phải
  `gỡ .venv khỏi git`). Đây là quy ước có thật của repo.
- Động từ trước, nói **kết quả** chứ không kể thao tác.
- Một dòng, dưới ~72 ký tự. Cần giải thích thêm thì để ở phần thân, cách 1 dòng trống.
- **Không** thêm scope kiểu `feat(api):` — repo chưa dùng.

Các `type` đã dùng và nên dùng tiếp: `feat` · `fix` · `chore` · `theme` ·
`refactor` · `docs`. Không phát minh type mới.

## Quy trình

### 1. Xem đã có gì

```bash
git status --short
git diff --stat
git diff
git log --oneline -5
git branch --show-current
```

Không có thay đổi → nói "không có gì để commit" và dừng.

### 2. Kiểm tra an toàn — bắt buộc, trước khi `git add`

| Kiểm | Xử lý khi dính |
|---|---|
| `.env`, `token.txt`, `gen_test_token.py`, file `*secret*` có trong diff? | **DỪNG**, báo người dùng, không commit |
| Có secret/API key/mật khẩu nằm trong nội dung code sửa? | **DỪNG**, báo chính xác `file:dòng` |
| Đang ở nhánh `main`? | Cảnh báo và hỏi có muốn tạo nhánh mới không |
| File `.pyc`, `__pycache__/`, `.venv/` lọt vào? | Bỏ ra, nhắc kiểm `.gitignore` |

### 3. Đề xuất — CHƯA commit

Nhiều thay đổi rời rạc thì **đề xuất tách thành nhiều commit** và nói rõ vì sao
(mỗi commit một chủ đề thì sau này `git log` mới đọc được, và revert được từng
phần). Đưa ra:

```
Sẽ commit <n> file:
  <danh sách file>

Message đề xuất:
  <type>: <mo ta khong dau>

Lý do chọn type này: <một câu>
```

Rồi **hỏi người dùng duyệt**. Được duyệt mới sang bước 4.

### 4. Commit

```bash
git add <đúng những file đã liệt kê>     # KHÔNG dùng git add -A hay git add .
git commit -m "<message>"
```

Chỉ `add` những file đã liệt kê ở bước 3 — `git add .` là cách nhanh nhất để
lỡ tay commit file rác.

### 5. Không tự push

Xong thì in `git log --oneline -1` và dừng. **Không `git push`** trừ khi người
dùng nói rõ. Nếu người dùng muốn push, nhắc: nhánh hiện tại là
`feat/theme-papasan`, không phải `main`.

## Điều tuyệt đối không làm

- Không `git add -A` / `git add .`.
- Không `--amend` commit đã push.
- Không `--no-verify`.
- Không `git push --force` (đã bị chặn ở `.claude/settings.json`).
- Không viết message tiếng Anh hay có dấu — lệch khỏi lịch sử hiện có.

> Vấn đề tồn đọng, **không tự xử lý**: `.env` đã bị commit ở `78a2c1e` và đã
> push lên `origin` — mọi secret trong đó nằm vĩnh viễn trong lịch sử git. Gỡ
> khỏi index không xoá được khỏi lịch sử. Việc này cần xoay vòng secret + viết
> lại lịch sử; hãy nêu với người dùng, đừng tự làm.
