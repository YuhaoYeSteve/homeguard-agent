from typing import Dict, Union

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter()


@router.get("/health")
def health() -> Dict[str, Union[bool, str]]:
    settings = get_settings()
    return {
        "status": "ok",
        "vikingdb_configured": bool(settings.vikingdb_ak and settings.vikingdb_sk),
    }
