from fastapi import APIRouter, Depends

from app.api.v1 import auth, items, users
from app.core.security import get_current_user

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
    items.router,
    prefix="/api/item",
    tags=["Items"],
    dependencies=[Depends(get_current_user)],
    responses={404: {"description": "Not found"}},
    **params,
)
