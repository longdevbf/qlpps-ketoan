<!-- SINH TỰ ĐỘNG — ĐỪNG sửa file này.
     Sửa `claude-kit/core/rules/dung-agent.md` (chung 7 app) hoặc `claude-kit/overlay/ketoan/rules/dung-agent.md` (riêng app này),
     rồi chạy: cd d:\PapaSanIT\claude-kit && python sync.py -->
# Dùng AI Agent cho việc nặng — mặc định bung song song

Người dùng đã nói rõ (10/09/2026): **token không phải ràng buộc**. Ràng buộc thật là thời gian của
người dùng và độ chính xác. Việc nặng thì **bung agent song song**, không làm tuần tự, và **không hỏi
xin phép vì tốn token**. Bản đầy đủ: `QLPPS-UI-DOC/01-ban-thao/13-quy-tac-dung-ai-agent.md`.

## Ngưỡng — khi nào bung

| Điều kiện | Làm gì |
|---|---|
| ≤ 2 file, ≤ 200 dòng phải đọc | Tự làm. Bung agent ở đây chỉ chậm hơn |
| 3–8 file trong repo này | 1 agent phụ đọc/kiểm kê, tự mình sửa |
| > 8 file **hoặc** > 1.500 dòng phải đọc | **Bắt buộc** bung, chia theo file hoặc theo khoảng dòng |
| Chạm repo anh em ngoài repo này | **Bắt buộc** bung, mỗi repo một agent, agent chỉ đọc |

## Chia việc thường gặp

| Việc | Cách bung |
|---|---|
| Dựng / dựng lại 1 màn hình | `layout-architect` → tự code → `ui-reviewer` (nối tiếp, không song song) |
| Đổi hex → token 1 template > 300 dòng | 1–2 agent, chia theo khoảng dòng không chồng lấn |
| Review trước khi báo xong | `ui-reviewer` ‖ `code-reviewer` chạy song song |
| Sửa `shared/` | `shared-impact` TRƯỚC, người dùng duyệt rồi mới sửa |
| Phân tích ảnh thiết kế | 3 góc độc lập: bố cục · token/màu/chữ · dữ liệu cần API nào |

## Luật an toàn — không có hook nào cưỡng chế, phải tự giữ

1. **Một agent ghi — một file.** Lập danh sách file cho từng agent, tự kiểm không file nào xuất hiện hai lần.
2. **Agent không sửa `.claude/**` hay `static/css/theme.css`** — đó là bản sinh từ `claude-kit`, sửa là mất.
3. **Prompt agent con phải tự đủ:** đường dẫn tuyệt đối, luật cấm (React/Vue/Tailwind/Alpine/htmx/Stimulus,
   jQuery mới, CDN mới), phạm vi file được ghi, định dạng trả về.
4. **Kết quả agent là CHƯA KIỂM** (`trung-thuc.md`). Số, đường dẫn, "đã sửa xong" — kiểm lại bằng lệnh
   trước khi báo người dùng.
5. **Công cụ Workflow** (điều phối hàng chục agent) chỉ dùng khi người dùng bật: gõ `ultracode` hoặc nói
   "dùng workflow". Agent đơn lẻ thì rule này đã cho phép, không cần hỏi.
