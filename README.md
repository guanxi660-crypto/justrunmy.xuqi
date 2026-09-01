# 🚀 JustRunMy 自动续期（GitHub Actions）
修改自 https://github.com/losy-mify/JustRunMy-Renew，
现已改为通过浏览器 Cookie 登录，并支持外部 SOCKS5 代理以通过 Cloudflare 人机验证。

这是一个基于 GitHub Actions 的自动化脚本，用于定时注入登录 Cookie 并自动点击 Reset timer 续期 JustRunMy 应用。

━━━━━━━━━━━━━━━━━━━━━━

🔐 Secrets 配置说明

| Secret 名称        | 是否必填 | 说明                                                                 |
|-------------------|----------|----------------------------------------------------------------------|
| JUSTRUNMY_COOKIE  | ✅ 必填  | 浏览器登录后的完整 Cookie 串（格式：`name1=value1; name2=value2`），关键的一条是 `.AspNetCore.Identity.Application` |
| JUSTRUNMY_PROXY   | ❌ 推荐  | SOCKS5 代理地址（如 `socks5://user:pass@ip:port`），支持带账号密码认证，由 workflow 内 gost 自动转发；不填则尝试 SSH 隧道，再不行就直连 |
| JUSTRUNMY_APP_URL | ❌ 可选  | 要续期的应用详情页地址（如 `https://justrunmy.app/panel/application/57562/`），不填则使用脚本内置默认值 |
| SSH_HOST          | ❌ 可选  | SSH 代理服务器地址（与 JUSTRUNMY_PROXY 二选一，填写后脚本会建立 ssh -D 动态隧道） |
| SSH_USER          | ❌ 可选  | SSH 用户名                                                          |
| SSH_PASS          | ❌ 可选  | SSH 密码                                                            |
| SSH_PORT          | ❌ 可选  | SSH 端口（默认 22）                                                  |
| TG_BOT_TOKEN      | ❌ 可选  | Telegram Bot Token（用于发送通知）                                   |
| TG_CHAT_ID        | ❌ 可选  | Telegram Chat ID（接收通知的用户或群组 ID）                           |

> ⚠️ 注意：JUSTRUNMY_EMAIL / JUSTRUNMY_PASSWORD / GOST_PROXY_TARGET 是旧版（邮箱+密码登录）方案使用的变量，当前脚本已不再读取，无需配置。

━━━━━━━━━━━━━━━━━━━━━━

📌 获取 JUSTRUNMY_COOKIE 的方法

1. 用浏览器登录 https://justrunmy.app ，确认处于已登录状态（能看到应用详情页）
2. 按 F12 打开开发者工具 → Network（网络）标签
3. 刷新页面，点开任意一个发往 justrunmy.app 的请求 → Request Headers（请求标头）
4. 复制 `Cookie:` 冒号后面的整串内容，原样填入 Secret（不要带 `Cookie:` 前缀、不要加引号、保持一整行）

Cookie 会过期。如果运行日志提示 "页面被重定向到了登录页"，重新按上述步骤抓一次即可。

━━━━━━━━━━━━━━━━━━━━━━

📌 示例填写格式（复制下面内容，分开添加）：

JUSTRUNMY_COOKIE=.AspNetCore.Identity.Application=CfDJ8...; cookieyes-consent=...  
JUSTRUNMY_PROXY=socks5://user:pass@123.45.67.89:1080  
JUSTRUNMY_APP_URL=https://justrunmy.app/panel/application/12345/  
TG_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRstuVWXyz  
TG_CHAT_ID=123456789  

━━━━━━━━━━━━━━━━━━━━━━

📌 运行逻辑

1. 读取 JUSTRUNMY_COOKIE，注入到 justrunmy.app 域下
2. 打开应用详情页；若被重定向到登录页则判定 Cookie 失效并报错
3. 点击 Reset timer 打开续期弹窗
4. 通过 CDP 模拟物理点击击穿 Cloudflare Turnstile 人机验证
5. 点击 Just Reset 完成续期，成功后发送 Telegram 通知

如果验证总是拿不到 Token，通常是代理节点的 IP 被 Cloudflare 标记，换一个节点即可。
