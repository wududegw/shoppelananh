# Dashboard trắng–xanh lá — 25/09/2026

- Phục hồi dashboard React gốc tại cổng 8100, giữ tổng quan, dự án, nhân vật,
  video, pipeline, thư viện, nhật ký, hướng dẫn, cài đặt và bộ ngôn ngữ gốc.
- Tích hợp Studio thời trang thành trang React, có ảnh trang phục/người mẫu/
  bối cảnh, lưu bản nháp, chọn chủ thể, thời lượng và tỷ lệ, duyệt kịch bản,
  sửa hành động từng cảnh, tiến độ, nhật ký, tải video và video gần đây.
- Mọi cảnh đều nhận mô tả mẫu, trang phục và bối cảnh. Loại bỏ các prompt
  catwalk cố định xung đột. Chế độ chỉ sản phẩm không đính kèm ảnh người mẫu.
- Chuyển tối đa ba ảnh tham chiếu có thứ tự qua transport UI. Không tự gửi
  lại lệnh tạo khi kết quả không rõ ràng. Bảo vệ nội dung đang soạn trên Flow.
- Không cho đổi Flow Project ID trong lúc một job Studio đang chạy.
- Video Studio hoàn thành không cần upscale để được đánh dấu hoàn thành.
- File Windows build dashboard lần đầu và mở dashboard chính; dữ liệu cũ
  dùng chung backend, không cần chuyển database.

## Kiểm tra

- `npm run lint`, `npm run build`: đạt.
- 38 bài Python: UI transport, scene plan, dashboard routes, SDK operations.
- 4 bài Node về trạng thái video, 5 bài Node về extension/selector/reentry.
- Kiểm tra trình duyệt: dashboard với dữ liệu hiện có, dự án và pipeline,
  cài đặt, Studio chọn mẫu nhí và sửa cảnh 2; bố cục desktop 1440px và mobile
  390px. Không tràn ngang ở Studio mobile.
- Bản đang cài tại `C:\toollam\flowkit`. Tệp cũ đã sao lưu trong
  `backup-dashboard-20260925` trước khi ghi đè.

## Giới hạn kiểm chứng

Lần cập nhật này không gửi thêm yêu cầu render tính phí. Luồng một ảnh đã tạo
và ghép video 15 giây trước đó; việc chọn nhiều ảnh trong giao diện Flow mới
chưa được kiểm chứng bằng một video render thực tế. Kết quả nhận dạng nhân
vật và chấp nhận nội dung vẫn phụ thuộc Flow. Các chức năng upstream đòi hỏi
dịch vụ/CLI riêng (ví dụ AI review) vẫn cần cài và cấu hình nhà cung cấp đó.
