"""
Unified LLM client for the Query Engine, with retry support and smart response parsing.
Compatible with OpenAI, Gemini, v1, and other API formats.
"""

import os
import sys
from datetime import datetime
from typing import Any, Dict, Optional, Generator
from loguru import logger

# OpenAI SDK
from openai import OpenAI

# 引入项目配置
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
utils_dir = os.path.join(project_root, "utils")
if utils_dir not in sys.path:
    sys.path.append(utils_dir)

try:
    from retry_helper import with_retry, LLM_RETRY_CONFIG
except ImportError:
    def with_retry(config=None):
        def decorator(func):
            return func
        return decorator
    LLM_RETRY_CONFIG = None

try:
    from utils.config import LLM_CONFIG
except ImportError:
    LLM_CONFIG = {}


class LLMClient:
    """
    Unified LLM client for multiple API formats.
    Users provide API key, model name, base URL optionally.
    Response parsing is fully automated.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None, base_url: Optional[str] = None, **kwargs):
        # 从 config 或环境变量读取默认值
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

        # OpenAI-compatible client
        client_kwargs: Dict[str, Any] = {"api_key": self.api_key, "max_retries": 0}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        self.client = OpenAI(**client_kwargs)

        # 保留 provider 信息
        self.provider = self.model_name

    @with_retry(LLM_RETRY_CONFIG)
    def invoke(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        """
        标准调用 LLM，返回解析后的文本。
        """
        user_prompt = self._prepend_current_time(user_prompt)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        allowed_keys = {"temperature", "top_p", "presence_penalty", "frequency_penalty", "stream"}
        extra_params = {k: v for k, v in kwargs.items() if k in allowed_keys and v is not None}
        timeout = kwargs.pop("timeout", self.timeout)

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            timeout=timeout,
            **extra_params,
        )

        # 智能解析返回数据
        if hasattr(response, "choices") and response.choices:
            content = getattr(response.choices[0], "message", {}).get("content", None)
            return self.parse_response(content)
        return self.parse_response(response)

    def stream_invoke(self, system_prompt: str, user_prompt: str, **kwargs) -> Generator[str, None, None]:
        """
        流式调用 LLM，逐步返回响应内容。
        """
        user_prompt = self._prepend_current_time(user_prompt)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        allowed_keys = {"temperature", "top_p", "presence_penalty", "frequency_penalty"}
        extra_params = {k: v for k, v in kwargs.items() if k in allowed_keys and v is not None}
        extra_params["stream"] = True
        timeout = kwargs.pop("timeout", self.timeout)

        try:
            stream = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                timeout=timeout,
                **extra_params
            )

            for chunk in stream:
                if hasattr(chunk, "choices") and chunk.choices:
                    delta = getattr(chunk.choices[0], "delta", None)
                    if delta and getattr(delta, "content", None):
                        yield delta.content
        except Exception as e:
            logger.error(f"LLM stream request failed: {e}")
            raise e

    @with_retry(LLM_RETRY_CONFIG)
    def stream_invoke_to_string(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        """
        流式调用并拼接为完整字符串，避免多字节截断。
        """
        byte_chunks = []
        for chunk in self.stream_invoke(system_prompt, user_prompt, **kwargs):
            byte_chunks.append(chunk.encode("utf-8"))
        if byte_chunks:
            return self.parse_response(b"".join(byte_chunks).decode("utf-8", errors="replace"))
        return ""

    @staticmethod
    def parse_response(raw_response: Any) -> str:
        """
        智能解析 LLM 返回数据，兼容各种格式。
        """
        if raw_response is None:
            return ""
        if isinstance(raw_response, str):
            return raw_response.strip()
        if isinstance(raw_response, dict):
            # 尝试解析 choices -> message -> content
            if "choices" in raw_response:
                texts = []
                for choice in raw_response["choices"]:
                    msg = choice.get("message", {})
                    content = msg.get("content") or choice.get("text")
                    if content:
                        texts.append(str(content))
                return "\n".join(texts).strip()
            return "\n".join(str(v) for v in raw_response.values()).strip()
        if isinstance(raw_response, list):
            return "\n".join(str(item) for item in raw_response).strip()
        return str(raw_response).strip()

    @staticmethod
    def _prepend_current_time(user_prompt: Optional[str]) -> str:
        current_time = datetime.now().strftime("%Y年%m月%d日%H时%M分")
        time_prefix = f"今天的实际时间是{current_time}"
        return f"{time_prefix}\n{user_prompt}" if user_prompt else time_prefix

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model_name,
            "api_base": self.base_url or "default",
        }
