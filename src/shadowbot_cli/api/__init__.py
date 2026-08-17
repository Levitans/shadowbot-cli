"""OpenAPI 层：影刀开放平台接口封装。

一个方法对应一个接口；依赖 http 层（发请求/限流）与 config（凭据/令牌），
不依赖 cli 层。
"""

from .client import ApiClient, build_api_client
from .models import Token

__all__ = ["ApiClient", "build_api_client", "Token"]
