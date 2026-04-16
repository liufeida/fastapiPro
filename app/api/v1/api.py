from fastapi import APIRouter, Depends

from app.api.v1 import auth, files, ollama, users
from app.core.security import get_current_user

router = APIRouter()

params = {}

router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Auth"],
    responses={404: {"description": "Not found"}},
    **params,
)
router.include_router(
    ollama.router,
    prefix="/ollama",
    tags=["Ollama"],
    # dependencies=[Depends(get_current_user)],
    responses={404: {"description": "Not found"}},
    **params,
)
router.include_router(
    users.router,
    prefix="/users",
    tags=["Users"],
    dependencies=[Depends(get_current_user)],
    responses={404: {"description": "Not found"}},
    **params,
)
router.include_router(
    files.router,
    prefix="/files",
    tags=["Files"],
    dependencies=[Depends(get_current_user)],
    responses={404: {"description": "Not found"}},
    **params,
)
