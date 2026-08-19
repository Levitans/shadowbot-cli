# shadowbot-cli app run

启动应用运行。

## 用法

    shadowbot-cli app run --app-id <应用ID> --account-name <机器人账号> [--params '<JSON>']

## 选项

| 选项 | 说明 |
| --- | --- |
| `--app-id` | 应用 ID，必填。即 `app list` 返回的 `appId` |
| `--account-name` | 机器人账号，必填。即 `robot list` 返回的 `robotClientName`（如 `guodong@fckjjs`） |
| `--params` | 运行参数 JSON 对象，可选。`"-"` 表示从 stdin 读取 |

## --params

格式为 JSON 对象 `{参数名: 值}`，无需指定参数类型，以最近一次 `app list` 查询到的参数说明为准自动补齐。
参数名必须在应用的入参列表中，否则报错并列出可选参数名。

`file` 类型参数必须给本地文件路径（如 `/Users/wentao/Downloads/测试数据.xlsx`），会自动上传并替换为 fileKey。

应用没有入参时可省略 `--params`。

## 示例

    shadowbot-cli app run --app-id ea705757-e19d-4f75-beba-18af746819b6 --account-name guodong@fckjjs --params '{"入参1": "abc", "入参5": "/tmp/数据.xlsx"}'

## 输出

成功时 stdout 输出 JSON 信封，`data` 为接口返回的运行信息（含 jobUuid 等）。

    {"success": true, "data": {"jobUuid": "..."}, "error": null}

## 相关命令

- `shadowbot-cli app list`：查询应用（取 `appId` 与参数说明）
- `shadowbot-cli robot list`：查询机器人（取 `robotClientName`）
