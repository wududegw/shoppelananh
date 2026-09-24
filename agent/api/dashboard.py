"""Serve the built React dashboard alongside the existing API."""
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(include_in_schema=False)
DIST = Path(__file__).resolve().parents[2] / "dashboard" / "dist"


@router.get("/")
@router.get("/studio")
@router.get("/projects")
@router.get("/projects/{project_id}")
@router.get("/gallery")
@router.get("/logs")
@router.get("/guide")
@router.get("/settings")
async def dashboard(project_id: str = ""):
    page = DIST / "index.html"
    if not page.is_file():
        raise HTTPException(503, "Chưa build dashboard. Chạy Chay_Tool_Tao_Video.bat hoặc npm run build trong dashboard.")
    return FileResponse(page, headers={"Cache-Control": "no-cache"})
