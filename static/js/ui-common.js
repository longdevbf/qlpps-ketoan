/* ui-common.js — helper dùng chung cho MỌI trang.
 *
 * Nạp 1 lần trong `templates/_header.html` (partial này được 25/28 template
 * include) nên mọi trang đều có sẵn, không cần khai báo lại.
 *
 * Trước đây mỗi template tự viết lại các hàm này: `esc` 9 bản (4 biến thể),
 * `escHtml` 3 bản, `initials` 3 bản. Gom về đây để sửa 1 chỗ ăn cả hệ thống.
 *
 * Thêm helper mới vào đây khi nó được dùng từ 2 trang trở lên. Hàm chỉ 1
 * trang dùng thì để nguyên trong trang đó.
 */
(function (w) {
  'use strict';

  var ESC_MAP = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  };

  /**
   * Escape chuỗi trước khi nhét vào HTML.
   *
   * Escape đủ cả 5 ký tự — QUAN TRỌNG: nhiều chỗ dùng trong ngữ cảnh
   * thuộc tính (`title="${esc(x)}"`, `value="${esc(x)}"`). Vài bản cũ chỉ
   * escape `& < >`, giá trị chứa dấu nháy sẽ thoát ra khỏi thuộc tính.
   *
   * null/undefined → chuỗi rỗng.
   */
  function esc(s) {
    return (s === null || s === undefined ? '' : String(s))
      .replace(/[&<>"']/g, function (c) { return ESC_MAP[c]; });
  }

  /**
   * Viết tắt tên người: "Nguyễn Văn An" → "NA". Dùng cho avatar chữ.
   * Lấy chữ cái đầu của mỗi từ, tối đa 2 ký tự.
   */
  function initials(name) {
    return (name || '?')
      .trim()
      .split(/\s+/)
      .map(function (word) { return word[0]; })
      .join('')
      .toUpperCase()
      .slice(0, 2);
  }

  w.esc = esc;
  w.escHtml = esc;   // alias — vài trang gọi tên này
  w.initials = initials;
})(window);
