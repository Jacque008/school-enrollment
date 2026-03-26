import httpx
from app.config import get_settings

settings = get_settings()

WECHAT_LOGIN_URL = "https://api.weixin.qq.com/sns/jscode2session"


async def code_to_session(code: str) -> dict:
    """Exchange WeChat login code for session info (openid, session_key)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            WECHAT_LOGIN_URL,
            params={
                "appid": settings.WECHAT_APP_ID,
                "secret": settings.WECHAT_APP_SECRET,
                "js_code": code,
                "grant_type": "authorization_code",
            },
        )
        data = resp.json()
        if "errcode" in data and data["errcode"] != 0:
            raise ValueError(f"WeChat login failed: {data.get('errmsg', 'unknown')}")
        return data
