"""Thin JSON-mode client for any OpenAI-compatible provider (Gemini, Groq, OpenRouter, ...)."""
import json
import re
import time

from openai import APIStatusError, BadRequestError, OpenAI, RateLimitError

from . import config


class LLMError(Exception):
    pass


_client = None


def client() -> OpenAI:
    global _client
    if not config.LLM_API_KEY:
        raise LLMError("کلید مدل زبانی (LLM_API_KEY) تنظیم نشده است.")
    if _client is None:
        _client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY, timeout=120, max_retries=1)
    return _client


def parse_json(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        a, b = text.find("{"), text.rfind("}")
        if a >= 0 and b > a:
            return json.loads(text[a:b + 1])
        raise


def chat_json(system: str, user: str, temperature: float = 0.2) -> dict:
    """Ask for one JSON object. Busy/rate-limited models fall back to the next model in config.LLM_MODELS."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    models = list(config.LLM_MODELS)
    use_json_mode = True
    last_err = None
    for attempt in range(7):
        model = models[0]
        try:
            kwargs = {"model": model, "messages": messages, "temperature": temperature}
            if use_json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            resp = client().chat.completions.create(**kwargs)
            text = resp.choices[0].message.content or ""
            try:
                return parse_json(text)
            except (json.JSONDecodeError, ValueError) as e:
                last_err = e
                messages = messages + [
                    {"role": "assistant", "content": text[:4000]},
                    {"role": "user", "content": "Your previous reply was not valid JSON. Reply again with ONLY one valid JSON object."},
                ]
        except BadRequestError as e:
            last_err = e
            if use_json_mode:  # some providers/models reject response_format
                use_json_mode = False
                continue
            raise LLMError(f"درخواست به مدل زبانی رد شد: {e}") from e
        except (RateLimitError, APIStatusError) as e:
            last_err = e
            status = getattr(e, "status_code", 429)
            if status not in (404, 429) and status < 500:
                raise LLMError(f"خطای سرویس مدل زبانی ({status})") from e
            if len(models) > 1:
                models.append(models.pop(0))  # rotate to the next model, keep this one as a last resort
                print(f"[llm] {model} -> {status}; trying {models[0]}")
                time.sleep(1)
            else:
                time.sleep(4 * (attempt + 1))
        except Exception as e:
            last_err = e
            time.sleep(2)
    raise LLMError(f"پاسخ معتبری از مدل زبانی دریافت نشد: {str(last_err)[:200]}")
