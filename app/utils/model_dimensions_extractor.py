"""
가구 치수 이미지 추출기

요청 이미지와 프롬프트를 Gemini로 전송하고 치수(width/depth/height)를 추출합니다.
"""

import base64
import json
import logging
import mimetypes
import os
import re
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

FALLBACK_PROMPT = """Role:
You are a Data Analysis Expert specializing in accurately identifying and extracting dimension data from blueprints and product images.

Task:
Analyze the attached product dimension image and extract the overall Width, Depth, and Height of the product.

Critical rules:
- If a dimension is a range (e.g. 1170~1290), use the maximum value only.
- Convert all values to centimeters.
- Return strict JSON only.

{
  \"dimensions\": {
    \"width\": 0,
    \"depth\": 0,
    \"height\": 0,
    \"unit\": \"cm\"
  }
}
"""


class ModelDimensionsExtractor:
    """Gemini 기반 치수 추출 서비스"""

    def __init__(self, config):
        self.config = config
        self.api_key = config.get("GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.timeout_seconds = int(config.get("DIMENSIONS_GEMINI_TIMEOUT", 45))

        primary_model = config.get("DIMENSIONS_GEMINI_PRIMARY_MODEL") or config.get("GEMINI_PRIMARY_MODEL") or "gemini-2.5-flash"
        fallback_models = config.get("DIMENSIONS_GEMINI_FALLBACK_MODELS") or config.get("GEMINI_FALLBACK_MODELS") or ["gemini-2.5-pro", "gemini-3-flash"]

        self.models = [primary_model] + [m for m in list(fallback_models) if m and m != primary_model]
        self.prompt = self._load_prompt_text(config)

    def extract_dimensions(self, image_url: str) -> Dict[str, Any]:
        """
        이미지에서 치수를 추출합니다.

        Returns:
            {
                "width": float,
                "depth": float,
                "height": float,
                "unit": "cm"
            }
        """
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY가 설정되지 않았습니다")

        image_bytes, mime_type = self._load_image_bytes(image_url)
        response_text = self._call_gemini(prompt=self.prompt, image_bytes=image_bytes, mime_type=mime_type)
        dimensions = self._parse_dimensions_payload(response_text)
        return dimensions

    def _load_prompt_text(self, config) -> str:
        configured_path = config.get("DIMENSIONS_PROMPT_FILE")
        if configured_path:
            candidate = configured_path
        else:
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            candidate = os.path.join(project_root, "가구사이즈이미지추출프롬프트")

        try:
            with open(candidate, "r", encoding="utf-8") as fp:
                prompt = fp.read().strip()
                if prompt:
                    logger.info("치수 추출 프롬프트 로드 완료: %s", candidate)
                    return prompt
        except Exception as exc:
            logger.warning("치수 추출 프롬프트 로드 실패 (%s): %s", candidate, exc)

        logger.warning("기본 프롬프트(FALLBACK_PROMPT) 사용")
        return FALLBACK_PROMPT

    @staticmethod
    def _is_url(source: str) -> bool:
        lowered = str(source or "").strip().lower()
        return lowered.startswith("http://") or lowered.startswith("https://")

    def _resolve_localhost_url_to_file(self, image_url: str) -> Optional[str]:
        try:
            parsed = urlparse(image_url)
        except Exception:
            return None

        host = (parsed.hostname or "").lower()
        if host not in {"localhost", "127.0.0.1"}:
            return None

        filename = os.path.basename(parsed.path or "")
        if not filename:
            return None

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        candidates = [
            os.path.join(project_root, "uploads", filename),
            os.path.join(project_root, "uploads", "images", filename),
            os.path.join(project_root, "uploads", "models", filename),
            os.path.join(project_root, "test_images", filename),
        ]

        for path in candidates:
            if os.path.exists(path):
                return path

        uploads_root = os.path.join(project_root, "uploads")
        if os.path.isdir(uploads_root):
            for root, _dirs, files in os.walk(uploads_root):
                if filename in files:
                    return os.path.join(root, filename)

        return None

    def _load_image_bytes(self, image_url: str) -> Tuple[bytes, str]:
        if not image_url:
            raise ValueError("image_url이 비어 있습니다")

        source = str(image_url).strip()
        if not source:
            raise ValueError("image_url이 비어 있습니다")

        if not self._is_url(source):
            if not os.path.exists(source):
                raise ValueError(f"이미지 파일을 찾을 수 없습니다: {source}")
            return self._read_local_file(source)

        local_candidate = self._resolve_localhost_url_to_file(source)
        if local_candidate:
            return self._read_local_file(local_candidate)

        response = requests.get(source, timeout=15)
        response.raise_for_status()

        content_type = str(response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        mime_type = content_type if content_type.startswith("image/") else ""
        if not mime_type:
            guessed_mime, _ = mimetypes.guess_type(urlparse(source).path or "")
            mime_type = guessed_mime or "image/png"

        return response.content, mime_type

    @staticmethod
    def _read_local_file(path: str) -> Tuple[bytes, str]:
        with open(path, "rb") as fp:
            image_bytes = fp.read()

        guessed_mime, _ = mimetypes.guess_type(path)
        mime_type = guessed_mime or "image/png"
        return image_bytes, mime_type

    def _call_gemini(self, prompt: str, image_bytes: bytes, mime_type: str) -> str:
        if not image_bytes:
            raise ValueError("이미지 바이트가 비어 있습니다")

        encoded_image = base64.b64encode(image_bytes).decode("ascii")

        last_error: Optional[Exception] = None
        for model in self.models:
            try:
                endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                params = {"key": self.api_key}
                payload = {
                    "contents": [
                        {
                            "parts": [
                                {"text": prompt},
                                {
                                    "inline_data": {
                                        "mime_type": mime_type or "image/png",
                                        "data": encoded_image,
                                    }
                                },
                            ]
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.0,
                        "maxOutputTokens": 2048,
                    },
                }

                logger.info("치수 추출 Gemini 호출: model=%s", model)
                response = requests.post(endpoint, params=params, json=payload, timeout=self.timeout_seconds)
                response.raise_for_status()

                body = response.json()
                text = self._extract_text_from_generate_response(body)
                if not text:
                    raise ValueError("Gemini 응답에서 텍스트를 찾을 수 없습니다")

                return text
            except Exception as exc:
                last_error = exc
                logger.warning("치수 추출 Gemini 호출 실패(model=%s): %s", model, exc)
                continue

        raise RuntimeError(f"모든 Gemini 모델 호출 실패: {last_error}")

    @staticmethod
    def _extract_text_from_generate_response(payload: Dict[str, Any]) -> str:
        candidates = payload.get("candidates") or []
        if not candidates:
            prompt_feedback = payload.get("promptFeedback")
            if prompt_feedback:
                raise ValueError(f"Gemini 후보 응답 없음: {prompt_feedback}")
            return ""

        first = candidates[0] or {}
        content = first.get("content") or {}
        parts = content.get("parts") or []

        texts = []
        for part in parts:
            if isinstance(part, dict) and part.get("text"):
                texts.append(str(part.get("text")))

        return "\n".join(texts).strip()

    def _parse_dimensions_payload(self, response_text: str) -> Dict[str, Any]:
        json_blob = self._extract_json_blob(response_text)
        parsed = json.loads(json_blob)

        dimensions = parsed.get("dimensions")
        if not isinstance(dimensions, dict):
            raise ValueError("응답 JSON에 dimensions 객체가 없습니다")

        width = self._coerce_dimension_value(dimensions.get("width"), field_name="width")
        depth = self._coerce_dimension_value(dimensions.get("depth"), field_name="depth")
        height = self._coerce_dimension_value(dimensions.get("height"), field_name="height")

        unit = str(dimensions.get("unit") or "cm").strip().lower()
        width, depth, height, normalized_unit = self._normalize_unit(width, depth, height, unit)

        for field_name, value in (("width", width), ("depth", depth), ("height", height)):
            if value < 0:
                raise ValueError(f"{field_name} 값은 음수일 수 없습니다: {value}")

        return {
            "width": round(width, 3),
            "depth": round(depth, 3),
            "height": round(height, 3),
            "unit": normalized_unit,
        }

    @staticmethod
    def _extract_json_blob(text: str) -> str:
        source = str(text or "").strip()
        if not source:
            raise ValueError("Gemini 응답 텍스트가 비어 있습니다")

        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", source, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            return fenced.group(1)

        start_index = source.find("{")
        if start_index < 0:
            raise ValueError("JSON 시작 문자 '{'를 찾을 수 없습니다")

        brace_count = 0
        in_string = False
        escape = False
        for idx in range(start_index, len(source)):
            ch = source[idx]

            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch == "{":
                brace_count += 1
            elif ch == "}":
                brace_count -= 1
                if brace_count == 0:
                    return source[start_index:idx + 1]

        raise ValueError("완전한 JSON 객체를 추출하지 못했습니다")

    @staticmethod
    def _coerce_dimension_value(value: Any, field_name: str) -> float:
        if isinstance(value, (int, float)):
            return float(value)

        if value is None:
            raise ValueError(f"{field_name} 값이 없습니다")

        text = str(value).strip().lower()
        if not text:
            raise ValueError(f"{field_name} 값이 비어 있습니다")

        if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
            return float(text)

        number_tokens = re.findall(r"\d+(?:\.\d+)?", text)
        if not number_tokens:
            raise ValueError(f"{field_name} 값을 숫자로 해석할 수 없습니다: {value}")

        numbers = [float(token) for token in number_tokens]

        if "~" in text or "to" in text or "-" in text:
            return max(numbers)

        return numbers[0]

    @staticmethod
    def _normalize_unit(width: float, depth: float, height: float, unit: str) -> Tuple[float, float, float, str]:
        normalized_unit = unit.strip().lower()

        if normalized_unit in {"cm", "centimeter", "centimeters"}:
            return width, depth, height, "cm"

        if normalized_unit in {"mm", "millimeter", "millimeters"}:
            return width / 10.0, depth / 10.0, height / 10.0, "cm"

        if normalized_unit in {"m", "meter", "meters"}:
            return width * 100.0, depth * 100.0, height * 100.0, "cm"

        if not normalized_unit:
            return width, depth, height, "cm"

        raise ValueError(f"지원하지 않는 단위입니다: {unit}")
