from fastapi import APIRouter, Depends

from app.api.v1 import ai, ai_model_config, auth, chat_conversations, deepseek, files, logs, ollama, prompts, users
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
# router.include_router(
#     ollama.router,
#     prefix="/ollama",
#     tags=["Ollama"],
#     # dependencies=[Depends(get_current_user)],
#     responses={404: {"description": "Not found"}},
#     **params,
# )
router.include_router(
    ai.router,
    prefix="/ai",
    tags=["AI Stream"],
    # dependencies=[Depends(get_current_user)],
    responses={404: {"description": "Not found"}},
    **params,
)
router.include_router(
    chat_conversations.router,
    prefix="/conversations",
    tags=["AI Chat Conversations"],
    responses={404: {"description": "Not found"}},
    **params,
)
router.include_router(
    ai_model_config.router,
    prefix="/ai-models",
    tags=["AI Model Config"],
    # dependencies=[Depends(get_current_user)],
    responses={404: {"description": "Not found"}},
    **params,
)
# router.include_router(
#     deepseek.router,
#     prefix="/deepseek",
#     tags=["DeepSeek"],
#     # dependencies=[Depends(get_current_user)],
#     responses={404: {"description": "Not found"}},
#     **params,
# )
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
router.include_router(
    prompts.router,
    prefix="/prompts",
    tags=["System Prompts"],
    responses={404: {"description": "Not found"}},
    **params,
)
router.include_router(
    logs.router,
    prefix="/logs",
    tags=["Logs"],
    responses={404: {"description": "Not found"}},
    **params,
)
