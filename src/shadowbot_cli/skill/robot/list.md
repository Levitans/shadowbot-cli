# shadowbot-cli robot list

查询机器人列表（影刀中一个机器人即一台电脑）。

## 用法

    shadowbot-cli robot list

无参数

## 输出

| 字段 | 说明 |
| --- | --- |
| `robotClientUuid` | 机器人 UUID |
| `robotClientName` | 机器人名称 |
| `status` | 在线状态（`online` / `offline`） |

    {"success": true, "data": {"list": [{"robotClientUuid": "...", "robotClientName": "桉夏@fckjjs", "status": "offline"}], "total": 5}, "error": null}


## 相关命令

- `shadowbot-cli robot groups`：查询机器人组列表
