from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.files import File, FileCreate


class FilesRepository:
    """文件元数据持久化层."""

    async def get_file_by_id(self, session: AsyncSession, file_id: str) -> File | None:
        """根据 id 查找一个文件元数据记录."""

        result = await session.execute(select(File).where(File.id == file_id))
        return result.scalar_one_or_none()

    async def create_file(self, session: AsyncSession, data: FileCreate) -> File:
        """创建一个文件元数据."""

        db_file = File.model_validate(data)
        session.add(db_file)
        await session.commit()
        await session.refresh(db_file)
        return db_file

    async def create_files(
        self, session: AsyncSession, data_list: list[FileCreate]
    ) -> list[File]:
        """在一个事务中创建多个文件元数据记录."""

        db_files = [File.model_validate(data) for data in data_list]
        session.add_all(db_files)
        await session.commit()

        for db_file in db_files:
            await session.refresh(db_file)

        return db_files


files_repository = FilesRepository()
