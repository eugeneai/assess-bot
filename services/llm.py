import json
import logging
from typing import Any

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"


async def call_deepseek(
    prompt: str,
    expect_json: bool = False,
    max_tokens: int = 2000,
) -> tuple[Any, dict[str, int] | None]:
    if not settings.deepseek_api_key:
        logger.warning("DEEPSEEK_API_KEY not set, skipping LLM call")
        return None, None

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                DEEPSEEK_API_URL,
                headers={
                    "Authorization": f"Bearer {settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.deepseek_model,
                    "messages": [
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            data = response.json()

            usage: dict[str, int] | None = data.get("usage")
            content = data["choices"][0]["message"]["content"].strip()

            if expect_json:
                if "```" in content:
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                content = content.strip()
                return json.loads(content), usage

            return content, usage

    except httpx.HTTPError as e:
        logger.error("DeepSeek API HTTP error: %s", e)
        return None, None
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error("DeepSeek API parse error: %s", e)
        return None, None
    except Exception as e:
        logger.error("DeepSeek API error: %s", e)
        return None, None
