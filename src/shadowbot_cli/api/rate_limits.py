"""各接口的 QPS 限流登记表（OpenAPI 层）。

数值来自影刀开放平台文档的"频率限制"列（单位：次/秒）。
接入新接口时在此登记即可，api 层调用时通过 rate_limit_for(path) 自动取用。

令牌桶语义：
  - rate     = 该接口的 QPS（每秒补充的令牌数）
  - capacity = 允许的瞬时突发；这里取 = QPS（一秒钟配额内可一次性打出）
若影刀按"固定 1 秒窗口"严格计数、不允许突发，可把个别接口 capacity 调小
（如 1）以强制匀速发送。
"""

from __future__ import annotations

from ..http.rate_limiter import RateLimit

# 常用接口路径
TOKEN_PATH = "/oapi/token/v2/token/create"
APP_LIST_PATH = "/oapi/app/open/query/list"
APP_ONLINE_DETAIL_PATH = "/oapi/app/open/query/appOnlineDetailWithParam"
APP_VERSION_DETAIL_PATH = "/oapi/app/open/query/appVersionDetail"
CLIENT_LIST_PATH = "/oapi/dispatch/v2/client/list"
CLIENT_GROUP_LIST_PATH = "/oapi/dispatch/v2/client/group/list"
JOB_START_PATH = "/oapi/dispatch/v2/job/start"
JOB_QUERY_PATH = "/oapi/dispatch/v2/job/query"
JOB_LIST_PATH = "/oapi/dispatch/v2/job/list"
JOB_STOP_PATH = "/oapi/dispatch/v2/job/stop"
FILE_UPLOAD_PATH = "/oapi/dispatch/v2/file/upload"

# 文档登记的接口频率限制（次/秒）
ENDPOINT_QPS: dict[str, float] = {
    # --- 调度 / 任务 ---
    JOB_QUERY_PATH: 30,
    "/oapi/dispatch/v2/client/query": 20,
    "/oapi/dispatch/v2/task/list": 10,
    "/oapi/dispatch/v2/task/process/detail": 10,
    "/oapi/dispatch/v2/schedule/list": 10,
    JOB_STOP_PATH: 10,
    "/oapi/dispatch/v2/task/query": 10,
    JOB_LIST_PATH: 10,
    JOB_START_PATH: 10,
    CLIENT_LIST_PATH: 10,
    "/oapi/dispatch/v2/task/start": 10,
    "/oapi/dispatch/v2/schedule/detail": 10,
    "/oapi/dispatch/v2/task/stop": 10,
    "/oapi/dispatch/v2/job/retry": 10,
    "/oapi/dispatch/v2/job/log/search": 5,
    "/oapi/dispatch/v2/job/log/notify": 5,
    "/oapi/dispatch/v2/job/log/query": 5,
    CLIENT_GROUP_LIST_PATH: 5,
    FILE_UPLOAD_PATH: 5,
    "/oapi/dispatch/v2/task/newest/list": 5,
    # --- 应用市场 / 应用查询 ---
    "/oapi/app/open/market/addMarketUser": 5,
    "/oapi/app/open/marketchangeMarketUser": 5,
    "/oapi/app/open/market/dealApproval": 5,
    "/oapi/app/open/market/pageByMarketIdList": 5,
    "/oapi/app/open/market/listByMarketIdsAndUserId": 5,
    "/oapi/app/open/market/listMarketByMarketOwnerId": 5,
    "/oapi/app/open/market/batchSaveMarket": 5,
    "/oapi/app/open/market/deleteMarketApp": 5,
    "/oapi/app/open/translate/owner": 5,
    APP_LIST_PATH: 5,
    "/oapi/app/open/query/use/record/list": 5,
    "/oapi/app/open/query/pageRunRecordData": 5,
    APP_VERSION_DETAIL_PATH: 5,
    APP_ONLINE_DETAIL_PATH: 5,
    "/oapi/app/open/historyVersionList": 5,
    # --- 机器人 ---
    "/oapi/robot/v2/query": 5,
    "/oapi/robot/v2/queryRobotParam": 3,
    # --- 资源标签 ---
    "/oapi/resource/tag/save": 5,
    "/oapi/resource/tag/delete": 5,
    "/oapi/resource/tag/listByIds": 5,
    # --- RPA 用户 ---
    "/oapi/rpa/user/v1/list": 5,
    "/oapi/rpa/user/v1/create": 10,
    "/oapi/rpa/user/v1/modify": 5,
    "/oapi/rpa/user/v1/delete": 5,
    "/oapi/rpa/user/v1/createExtraRpaEnterpriseUser": 5,
    "/oapi/rpa/user/v1/delayExtraRpaEnterpriseUser": 5,
    "/oapi/rpa/user/v2/create": 10,
    # --- 令牌 ---
    TOKEN_PATH: 20,
    "/oapi/token/v2/signature/create": 5,
    # --- 日历 ---
    "/oapi/calendar/v1/save": 5,
    "/oapi/calendar/v1/delete": 5,
    "/oapi/calendar/v1/queryCalendarDetail": 5,
}


def rate_limit_for(path: str) -> RateLimit | None:
    """按路径取限流配置；未登记返回 None（不限流）。

    rate = QPS，capacity = QPS（一秒钟配额内可一次性打出）；
    桶名取路径（去前导斜杠），作为跨进程状态文件的文件名。
    """
    qps = ENDPOINT_QPS.get(path)
    if qps is None:
        return None
    return RateLimit(rate=qps, capacity=qps, name=path.lstrip("/"))
