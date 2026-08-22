<!-- SINH TỰ ĐỘNG — ĐỪNG sửa file này.
     Sửa `claude-kit/core/rules/coding-style.md` (chung 7 app) hoặc `claude-kit/overlay/ketoan/rules/coding-style.md` (riêng app này),
     rồi chạy: cd d:\PapaSanIT\claude-kit && python sync.py -->
# Quy tắc viết code — toàn dự án

Chỉ ghi những điều **khác mặc định** của repo này. Quy tắc theo tầng nằm ở
`routers.md`, `templates.md`, `models-migrations.md` — không lặp lại ở đây.

## Ngôn ngữ

Tiếng Việt là ngôn ngữ chính của **định danh, tên cột DB, slug route, comment,
text UI**. `ho_ten`, `tien_trinh`, `khuyen_mai`, `/dang-ky-truc`.

- Viết **không dấu, snake_case** cho định danh Python và cột DB: `ngay_bat_dau`,
  không phải `ngày_bắt_đầu` hay `startDate`.
- **Có dấu** cho text hiển thị và comment: `"Chưa gọi"`, `# Bỏ qua lead đã chốt`.
- Không "chuẩn hoá" tên tiếng Việt có sẵn sang tiếng Anh. Một lần đổi tên là
  một lần vỡ template hoặc vỡ query raw SQL đang tham chiếu nó.
- Tên tiếng Anh chỉ dùng khi đó là thuật ngữ kỹ thuật thật: `router`, `schema`,
  `response_model`, `session`.

## Comment

Comment giải thích **tại sao**, không mô tả lại code đang làm gì.

```python
# ĐÚNG — nói lý do, đọc xong biết vì sao không được sửa
# Dùng CAST vì :frm::date không bind được trong text() của SQLAlchemy.
sql = text("... WHERE ngay >= CAST(:frm AS date)")

# SAI — chép lại code bằng tiếng Việt, không thêm thông tin gì
# Tạo câu SQL rồi gán vào biến sql
```

Với người đang học: khi viết một đoạn dùng pattern lạ (dependency injection,
JSONB, `selectinload`), thêm **một** dòng comment nói pattern đó là gì. Một
dòng thôi — comment dài quá sẽ không ai cập nhật khi code đổi.

## Định dạng

Không có formatter (`black`/`ruff` đều không được cấu hình), nên định dạng là
**giữ giống code xung quanh**, không áp chuẩn cá nhân:

- 4 space, không tab.
- Dòng ~100 ký tự — repo hiện tại không nhất quán, đừng đi xuống dòng lại
  những dòng bạn không sửa (làm diff phình ra, che mất thay đổi thật).
- Import: thư viện chuẩn → thư viện ngoài → `shared.*` → `ketoan.app.*`.
- **Đừng chạy formatter lên cả file.** Diff sẽ toàn nhiễu và người đọc không
  tìm được thay đổi thật.

## Kiểu dữ liệu và Pydantic

- Endpoint mới **phải** có `response_model`. Repo mới có 220/449 route làm
  được điều này — đừng làm tỉ lệ đó tệ hơn.
- Giá trị enum (`trang_thai`, `loai`…) khai ở **hai chỗ phải khớp nhau**:
  `CheckConstraint` trong model và `Literal[...]` trong `app/schemas/`. Sửa một
  chỗ mà quên chỗ kia thì lỗi chỉ lộ ra lúc chạy, dạng 422 hoặc lỗi ràng buộc DB.
- Tập giá trị **không nhất quán giữa các module** (chỗ tiếng Anh, chỗ tiếng
  Việt). **Luôn đọc model trước khi ghi giá trị**, không suy đoán theo module khác.

## Xử lý lỗi

**Không viết `except SQLAlchemyError: return []`.** Đây là lỗi tốn thời gian
nhất trong repo: query hỏng trông y hệt "không có dữ liệu" — không log, không
toast, không dấu vết. Để lỗi nổi lên cho error handler chung xử lý.

Cần bắt lỗi thật thì bắt hẹp và **luôn log**:

```python
except IntegrityError as e:
    logger.warning("Trùng khoá khi tạo lead: %s", e)
    raise HTTPException(409, "Lead đã tồn tại")
```

## Bảo mật

- Không log/print secret, token, mật khẩu — kể cả khi debug.
- Không hard-code chuỗi kết nối, khoá API. Đọc qua `shared/config.py`.
- Không nới lỏng `Depends(require_app("ketoan"))` để "cho dễ test".
- Query raw SQL **luôn dùng bind param**, không nối chuỗi:
  `text("... WHERE id = :id")`, không phải `text(f"... WHERE id = {id}")`.

## Phạm vi thay đổi

Một task = một chủ đề. Sửa thêm thứ không được yêu cầu (đổi tên biến, sắp lại
import, xoá code chết chỗ khác) làm diff khó review — với người đang học thì
diff khó review nghĩa là **bỏ qua không đọc**, và đó là mất cơ hội học.

Thấy vấn đề ngoài phạm vi thì báo một dòng ở cuối câu trả lời, không tự sửa.
