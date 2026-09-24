# FlowKit Studio trên Windows

Bản sao mã nguồn đang dùng tại máy phát triển, gồm Studio, extension 0.3.3 và
luồng tạo video qua giao diện Flow. Nguồn gốc: https://github.com/crisng95/flowkit.

## Khởi động

1. Cài Node.js LTS, Python 3.12 và FFmpeg; bảo đảm `python`, `ffmpeg`, `ffprobe` có trong PATH.
2. Chạy `python -m pip install -r requirements.txt` trong thư mục repo.
3. Sao chép `.env.example` thành `.env`, điền `FLOW_PROJECT_ID` lấy từ URL dự án Flow.
4. Trong `chrome://extensions`, bật Developer mode, chọn Load unpacked và chọn thư mục `extension`.
5. Đăng nhập Google Flow trong Chrome, mở đúng trang dự án và để trống ô nhập prompt.
6. Chạy `Chay_Tool_Tao_Video.bat`: lần đầu script cài dependency và build dashboard. Mở http://127.0.0.1:8100/ để xem tổng quan; mục Studio thời trang ở http://127.0.0.1:8100/studio.
7. Khi cập nhật frontend, chạy `npm ci` và `npm run build` trong `dashboard`, sau đó khởi động lại backend và tải lại trang.

Studio chia video thành nhiều clip, gửi lần lượt qua giao diện Flow, lấy URL
kết quả qua RPC, rồi cắt và ghép bằng FFmpeg. Khi cập nhật extension, tải lại
extension và tab Flow. Sau khi sửa Python, khởi động lại backend.

## Trạng thái bản này

- Đã kiểm tra luồng tạo ba clip và ghép thành video dọc khoảng 15 giây.
- Đã sửa lỗi bỏ mất mô tả ở cảnh sau: tất cả cảnh dùng chung mô tả mẫu, trang phục, bối cảnh và cho phép sửa hành động riêng trước khi tạo.
- Có ba chế độ mẫu trưởng thành, mẫu nhí và chỉ sản phẩm. Mô tả mẫu được đưa vào prompt mỗi cảnh; đây không phải bảo đảm AI giữ giống khuôn mặt tuyệt đối.
- Ảnh mẫu và bối cảnh được chuyển cùng ảnh trang phục qua luồng UI. Chọn nhiều ảnh đã có kiểm tra dữ liệu gửi; vẫn cần xác nhận với giao diện Flow thực tế của tài khoản.
- Giữ các màn gốc: tổng quan, dự án/nhân vật/video/pipeline, thư viện, nhật ký, hướng dẫn, cài đặt, và bảy ngôn ngữ. Studio mới dùng tiếng Việt. Các khả năng upstream chưa hỗ trợ vẫn báo lỗi rõ ràng; đổi giao diện không bổ sung các API đó.
- Bản nháp Studio lưu trong trình duyệt; trạng thái job lưu trong backend trong phiên chạy. Sau khi khởi động lại, xem các cảnh đã tạo ở mục Dự án trước khi chạy lại.
- Lỗi từ bộ lọc nội dung của Flow được báo lại; bản này không bảo đảm mọi yêu
  cầu tạo video đều được Flow chấp nhận.
- `.env`, database, log, ánh xạ ảnh cục bộ, ảnh tải lên và video đầu ra không
  được đưa vào repo. Cài trên máy mới cần cấu hình và tải ảnh lại.

Tài liệu phía dưới trong README được kế thừa từ upstream; trạng thái Studio
cụ thể của bản này được mô tả tại đây.
