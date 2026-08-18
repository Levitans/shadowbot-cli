# shadowbot-cli login

登录影刀 RPA 开放平台，获取访问令牌并保存到本地。

## 用法

    shadowbot-cli login [OPTIONS]

## 选项

| 选项 | 说明 |
| --- | --- |
| `--access-key-id` | 应用 Access Key ID，可用环境变量 `SHADOWBOT_ACCESS_KEY_ID` |
| `--access-key-secret` | 应用 Access Key Secret，可用环境变量 `SHADOWBOT_ACCESS_KEY_SECRET` |

凭据来源：命令行参数 > 环境变量 > `.env` 文件。命令**非交互式**，不会弹出提示输入。

## 示例

### 参数直传

    shadowbot-cli login --access-key-id YOUR_KEY_ID --access-key-secret YOUR_KEY_SECRET

### 环境变量

    export SHADOWBOT_ACCESS_KEY_ID=YOUR_KEY_ID
    export SHADOWBOT_ACCESS_KEY_SECRET=YOUR_KEY_SECRET
    shadowbot-cli login

### 使用 .env

复制 `.env.example` 为 `.env` 并填入真实凭据后，直接运行 `shadowbot-cli login`。

## 输出

成功时 stdout 输出 JSON 信封，`data` 含保存路径与令牌有效期（不输出令牌本体）：

    {"success": true, "data": {"saved_to": "...", "expires_in": 7200}, "error": null}

缺少凭据时以退出码 2 输出错误信封（code=usage_error）。

## 说明

- 凭据与令牌按 XDG 规范保存到 `~/.config/shadowbot-cli/config.json`，文件权限 0600
- 令牌过期后会用已保存的凭据自动续期；仅当 Access Key 失效时才需重新登录
