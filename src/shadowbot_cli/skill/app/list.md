# shadowbot-cli app list

查询已发版应用列表，附带每个应用的参数说明（flowParams）与使用说明（instruction）。

## 用法

    shadowbot-cli app list [OPTIONS]

## 选项

| 选项 | 说明 |
| --- | --- |
| `--app-name` | 按应用名关键词查询（对应接口 appName） |
| `--owner-account` | 按负责人账号查询（对应接口 ownerUserSearchKey） |
| `--include-all` | 不过滤，返回全部应用（含未发版与指令类型） |

`--app-name` 与 `--owner-account` 只能二选一；两者都不给时返回全部已发版应用。

默认只返回 `appType=app`、已发版、且带使用说明（`instruction` 非空）的应用；
没有使用说明的应用 Agent 无法判断用途，不会返回。`--include-all` 关闭全部过滤（含未发版、指令类型、无使用说明）。

## 示例

### 按应用名查询

    shadowbot-cli app list --app-name "测试"

### 按负责人账号查询

    shadowbot-cli app list --owner-account "guodong@fckjjs"

### 全量查询

    shadowbot-cli app list

## 输出

成功时 stdout 输出 JSON 信封，`data.list` 为应用数组，`data.total` 为应用数量。每个应用含：

| 字段 | 说明 |
| --- | --- |
| `appId` | 应用 ID |
| `appName` | 应用名称 |
| `ownerName` | 负责人显示名 |
| `ownerAccount` | 负责人账号 |
| `instruction` | 使用说明（HTML 文本） |
| `flowParams` | 参数列表，每项含 name / direction / type / value / description / kind |

    {"success": true, "data": {"list": [{"appId": "...", "appName": "...", "ownerName": "...", "ownerAccount": "...", "instruction": "...", "flowParams": [...]}], "total": 11}, "error": null}

未登录时退出码 1、`error.code=auth_error`；`--app-name` 与 `--owner-account` 同时给时退出码 2、`error.code=usage_error`。
