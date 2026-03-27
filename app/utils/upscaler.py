"""
고정형 이미지 업스케일러 (Fixed Real-ESRGAN x4plus Upscaler)

모든 이미지에 동일한 전략 적용:
- 모델: realesrgan-x4plus (4배 고정)
- 다운샘플: 1024px 제한
- 폴백: 없음 (Real-ESRGAN 필수)

Real-ESRGAN 사용: NCNN Vulkan 독립 실행형 .exe 파일
"""

import os
import time
import logging
import subprocess
import tempfile
from typing import Tuple, Dict, Any, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def _find_realesrgan_exe() -> Optional[str]:
    """Real-ESRGAN NCNN Vulkan .exe 파일 찾기"""
    search_paths = [
        os.path.abspath("realesrgan-ncnn-vulkan.exe"),
        os.path.expanduser("~/realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan.exe"),
        os.path.abspath("Real-ESRGAN/realesrgan-ncnn-vulkan.exe"),
    ]
    
    for path in search_paths:
        if os.path.exists(path):
            logger.info(f"Real-ESRGAN NCNN Vulkan found: {path}")
            return path
    
    return None


def _find_models_dir() -> Optional[str]:
    """Real-ESRGAN 모델 디렉토리 찾기 (로컬 models/)"""
    search_paths = [
        os.path.abspath("models"),
        os.path.abspath("./models"),
        os.path.expanduser("~/models"),
        os.path.abspath("Real-ESRGAN/models"),
    ]
    
    for path in search_paths:
        if os.path.exists(path):
            # .param 파일이 있는지 확인
            try:
                param_files = [f for f in os.listdir(path) if f.endswith('.param')]
                if param_files:
                    logger.info(f"Real-ESRGAN models directory found: {path}")
                    return path
            except Exception:
                pass
    
    return None


REALESRGAN_EXE = _find_realesrgan_exe()
REALESRGAN_MODELS_DIR = _find_models_dir()
REALESRGAN_AVAILABLE = REALESRGAN_EXE is not None and REALESRGAN_MODELS_DIR is not None

if REALESRGAN_EXE:
    logger.info("✓ Real-ESRGAN NCNN Vulkan ready")
else:
    logger.warning("✗ Real-ESRGAN not available")

if REALESRGAN_MODELS_DIR:
    logger.info(f"✓ Models directory: {REALESRGAN_MODELS_DIR}")
else:
    logger.warning("✗ Models directory not found")


class FixedUpscaler:
    """고정형 업스케일러 (realesrgan-x4plus 전용)"""

    def __init__(
        self,
        real_esrgan_exe_path: Optional[str] = None,
        models_dir: Optional[str] = None,
    ):
        """
        Args:
            real_esrgan_exe_path: exe 파일 경로
            models_dir: 모델 디렉토리 경로
        """
        self.real_esrgan_exe_path = real_esrgan_exe_path or REALESRGAN_EXE
        self.models_dir = models_dir or REALESRGAN_MODELS_DIR
        
        if not self.real_esrgan_exe_path:
            logger.error("Real-ESRGAN executable not found!")
        if not self.models_dir:
            logger.error("Real-ESRGAN models directory not found!")

    def upscale(self, input_path: str, output_path: str) -> Dict[str, Any]:
        """
        고정 전략으로 업스케일
        
        Args:
            input_path: 입력 이미지 경로
            output_path: 출력 이미지 경로
            
        Returns:
            메타데이터 딕셔너리
        """
        meta = {
            'success': False,
            'engine': 'real-esrgan-x4plus',
            'strategy': 'fixed-x4plus',
            'original_size': None,
            'upscaled_size': None,
            'scale_factor': 4.0,
            'processing_time_sec': 0.0,
            'output_path': None,
            'error': None
        }
        
        start_time = time.time()
        
        try:
            # 입력 이미지 정보 수집
            if not os.path.exists(input_path):
                meta['error'] = f"Input image not found: {input_path}"
                logger.error(meta['error'])
                return meta
            
            img = cv2.imread(input_path)
            if img is None:
                meta['error'] = f"Cannot read image: {input_path}"
                logger.error(meta['error'])
                return meta
            
            height, width = img.shape[:2]
            meta['original_size'] = (width, height)
            
            # Real-ESRGAN 업스케일
            if not self._upscale_with_real_esrgan(input_path, output_path):
                meta['error'] = "Real-ESRGAN upscaling failed"
                logger.error(meta['error'])
                return meta
            
            # 결과 이미지 정보 수집
            result_img = cv2.imread(output_path)
            if result_img is None:
                meta['error'] = f"Cannot read upscaled image: {output_path}"
                logger.error(meta['error'])
                return meta
            
            result_height, result_width = result_img.shape[:2]
            
            # 1024px 제한 - 다운샘플
            max_dim = max(result_width, result_height)
            if max_dim > 1024:
                logger.info(f"Downsampling from {max_dim}px to 1024px")
                scale_ratio = 1024.0 / max_dim
                new_width = int(result_width * scale_ratio)
                new_height = int(result_height * scale_ratio)
                result_img = cv2.resize(
                    result_img,
                    (new_width, new_height),
                    interpolation=cv2.INTER_AREA
                )
                cv2.imwrite(output_path, result_img)
                result_height, result_width = result_img.shape[:2]
            
            meta['upscaled_size'] = (result_width, result_height)
            meta['output_path'] = output_path
            meta['success'] = True
            meta['processing_time_sec'] = time.time() - start_time
            
            logger.info(
                f"Upscaling successful: {meta['original_size']} → {meta['upscaled_size']} "
                f"({meta['processing_time_sec']:.2f}s)"
            )
            
        except Exception as e:
            meta['error'] = str(e)
            logger.error(f"Upscaling error: {e}", exc_info=True)
        
        return meta

    def _upscale_with_real_esrgan(self, input_path: str, output_path: str) -> bool:
        """Real-ESRGAN NCNN Vulkan exe로 업스케일"""
        if not self.real_esrgan_exe_path or not os.path.exists(self.real_esrgan_exe_path):
            logger.error(f"Real-ESRGAN exe not found: {self.real_esrgan_exe_path}")
            return False
        
        if not self.models_dir or not os.path.exists(self.models_dir):
            logger.error(f"Models directory not found: {self.models_dir}")
            return False
        
        try:
            # 모델은 항상 realesrgan-x4plus 고정
            model_name = "realesrgan-x4plus"
            
            cmd = [
                self.real_esrgan_exe_path,
                "-i", input_path,
                "-o", output_path,
                "-n", model_name,
                "-s", "4",
            ]
            
            logger.info(f"Running Real-ESRGAN with model: {model_name}")
            logger.debug(f"Command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            
            logger.debug(f"Return code: {result.returncode}")
            
            if result.returncode == 0 and os.path.exists(output_path):
                logger.info(f"✓ Real-ESRGAN succeeded: {output_path}")
                return True
            else:
                logger.error(f"✗ Real-ESRGAN failed (code={result.returncode})")
                if result.stderr:
                    logger.error(f"Stderr: {result.stderr[:200]}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("Real-ESRGAN execution timeout (300s)")
            return False
        except Exception as e:
            logger.error(f"Real-ESRGAN execution error: {type(e).__name__}: {e}")
            return False


def create_upscaler() -> FixedUpscaler:
    """업스케일러 생성 헬퍼 함수"""
    return FixedUpscaler()
