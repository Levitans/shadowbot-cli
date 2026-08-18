# shadowbot-cli robot groups

查询机器人组列表（多个机器人可组成一个机器人组）。

## 用法

    shadowbot-cli robot groups

无参数，返回全部机器人组（自动拉取所有分页）。

## 输出

成功时 stdout 输出 JSON 信封，`data.list` 为机器人组数组，`data.total` 为组数量。每个组含：

| 字段 | 说明 |
| --- | --- |
| `robotClientGroupUuid` | 机器人组 UUID |
| `robotClientGroupName` | 机器人组名称 |

    {"success": true, "data": {"list": [{"robotClientGroupUuid": "...", "robotClientGroupName": "桉夏"}], "total": 3}, "error": null}

未登录时退出码 1、`error.code=auth_error`。

## 相关命令

- `shadowbot-cli robot list`：查询机器人列表
