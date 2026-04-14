import uuid
from typing import Any

from fastapi import FastAPI, Request, logger
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.schemas.exceptions import ErrorResponseModel, ResponseModel


# 响应模型类
class Execute:
    def response(self, data=None, message="success", code=200):
        return ResponseModel(code=code, message=message, data=data)


Execute = Execute()


# 响应异常类
class BusinessException(Exception):
    """
    自定义业务异常类
    - 继承自 Python 内置的 Exception 类。
    - 业务异常，通常用于预期内的错误情况，如用户输入错误、权限不足等。
    - 业务异常通常仍返回 200, 通过 code 区分具体错误类型。
    """

    def __init__(
        self, code: int = 400, message: str = "请联系管理员", detail: Any = None
    ):
        self.code = code
        self.message = message
        self.detail = detail


def register_exception_handlers(app: FastAPI):
    """
    捕获以下内容 :
    - 1. 自定义业务异常 (BusinessException)
    - 2. 捕获响应 (ValidationError)
    - 3. fastapi 内置 (HTTPException, RequestValidationError)
    - 4. 数据库 (IntegrityError, SQLAlchemyError)
    """

    @app.exception_handler(BusinessException)
    async def business_exception_handler(request, exc: BusinessException):
        return JSONResponse(
            # 业务异常通常仍返回 200，通过 code 区分
            status_code=200,
            content=ErrorResponseModel(
                code=exc.code, message=exc.message, detail=exc.detail
            ).model_dump(),
        )

    # 捕获响应模型的效验失败，根据 response_model 参数对返回值进行 Pydantic 模型效验
    @app.exception_handler(PydanticValidationError)
    async def pydantic_validation_error_handler(
        request: Request, exc: PydanticValidationError
    ):
        return JSONResponse(
            status_code=500,
            content=ErrorResponseModel(
                code=500, message="响应数据模型校验失败", detail=exc.errors()
            ).model_dump(),
        )

    # 捕获 fastapi 内置异常，请求参数效验
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        return JSONResponse(
            status_code=422,
            content=ErrorResponseModel(
                code=422, message="请求数据校验失败", detail=exc.errors()
            ).model_dump(),
        )

    # 捕获 fastapi 内置异常
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponseModel(
                code=exc.status_code, message=exc.detail
            ).model_dump(),
        )

    # 捕获数据库异常
    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError):
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponseModel(
                code=exc.status_code, message=exc.detail
            ).model_dump(),
        )

    # 捕获数据库异常
    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
        trace_id = str(uuid.uuid4())

        logger.error(f"[{trace_id}] SQLAlchemyError: {exc}")

        return JSONResponse(
            status_code=500,
            content=ErrorResponseModel(code=500, message="数据库错误"),
        )

    # 捕获所有未处理异常（兜底）
    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        # 记录日志
        return JSONResponse(
            status_code=500,
            content=ErrorResponseModel(code=500, message="服务器内部错误"),
        )
