from typing import Annotated

from fastapi import Cookie, FastAPI, File, Header
from pydantic import BaseModel

app = FastAPI()


@app.get("/items/", tags=["Cookie"])
async def read_items(ads_id: Annotated[str | None, Cookie()] = None):
    return {"ads_id": ads_id}


@app.get("/items2/", tags=["Header"])
async def read_items2(user_agent: Annotated[str | None, Header()] = None):
    return {"User-Agent": user_agent}


@app.get("/items3/", tags=["Header"])
async def read_items3(x_token: Annotated[list[str] | None, Header()] = None):
    return {"X-Token values": x_token}


class CommonHeaders(BaseModel):
    model_config = {"extra": "forbid"}
    host: str | None = None
    referer: str | None = None
    user_agent: str | None = None
    save_data: bool | None = None
    accept: str | None = None
    if_modified_since: str | None = None
    traceparent: str | None = None
    x_tag: list[str] = []


@app.get("/items4/")
async def read_items4(headers: Annotated[CommonHeaders, Header()]):
    return headers


@app.post("/files/", tags=["File"])
async def create_file(file: Annotated[bytes, File()]):
    return {"file_size": len(file), "file_content": file.decode("utf-8")}
