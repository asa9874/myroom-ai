"""
3D 모델 생성 유틸리티

이미지를 3D 모델로 변환하는 AI API와 통신하는 모듈입니다.
"""

import base64
import logging
import os
import requests
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# 3D 모델 생성 API 설정
API_BASE_URL = "http://127.0.0.1:7960"


class Model3DGenerator:
    """
    3D 모델 생성을 담당하는 클래스
    
    이미지를 입력받아 AI API를 통해 3D 모델(.glb)을 생성합니다.
    """
    
    def __init__(self, api_base_url: str = API_BASE_URL):
        """
        3D 모델 생성기 초기화
        
        Args:
            api_base_url: 3D 모델 생성 API의 기본 URL
        """
        self.api_base_url = api_base_url
    
    def image_to_base64(self, image_path: str) -> str:
        """
        이미지 파일을 base64 문자열로 변환
        
        Args:
            image_path: 이미지 파일 경로
            
        Returns:
            base64로 인코딩된 이미지 문자열
            
        Raises:
            FileNotFoundError: 이미지 파일을 찾을 수 없는 경우
            Exception: 인코딩 중 오류가 발생한 경우
        """
        try:
            with open(image_path, 'rb') as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            logger.info(f"이미지 base64 인코딩 완료: {image_path}")
            return encoded_string
        except FileNotFoundError:
            logger.error(f"이미지 파일을 찾을 수 없음: {image_path}")
            raise
        except Exception as e:
            logger.error(f"이미지 인코딩 실패: {str(e)}")
            raise
    
    def generate_3d_model(
        self,
        image_path: str,
        output_dir: str,
        member_id: int,
        seed: int = 42,
        ss_guidance_strength: float = 7.5,
        ss_sampling_steps: int = 30,
        slat_guidance_strength: float = 7.5,
        slat_sampling_steps: int = 30,
        mesh_simplify_ratio: float = 0.95,
        texture_size: int = 1024
    ) -> str:
        """
        실제 AI API를 사용하여 3D 모델 생성
        
        Args:
            image_path: 입력 이미지 경로
            output_dir: 생성된 모델을 저장할 디렉토리
            member_id: 사용자 ID (파일명에 사용)
            seed: 랜덤 시드 (기본값: 42)
            ss_guidance_strength: 첫 번째 단계 가이던스 강도 (기본값: 7.5)
            ss_sampling_steps: 첫 번째 단계 샘플링 스텝 수 (기본값: 30)
            slat_guidance_strength: 두 번째 단계 가이던스 강도 (기본값: 7.5)
            slat_sampling_steps: 두 번째 단계 샘플링 스텝 수 (기본값: 30)
            mesh_simplify_ratio: 메시 단순화 비율 (기본값: 0.95)
            texture_size: 텍스처 크기 (기본값: 1024)
            
        Returns:
            생성된 3D 모델 파일 경로 (.glb)
            
        Raises:
            Exception: 3D 모델 생성 실패 시
        """
        logger.info(f"이미지를 base64로 변환 중: {image_path}")
        image_base64 = self.image_to_base64(image_path)
        
        # 3D 모델 생성 파라미터 설정
        params = {
            'image_base64': image_base64,
            'seed': seed,
            'ss_guidance_strength': ss_guidance_strength,
            'ss_sampling_steps': ss_sampling_steps,
            'slat_guidance_strength': slat_guidance_strength,
            'slat_sampling_steps': slat_sampling_steps,
            'mesh_simplify_ratio': mesh_simplify_ratio,
            'texture_size': texture_size,
            'output_format': 'glb'
        }
        
        # 3D 생성 API 호출
        logger.info("3D 모델 생성 API 호출 중...")
        try:
            response = requests.post(
                f"{self.api_base_url}/generate_no_preview",
                data=params,
                timeout=300
            )
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"3D 모델 생성 API 호출 실패: {str(e)}")
            raise Exception(f"3D 모델 생성 API 호출 실패: {str(e)}")
        
        # 상태 확인 (완료될 때까지 폴링)
        logger.info("3D 모델 생성 진행 상황 확인 중...")
        max_retries = 180  # 최대 6분 대기 (2초 * 180)
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                status_response = requests.get(
                    f"{self.api_base_url}/status",
                    timeout=30
                )
                status_response.raise_for_status()
                status = status_response.json()
                
                progress = status.get('progress', 0)
                logger.info(f"진행률: {progress}%")
                
                if status['status'] == 'COMPLETE':
                    logger.info("3D 모델 생성 완료!")
                    break
                elif status['status'] == 'FAILED':
                    error_msg = status.get('message', '알 수 없는 오류')
                    logger.error(f"3D 모델 생성 실패: {error_msg}")
                    raise Exception(f"3D 모델 생성 실패: {error_msg}")
                
                time.sleep(2)  # 2초마다 상태 확인
                retry_count += 1
                
            except requests.RequestException as e:
                logger.warning(f"상태 확인 중 오류 (재시도 {retry_count}/{max_retries}): {str(e)}")
                retry_count += 1
                time.sleep(2)
        
        if retry_count >= max_retries:
            raise Exception("3D 모델 생성 타임아웃: 최대 대기 시간 초과")
        
        # 생성된 3D 모델 다운로드
        logger.info("생성된 3D 모델 다운로드 중...")
        try:
            model_response = requests.get(
                f"{self.api_base_url}/download/model",
                timeout=60
            )
            model_response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"3D 모델 다운로드 실패: {str(e)}")
            raise Exception(f"3D 모델 다운로드 실패: {str(e)}")
        
        # 3D 모델 파일 저장
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"model3d_{member_id}_{timestamp}.glb"
        filepath = os.path.join(output_dir, filename)
        
        # 디렉토리가 없으면 생성
        os.makedirs(output_dir, exist_ok=True)
        
        with open(filepath, 'wb') as f:
            f.write(model_response.content)
        
        logger.info(f"3D 모델 저장 완료: {filepath}")
        logger.info(f"파일 크기: {len(model_response.content)} bytes")
        
        return filepath
    
    def check_api_health(self) -> bool:
        """
        3D 모델 생성 API의 상태를 확인
        
        Returns:
            API가 정상 작동 중이면 True, 아니면 False
        """
        try:
            response = requests.get(f"{self.api_base_url}/health", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"API 상태 확인 실패: {str(e)}")
            return False


def create_generator(api_base_url: Optional[str] = None) -> Model3DGenerator:
    """
    3D 모델 생성기 인스턴스 생성 헬퍼 함수
    
    Args:
        api_base_url: API 기본 URL (None이면 기본값 사용)
        
    Returns:
        Model3DGenerator 인스턴스
    """
    if api_base_url:
        return Model3DGenerator(api_base_url)
    return Model3DGenerator()
