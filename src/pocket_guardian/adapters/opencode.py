"""M02 OpenCode HTTP adapter. Core implementation belongs to the learner."""
from datetime import datetime, timezone
from pathlib import Path

import httpx
import asyncio
import json
from typing import TypedDict

from pocket_guardian.contracts.execution import SuccessResult, FailureResult, UnknownResult


class HealthStatus(TypedDict):
    healthy: bool
    version:str
class OpenCodeInvalidResponseError(Exception):
    pass
class ResponseTooLargeError(ValueError):
    pass
class OpenCodeReportedError(Exception):
    def __init__(self, message: str, reported_model: str | None):
        super().__init__(message)
        self.reported_model = reported_model


class OpenCodeAdapter:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        workspace: Path | None = None,
        total_timeout_seconds: float = 60.0,
        max_response_bytes: int = 1024 * 1024,
    ):
        """Bind this adapter to a directory selected by the server, when supplied."""
        if workspace is not None:
            if not workspace.is_absolute():
                raise ValueError("OpenCode workspace must be an absolute path")
            workspace = workspace.resolve(strict=True)
            if not workspace.is_dir():
                raise ValueError("OpenCode workspace must be a directory")
        self.client = client
        self._workspace = workspace
        self.total_timeout_seconds = total_timeout_seconds
        self.max_response_bytes = max_response_bytes

    async def _post_json_limited(self, path, payload):
        params = {"directory": str(self._workspace)} if self._workspace is not None else None
        async with self.client.stream("POST", path, json=payload, params=params) as response:
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(body) + len(chunk) > self.max_response_bytes:
                    raise ResponseTooLargeError()
                body.extend(chunk)

        try:
            return json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise OpenCodeInvalidResponseError("OpenCode 返回的内容无法解析为 JSON") from exc

    async def check_health(self)->HealthStatus:
        response= await self.client.get("/global/health")
        response.raise_for_status()
        dic=response.json()
        if not isinstance(dic,dict):
            raise ValueError
        version = dic.get("version")
        healthy = dic.get("healthy")
        if not isinstance(healthy,bool):
            raise ValueError
        if not isinstance(version,str) or not version.strip():
            raise ValueError

        return dic
    async def _execute_once(
            self,text:str,provider:str,model:str
    )->SuccessResult:
        #第一步创建会话
        session_payload={
            "permission":[
                {"permission": "*","pattern":"*","action":"deny"}
            ]
        }
        data= await self._post_json_limited("/session",session_payload)
        if not isinstance(data,dict):
            raise OpenCodeInvalidResponseError("OpemCode响应会话必须是字典")
        id=data.get("id")
        if not isinstance(id,str):
            raise OpenCodeInvalidResponseError("OpemCode会话ID必须是字符串")
        if not id.strip():
            raise OpenCodeInvalidResponseError("OpemCodeID会话ID不能为空")

        #第二步 向会话提交消息
        message_payload={
     "model": {
             "providerID": provider,
             "modelID": model,
              },
     "parts": [
             {"type": "text", "text": text}
        ],
                         }
        # 第三步判断回复是否可靠完成 根据OpenCode返回的数据

        reply_payload = await self._post_json_limited(
            f"/session/{id}/message", message_payload
        )
        if not isinstance(reply_payload, dict):
            raise OpenCodeInvalidResponseError("OpenCode 回复应是一个字典")

        info = reply_payload.get("info")
        if not isinstance(info, dict) or info.get("role") != "assistant":
            raise OpenCodeInvalidResponseError("OpenCode 回复缺少有效的助手消息")

        reported_model = info.get("modelID")
        if not isinstance(reported_model, str) or not reported_model.strip():
            reported_model = None

        error = info.get("error")
        if error is not None:
            name = error.get("name") if isinstance(error, dict) else None
            details = error.get("data") if isinstance(error, dict) else None
            status = details.get("statusCode") if isinstance(details, dict) else None
            # Map known evidence to user-facing text without leaking provider diagnostics.
            if name == "ProviderAuthError" or status == 401:
                message = "模型服务认证失败，请检查提供商凭据"
            elif status == 402:
                message = "模型服务要求付费，请检查账户余额或账单"
            elif status == 403:
                message = "模型服务拒绝访问，请检查模型权限"
            elif status == 429:
                message = "模型服务限制了请求，请检查速率限制或额度"
            elif type(status) is int and 500 <= status < 600:
                message = f"模型服务返回服务器错误（HTTP {status}）"
            else:
                message = "OpenCode 报告任务执行失败，未能确认更具体的原因"
            raise OpenCodeReportedError(message, reported_model)

        parts = reply_payload.get("parts")
        if not isinstance(parts, list):
            raise OpenCodeInvalidResponseError("OpenCode 回复缺少有效的 parts 列表")
        time_dict = info.get("time")
        if not isinstance(time_dict, dict):
            raise OpenCodeInvalidResponseError("OpenCode 回复缺少时间信息")
        time_completed = time_dict.get("completed")
        finished = info.get("finish")
        if finished!="stop":
            raise OpenCodeInvalidResponseError("OpenCode返回数据的finished不为stop")
        if type(time_completed) is not int or time_completed <= 0:
            raise OpenCodeInvalidResponseError("OpenCode返回数据的time_completed不大于0的整数")

        #提取parts回答,来自opencode
        answer=[]
        for chunk in parts:
            if not isinstance(chunk,dict):
                raise OpenCodeInvalidResponseError("chunk不为字典")
            if chunk.get("type") != "text" or chunk.get("ignored"):
                continue
            part_text=chunk.get("text")
            if not isinstance(part_text,str):
                raise  OpenCodeInvalidResponseError("chunk片段字段缺失")
            if not  part_text.strip() :
                continue

            answer.append(part_text)
        answer="\n".join(answer)
        if answer=="":
            raise OpenCodeInvalidResponseError("没有提取到有效回答")
        return SuccessResult(
            adapter="opencode",
            provider=provider,
            requested_model=model,
            reported_model=reported_model,
            text=answer,
            finished_at=datetime.now(timezone.utc),

        )

    async def execute(
                      self, text: str, provider: str, model: str
        )->SuccessResult|FailureResult|UnknownResult:

        try:
            async with asyncio.timeout(self.total_timeout_seconds):
                return await self._execute_once(text, provider, model)
        except OpenCodeReportedError as exc:
            return FailureResult(
                adapter="opencode",
                provider=provider,
                requested_model=model,
                reported_model=exc.reported_model,
                error_code="opencode_reported_error",
                message=str(exc),
                finished_at=datetime.now(timezone.utc),
            )
        except OpenCodeInvalidResponseError as exc:
            error_code, message = "opencode_invalid_response", str(exc)
        except TimeoutError:
            error_code = "opencode_deadline_exceeded"
            message = "任务超过总期限，执行状态待核实"
        except ResponseTooLargeError:
            error_code = "opencode_response_too_large"
            message = "OpenCode 响应超过大小上限，执行状态待核实"
        except (httpx.ConnectError, httpx.ConnectTimeout):
            return FailureResult(
                adapter="opencode",
                provider=provider,
                requested_model=model,
                error_code="opencode_connection_failed",
                message="无法连接到 OpenCode",
                finished_at=datetime.now(timezone.utc),
            )
        except httpx.ReadTimeout:
            error_code = "opencode_read_timeout"
            message = "等待 OpenCode 响应超时，执行状态待核实"
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            error_code = f"opencode_http_{status_code}"
            if 400 <= status_code < 500 and status_code != 408:
                messages = {
                    401: "OpenCode 认证失败",
                    402: "OpenCode 返回付费要求（HTTP 402）",
                    403: "OpenCode 拒绝访问",
                    429: "OpenCode 限制了请求",
                }
                return FailureResult(
                    adapter="opencode",
                    provider=provider,
                    requested_model=model,
                    error_code="opencode_authentication_failed" if status_code == 401 else error_code,
                    message=messages.get(status_code, f"OpenCode 拒绝请求（HTTP {status_code}）"),
                    finished_at=datetime.now(timezone.utc),
                )
            message = f"OpenCode 返回 HTTP {status_code}，执行状态待核实"
        except httpx.RequestError:
            error_code = "opencode_request_error"
            message = "与 OpenCode 通信中断，执行状态待核实"

        return UnknownResult(
            adapter="opencode",
            provider=provider,
            requested_model=model,
            error_code=error_code,
            message=message,
            observed_at=datetime.now(timezone.utc),
        )
