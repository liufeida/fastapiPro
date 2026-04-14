from typing import Annotated

from fastapi import APIRouter
from fastapi import File as FastAPIFile
from fastapi import UploadFile
from fastapi.responses import FileResponse

from app.api.dependencies import SessionDeep
from app.core.exceptions import Execute
from app.models.files import FileOut, PageResult, QueryRequest
from app.schemas.exceptions import ResponseModel
from app.services.files import files_services

router = APIRouter()


@router.get("/preview/{file_id}", response_class=FileResponse, summary="预览文件")
async def preview_file(session: SessionDeep, file_id: str):
    """预览文件"""

    return await files_services.preview_file(session, file_id)


@router.get(
    "/download/{file_id}", response_class=FileResponse, summary="根据 fileId 下载单文件"
)
async def download_file(session: SessionDeep, file_id: str):
    """下载单文件"""

    return await files_services.download_file(session, file_id)


@router.post("/uploadfile", response_model=ResponseModel[FileOut], summary="单文件上传")
async def upload_file(
    session: SessionDeep,
    file: Annotated[UploadFile, FastAPIFile(description="单文件")],
):
    """上传单文件并返回元数据"""

    data = await files_services.upload_file(session, file)
    return Execute.response(data)


@router.post(
    "/uploadfiles", response_model=ResponseModel[list[FileOut]], summary="多文件上传"
)
async def upload_files(
    session: SessionDeep,
    files: Annotated[
        list[UploadFile],
        FastAPIFile(description="多文件"),
    ],
):
    """上传多文件并返回元数据"""

    data = await files_services.upload_files(session, files)
    return Execute.response(data)


@router.post(
    "/fileList",
    response_model=ResponseModel[PageResult[FileOut]],
    summary="根据 ids 获取文件分页列表",
)
async def file_list(session: SessionDeep, query: QueryRequest):

    data = await files_services.file_list(session, query)
    return Execute.response(data)
