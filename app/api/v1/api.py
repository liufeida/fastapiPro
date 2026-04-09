from fastapi import APIRouter

from app.api.v1 import auth, files, users

router = APIRouter()

params = {}

router.include_router(
    auth.router,
    prefix="/api/auth",
    tags=["Auth"],
    responses={404: {"description": "Not found"}},
    **params,
)
router.include_router(
    users.router,
    prefix="/api/users",
    tags=["Users"],
    # dependencies=[Depends(get_current_user)],
    responses={404: {"description": "Not found"}},
    **params,
)
router.include_router(
    files.router,
    prefix="/api/files",
    tags=["Files"],
    # dependencies=[Depends(get_current_user)],
    responses={404: {"description": "Not found"}},
    **params,
)
