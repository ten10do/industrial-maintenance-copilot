"""静态文件服务：上传附件访问。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.deps import get_current_user

router = APIRouter(prefix="/files", tags=["files"])


def _resolve_storage_path(base: Path, path: str) -> Path:
    resolved_base = base.resolve()
    full = (resolved_base / path).resolve()
    if not full.is_relative_to(resolved_base):
        raise HTTPException(status_code=403, detail="禁止访问")
    return full


@router.get("/{path:path}")
def serve_file(path: str, _=Depends(get_current_user)):
    base = Path(settings.STORAGE_LOCAL_DIR).resolve()
    full = _resolve_storage_path(base, path)
    if not full.exists() or not full.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(full)
