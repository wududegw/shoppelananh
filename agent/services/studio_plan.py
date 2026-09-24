"""Shared, reviewable scene prompts for the fashion Studio."""


def build_scene_plan(req):
    count = req.duration_seconds // 5
    actions = req.scene_actions if req.scene_actions is not None else [req.motion_prompt] * count
    if len(actions) != count:
        raise ValueError(f"Cần đúng {count} cảnh cho video {req.duration_seconds} giây.")
    if any(not action.strip() for action in actions):
        raise ValueError("Chuyển động của mỗi cảnh không được để trống.")
    subject = {
        "child": "Chủ thể là mẫu nhí. Giữ nguyên độ tuổi trẻ em, hoạt động tự nhiên phù hợp độ tuổi.",
        "adult": "Chủ thể là người mẫu trưởng thành.",
        "product": "Chỉ giới thiệu trang phục như sản phẩm, không thêm người mẫu.",
    }[req.subject_mode]
    references = ["Ảnh tham chiếu 1: trang phục cần giữ nguyên màu, họa tiết và kiểu dáng."]
    if req.model_media_id and req.subject_mode != "product":
        references.append("Ảnh tham chiếu 2: người mẫu cần giữ nhất quán.")
    if req.location_media_id:
        references.append(f"Ảnh tham chiếu {len(references) + 1}: bối cảnh cần giữ nhất quán.")
    context = "\n".join([
        subject,
        f"Mô tả người mẫu: {req.model_prompt}" if req.subject_mode != "product" else "Trưng bày sản phẩm.",
        f"Trang phục: {req.clothing_prompt}",
        f"Bối cảnh: {req.location_prompt}",
        *references,
        "Giữ nguyên trang phục và bối cảnh giữa các cảnh; không thêm người." if req.subject_mode == "product" else "Giữ cùng nhân vật, độ tuổi, trang phục và bối cảnh giữa các cảnh; không tự thay đổi thiết kế trang phục.",
    ])
    return [{
        "index": i, "title": f"Cảnh {i + 1}", "start_seconds": i * 5,
        "end_seconds": (i + 1) * 5, "action": action.strip(),
        "prompt": f"{context}\nCảnh {i + 1}/{count}. 0-5s: {action.strip()}",
    } for i, action in enumerate(actions)]
