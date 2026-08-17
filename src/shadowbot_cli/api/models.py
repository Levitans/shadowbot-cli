"""OpenAPI 层的数据模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    access_token: str
    expires_in: int
