"""
Unified LLM client for the Query Engine, with retry support and smart response parsing.
Compatible with OpenAI, Gemini, v1, and other API formats.
"""

import os
from datetime import datetime
from typing import Any, Dict, Optional, Generator
from loguru import logger

# OpenAI SDK
from openai import OpenAI

# 引入项目配置
try:
    from ..utils.config import LLM_CONFIG
except ImportError:
    from utils.config import LLM_CONFIG


def with_retry(config=None):
    def decorator(func):
        return func
    return decorator


LLM_RETRY_CONFIG = None


class LLMClient:
    """
    Unified LLM client for multiple API formats.
    Users provide API key, model name, base URL optionally.
    Response parsing is fully automated.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None, base_url: Optional[str] = None, **kwargs):
        self.api_key = api_key or LLM_CONFIG.get("api_key") or os.getenv("LLM_API_KEY")
        self.model_name = model_name or LLM_CONFIG.get("model_name") or os.getenv("LLM_MODEL_NAME")
        self.base_url = base_url or LLM_CONFIG.get("base_url") or os.getenv("LLM_API_BASE")
        timeout_default = LLM_CONFIG.get("timeout") or os.getenv("LLM_REQUEST_TIMEOUT") or 1800

        try:
            self.timeout = float(timeout_default)
        except ValueError:
            self.timeout = 1800.0

        if not self.api_key:
            raise ValueError("LLM API key is required.")
        if not self.model_name:
            raise ValueError("LLM model name is required.")

        client_kwargs = {"api_key": self.api_key, "max_retries": 0}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        self.client = OpenAI(**client_kwargs)

    # ----------------------- 🔥 新增：时间前缀 -----------------------
    def _prepend_current_time(self, text: str) -> str:
        """给 prompt 自动加当前时间，提高语境一致性"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"[当前时间: {now}]\n{text}"

    # ----------------------- 🔥 通用调用 -----------------------
    @with_retry(LLM_RETRY_CONFIG)
    def invoke(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        user_prompt = self._prepend_current_time(user_prompt)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        allowed_keys = {"temperature", "top_p", "presence_penalty", "frequency_penalty", "stream"}
        extra_params = {k: v for k, v in kwargs.items() if k in allowed_keys and v is not None}
        
        # 处理json_mode参数
        json_mode = kwargs.pop("json_mode", False)
        if json_mode:
            # 使用response_format参数而不是json_mode
            extra_params["response_format"] = {"type": "json_object"}

        timeout = kwargs.pop("timeout", self.timeout)

        # 记录LLM请求详细信息
        logger.info(f"[LLM Request] 调用模型: {self.model_name}")
        logger.info(f"[LLM Request] 系统提示词长度: {len(system_prompt)} 字符")
        logger.info(f"[LLM Request] 用户提示词长度: {len(user_prompt)} 字符")
        logger.info(f"[LLM Request] 参数: temperature={extra_params.get('temperature', 'default')}, json_mode={json_mode}")

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            timeout=timeout,
            **extra_params,
        )

        # OpenAI SDK: response.choices[0].message.content
        try:
            raw_content = response.choices[0].message.content
            logger.info(f"[LLM Response] 成功获取响应，长度: {len(raw_content)} 字符")
            logger.info(f"[LLM Response] 完整响应内容: {raw_content}")
        except Exception as e:
            logger.error(f"[LLM Response] 获取响应失败: {str(e)}")
            raw_content = response

        parsed_content = self.parse_model_response(raw_content)
        return parsed_content

    # ----------------------- 🔥 流式调用 -----------------------
    def stream_invoke(self, system_prompt: str, user_prompt: str, **kwargs) -> Generator[str, None, None]:
        user_prompt = self._prepend_current_time(user_prompt)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        extra_params = {k: v for k, v in kwargs.items() if k in {"temperature", "top_p", "presence_penalty", "frequency_penalty"}}
        extra_params["stream"] = True

        timeout = kwargs.pop("timeout", self.timeout)

        try:
            stream = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                timeout=timeout,
                **extra_params,
            )

            for chunk in stream:
                if hasattr(chunk, "choices") and chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta and getattr(delta, "content", None):
                        yield delta.content
        except Exception as e:
            logger.error(f"LLM stream request failed: {e}")
            raise e

    def stream_invoke_to_string(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        byte_chunks = []
        for chunk in self.stream_invoke(system_prompt, user_prompt, **kwargs):
            byte_chunks.append(chunk.encode("utf-8"))
        if byte_chunks:
            return self.parse_model_response(b"".join(byte_chunks).decode("utf-8", errors="replace"))
        return ""

    # ----------------------- 🔥 更强的模型解析 -----------------------
    @staticmethod
    def parse_model_response(resp: Any) -> str:
        """智能解析各种大模型格式"""

        if resp is None:
            return ""

        # string
        if isinstance(resp, str):
            return resp

        # dict 格式
        if isinstance(resp, dict):
            # OpenAI
            if "choices" in resp:
                try:
                    return resp["choices"][0]["message"]["content"]
                except:
                    pass

            # Gemini
            if "candidates" in resp:
                try:
                    parts = resp["candidates"][0]["content"]
                    return "".join([p.get("text", "") for p in parts])
                except:
                    pass

            if "output_text" in resp:
                return resp["output_text"]

            return str(resp)

        # openai.ChatCompletionObject
        if hasattr(resp, "choices"):
            try:
                return resp.choices[0].message.content
            except:
                pass

        # openai.ChatCompletionMessage
        if hasattr(resp, "content"):
            return resp.content

        return str(resp)
