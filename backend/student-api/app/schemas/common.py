from typing import Any, Generic, Optional, TypeVar
from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class PaginationMeta(BaseModel):
    page: int
    limit: int
    total: int


class StandardResponse(BaseModel, Generic[T]):
    success: bool = True
    data: Optional[T] = None
    message: Optional[str] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class PaginatedResponse(BaseModel, Generic[T]):
    success: bool = True
    data: list[T]
    meta: PaginationMeta

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail


def ok(data: Any = None, message: Optional[str] = None) -> dict:
    return {"success": True, "data": data, "message": message}


def paginated(data: list, page: int, limit: int, total: int) -> dict:
    return {
        "success": True,
        "data": data,
        "meta": {"page": page, "limit": limit, "total": total},
    }


def err(code: str, message: str, status_code: int = 400):
    from fastapi import HTTPException
    raise HTTPException(
        status_code=status_code,
        detail={"success": False, "error": {"code": code, "message": message}},
    )
