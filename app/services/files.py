import re
import uuid
from pathlib import Path

import aiofiles
from fastapi import HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.files import File, FileCreate, FileOut
from app.repository.files import files_repository


class FilesServices:
    """文件上传业务逻辑."""

    _UPLOAD_DIR = Path("uploads")
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    _CHUNK_SIZE = 1024 * 1024

    def _build_storage_name(self, original_filename: str) -> str:
        """为本地存储创建一个安全且独特的文件名."""

        clean_name = Path(original_filename).name.strip()
        if not clean_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file must include a filename.",
            )

        suffix = Path(clean_name).suffix.lower()
        stem = Path(clean_name).stem or "file"
        safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "file"
        return f"{safe_stem}_{uuid.uuid4().hex}{suffix}"

    async def _save_file_to_disk(self, upload_file: UploadFile) -> tuple[Path, int]:
        """将一个上传的文件保存到磁盘，并返回其路径和大小."""

        stored_name = self._build_storage_name(upload_file.filename or "")
        target_path = self._UPLOAD_DIR / stored_name
        file_size = 0

        try:
            async with aiofiles.open(target_path, "wb") as output_file:
                while chunk := await upload_file.read(self._CHUNK_SIZE):
                    file_size += len(chunk)
                    await output_file.write(chunk)
        except Exception as exc:
            target_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save file: {exc}",
            ) from exc
        finally:
            await upload_file.close()

        return target_path, file_size

    async def _cleanup_saved_files(self, saved_paths: list[Path]) -> None:
        """如果上传操作失败，删除那些在上传过程中已写入的文件."""

        for path in saved_paths:
            path.unlink(missing_ok=True)

    async def _prepare_file_record(
        self, upload_file: UploadFile
    ) -> tuple[FileCreate, Path]:
        """将文件保存到磁盘，并构建元数据数据包."""

        target_path, file_size = await self._save_file_to_disk(upload_file)
        file_record = FileCreate(
            filename=Path(upload_file.filename or "").name,
            file_path=str(target_path),
            file_size=file_size,
            content_type=upload_file.content_type or "application/octet-stream",
        )
        return file_record, target_path

    async def _get_stored_file(
        self, session: AsyncSession, file_id: str
    ) -> tuple[File, Path]:
        """加载存储的文件元数据并验证其本地路径."""

        db_file = await files_repository.get_file_by_id(session, file_id)
        if not db_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found.",
            )

        upload_root = self._UPLOAD_DIR.resolve()
        file_path = Path(db_file.file_path).resolve()

        try:
            file_path.relative_to(upload_root)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Stored file path is invalid.",
            ) from exc

        if not file_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stored file does not exist.",
            )

        return db_file, file_path

    async def download_file(self, session: AsyncSession, file_id: str) -> FileResponse:
        """根据 id 加载一个文件，并将其作为附件响应返回."""

        db_file, file_path = await self._get_stored_file(session, file_id)
        return FileResponse(
            path=file_path,
            media_type=db_file.content_type,
            filename=db_file.filename,
        )

    async def preview_file(self, session: AsyncSession, file_id: str) -> FileResponse:
        """根据 id 加载一个文件，并将其作为内联响应返."""

        db_file, file_path = await self._get_stored_file(session, file_id)
        return FileResponse(
            path=file_path,
            media_type=db_file.content_type,
            filename=db_file.filename,
            content_disposition_type="inline",
        )

    async def upload_file(self, session: AsyncSession, file: UploadFile) -> FileOut:
        """上传一个文件，将其保存在本地，并保留元数据信息."""

        db_files = await self.upload_files(session, [file])
        return db_files[0]

    async def upload_files(
        self, session: AsyncSession, files: list[UploadFile]
    ) -> list[FileOut]:
        """在一个数据库事务中上传多个文件并保存元数据."""

        if not files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one file is required.",
            )

        saved_paths: list[Path] = []
        file_records: list[FileCreate] = []

        try:
            for upload_file in files:
                file_record, saved_path = await self._prepare_file_record(upload_file)
                file_records.append(file_record)
                saved_paths.append(saved_path)

            db_files = await files_repository.create_files(session, file_records)
        except HTTPException:
            await self._cleanup_saved_files(saved_paths)
            await session.rollback()
            raise
        except Exception as exc:
            await self._cleanup_saved_files(saved_paths)
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload files: {exc}",
            ) from exc

        return [FileOut.model_validate(db_file) for db_file in db_files]


files_services = FilesServices()
