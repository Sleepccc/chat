# PocketGuardian — M01 本地服务

M01 为 PocketGuardian 建立最小本地 HTTP 服务：配置校验、健康检查、本地凭据认证和请求来源检查。尚未接入 Agent、数据库、任务执行或手机配对；不代表完整产品或公网部署验收。

## 模块与运行链路

| 文件 | 职责 |
| --- | --- |
| `src/pocket_guardian/config.py` | `Setting`（配置）校验环境变量；`load_settings`（加载配置）返回配置对象 |
| `src/pocket_guardian/api/app.py` | `create_app`（创建应用）保存配置，注册路由和 Host/Origin 检查 |
| `src/pocket_guardian/auth/local.py` | `verify_token`（核验凭据）比较双方 Token；`require_local_actor`（要求本地身份）验证当前请求并提供服务端身份 |
| `src/pocket_guardian/__main__.py` | `main`（主入口）读取配置；`build_server`（构建服务器）返回配置好的 Uvicorn Server；`run` 启动监听 |
| `tests/unit` | 独立检查配置、应用创建和凭据比较 |
| `tests/integration` | TestClient 在进程内调用应用，不监听端口 |
| `tests/e2e` | 真正启动 Uvicorn 并发送本机 HTTP 请求；另起命令行进程检查启动失败 |

启动：环境变量 → load_settings → create_app → Uvicorn 监听。
请求：Uvicorn → Host 检查 → Origin 检查 → 路由及所需认证 → HTTP 响应。
框架为请求提供 `request.app`；`app.state.settings` 是项目主动保存的配置引用。

## 安装与启动（Windows PowerShell）

在项目根目录使用 Python 3.13 虚拟环境。已有 `.venv` 时跳过创建步骤：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
```

`-e` 表示从当前源码运行，修改 Python 文件后不必重装；`[dev]` 同时安装测试依赖。

```powershell
$env:PG_TOKEN = & .\.venv\Scripts\python.exe -c 'import secrets; print(secrets.token_urlsafe(32))'
$env:PG_HOST = '127.0.0.1'
$env:PG_PORT = '8000'
.\.venv\Scripts\python.exe -m pocket_guardian
```

生成命令的结果直接赋给当前终端环境变量，不需要复制到源码或聊天。`token_urlsafe(32)` 使用 32 个随机字节（256 位），编码后的文本约 43 个字符；不同于配置要求的“至少 32 个字符”。这些环境变量只影响当前终端及它启动的子进程，不会自动传到另一个已打开的终端。当前不自动读取 `.env` 文件。

`-m pocket_guardian` 执行包中的 `__main__.py`。在浏览器访问 `http://127.0.0.1:8000/health`，应看到 `{"status":"ok"}`。按 Ctrl+C 结束服务；退出后可在同一终端执行 `Remove-Item Env:PG_TOKEN` 清除本次凭据。

| 配置 | 默认与限制 | 含义 |
| --- | --- | --- |
| `PG_HOST` | 默认且仅允许 `127.0.0.1` | 本机 IPv4 回环地址，不能从其他设备直连 |
| `PG_PORT` | 默认 `8000`，允许 `1`～`65535` | 8000 是项目选择；TCP 端口为 16 位，本项目排除表示自动选端口的 0 |
| `PG_TOKEN` | 必填，至少 32 个字符 | 本地服务访问凭据；长度限制不保证随机性，测试假值不能用于实际服务 |

非法配置会在监听前退出，退出码为 2（项目约定的配置失败）；端口占用由 Uvicorn 报错并非零退出，不终止占用者，也不悄悄换端口。正常停止返回 0。启动外壳禁用代理头信任、Server 响应头与访问日志，避免不必要的来源推断和日志输出。

## HTTP 约定

| 请求/条件 | 状态码与结果 |
| --- | --- |
| `GET /health` | 200，`{"status":"ok"}`；允许匿名，不调用模型 |
| `GET /identity` + 正确 `Authorization: Bearer <本地Token>` | 200，`{"actor_id":"local-owner"}` |
| 受保护接口缺失或错误凭据 | 401，非敏感 detail，`WWW-Authenticate: Bearer` |
| 不可信 Host | 400；框架返回错误文本 |
| 显式提供不可信 Origin | 403，`{"error":"Untrust origin"}` |
| 可信来源下的未知路径 / 不支持的方法 | 404 / 405 |

认证比较请求 Token 与服务端配置 Token，不允许客户端自报身份；它不是模型 API Key，也不代表登录注册系统。SecretStr 只减少常见打印泄露，不是加密存储。错误信息使用隐藏输入的文本形式，不能随意记录包含原始输入的结构化校验错误。

Host 只允许 `127.0.0.1`，当前不接收 `localhost`。Origin 缺失可继续处理；显式提供时只允许 `http://127.0.0.1:<配置端口>`，端口 80 的规范写法省略 `:80`。空字符串、`null`、其他协议/端口或附带路径均拒绝。Host/Origin 是请求声明，不能替代 Token 认证。M03 若增加不同端口的前端，应明确设计来源许可和 CORS，当前没有提前开放。

## 测试与证据

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q --tb=short -p no:cacheprovider
.\.venv\Scripts\python.exe -m pip check
```

2026-11-08，Codex 在 Windows / Python 3.13.0 执行：**96 passed**，无警告；依赖检查通过。其中单元测试 45 项、TestClient 集成测试 39 项、真实 HTTP/命令行测试 12 项。真实服务仅监听 `127.0.0.1`，测试使用临时随机凭据与系统选择的空闲端口，结束后程序化正常关闭并验证端口已释放。命令行错误测试覆盖缺失/短凭据、非法地址/端口和端口占用。没有调用模型，没有重复 M00 实验；未据此宣称手工 Ctrl+C、跨平台或高并发已验证。

本次环境：FastAPI 0.162.0、Starlette 1.10.0、Uvicorn 0.54.0、Pydantic 2.14.3、pydantic-settings 2.16.2、pytest 9.2.0、httpx2 2.16.0。`pyproject.toml` 声明依赖范围而非完整锁定文件；上述结果只证明本次安装组合。

## 学习来源与提交范围

用户在讲解、示例及纠错提示后编写配置、应用工厂、路由、认证和 Origin 判断，并配置 Host 中间件；不能将这些成果全部记为无提示独立开发。Codex 提供依赖配置、导入与样板、启动外壳、测试和本文档，负责实际验收运行。

M00 探针及其学习记录保留在本地，首次 M01 发布只包含本关源码、测试、依赖配置、忽略规则和本说明。原始证据与私人学习记录不随本次上传。首次 Git 同步和用户复盘尚待完成；M01 仍待最终验收，不自动进入 M02。
