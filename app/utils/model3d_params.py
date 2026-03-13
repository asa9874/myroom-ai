"""
3D 모델 생성 파라미터 관리 모듈

모델 생성에 필요한 파라미터를 JSON 파일에서 읽고/검증/저장합니다.
GUI와 서버가 동일한 파일을 공유하여 파라미터를 일관되게 관리합니다.
"""

import json
import os
from threading import Lock
from typing import Any, Dict, Optional


DEFAULT_MODEL3D_PARAMS: Dict[str, Any] = {
    "api": {
        "base_url": "http://127.0.0.1:7960"
    },
    "quality_thresholds": {
        "minimum": 50,
        "standard": 70,
        "premium": 80
    },
    "generation_defaults": {
        "seed": 42,
        "ss_guidance_strength": 7.5,
        "ss_sampling_steps": 20,
        "slat_guidance_strength": 7.5,
        "slat_sampling_steps": 20,
        "mesh_simplify_ratio": 0.85,
        "texture_size": 512,
        "output_format": "glb"
    }
}


def _deep_copy(data: Dict[str, Any]) -> Dict[str, Any]:
    return json.loads(json.dumps(data))


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = _deep_copy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_default_parameter_file_path() -> str:
    env_path = os.environ.get("MODEL3D_PARAMS_FILE")
    if env_path:
        return os.path.abspath(env_path)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(project_root, "config", "model3d_params.json")


class Model3DParameterManager:
    """3D 모델 생성 파라미터 JSON 파일 관리자"""

    _lock = Lock()

    def __init__(self, parameter_file_path: Optional[str] = None):
        self.parameter_file_path = parameter_file_path or get_default_parameter_file_path()
        self._ensure_parameter_file()

    def _ensure_parameter_file(self) -> None:
        os.makedirs(os.path.dirname(self.parameter_file_path), exist_ok=True)
        if not os.path.exists(self.parameter_file_path):
            self.save(_deep_copy(DEFAULT_MODEL3D_PARAMS))

    def load(self) -> Dict[str, Any]:
        with self._lock:
            try:
                with open(self.parameter_file_path, "r", encoding="utf-8") as file:
                    loaded = json.load(file)
            except (json.JSONDecodeError, OSError):
                loaded = {}
            merged = _deep_merge(DEFAULT_MODEL3D_PARAMS, loaded)
            self.sanitize(merged)
            return merged

    def save(self, params: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            merged = _deep_merge(DEFAULT_MODEL3D_PARAMS, params or {})
            self.sanitize(merged)
            with open(self.parameter_file_path, "w", encoding="utf-8") as file:
                json.dump(merged, file, ensure_ascii=False, indent=2)
            return merged

    def update(self, patch_params: Dict[str, Any]) -> Dict[str, Any]:
        current = self.load()
        merged = _deep_merge(current, patch_params or {})
        return self.save(merged)

    def get_api_base_url(self) -> str:
        return self.load().get("api", {}).get("base_url", DEFAULT_MODEL3D_PARAMS["api"]["base_url"])

    def get_quality_thresholds(self) -> Dict[str, int]:
        return self.load().get("quality_thresholds", _deep_copy(DEFAULT_MODEL3D_PARAMS["quality_thresholds"]))

    def get_generation_defaults(self) -> Dict[str, Any]:
        return self.load().get("generation_defaults", _deep_copy(DEFAULT_MODEL3D_PARAMS["generation_defaults"]))

    @staticmethod
    def sanitize(params: Dict[str, Any]) -> None:
        thresholds = params.setdefault("quality_thresholds", {})
        minimum = int(thresholds.get("minimum", 50))
        standard = int(thresholds.get("standard", 70))
        premium = int(thresholds.get("premium", 80))

        minimum = max(0, min(minimum, 100))
        standard = max(minimum, min(standard, 100))
        premium = max(standard, min(premium, 100))

        thresholds["minimum"] = minimum
        thresholds["standard"] = standard
        thresholds["premium"] = premium

        defaults = params.setdefault("generation_defaults", {})
        defaults["seed"] = int(defaults.get("seed", 42))
        defaults["ss_guidance_strength"] = float(defaults.get("ss_guidance_strength", 7.5))
        defaults["ss_sampling_steps"] = int(defaults.get("ss_sampling_steps", 20))
        defaults["slat_guidance_strength"] = float(defaults.get("slat_guidance_strength", 7.5))
        defaults["slat_sampling_steps"] = int(defaults.get("slat_sampling_steps", 20))
        defaults["mesh_simplify_ratio"] = float(defaults.get("mesh_simplify_ratio", 0.85))
        defaults["texture_size"] = int(defaults.get("texture_size", 512))
        defaults["output_format"] = str(defaults.get("output_format", "glb"))

        defaults["ss_sampling_steps"] = max(1, defaults["ss_sampling_steps"])
        defaults["slat_sampling_steps"] = max(1, defaults["slat_sampling_steps"])
        defaults["mesh_simplify_ratio"] = max(0.1, min(defaults["mesh_simplify_ratio"], 1.0))
        defaults["texture_size"] = max(64, defaults["texture_size"])

        api = params.setdefault("api", {})
        api_base_url = str(api.get("base_url", "")).strip()
        api["base_url"] = api_base_url or DEFAULT_MODEL3D_PARAMS["api"]["base_url"]


class RuntimeModel3DParameterStore:
    """서버 프로세스 내 런타임 파라미터 저장소 (파일 직접 수정 없이 즉시 반영)"""

    _instance = None
    _instance_lock = Lock()

    def __new__(cls, parameter_manager: Optional[Model3DParameterManager] = None):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self, parameter_manager: Optional[Model3DParameterManager] = None):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._lock = Lock()
        self.parameter_manager = parameter_manager or Model3DParameterManager()
        self._runtime_params = self.parameter_manager.load()

    def get_params(self) -> Dict[str, Any]:
        with self._lock:
            return _deep_copy(self._runtime_params)

    def apply_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            merged = _deep_merge(DEFAULT_MODEL3D_PARAMS, params or {})
            Model3DParameterManager.sanitize(merged)
            self._runtime_params = merged
            return _deep_copy(self._runtime_params)

    def patch_params(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            merged = _deep_merge(self._runtime_params, patch or {})
            Model3DParameterManager.sanitize(merged)
            self._runtime_params = merged
            return _deep_copy(self._runtime_params)

    def reload_from_file(self) -> Dict[str, Any]:
        with self._lock:
            self._runtime_params = self.parameter_manager.load()
            return _deep_copy(self._runtime_params)

    def persist_to_file(self) -> Dict[str, Any]:
        with self._lock:
            saved = self.parameter_manager.save(self._runtime_params)
            self._runtime_params = saved
            return _deep_copy(self._runtime_params)
