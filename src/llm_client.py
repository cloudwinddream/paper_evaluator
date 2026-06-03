"""
多 Provider LLM 调用客户端
支持按优先级依次尝试多个 API 提供商，遇限流/鉴权/token不足自动切换
"""

import json
from typing import Optional

import requests


def _is_token_limit_error(response: requests.Response) -> bool:
    """判断是否是 token 超限错误"""
    if response.status_code != 400:
        return False
    try:
        data = response.json()
        msg = json.dumps(data).lower()
        keywords = [
            "maximum context length", "context_length_exceeded",
            "too many tokens", "token limit", "max_tokens",
            "maximum prompt length", "input too long",
            "token capacity", "context window",
        ]
        return any(k in msg for k in keywords)
    except Exception:
        return False


class LLMClient:
    """支持多 Provider 自动切换的 LLM 调用客户端"""

    def __init__(self, providers: list[dict]):
        """
        providers: [{"base_url": "...", "api_key": "...", "model": "..."}, ...]
        按优先级排列，第一个为首选
        """
        self.providers = providers
        self.current_idx = 0

    @property
    def current(self) -> dict:
        return self.providers[self.current_idx]

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        max_retries_per_provider: int = 3,
    ) -> str:
        """调用 LLM，遇故障自动切换 provider"""
        last_error = ""

        for attempt in range(len(self.providers) * max_retries_per_provider):
            provider = self.providers[self.current_idx]
            base_url = provider["base_url"].rstrip("/")
            url = f"{base_url}/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {provider['api_key']}",
            }
            payload = {
                "model": provider["model"],
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=180)
            except requests.exceptions.Timeout:
                last_error = f"[{provider['model']}] 请求超时"
                print(f"  \u26a0 {last_error}，切换下一个...")
                self._switch_provider()
                continue
            except requests.exceptions.ConnectionError:
                last_error = f"[{provider['model']}] 连接失败"
                print(f"  \u26a0 {last_error}，切换下一个...")
                self._switch_provider()
                continue
            except requests.exceptions.RequestException as e:
                last_error = f"[{provider['model']}] 网络错误: {e}"
                print(f"  \u26a0 {last_error}，切换下一个...")
                self._switch_provider()
                continue

            if resp.status_code == 429:
                last_error = f"[{provider['model']}] 触发限流"
                print(f"  \u26a0 {last_error}，切换下一个...")
                self._switch_provider()
                continue

            if resp.status_code == 401:
                last_error = f"[{provider['model']}] 鉴权失败（API Key 无效）"
                print(f"  \u26a0 {last_error}，切换下一个...")
                self._switch_provider()
                continue

            if _is_token_limit_error(resp):
                last_error = f"[{provider['model']}] Token 超限"
                print(f"  \u26a0 {last_error}，切换下一个...")
                self._switch_provider()
                continue

            if resp.status_code != 200:
                try:
                    detail = resp.json()
                except Exception:
                    detail = resp.text[:200]
                last_error = f"[{provider['model']}] HTTP {resp.status_code}: {detail}"
                print(f"  \u26a0 {last_error}，切换下一个...")
                self._switch_provider()
                continue

            try:
                return resp.json()["choices"][0]["message"]["content"]
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                last_error = f"[{provider['model']}] 响应解析失败: {e}"
                print(f"  \u26a0 {last_error}，切换下一个...")
                self._switch_provider()
                continue

        raise RuntimeError(f"所有 Provider 均失败，最后错误: {last_error}")

    def _switch_provider(self):
        """切换到下一个 provider"""
        self.current_idx = (self.current_idx + 1) % len(self.providers)
        p = self.providers[self.current_idx]
        print(f"  \u2192 切换到 {p['model']} ({p['base_url']})")
