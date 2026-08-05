from pathlib import Path

from fastapi import UploadFile

from app.core.exceptions import BusinessException


class FileParser:
    """纯文本类文件解析器."""

    # 支持的文件后缀
    _SUPPORTED_SUFFIXES = {
        ".txt", ".md", ".csv", ".json", ".py", ".log", ".html", ".xml",
        ".yaml", ".yml", ".js", ".ts", ".java", ".c", ".cpp", ".go",
        ".rs", ".sql", ".sh", ".bat",
    }

    # 文件大小上限（10MB）
    _MAX_SIZE = 10 * 1024 * 1024

    async def parse(self, upload_file: UploadFile) -> str:
        """解析单个上传文件并返回其文本内容."""

        filename = upload_file.filename or ""
        suffix = Path(filename).suffix.lower()
        if suffix not in self._SUPPORTED_SUFFIXES:
            raise BusinessException(
                code=400, message=f"暂不支持的文件类型: {suffix}"
            )

        content_bytes = await upload_file.read()
        if len(content_bytes) > self._MAX_SIZE:
            raise BusinessException(
                code=400, message="文件过大，最大支持 10MB"
            )

        return content_bytes.decode("utf-8", errors="ignore")

    async def parse_many(self, files: list[UploadFile]) -> str:
        """解析多个上传文件并拼接为带文件名标注的上下文块."""

        if not files:
            return ""

        blocks: list[str] = []
        for upload_file in files:
            content = await self.parse(upload_file)
            filename = upload_file.filename or ""
            blocks.append(f"===== 文件: {filename} =====\n{content}")

        return "\n\n".join(blocks)


file_parser = FileParser()
