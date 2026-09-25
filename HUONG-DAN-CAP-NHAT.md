# Sửa nhận diện project Flow — extension 0.3.4

Lỗi `UI_VIDEO: Mở đúng project Flow trong Chrome rồi thử lại` được trả về từ
extension/background.js khi không tìm thấy tab phù hợp. Điều này chứng tỏ request
đã tới extension. Dòng xanh trước đây chỉ phản ánh kết nối WebSocket, chưa xác nhận
tab Flow đã sẵn sàng. Chưa xác nhận nguyên nhân thực tế trên máy trong ảnh.

## Thay đổi

- Backend thử extension ở profile khác chỉ khi nhận mã lỗi xác nhận chưa tương tác
  với trang (`UI_PROJECT_TAB_UNAVAILABLE`). Không tự gửi lại khi timeout hoặc mất kết nối.
- Extension so khớp toàn bộ đường dẫn project, hỗ trợ dấu / cuối và chữ hoa UUID.
- Phân biệt tab không có trong profile và tab đang ngủ. Tab ở màn chỉnh sửa clip
  cần quay về trang project trước khi chạy.
- Ghi log UI:probe, UI:refresh, UI:generate kể cả khi không tìm thấy tab.
- Nhãn Studio đổi thành “Extension đã kết nối” để phản ánh đúng trạng thái.

## Cập nhật trên máy đã có tool

1. Dừng backend đang chạy. Sao lưu thư mục tool hiện tại.
2. Giải nén bản sửa, chép đè các thư mục `extension`, `agent`, `dashboard/src`, `dashboard/dist`
   từ bản sửa vào thư mục tool đang dùng. Giữ `.env`, dữ liệu và ảnh/video hiện có.
3. Trong chrome://extensions, tải lại Flow Kit. Nếu cài lần đầu, chọn Load unpacked
   và trỏ tới thư mục extension. Kiểm tra phiên bản hiển thị là 0.3.4.
4. Trong đúng profile Chrome đó, mở liên kết project đã lưu trong Studio.
   Tải lại tab Flow, quay về trang project, đóng khung Agent để hiện ô tạo và để prompt trống.
5. Gói sửa đã kèm dashboard/dist build sẵn. Nếu tự sửa giao diện về sau, chạy
   `npm ci` rồi `npm run build` trong thư mục dashboard.
6. Chạy lại Chay_Tool_Tao_Video.bat. Tải lại Studio và bấm “Gửi lại sang Flow”.

Nếu lỗi còn xuất hiện, mở bảng log của Flow Kit để xem dòng UI:probe và lỗi chi tiết.
Đảm bảo chỉ chạy một backend; tránh dùng extension cũ cùng lúc với bản mới.

## Kiểm chứng

Đã build dashboard thành công, chạy 9 kiểm tra JavaScript và 57 kiểm tra Python về chọn tab, nhiều profile,
khởi động MV3, giao diện và batch transport. Test selector cũ được bổ sung mock
querySelectorAll còn thiếu. Chưa kiểm thử tạo video trực tiếp trên tài khoản Flow
của người dùng; các kiểm tra này không xác nhận giao diện Flow thực tế đang hoạt động.
