"""Studio Phan Doan Hoang — 1-Click Video Creation Web App & API.
White & Blue Elegant Theme & Visual Prompt Studio.
Specialized for:
- Clothing Photo (Required) + Model Photo/Prompt + Location Photo/Prompt -> Multi-scene Long Fashion Video (15s/30s/60s).
"""
import asyncio
import base64
import os
import json
import time
import uuid
import logging
import urllib.request
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel, Field

import agent.config as config
from agent.db import crud
from agent.services.flow_client import get_flow_client
from agent.services.post_process import merge_videos, trim_video
from agent.worker.processor import get_worker_controller

logger = logging.getLogger(__name__)

router = APIRouter(tags=["studio"])

_STUDIO_JOBS: Dict[str, Dict[str, Any]] = {}
OUTPUT_DIR = config.BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class ConfigUpdateRequest(BaseModel):
    flow_project_id: str


class UploadBase64ImageRequest(BaseModel):
    image_base64: str
    file_name: str = "uploaded_asset.png"


class AdvancedFashionVideoRequest(BaseModel):
    title: str = Field(default="Video Thời Trang Catwalk")
    # 1. Clothing
    clothing_media_id: str
    clothing_prompt: str = Field(
        default="Bộ trang phục thời trang cao cấp từ ảnh, giữ nguyên chất liệu vải, màu sắc, hoa văn và đường may."
    )
    # 2. Model (Custom image or prompt)
    model_media_id: Optional[str] = None
    model_prompt: str = Field(
        default="Người mẫu nữ châu Á, khuôn mặt thanh tú sắc sảo, vóc dáng chuẩn catwalk, thần thái high-fashion cuốn hút."
    )
    # 3. Location (Custom image or prompt)
    location_media_id: Optional[str] = None
    location_prompt: str = Field(
        default="Sàn diễn thời trang Brutalist tối giản, kiến trúc bê tông cao cấp, ánh sáng studio mềm mại, đèn rọi sàn catwalk."
    )
    # 4. Motion & Camera Prompt
    motion_prompt: str = Field(
        default="Người mẫu tự tin sải bước catwalk, váy áo chuyển động mềm mại theo từng nhịp bước, camera lia góc 180 độ cận cảnh chất vải, sau đó dừng lại tạo dáng sang chảnh."
    )
    # 5. Settings
    duration_seconds: int = Field(default=15)  # 15, 30, 60
    orientation: str = Field(default="VERTICAL")  # VERTICAL (9:16) or HORIZONTAL (16:9)


@router.get("/", response_class=HTMLResponse)
async def root_redirect():
    return RedirectResponse(url="/studio")


@router.get("/api/studio/status")
async def get_studio_status():
    client = get_flow_client()
    controller = get_worker_controller()
    return {
        "status": "ok",
        "extension_connected": client.connected,
        "flow_project_id": config.FLOW_PROJECT_ID,
        "video_transport": os.environ.get("FLOW_VIDEO_TRANSPORT", "batch"),
        "active_tasks": controller.active_count if controller else 0,
        "output_dir": str(OUTPUT_DIR),
    }


@router.post("/api/studio/config")
async def update_studio_config(body: ConfigUpdateRequest):
    new_pid = body.flow_project_id.strip()
    config.FLOW_PROJECT_ID = new_pid
    os.environ["FLOW_PROJECT_ID"] = new_pid

    env_file = config.BASE_DIR / ".env"
    try:
        lines = []
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if not line.strip().startswith("FLOW_PROJECT_ID="):
                    lines.append(line)
        lines.append(f"FLOW_PROJECT_ID={new_pid}")
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception as e:
        logger.warning("Could not persist .env: %s", e)

    return {"ok": True, "flow_project_id": config.FLOW_PROJECT_ID}


@router.post("/api/studio/upload-image")
async def studio_upload_image(body: UploadBase64ImageRequest):
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension chưa kết nối! Vui lòng mở Chrome đăng nhập flow.google.com")
    
    b64_str = body.image_base64
    mime = "image/png"
    if "," in b64_str:
        header, b64_str = b64_str.split(",", 1)
        if "jpeg" in header or "jpg" in header:
            mime = "image/jpeg"
        elif "webp" in header:
            mime = "image/webp"

    uploads_dir = OUTPUT_DIR / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    local_file = uploads_dir / f"up_{int(time.time())}_{body.file_name}"
    try:
        local_file.write_bytes(base64.b64decode(b64_str))
    except Exception as e:
        logger.warning("Could not save local copy: %s", e)

    result = await client.upload_image(
        b64_str,
        mime_type=mime,
        project_id=config.FLOW_PROJECT_ID,
        file_name=body.file_name,
    )
    if result.get("error") or (isinstance(result.get("status"), int) and result["status"] >= 400):
        raise HTTPException(result.get("status", 502), result.get("error", result.get("data")))
    
    media_id = result.get("_mediaId")
    if not media_id:
        data_raw = result.get("data", {})
        if isinstance(data_raw, dict):
            media_id = data_raw.get("media", {}).get("name")
    
    return {
        "media_id": media_id,
        "local_path": str(local_file),
        "file_name": body.file_name,
    }


@router.get("/api/studio/jobs/{job_id}")
async def get_job_status(job_id: str):
    job = _STUDIO_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/api/studio/outputs")
async def list_outputs():
    videos = []
    if OUTPUT_DIR.exists():
        for p in sorted(OUTPUT_DIR.glob("**/*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True):
            if "_workflow_videos" in str(p) or "frames" in str(p):
                continue
            rel = p.relative_to(OUTPUT_DIR).as_posix()
            stat = p.stat()
            videos.append({
                "filename": p.name,
                "relative_path": rel,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                "stream_url": f"/api/studio/stream/{rel}",
            })
    return {"videos": videos}


@router.get("/api/studio/stream/{filepath:path}")
async def stream_video(filepath: str):
    safe_path = (OUTPUT_DIR / filepath).resolve()
    if not str(safe_path).startswith(str(OUTPUT_DIR.resolve())) or not safe_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found")
    return FileResponse(safe_path, media_type="video/mp4", filename=safe_path.name)


async def _run_advanced_fashion_pipeline(job_id: str, req: AdvancedFashionVideoRequest):
    """Executes the visual prompt studio pipeline:
    - Garment Photo (Required)
    - Custom Model Photo or Prompt
    - Custom Location Photo or Prompt
    - Multi-angle Motion Prompts
    - FFmpeg Concat to 15s/30s/60s
    """
    job = _STUDIO_JOBS[job_id]

    def log(msg: str, progress: int = None):
        if progress is not None:
            job["progress"] = progress
        job["message"] = msg
        job["logs"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")
        logger.info("[Job %s - AdvFashion] %s", job_id[:8], msg)

    try:
        client = get_flow_client()
        if not client.connected:
            raise RuntimeError("Chrome Extension chưa kết nối! Vui lòng mở Chrome vào flow.google.com")

        if not config.FLOW_PROJECT_ID:
            raise RuntimeError("Chưa cấu hình FLOW_PROJECT_ID! Vui lòng bấm 'Cấu hình Flow ID' góc trên bên phải")

        num_scenes = max(1, req.duration_seconds // 5)
        log(f"🚀 Bắt đầu khởi tạo dự án: {req.title} (Thời lượng: {req.duration_seconds}s - {num_scenes} phân cảnh)", 5)

        # 1. Register entities in project
        # If user did not upload a separate model photo, use the uploaded outfit photo directly
        model_mid = req.model_media_id if req.model_media_id else req.clothing_media_id
        characters_payload = [
            {
                "name": "TrangPhucGoc",
                "entity_type": "visual_asset",
                "description": req.clothing_prompt,
                "media_id": req.clothing_media_id,
            },
            {
                "name": "NguoiMau",
                "entity_type": "character",
                "description": f"{req.model_prompt}. Full body portrait wearing {req.clothing_prompt}.",
                "media_id": model_mid,
            },
        ]
        if req.location_media_id:
            characters_payload.append({
                "name": "BoiCanh",
                "entity_type": "location",
                "description": req.location_prompt,
                "media_id": req.location_media_id,
            })

        project = await crud.create_project(
            name=req.title,
            story=f"Fashion Runway: {req.title}. Model: {req.model_prompt}. Outfit: {req.clothing_prompt}. Setting: {req.location_prompt}",
            material="realistic",
        )
        pid = project["id"]
        job["project_id"] = pid
        log(f"Đã tạo Project ID: {pid[:8]}", 10)

        for c in characters_payload:
            mid = c.get("media_id") or None
            char = await crud.create_character(
                name=c["name"],
                entity_type=c["entity_type"],
                description=c["description"],
                image_prompt=c.get("image_prompt", c["description"]),
                media_id=mid,
            )
            await crud.link_character_to_project(pid, char["id"])

        log("✅ Toàn bộ thực thể tham chiếu đã sẵn sàng!", 30)

        # 3. Create Video container & Scenes
        video = await crud.create_video(
            project_id=pid,
            title=f"{req.title} ({req.duration_seconds}s)",
            orientation=req.orientation,
        )
        vid = video["id"]
        job["video_id"] = vid

        active_char_names = ["TrangPhucGoc", "NguoiMau"]
        if req.location_media_id:
            active_char_names.append("BoiCanh")

        # Camera & Director angles
        scene_directives = [
            {
                "title": "Toàn Cảnh Catwalk",
                "prompt": f"NguoiMau wearing TrangPhucGoc walking catwalk in {req.location_prompt}. Full body wide shot, confident elegant stride.",
                "video_prompt": f"0-5s: Smooth wide tracking backward shot. NguoiMau strides forward with catwalk presence wearing TrangPhucGoc in {req.location_prompt}. Fabric flows naturally. Cinematic slow motion 60fps. {req.motion_prompt}",
            },
            {
                "title": "Quay Cận Cảnh 180° Orbit",
                "prompt": f"NguoiMau medium shot wearing TrangPhucGoc at {req.location_prompt}. Detailed fabric texture, high fashion posing.",
                "video_prompt": f"0-5s: Medium close-up, smooth 180-degree orbit arc camera shot around NguoiMau. Focus on the luxury fabric, textures, cuts and fine details of TrangPhucGoc. Shallow depth of field, creamy bokeh.",
            },
            {
                "title": "Góc Thấp Tạo Dáng Kết Màn",
                "prompt": f"NguoiMau stops, turns toward camera wearing TrangPhucGoc at {req.location_prompt}. Dramatic rim light.",
                "video_prompt": f"0-5s: Low angle shot looking up. NguoiMau stops gracefully, strikes high fashion pose showcasing both back and front of TrangPhucGoc. Fierce confident gaze at camera. Locked-off static, dramatic rim light.",
            },
            {
                "title": "Góc Nghiêng Chuyển Động (Side Profile)",
                "prompt": f"Side profile shot of NguoiMau walking slowly in {req.location_prompt} wearing TrangPhucGoc.",
                "video_prompt": f"0-5s: Smooth side-tracking camera movement. NguoiMau moves gracefully in profile view, showcasing the elegant drape and silhouette of TrangPhucGoc.",
            },
            {
                "title": "Chi Tiết Đường May & Chất Liệu",
                "prompt": f"Extreme close-up on the intricate details, seams, and fabric tailoring of TrangPhucGoc on NguoiMau in {req.location_prompt}.",
                "video_prompt": f"0-5s: Slow macro pan across the tailoring details and material of TrangPhucGoc. Luxury editorial commercial feel.",
            },
            {
                "title": "Grand Finale Runway",
                "prompt": f"NguoiMau grand finale runway pose, smiling confidently in TrangPhucGoc at {req.location_prompt}.",
                "video_prompt": f"0-5s: Wide runway walk, flashlights blinking, NguoiMau performs final turn and strike pose facing the audience.",
            }
        ]

        created_scenes = []
        prefix = "vertical" if req.orientation == "VERTICAL" else "horizontal"
        for i in range(num_scenes):
            d = scene_directives[i % len(scene_directives)]
            sc = await crud.create_scene(
                video_id=vid,
                display_order=i,
                prompt=d["prompt"],
                video_prompt=d["video_prompt"],
                character_names=active_char_names,
                chain_type="ROOT",
                parent_scene_id=None,
            )
            # All scenes directly use the uploaded clothing/model image as their starting frame!
            # This ensures 100% fidelity to the user's uploaded outfit, avoids model drift,
            # and prevents UNUSUAL_ACTIVITY from redundant image generation calls.
            await crud.update_scene(
                sc["id"],
                **{f"{prefix}_image_media_id": req.clothing_media_id, f"{prefix}_image_status": "COMPLETED"}
            )
            created_scenes.append(sc)

        log("✅ Đã thiết lập xong góc máy cho toàn bộ các cảnh từ ảnh trang phục gốc!", 50)

        # 5. Generate video clips
        log(f"🎬 Đang render video chuyển động cho {num_scenes} phân cảnh...", 55)
        video_reqs = []
        for sc in created_scenes:
            r = await crud.create_request(
                req_type="GENERATE_VIDEO",
                scene_id=sc["id"],
                project_id=pid,
                video_id=vid,
                orientation=req.orientation,
            )
            video_reqs.append(r["id"])

        start_wait = time.time()
        while True:
            completed_count = 0
            for rid in video_reqs:
                req_obj = await crud.get_request(rid)
                if not req_obj:
                    continue
                if req_obj.get("status") == "FAILED":
                    raise RuntimeError(f"Lỗi khi render video: {req_obj.get('error_message')}")
                if req_obj.get("status") == "COMPLETED":
                    completed_count += 1

            progress_val = 55 + int((completed_count / len(video_reqs)) * 35)
            job["progress"] = progress_val
            job["message"] = f"Đã kết xuất {completed_count}/{len(video_reqs)} clip ({completed_count * 5}s / {req.duration_seconds}s)..."

            if completed_count == len(video_reqs):
                break
            if time.time() - start_wait > 1800:
                raise TimeoutError("Quá thời gian kết xuất video")
            await asyncio.sleep(5)

        log(f"✅ Đã có đủ {num_scenes} clip! Đang dùng FFmpeg nối thành video dài {req.duration_seconds}s...", 92)

        # 6. Post-process & Concat
        project_slug = pid[:8]
        proj_dir = OUTPUT_DIR / project_slug
        proj_dir.mkdir(parents=True, exist_ok=True)

        downloaded_clips = []
        scenes_in_order = await crud.list_scenes(vid)

        for i, sc in enumerate(scenes_in_order):
            prefix = "vertical" if req.orientation == "VERTICAL" else "horizontal"
            vurl = sc.get(f"{prefix}_video_url")
            clip_path = proj_dir / f"scene_{i:02d}.mp4"

            if vurl:
                if vurl.startswith("file://"):
                    local_f = Path(vurl.replace("file:///", "").replace("file://", ""))
                    if local_f.exists():
                        clip_path.write_bytes(local_f.read_bytes())
                elif Path(vurl).exists():
                    clip_path.write_bytes(Path(vurl).read_bytes())
                elif vurl.startswith("http"):
                    req_http = urllib.request.Request(vurl, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req_http, timeout=60) as resp, open(clip_path, "wb") as out_f:
                        out_f.write(resp.read())

            if not clip_path.exists() or clip_path.stat().st_size == 0:
                raise RuntimeError(f"Không thể tải file video cảnh {i+1}")

            trimmed_path = proj_dir / f"trimmed_{i:02d}.mp4"
            if trim_video(str(clip_path), str(trimmed_path), start=0.0, end=5.0):
                downloaded_clips.append(str(trimmed_path))
            else:
                downloaded_clips.append(str(clip_path))

        final_output_file = proj_dir / f"{project_slug}_thoi_trang_{req.duration_seconds}s.mp4"
        if not merge_videos(downloaded_clips, str(final_output_file)):
            raise RuntimeError("Lỗi FFmpeg khi ghép nối video")

        rel_path = final_output_file.relative_to(OUTPUT_DIR).as_posix()
        final_url = f"/api/studio/stream/{rel_path}"

        job["final_video_url"] = final_url
        job["status"] = "COMPLETED"
        job["progress"] = 100
        log(f"🎉 HOÀN THÀNH XUẤT SẮC! Video dài {req.duration_seconds}s đã sẵn sàng tại: {final_url}", 100)

    except Exception as e:
        logger.exception("Advanced fashion pipeline failed: %s", e)
        job["status"] = "FAILED"
        job["message"] = f"Lỗi: {str(e)}"
        job["logs"].append(f"[{time.strftime('%H:%M:%S')}] ❌ LỖI: {str(e)}")


@router.post("/api/studio/generate-advanced")
async def start_advanced_pipeline(body: AdvancedFashionVideoRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    _STUDIO_JOBS[job_id] = {
        "id": job_id,
        "title": body.title,
        "status": "PROCESSING",
        "progress": 0,
        "message": "Đang chuẩn bị nhận các thành phần prompt...",
        "logs": [],
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "final_video_url": None,
        "project_id": None,
        "video_id": None,
    }
    background_tasks.add_task(_run_advanced_fashion_pipeline, job_id, body)
    return {"job_id": job_id, "status": "PROCESSING"}


# ─── FRONTEND HTML (White & Blue Modern Aesthetic) ─────────────

_STUDIO_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FlowKit Studio — Phan Doan Hoang Edition</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    body { background-color: #f8fafc; color: #0f172a; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
    .bg-gradient-blue { background: linear-gradient(135deg, #1d4ed8 0%, #2563eb 50%, #0ea5e9 100%); }
    .card-white { background: #ffffff; border: 1px solid #e2e8f0; box-shadow: 0 4px 20px -2px rgba(14, 165, 233, 0.06); }
    .card-hover:hover { border-color: #3b82f6; box-shadow: 0 10px 25px -4px rgba(37, 99, 235, 0.12); }
    .btn-blue { background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); box-shadow: 0 4px 15px rgba(37, 99, 235, 0.3); }
    .btn-blue:hover { background: linear-gradient(135deg, #1d4ed8 0%, #1e40af 100%); box-shadow: 0 6px 20px rgba(37, 99, 235, 0.45); }
    .prompt-box { background: #f1f5f9; border-left: 4px solid #2563eb; }
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
  </style>
</head>
<body class="min-h-screen flex flex-col">

  <!-- Header: Clean White with Blue Accents -->
  <header class="bg-white sticky top-0 z-50 px-8 py-3.5 flex items-center justify-between border-b border-slate-200/80 shadow-sm">
    <div class="flex items-center space-x-3.5">
      <div class="w-10 h-10 rounded-xl bg-gradient-blue flex items-center justify-center text-white font-bold text-xl shadow-md shadow-blue-500/20">
        <i class="fa-solid fa-wand-magic-sparkles"></i>
      </div>
      <div>
        <div class="flex items-center space-x-2">
          <h1 class="text-xl font-extrabold text-slate-900 tracking-tight">FlowKit Studio</h1>
          <span class="text-[11px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">Prompt Studio</span>
        </div>
        <p class="text-xs text-slate-500 font-medium">Phan Doan Hoang Edition &bull; Biến Ảnh Quần Áo & Prompt Thành Video Dài (15s–60s)</p>
      </div>
    </div>

    <!-- Status badges -->
    <div class="flex items-center space-x-3">
      <div id="ext-status" class="flex items-center space-x-2 text-xs font-semibold px-3 py-1.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
        <span class="w-2.5 h-2.5 rounded-full bg-amber-400 animate-pulse"></span>
        <span>Đang kiểm tra kết nối...</span>
      </div>
      <button onclick="openConfigModal()" class="text-xs font-bold bg-white hover:bg-slate-50 text-slate-700 px-3.5 py-1.5 rounded-xl border border-slate-300 shadow-sm flex items-center space-x-1.5 transition">
        <i class="fa-solid fa-key text-blue-600"></i>
        <span>Cấu hình Flow ID</span>
      </button>
    </div>
  </header>

  <!-- Main Container -->
  <main class="flex-1 max-w-7xl w-full mx-auto p-8 grid grid-cols-1 lg:grid-cols-12 gap-8">
    
    <!-- Left Column: Visual Prompt Builder (7 cols) -->
    <div class="lg:col-span-7 space-y-6">
      
      <form onsubmit="startAdvancedGeneration(event)" class="space-y-6">

        <!-- TITLE BAR -->
        <div class="card-white p-5 rounded-2xl flex items-center justify-between">
          <div class="flex-1 mr-4">
            <label class="block text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1">Tên Dự Án Video</label>
            <input type="text" id="inp-title" value="BST Thời Trang Mùa Thu" class="w-full text-base font-bold text-slate-800 bg-transparent border-b border-dashed border-slate-300 focus:border-blue-600 focus:outline-none pb-1">
          </div>
          <div class="flex items-center space-x-3">
            <div>
              <label class="block text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1">Tỷ Lệ</label>
              <select id="inp-orient" class="bg-slate-50 border border-slate-200 text-xs font-semibold rounded-lg px-2.5 py-1.5 text-slate-700 focus:outline-none focus:border-blue-500">
                <option value="VERTICAL" selected>Dọc 9:16 (TikTok, Reels, Shorts)</option>
                <option value="HORIZONTAL">Ngang 16:9 (YouTube Standard)</option>
              </select>
            </div>
            <div>
              <label class="block text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1">Thời Lượng</label>
              <select id="inp-duration" class="bg-blue-50 border border-blue-200 text-xs font-bold rounded-lg px-2.5 py-1.5 text-blue-800 focus:outline-none focus:border-blue-500">
                <option value="15" selected>15 Giây (3 scenes)</option>
                <option value="30">30 Giây (6 scenes)</option>
                <option value="60">60 Giây (12 scenes)</option>
              </select>
            </div>
          </div>
        </div>

        <!-- MODULE 1: CLOTHING ASSET (Bắt Buộc) -->
        <div class="card-white card-hover p-6 rounded-2xl transition duration-200">
          <div class="flex items-center justify-between mb-4">
            <div class="flex items-center space-x-2.5">
              <span class="w-7 h-7 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center font-bold text-xs">1</span>
              <h2 class="text-sm font-bold text-slate-800 uppercase tracking-wide">Trang Phục / Bộ Quần Áo (Ảnh Gốc)</h2>
            </div>
            <span class="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-rose-50 text-rose-600 border border-rose-200">Bắt buộc</span>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-12 gap-4 items-center">
            <!-- Upload Box -->
            <div class="md:col-span-4">
              <div id="clothing-dropzone" onclick="document.getElementById('clothing-file').click()" class="border-2 border-dashed border-blue-200 hover:border-blue-500 bg-blue-50/40 rounded-xl p-3 text-center cursor-pointer transition flex flex-col items-center justify-center aspect-square">
                <input type="file" id="clothing-file" accept="image/*" class="hidden" onchange="handleClothingUpload(event)">
                <div id="clothing-prompt-view" class="space-y-1">
                  <i class="fa-solid fa-cloud-arrow-up text-2xl text-blue-500 mb-1"></i>
                  <p class="text-xs font-bold text-slate-700">Tải ảnh đồ lên</p>
                  <p class="text-[10px] text-slate-400">Ảnh chụp áo/váy</p>
                </div>
                <div id="clothing-preview-view" class="hidden flex flex-col items-center">
                  <img id="clothing-img" class="max-h-24 rounded-lg object-contain border border-blue-300 shadow-sm mb-1">
                  <span class="text-[10px] font-bold text-emerald-600">✓ Đã nạp</span>
                </div>
              </div>
              <input type="hidden" id="clothing-media-id">
            </div>

            <!-- Prompt Box -->
            <div class="md:col-span-8 space-y-2">
              <label class="block text-xs font-bold text-slate-600">Mô Tả Chi Tiết Bộ Quần Áo</label>
              <textarea id="clothing-prompt" rows="3" class="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 text-xs text-slate-800 focus:bg-white focus:outline-none focus:border-blue-500 transition">Bộ trang phục thời trang cao cấp từ ảnh, giữ nguyên chất liệu vải sang trọng, màu sắc, hoa văn và đường may tinh xảo.</textarea>
              <p class="text-[11px] text-slate-400">💡 Mẹo: Nhấn mạnh chất liệu vải (lụa, da, len dạ...) để video tạo chuyển động vải đẹp nhất.</p>
            </div>
          </div>
        </div>

        <!-- MODULE 2: MODEL (Tuỳ chỉnh hoặc tải ảnh mẫu lên) -->
        <div class="card-white card-hover p-6 rounded-2xl transition duration-200">
          <div class="flex items-center justify-between mb-4">
            <div class="flex items-center space-x-2.5">
              <span class="w-7 h-7 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center font-bold text-xs">2</span>
              <h2 class="text-sm font-bold text-slate-800 uppercase tracking-wide">Người Mẫu Trình Diễn (Model)</h2>
            </div>
            <span class="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-blue-50 text-blue-600 border border-blue-200">Tuỳ chỉnh</span>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-12 gap-4 items-center">
            <!-- Custom Model Photo (Optional) -->
            <div class="md:col-span-4">
              <div id="model-dropzone" onclick="document.getElementById('model-file').click()" class="border-2 border-dashed border-slate-200 hover:border-blue-400 bg-slate-50 rounded-xl p-3 text-center cursor-pointer transition flex flex-col items-center justify-center aspect-square">
                <input type="file" id="model-file" accept="image/*" class="hidden" onchange="handleModelUpload(event)">
                <div id="model-prompt-view" class="space-y-1">
                  <i class="fa-solid fa-user-plus text-2xl text-slate-400 mb-1"></i>
                  <p class="text-xs font-semibold text-slate-600">Thêm ảnh mẫu riêng</p>
                  <p class="text-[10px] text-slate-400">(Tùy chọn)</p>
                </div>
                <div id="model-preview-view" class="hidden flex flex-col items-center">
                  <img id="model-img" class="max-h-24 rounded-lg object-contain border border-blue-300 shadow-sm mb-1">
                  <span class="text-[10px] font-bold text-emerald-600">✓ Đã nạp mẫu riêng</span>
                </div>
              </div>
              <input type="hidden" id="model-media-id">
            </div>

            <!-- Prompt Box & Presets -->
            <div class="md:col-span-8 space-y-2">
              <div class="flex items-center justify-between">
                <label class="block text-xs font-bold text-slate-600">Mô Tả Người Mẫu</label>
                <!-- Quick Tags -->
                <div class="flex space-x-1">
                  <button type="button" onclick="setModelPreset('asian')" class="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-100 hover:bg-blue-100 text-slate-600 hover:text-blue-700 transition">Nữ Châu Á</button>
                  <button type="button" onclick="setModelPreset('western')" class="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-100 hover:bg-blue-100 text-slate-600 hover:text-blue-700 transition">Nữ Tây Âu</button>
                  <button type="button" onclick="setModelPreset('male')" class="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-100 hover:bg-blue-100 text-slate-600 hover:text-blue-700 transition">Nam Người Mẫu</button>
                </div>
              </div>
              <textarea id="model-prompt" rows="3" class="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 text-xs text-slate-800 focus:bg-white focus:outline-none focus:border-blue-500 transition">Người mẫu nữ châu Á, khuôn mặt thanh tú sắc sảo, vóc dáng chuẩn catwalk, thần thái high-fashion cuốn hút, tóc đen suôn mượt.</textarea>
            </div>
          </div>
        </div>

        <!-- MODULE 3: LOCATION (Tuỳ chỉnh hoặc tải ảnh bối cảnh lên) -->
        <div class="card-white card-hover p-6 rounded-2xl transition duration-200">
          <div class="flex items-center justify-between mb-4">
            <div class="flex items-center space-x-2.5">
              <span class="w-7 h-7 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center font-bold text-xs">3</span>
              <h2 class="text-sm font-bold text-slate-800 uppercase tracking-wide">Bối Cảnh / Không Gian (Location)</h2>
            </div>
            <span class="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-blue-50 text-blue-600 border border-blue-200">Tuỳ chỉnh</span>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-12 gap-4 items-center">
            <!-- Custom Location Photo (Optional) -->
            <div class="md:col-span-4">
              <div id="loc-dropzone" onclick="document.getElementById('loc-file').click()" class="border-2 border-dashed border-slate-200 hover:border-blue-400 bg-slate-50 rounded-xl p-3 text-center cursor-pointer transition flex flex-col items-center justify-center aspect-square">
                <input type="file" id="loc-file" accept="image/*" class="hidden" onchange="handleLocUpload(event)">
                <div id="loc-prompt-view" class="space-y-1">
                  <i class="fa-solid fa-mountain-sun text-2xl text-slate-400 mb-1"></i>
                  <p class="text-xs font-semibold text-slate-600">Thêm ảnh bối cảnh</p>
                  <p class="text-[10px] text-slate-400">(Tùy chọn)</p>
                </div>
                <div id="loc-preview-view" class="hidden flex flex-col items-center">
                  <img id="loc-img" class="max-h-24 rounded-lg object-contain border border-blue-300 shadow-sm mb-1">
                  <span class="text-[10px] font-bold text-emerald-600">✓ Đã nạp bối cảnh</span>
                </div>
              </div>
              <input type="hidden" id="loc-media-id">
            </div>

            <!-- Prompt Box & Presets -->
            <div class="md:col-span-8 space-y-2">
              <div class="flex items-center justify-between">
                <label class="block text-xs font-bold text-slate-600">Mô Tả Bối Cảnh</label>
                <!-- Quick Tags -->
                <div class="flex space-x-1">
                  <button type="button" onclick="setLocPreset('runway')" class="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-100 hover:bg-blue-100 text-slate-600 hover:text-blue-700 transition">Sàn Runway</button>
                  <button type="button" onclick="setLocPreset('studio')" class="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-100 hover:bg-blue-100 text-slate-600 hover:text-blue-700 transition">Studio Bê Tông</button>
                  <button type="button" onclick="setLocPreset('paris')" class="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-100 hover:bg-blue-100 text-slate-600 hover:text-blue-700 transition">Đường Phố Paris</button>
                </div>
              </div>
              <textarea id="loc-prompt" rows="3" class="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 text-xs text-slate-800 focus:bg-white focus:outline-none focus:border-blue-500 transition">Sàn diễn thời trang Brutalist tối giản, kiến trúc bê tông cao cấp, ánh sáng studio sang trọng, đèn rọi sàn catwalk.</textarea>
            </div>
          </div>
        </div>

        <!-- MODULE 4: MOTION & CAMERA DIRECTIVE -->
        <div class="card-white card-hover p-6 rounded-2xl transition duration-200">
          <div class="flex items-center space-x-2.5 mb-3">
            <span class="w-7 h-7 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center font-bold text-xs">4</span>
            <h2 class="text-sm font-bold text-slate-800 uppercase tracking-wide">Chuyển Động & Góc Máy (Cinematic Directive)</h2>
          </div>
          <textarea id="motion-prompt" rows="2" class="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 text-xs text-slate-800 focus:bg-white focus:outline-none focus:border-blue-500 transition">Người mẫu tự tin sải bước catwalk, váy áo chuyển động mềm mại theo từng nhịp bước, camera lia góc 180 độ cận cảnh chất vải, sau đó dừng lại tạo dáng sang chảnh.</textarea>
        </div>

        <!-- LAUNCH BUTTON -->
        <button type="submit" id="btn-submit" class="w-full py-4 rounded-2xl btn-blue text-white font-extrabold text-base transition flex items-center justify-center space-x-2.5">
          <i class="fa-solid fa-film text-lg"></i>
          <span id="btn-text">BẮT ĐẦU TẠO VIDEO THỜI TRANG TỰ ĐỘNG</span>
        </button>

      </form>

    </div>

    <!-- Right Column: Live Monitor & Video Output (5 cols) -->
    <div class="lg:col-span-5 space-y-6">
      
      <!-- Video Player Card -->
      <div class="card-white p-6 rounded-2xl flex flex-col justify-between min-h-[460px]">
        <div>
          <div class="flex items-center justify-between mb-4">
            <h3 class="font-extrabold text-slate-900 text-base flex items-center space-x-2">
              <i class="fa-solid fa-play-circle text-blue-600 text-lg"></i>
              <span>Video Thành Phẩm</span>
            </h3>
            <span id="job-badge" class="hidden text-xs font-bold px-3 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
              Đang chờ lệnh
            </span>
          </div>

          <!-- Video Player Box -->
          <div id="video-container" class="w-full aspect-[9/16] max-h-[380px] mx-auto bg-slate-900 rounded-2xl border border-slate-200 flex flex-col items-center justify-center overflow-hidden relative shadow-md">
            <div id="placeholder-box" class="text-center p-6 text-slate-400 space-y-2.5">
              <div class="w-14 h-14 rounded-full bg-slate-800 text-slate-500 flex items-center justify-center mx-auto text-2xl">
                <i class="fa-solid fa-clapperboard"></i>
              </div>
              <p class="text-xs font-semibold text-slate-300">Chưa có video nào đang render.<br>Nạp ảnh đồ, chỉnh prompt và bấm nút để bắt đầu!</p>
            </div>
            <video id="player" controls class="hidden w-full h-full object-contain"></video>
          </div>

          <!-- Download Action -->
          <div id="download-box" class="hidden mt-4">
            <a id="download-link" href="#" download class="w-full py-3.5 bg-emerald-600 hover:bg-emerald-700 text-white text-center font-extrabold text-sm rounded-xl flex items-center justify-center space-x-2 transition shadow-lg shadow-emerald-600/20">
              <i class="fa-solid fa-download"></i>
              <span>TẢI VIDEO THÀNH PHẨM (.MP4)</span>
            </a>
          </div>

        </div>

        <!-- Progress Bar & Status -->
        <div id="progress-box" class="hidden mt-6 pt-4 border-t border-slate-200 space-y-2.5">
          <div class="flex justify-between text-xs font-bold">
            <span id="progress-msg" class="text-blue-700">Đang chuẩn bị...</span>
            <span id="progress-percent" class="text-slate-500 font-mono">0%</span>
          </div>
          <div class="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
            <div id="progress-bar" class="bg-gradient-blue h-2.5 rounded-full transition-all duration-300" style="width: 0%"></div>
          </div>
          
          <div class="mt-2">
            <div class="bg-slate-900 rounded-xl p-3 text-[11px] font-mono text-slate-300 max-h-28 overflow-y-auto" id="log-box">
              Chờ khởi động...
            </div>
          </div>
        </div>

      </div>

      <!-- Recent Videos Gallery -->
      <div class="card-white p-6 rounded-2xl">
        <h3 class="font-extrabold text-slate-900 text-sm mb-3 flex items-center justify-between">
          <span><i class="fa-solid fa-clock-rotate-left mr-2 text-blue-600"></i>Video Đã Tạo Gần Đây</span>
          <button onclick="loadOutputs()" class="text-xs text-slate-400 hover:text-blue-600 transition"><i class="fa-solid fa-rotate"></i></button>
        </h3>
        <div id="gallery" class="space-y-2 max-h-48 overflow-y-auto pr-1 text-xs">
          <div class="text-slate-400 text-center py-4">Đang tải danh sách...</div>
        </div>
      </div>

    </div>

  </main>

  <!-- Modal Cấu hình Flow Project ID -->
  <div id="config-modal" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 hidden flex items-center justify-center p-4">
    <div class="bg-white max-w-md w-full p-6 rounded-2xl border border-slate-200 shadow-2xl space-y-4">
      <div class="flex justify-between items-center">
        <h3 class="text-base font-extrabold text-slate-900 flex items-center space-x-2">
          <i class="fa-solid fa-key text-blue-600"></i>
          <span>Cấu hình Google Flow Project ID</span>
        </h3>
        <button onclick="closeConfigModal()" class="text-slate-400 hover:text-slate-700 font-bold">&times;</button>
      </div>
      <p class="text-xs text-slate-500 leading-relaxed">
        Mở <b>flow.google.com</b>, tạo 1 Project mới và copy chuỗi mã UUID trên đường link trình duyệt dán vào đây:
      </p>
      <div>
        <label class="block text-xs font-bold text-slate-700 mb-1">FLOW_PROJECT_ID (UUID)</label>
        <input type="text" id="modal-flow-id" placeholder="vd: 1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d" class="w-full bg-slate-50 border border-slate-300 rounded-xl px-4 py-2.5 text-slate-900 text-sm focus:outline-none focus:border-blue-600 font-mono">
      </div>
      <div class="flex justify-end space-x-2.5 pt-2">
        <button onclick="closeConfigModal()" class="px-4 py-2 rounded-xl text-xs font-bold text-slate-600 hover:bg-slate-100">Đóng</button>
        <button onclick="saveConfig()" class="px-5 py-2 rounded-xl text-xs font-bold btn-blue text-white">Lưu Cấu Hình</button>
      </div>
    </div>
  </div>

  <script>
    let activeJobId = null;
    let pollInterval = null;

    async function checkStatus() {
      try {
        const res = await fetch('/api/studio/status');
        const data = await res.json();
        const badge = document.getElementById('ext-status');
        
        if (data.extension_connected) {
          badge.innerHTML = '<span class="w-2.5 h-2.5 rounded-full bg-emerald-500"></span><span class="text-emerald-700">Extension đã kết nối</span>';
          badge.className = 'flex items-center space-x-2 text-xs font-semibold px-3 py-1.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200';
        } else {
          badge.innerHTML = '<span class="w-2.5 h-2.5 rounded-full bg-rose-500"></span><span class="text-rose-700">Chưa mở Flow Tab / Extension</span>';
          badge.className = 'flex items-center space-x-2 text-xs font-semibold px-3 py-1.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200';
        }

        if (data.flow_project_id) {
          document.getElementById('modal-flow-id').value = data.flow_project_id;
        }
      } catch (e) {
        console.error("Status check failed", e);
      }
    }

    function openConfigModal() {
      document.getElementById('config-modal').classList.remove('hidden');
    }

    function closeConfigModal() {
      document.getElementById('config-modal').classList.add('hidden');
    }

    async function saveConfig() {
      const pid = document.getElementById('modal-flow-id').value.trim();
      if (!pid) return alert('Vui lòng nhập Project UUID!');
      await fetch('/api/studio/config', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({flow_project_id: pid})
      });
      closeConfigModal();
      checkStatus();
      alert('Đã cập nhật FLOW_PROJECT_ID thành công!');
    }

    function setModelPreset(type) {
      if (type === 'asian') {
        document.getElementById('model-prompt').value = "Người mẫu nữ châu Á, khuôn mặt thanh tú sắc sảo, vóc dáng chuẩn catwalk, thần thái high-fashion cuốn hút, tóc đen suôn mượt.";
      } else if (type === 'western') {
        document.getElementById('model-prompt').value = "Người mẫu nữ Tây Âu, vóc dáng cao gầy thanh mảnh catwalk, mái tóc vàng vuốt ngược sang chảnh, ánh mắt sắc sảo lạnh lùng.";
      } else if (type === 'male') {
        document.getElementById('model-prompt').value = "Nam người mẫu thời trang lịch lãm, góc nghiêng nam tính mạnh mẽ, kiểu tóc hiện đại, sải bước tự tin cuốn hút.";
      }
    }

    function setLocPreset(type) {
      if (type === 'runway') {
        document.getElementById('loc-prompt').value = "Sàn diễn thời trang Brutalist tối giản, kiến trúc bê tông cao cấp, ánh sáng studio sang trọng, đèn rọi sàn catwalk.";
      } else if (type === 'studio') {
        document.getElementById('loc-prompt').value = "Studio chụp ảnh hiện đại cao cấp, phông nền bê tông xám sáng tối giản, ánh sáng khuếch tán tự nhiên thanh lịch.";
      } else if (type === 'paris') {
        document.getElementById('loc-prompt').value = "Đại lộ phong cách Haussmann tại Paris mùa thu ngập nắng vàng, hậu cảnh mờ ảo lãng mạn phong cách tạp chí Vogue.";
      }
    }

    // Generic upload handler helper
    function uploadAsset(file, imgElemId, promptViewId, previewViewId, mediaInputId) {
      const reader = new FileReader();
      reader.onload = async function(evt) {
        const base64Data = evt.target.result;
        document.getElementById(imgElemId).src = base64Data;
        document.getElementById(promptViewId).classList.add('hidden');
        document.getElementById(previewViewId).classList.remove('hidden');

        try {
          const res = await fetch('/api/studio/upload-image', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              image_base64: base64Data,
              file_name: file.name
            })
          });
          const data = await res.json();
          if (data.media_id) {
            document.getElementById(mediaInputId).value = data.media_id;
          } else {
            throw new Error("Không lấy được media_id");
          }
        } catch (err) {
          alert("Lỗi khi tải ảnh: " + err.message);
        }
      };
      reader.readAsDataURL(file);
    }

    function handleClothingUpload(e) {
      const f = e.target.files[0];
      if (f) uploadAsset(f, 'clothing-img', 'clothing-prompt-view', 'clothing-preview-view', 'clothing-media-id');
    }

    function handleModelUpload(e) {
      const f = e.target.files[0];
      if (f) uploadAsset(f, 'model-img', 'model-prompt-view', 'model-preview-view', 'model-media-id');
    }

    function handleLocUpload(e) {
      const f = e.target.files[0];
      if (f) uploadAsset(f, 'loc-img', 'loc-prompt-view', 'loc-preview-view', 'loc-media-id');
    }

    async function startAdvancedGeneration(e) {
      e.preventDefault();
      const clothingId = document.getElementById('clothing-media-id').value;
      if (!clothingId) {
        return alert("Vui lòng tải ảnh quần áo lên ở BƯỚC 1 trước!");
      }

      const payload = {
        title: document.getElementById('inp-title').value,
        clothing_media_id: clothingId,
        clothing_prompt: document.getElementById('clothing-prompt').value,
        model_media_id: document.getElementById('model-media-id').value || null,
        model_prompt: document.getElementById('model-prompt').value,
        location_media_id: document.getElementById('loc-media-id').value || null,
        location_prompt: document.getElementById('loc-prompt').value,
        motion_prompt: document.getElementById('motion-prompt').value,
        duration_seconds: parseInt(document.getElementById('inp-duration').value) || 15,
        orientation: document.getElementById('inp-orient').value,
      };

      const btn = document.getElementById('btn-submit');
      btn.disabled = true;
      btn.classList.add('opacity-50');
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>ĐANG TẠO VIDEO...</span>';

      document.getElementById('progress-box').classList.remove('hidden');
      document.getElementById('placeholder-box').classList.remove('hidden');
      document.getElementById('player').classList.add('hidden');
      document.getElementById('download-box').classList.add('hidden');

      try {
        const res = await fetch('/api/studio/generate-advanced', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        activeJobId = data.job_id;
        
        if (pollInterval) clearInterval(pollInterval);
        pollInterval = setInterval(pollJob, 2500);
      } catch (err) {
        alert("Lỗi khi gửi lệnh: " + err.message);
        btn.disabled = false;
        btn.classList.remove('opacity-50');
        btn.innerHTML = '<i class="fa-solid fa-film text-lg"></i><span>BẮT ĐẦU TẠO VIDEO THỜI TRANG TỰ ĐỘNG</span>';
      }
    }

    async function pollJob() {
      if (!activeJobId) return;
      try {
        const res = await fetch(`/api/studio/jobs/${activeJobId}`);
        const job = await res.json();

        document.getElementById('progress-percent').innerText = job.progress + '%';
        document.getElementById('progress-bar').style.width = job.progress + '%';
        document.getElementById('progress-msg').innerText = job.message;

        const logBox = document.getElementById('log-box');
        logBox.innerHTML = job.logs.join('<br>');
        logBox.scrollTop = logBox.scrollHeight;

        if (job.status === 'COMPLETED') {
          clearInterval(pollInterval);
          
          const btn = document.getElementById('btn-submit');
          btn.disabled = false;
          btn.classList.remove('opacity-50');
          btn.innerHTML = '<i class="fa-solid fa-rotate-right text-lg"></i><span>TẠO VIDEO KHÁC</span>';

          if (job.final_video_url) {
            const player = document.getElementById('player');
            player.src = job.final_video_url;
            player.classList.remove('hidden');
            document.getElementById('placeholder-box').classList.add('hidden');
            player.play();

            const dLink = document.getElementById('download-link');
            dLink.href = job.final_video_url;
            document.getElementById('download-box').classList.remove('hidden');
          }
          loadOutputs();
        } else if (job.status === 'FAILED') {
          clearInterval(pollInterval);
          
          const btn = document.getElementById('btn-submit');
          btn.disabled = false;
          btn.classList.remove('opacity-50');
          btn.innerHTML = '<i class="fa-solid fa-rotate-left"></i><span>THỬ LẠI</span>';

          alert("Tạo video thất bại: " + job.message);
        }
      } catch (e) {
        console.error("Polling error", e);
      }
    }

    async function loadOutputs() {
      try {
        const res = await fetch('/api/studio/outputs');
        const data = await res.json();
        const gallery = document.getElementById('gallery');
        if (!data.videos || data.videos.length === 0) {
          gallery.innerHTML = '<div class="text-slate-400 text-center py-4">Chưa có video nào được lưu.</div>';
          return;
        }
        gallery.innerHTML = data.videos.slice(0, 10).map(v => `
          <div class="flex items-center justify-between p-2.5 rounded-xl bg-slate-50 border border-slate-200 hover:border-blue-400 transition">
            <div class="truncate mr-2">
              <div class="font-bold text-slate-800 truncate">${v.filename}</div>
              <div class="text-[10px] text-slate-500">${v.size_mb} MB &bull; ${v.modified}</div>
            </div>
            <div class="flex space-x-1 shrink-0">
              <button onclick="playVideo('${v.stream_url}')" class="px-2.5 py-1 bg-blue-100 text-blue-700 hover:bg-blue-600 hover:text-white rounded-lg transition text-xs font-bold">
                <i class="fa-solid fa-play"></i>
              </button>
              <a href="${v.stream_url}" download class="px-2.5 py-1 bg-slate-200 text-slate-700 hover:bg-slate-300 rounded-lg transition text-xs">
                <i class="fa-solid fa-download"></i>
              </a>
            </div>
          </div>
        `).join('');
      } catch (e) {
        console.error(e);
      }
    }

    function playVideo(url) {
      const player = document.getElementById('player');
      player.src = url;
      player.classList.remove('hidden');
      document.getElementById('placeholder-box').classList.add('hidden');
      document.getElementById('download-link').href = url;
      document.getElementById('download-box').classList.remove('hidden');
      player.play();
    }

    // Startup
    checkStatus();
    loadOutputs();
    setInterval(checkStatus, 5000);
  </script>
</body>
</html>
"""


@router.get("/studio", response_class=HTMLResponse)
async def serve_studio():
    return HTMLResponse(
        content=_STUDIO_HTML,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
