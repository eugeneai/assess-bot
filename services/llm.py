import json
import logging
from typing import Any

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"


async def call_deepseek(prompt: str, expect_json: bool = False) -> Any | None:
    if not settings.deepseek_api_key:
        logger.warning("DEEPSEEK_API_KEY not set, skipping LLM call")
        return None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
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
                    "max_tokens": 500,
                },
            )
            response.raise_for_status()
            data = response.json()

            content = data["choices"][0]["message"]["content"].strip()

            if expect_json:
                if "```" in content:
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                content = content.strip()
                return json.loads(content)

            return content

    except httpx.HTTPError as e:
        logger.error("DeepSeek API HTTP error: %s", e)
        return None
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error("DeepSeek API parse error: %s", e)
        return None
    except Exception as e:
        logger.error("DeepSeek API error: %s", e)
        return None
