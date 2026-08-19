# shadowbot-cli job get

查询单个任务详情（状态、入参出参、执行时间等）。

## 用法

    shadowbot-cli job get --job-uuid <任务UUID>

## 选项

| 选项 | 说明 |
| --- | --- |
| `--job-uuid` | 任务 UUID（`app run` 返回的 `jobUuid`） |

## 输出

| 字段 | 说明 |
| --- | --- |
| `jobUuid` | 任务 UUID |
| `status` | 状态标识（`finish` / `running` / `error` / `stopped` / `cancel` / `pending` 等） |
| `statusName` | 状态中文名 |
| `robotUuid` | 应用 UUID |
| `robotName` | 应用名称 |
| `robotClientUuid` | 执行机器人 UUID |
| `robotClientName` | 执行机器人名称 |
| `createTime` | 创建时间 |
| `startTime` | 开始执行时间 |
| `endTime` | 结束时间 |
| `remark` | 备注（错误时含失败原因） |
| `screenshotUrl` | 截图 URL（部分状态有） |
| `inputs` | 入参数组，每项含 `name` / `value` / `type` |
| `outputs` | 出参数组，每项含 `name` / `value` / `type` |

    {"success": true, "data": {"jobUuid": "...", "status": "finish", "statusName": "完成", "robotUuid": "...", "robotName": "测试应用", "inputs": [], "outputs": []}, "error": null}

## 相关命令

- `shadowbot-cli job list`：查询任务列表
- `shadowbot-cli job stop`：停止任务
- `shadowbot-cli app run`：启动应用运行（创建任务）
