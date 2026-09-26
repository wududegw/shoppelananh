# Cập nhật 0.3.5 — giữ cấu hình model trên Flow

## Cài bản sửa vào tool hiện có

1. Tắt cửa sổ backend và sao lưu thư mục tool.
2. Giải nén gói shoppelananh-fixed-0.3.5.zip. Chép đè thư mục extension và agent
   vào thư mục tool đang chạy. Giữ nguyên .env, database và output của bạn.
3. Trong chrome://extensions, reload Flow Kit và kiểm tra phiên bản 0.3.5.
   Tắt các bản extension cũ ở những profile khác.
4. Tải lại tab project Flow. Chọn model muốn dùng, ví dụ Veo 3.1 - Lite với
   720p, 8 giây. Để ô prompt trống, không gắn sẵn ảnh vào ô tạo.
5. Chạy lại Chay_Tool_Tao_Video.bat, tải lại Studio, gửi lại ảnh rồi tạo video.

## Thay đổi

- Không còn bắt buộc các nút 720p và 6 giây. Tool giữ cấu hình model, độ phân giải
  và thời lượng trên Flow; không tự chọn model khác. Flow vẫn có thể tự điều chỉnh
  cấu hình khi đổi sang chế độ Thành phần.
- Tool tiếp tục chọn Video, Thành phần, tỷ lệ của Studio và x1. Model cần hỗ trợ
  các lựa chọn này. Studio lấy 5 giây đầu mỗi clip để ghép, vì vậy hãy chọn thời lượng
  clip ít nhất 5 giây (ví dụ 6 hoặc 8 giây).
- Tải ảnh dùng RPC, không còn yêu cầu ô tạo video sẵn sàng. Bước tạo video vẫn
  kiểm tra ô nhập và cài đặt, tránh ghi đè nội dung đang soạn.
- Lỗi nhận diện giao diện không còn mặc định kết luận người dùng phải đóng Agent.
  Probe trả thêm số nút cài đặt và trạng thái nhận diện ô nhập để chẩn đoán.

## Kiểm tra

15 kiểm tra JavaScript và 59 kiểm tra Python đã qua, gồm giao diện không có
nút thời lượng/độ phân giải, giữ lựa chọn 6/8 giây, tải ảnh khi composer không sẵn
sàng và không gửi lại yêu cầu tạo video khi kết quả chưa rõ.
Chưa kiểm thử tạo video trực tiếp trên tài khoản/máy trong ảnh. Nếu tiếp tục có
lỗi nhận diện ô tạo, cần kiểm tra DOM thực tế; bản này không phỏng đoán selector mới.
