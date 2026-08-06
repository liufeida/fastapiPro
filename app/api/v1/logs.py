from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Path, status

from app.api.dependencies import SessionDeep
from app.core.exceptions import Execute
from app.models.ai_chat_log import AIChatLogQueryParams, AIChatLogReo
from app.models.api_access_log import ApiAccessLogQueryParams, ApiAccessLogReo
from app.models.ai_model_config import PageResult
from app.repository.api_access_log import api_access_log_repository
from app.repository.ai_chat_log import ai_chat_log_repository
from app.schemas.exceptions import ResponseModel

router = APIRouter()

TRUNCATE_MAX_LEN = 1000


def _truncate_text(text: str | None, max_len: int = TRUNCATE_MAX_LEN) -> tuple[str | None, int]:
    if text is None:
        return None, 0
    return (text[:max_len], len(text)) if len(text) > max_len else (text, len(text))


def _build_api_access_log_record(orm_obj, truncate: bool = True) -> dict:
    reo = ApiAccessLogReo.model_validate(orm_obj)
    data = reo.model_dump()
    if truncate:
        for field in ("request_body", "response_body"):
            truncated, total = _truncate_text(data.get(field))
            data[field] = truncated
            data[f"{field}_total_length"] = total
    return data


def _build_ai_chat_log_record(orm_obj, truncate: bool = True) -> dict:
    reo = AIChatLogReo.model_validate(orm_obj)
    data = reo.model_dump()
    if truncate:
        for field in ("messages", "response_content", "system_prompt"):
            truncated, total = _truncate_text(data.get(field))
            data[field] = truncated
            data[f"{field}_total_length"] = total
    return data


@router.post(
    "/api/list",
    response_model=ResponseModel[PageResult],
    summary="HTTP 访问日志分页列表",
    operation_id="listApiAccessLogs",
)
async def list_api_access_logs(
    session: SessionDeep,
    query: Annotated[ApiAccessLogQueryParams, Body()],
):
    filters = query.model_dump(exclude_none=True, exclude={"page", "pageSize"})
    total = await api_access_log_repository.count(session, **filters)
    orm_list = await api_access_log_repository.list_paginated(
        session, query.offset, query.pageSize, **filters
    )
    records = [_build_api_access_log_record(obj, truncate=True) for obj in orm_list]
    result = PageResult(
        records=records,
        total=total,
        page=query.page,
        pageSize=query.pageSize,
        pages=(total + query.pageSize - 1) // query.pageSize if query.pageSize else 0,
    )
    return Execute.response(result)


@router.get(
    "/api/{log_id}",
    response_model=ResponseModel[ApiAccessLogReo],
    summary="HTTP 访问日志详情",
    operation_id="getApiAccessLogById",
)
async def get_api_access_log(
    session: SessionDeep,
    log_id: Annotated[str, Path(description="日志 ID")],
):
    log = await api_access_log_repository.get_by_id(session, log_id)
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return Execute.response(ApiAccessLogReo.model_validate(log))


@router.delete(
    "/api/{log_id}",
    response_model=ResponseModel[ApiAccessLogReo],
    summary="删除 HTTP 访问日志",
    operation_id="deleteApiAccessLog",
)
async def delete_api_access_log(
    session: SessionDeep,
    log_id: Annotated[str, Path(description="日志 ID")],
):
    log = await api_access_log_repository.get_by_id(session, log_id)
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    await api_access_log_repository.delete_by_id(session, log_id)
    return Execute.response(ApiAccessLogReo.model_validate(log))


@router.post(
    "/ai/list",
    response_model=ResponseModel[PageResult],
    summary="AI 调用日志分页列表",
    operation_id="listAIChatLogs",
)
async def list_ai_chat_logs(
    session: SessionDeep,
    query: Annotated[AIChatLogQueryParams, Body()],
):
    filters = query.model_dump(exclude_none=True, exclude={"page", "pageSize"})
    total = await ai_chat_log_repository.count(session, **filters)
    orm_list = await ai_chat_log_repository.list_paginated(
        session, query.offset, query.pageSize, **filters
    )
    records = [_build_ai_chat_log_record(obj, truncate=True) for obj in orm_list]
    result = PageResult(
        records=records,
        total=total,
        page=query.page,
        pageSize=query.pageSize,
        pages=(total + query.pageSize - 1) // query.pageSize if query.pageSize else 0,
    )
    return Execute.response(result)


@router.get(
    "/ai/{log_id}",
    response_model=ResponseModel[AIChatLogReo],
    summary="AI 调用日志详情",
    operation_id="getAIChatLogById",
)
async def get_ai_chat_log(
    session: SessionDeep,
    log_id: Annotated[str, Path(description="日志 ID")],
):
    log = await ai_chat_log_repository.get_by_id(session, log_id)
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return Execute.response(AIChatLogReo.model_validate(log))


@router.delete(
    "/ai/{log_id}",
    response_model=ResponseModel[AIChatLogReo],
    summary="删除 AI 调用日志",
    operation_id="deleteAIChatLog",
)
async def delete_ai_chat_log(
    session: SessionDeep,
    log_id: Annotated[str, Path(description="日志 ID")],
):
    log = await ai_chat_log_repository.get_by_id(session, log_id)
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    await ai_chat_log_repository.delete_by_id(session, log_id)
    return Execute.response(AIChatLogReo.model_validate(log))
