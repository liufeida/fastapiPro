"""Google 第三方登录验证模块。

方案：PyJWT + httpx（均为项目已有依赖），无需额外安装 google-auth。

- ``id_token``：从 https://www.googleapis.com/oauth2/v3/certs 拉取 Google 公钥 (JWKS)，
  校验 JWT 签名 (RS256)、iss、aud（必须等于 ``GOOGLE_CLIENT_ID``）、exp 过期时间，
  并按要求校验 ``email_verified``。
- ``access_token``：调用 https://www.googleapis.com/oauth2/v2/userinfo 换取用户信息。

代理支持（Google 接口在国内需走代理，与 web_search 保持一致）：
  - 优先 ``GOOGLE_PROXY``，其次 ``SEARCH_PROXY`` / ``HTTPS_PROXY`` / ``HTTP_PROXY``
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

import httpx
import jwt

logger = logging.getLogger(__name__)

GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
# Google id_token 历史上出现过两种 iss，都接受
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
GOOGLE_TOKEN_ALGORITHMS = ["RS256"]

# 证书缓存：Google 官方建议缓存至多 24 小时；kid 未命中时强制刷新一次
_CERTS_CACHE_TTL_SECONDS = 3600
_certs_cache: dict = {"fetched_at": 0.0, "keys": []}


class GoogleAuthError(Exception):
    """Google token 无效或验证失败。"""


@dataclass
class GoogleUserInfo:
    """从 Google 提取到的用户信息。"""

    email: str
    name: str = ""
    picture: str = ""
    sub: str = ""


def _get_proxy() -> str | None:
    return (
        os.getenv("GOOGLE_PROXY")
        or os.getenv("SEARCH_PROXY")
        or os.getenv("HTTPS_PROXY")
        or os.getenv("HTTP_PROXY")
        or None
    )


def _build_client() -> httpx.AsyncClient:
    kwargs: dict = {"timeout": 10}
    proxy = _get_proxy()
    if proxy:
        kwargs["proxy"] = proxy
    return httpx.AsyncClient(**kwargs)


async def _fetch_google_certs(force: bool = False) -> list[dict]:
    """拉取 Google 公钥 JWKS，带进程内内存缓存。"""
    now = time.monotonic()
    if (
        not force
        and _certs_cache["keys"]
        and now - _certs_cache["fetched_at"] < _CERTS_CACHE_TTL_SECONDS
    ):
        return _certs_cache["keys"]

    try:
        async with _build_client() as client:
            resp = await client.get(GOOGLE_CERTS_URL)
            resp.raise_for_status()
            keys = resp.json().get("keys", [])
    except Exception:
        # 网络失败时若有旧缓存则降级使用，否则抛给上层
        if _certs_cache["keys"]:
            return _certs_cache["keys"]
        raise

    _certs_cache["keys"] = keys
    _certs_cache["fetched_at"] = now
    return keys


def _find_signing_key(keys: list[dict], kid: str) -> dict | None:
    for key in keys:
        if key.get("kid") == kid:
            return key
    return None


async def verify_google_id_token(id_token: str) -> GoogleUserInfo:
    """验证 Google id_token（JWT）并提取用户信息。

    校验内容：签名 (RS256)、iss、aud（== GOOGLE_CLIENT_ID）、exp、email_verified。
    任一不通过抛 ``GoogleAuthError``。
    """
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    if not client_id:
        logger.error("GOOGLE_CLIENT_ID 未配置，无法校验 Google id_token 的 aud")
        raise GoogleAuthError("GOOGLE_CLIENT_ID not configured")

    try:
        # 1. 从 token 头部取 kid，定位对应公钥
        kid = jwt.get_unverified_header(id_token).get("kid")
        if not kid:
            raise GoogleAuthError("missing kid")

        keys = await _fetch_google_certs()
        jwk_data = _find_signing_key(keys, kid)
        if jwk_data is None:
            # kid 未命中：强制刷新一次证书缓存再试（key 轮换场景）
            keys = await _fetch_google_certs(force=True)
            jwk_data = _find_signing_key(keys, kid)
        if jwk_data is None:
            raise GoogleAuthError("unknown signing key")

        signing_key = jwt.PyJWK(jwk_data, algorithm="RS256")

        # 2. 验签 + 校验 aud / iss / exp / 必填声明
        payload = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=GOOGLE_TOKEN_ALGORITHMS,
            audience=client_id,
            issuer=GOOGLE_ISSUERS,
            options={"require": ["iss", "aud", "exp", "sub", "email"]},
        )
    except GoogleAuthError:
        raise
    except Exception as exc:
        # 签名错误、过期、aud/iss 不匹配、格式错误等，统一视为无效 token
        logger.warning("Google id_token 验证失败: %s", exc)
        raise GoogleAuthError("invalid id_token") from exc

    email = payload.get("email")
    if not email:
        raise GoogleAuthError("missing email")

    # Google 官方建议：仅当 email_verified 为 True 时才可用 email 标识/关联用户
    if not payload.get("email_verified"):
        raise GoogleAuthError("email not verified")

    return GoogleUserInfo(
        email=email,
        name=payload.get("name") or "",
        picture=payload.get("picture") or "",
        sub=payload.get("sub") or "",
    )


async def get_google_userinfo(access_token: str) -> GoogleUserInfo:
    """用 access_token 调 Google userinfo API 换取用户信息。"""
    try:
        async with _build_client() as client:
            resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                raise GoogleAuthError(f"userinfo http {resp.status_code}")
            data = resp.json()
    except GoogleAuthError:
        raise
    except Exception as exc:
        logger.warning("Google userinfo 请求失败: %s", exc)
        raise GoogleAuthError("userinfo request failed") from exc

    email = data.get("email")
    if not email:
        raise GoogleAuthError("missing email")

    return GoogleUserInfo(
        email=email,
        name=data.get("name") or "",
        picture=data.get("picture") or "",
        sub=data.get("sub") or data.get("id") or "",
    )
