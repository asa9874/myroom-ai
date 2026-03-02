"""
3D 모델 생성 유틸리티

이미지를 3D 모델로 변환하는 AI API와 통신하는 모듈입니다.
이미지 품질 검증 기능이 통합되어 있어 품질이 낮은 이미지는
사전에 걸러냅니다.
"""

import base64
import logging
import os
import requests
import time
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

# 이미지 품질 검증 모듈 import
from app.utils.image_quality import (
    detailed_validate,
    quick_validate,
    pre_workflow_check,
    get_image_score,
    ImageQualityValidator
)

logger = logging.getLogger(__name__)


class Model3DServerUnavailableError(Exception):
    """3D 모델링 서버 연결 불가 예외"""

    def __init__(self, api_url: str, message: str = None):
        self.api_url = api_url
        self.message = message or f"3D 모델링 서버에 연결할 수 없습니다 ({api_url})"
        super().__init__(self.message)


# 3D 모델 생성 API 설정
API_BASE_URL = "http://127.0.0.1:7960"

# 품질 검증 설정
QUALITY_THRESHOLDS = {
    'minimum': 50,      # 이 점수 미만은 거부
    'standard': 70,     # 표준 품질
    'premium': 80       # 고품질
}


class Model3DGenerator:
    """
    3D 모델 생성을 담당하는 클래스
    
    이미지를 입력받아 AI API를 통해 3D 모델(.glb)을 생성합니다.
    이미지 품질 검증 기능이 통합되어 있어 품질이 낮은 이미지는
    사전에 걸러냅니다.
    """
    
    def __init__(self, api_base_url: str = API_BASE_URL, enable_quality_check: bool = True):
        """
        3D 모델 생성기 초기화
        
        Args:
            api_base_url: 3D 모델 생성 API의 기본 URL
            enable_quality_check: 이미지 품질 검증 활성화 여부
        """
        self.api_base_url = api_base_url
        self.enable_quality_check = enable_quality_check
        self.quality_validator = None
        
        if enable_quality_check:
            try:
                self.quality_validator = ImageQualityValidator()
                logger.info("이미지 품질 검증기 초기화 완료")
            except Exception as e:
                logger.warning(f"품질 검증기 초기화 실패 (기본 검증만 사용): {e}")
    
    def validate_image_quality(self, image_path: str, strict_mode: bool = False) -> Dict[str, Any]:
        """
        이미지 품질 사전 검증
        
        3D 모델 생성 전에 이미지 품질을 검증하여 실패 가능성을 사전에 판단합니다.
        
        Args:
            image_path: 검증할 이미지 경로
            strict_mode: 엄격 모드 (True: 80점 이상, False: 70점 이상)
            
        Returns:
            Dict: 검증 결과
            {
                'can_proceed': bool,        # 3D 모델링 진행 가능 여부
                'quality_tier': str,        # 'premium', 'standard', 'basic', 'rejected'
                'score': float,             # 종합 점수 (0-100)
                'issues': list,             # 발견된 문제점들
                'recommendations': list,    # 개선 권장사항
                'object_info': dict,        # 객체 감지 정보
                'processing_params': dict   # 권장 처리 파라미터
            }
        """
        result = {
            'can_proceed': False,
            'quality_tier': 'rejected',
            'score': 0.0,
            'scores': {},
            'issues': [],
            'recommendations': [],
            'object_info': {},
            'processing_params': {}
        }
        
        if not self.enable_quality_check:
            logger.info("품질 검증이 비활성화되어 있어 검증을 건너뜁니다")
            result['can_proceed'] = True
            result['quality_tier'] = 'unknown'
            return result
        
        try:
            logger.info(f"[검증] 이미지 품질 검증 시작: {image_path}")
            
            # 상세 품질 검증 수행
            validation_result = detailed_validate(image_path)
            
            score = validation_result['overall_score']
            result['score'] = score
            result['issues'] = validation_result.get('issues', [])
            result['recommendations'] = validation_result.get('recommendations', [])
            
            # 개별 점수 추출 (scores 필드)
            raw_scores = validation_result.get('scores', {})
            result['scores'] = {
                'blur_score': raw_scores.get('blur'),
                'brightness_score': raw_scores.get('brightness'),
                'contrast_score': raw_scores.get('contrast'),
                'object_score': raw_scores.get('object'),
                'composition_score': raw_scores.get('composition')
            }
            
            # 객체 정보 추출
            if raw_scores.get('object_info'):
                result['object_info'] = raw_scores['object_info']
            
            # 품질 등급 결정 (strict_mode에 따라 통과 기준이 다름)
            # strict_mode=True: 80점 이상만 통과
            # strict_mode=False: 50점 이상 통과
            min_required_score = QUALITY_THRESHOLDS['premium'] if strict_mode else QUALITY_THRESHOLDS['minimum']
            
            if score >= QUALITY_THRESHOLDS['premium']:
                result['quality_tier'] = 'premium'
                result['can_proceed'] = True
                result['processing_params'] = self._get_premium_params()
                logger.info(f"[PREMIUM] 프리미엄 품질 ({score:.1f}점) - 최적의 3D 모델 생성 가능")
                
            elif score >= QUALITY_THRESHOLDS['standard']:
                result['quality_tier'] = 'standard'
                # strict_mode일 때는 80점 미만이면 거부
                result['can_proceed'] = not strict_mode
                result['processing_params'] = self._get_standard_params()
                if strict_mode:
                    logger.warning(f"[REJECTED] 표준 품질 ({score:.1f}점) - 엄격 모드에서 거부됨 (80점 이상 필요)")
                else:
                    logger.info(f"[STANDARD] 표준 품질 ({score:.1f}점) - 3D 모델 생성 가능")
                
            elif score >= QUALITY_THRESHOLDS['minimum']:
                result['quality_tier'] = 'basic'
                # strict_mode일 때는 80점 미만이면 거부
                result['can_proceed'] = not strict_mode
                result['processing_params'] = self._get_basic_params()
                if strict_mode:
                    logger.warning(f"[REJECTED] 기본 품질 ({score:.1f}점) - 엄격 모드에서 거부됨 (80점 이상 필요)")
                else:
                    logger.warning(f"[BASIC] 기본 품질 ({score:.1f}점) - 3D 모델 생성 가능하나 품질 저하 가능")
                
            else:
                result['quality_tier'] = 'rejected'
                result['can_proceed'] = False
                logger.error(f"[REJECTED] 품질 미달 ({score:.1f}점) - 3D 모델 생성 불가")
            
            # 다중 객체 경고
            obj_info = result['object_info']
            if obj_info.get('detected_objects', 0) > 1:
                if not obj_info.get('is_single_object', True):
                    main_ratio = obj_info.get('main_object_ratio', 0)
                    if main_ratio < 0.3:
                        result['can_proceed'] = False
                        result['quality_tier'] = 'rejected'
                        result['issues'].append(f"주 객체가 불분명합니다 ({obj_info['detected_objects']}개 객체 감지)")
                        result['recommendations'].append("단일 가구가 명확하게 보이도록 다시 촬영해주세요")
                        logger.error(f"[REJECTED] 다중 객체로 인한 거부 - 주 객체 비율: {main_ratio:.1%}")
            
            return result
            
        except Exception as e:
            logger.error(f"품질 검증 중 오류 발생: {e}")
            result['issues'].append(f"품질 검증 오류: {str(e)}")
            # 오류 발생 시 기본적으로 진행 허용 (품질 검증 실패가 전체 워크플로우를 막지 않도록)
            result['can_proceed'] = True
            result['quality_tier'] = 'unknown'
            return result
    
    def _get_premium_params(self) -> Dict[str, Any]:
        """프리미엄 품질 이미지용 파라미터"""
        return {
            'ss_sampling_steps': 25,
            'slat_sampling_steps': 25,
            'mesh_simplify_ratio': 0.90,
            'texture_size': 1024,
            'enhancement': 'minimal'
        }
    
    def _get_standard_params(self) -> Dict[str, Any]:
        """표준 품질 이미지용 파라미터"""
        return {
            'ss_sampling_steps': 20,
            'slat_sampling_steps': 20,
            'mesh_simplify_ratio': 0.85,
            'texture_size': 512,
            'enhancement': 'moderate'
        }
    
    def _get_basic_params(self) -> Dict[str, Any]:
        """기본 품질 이미지용 파라미터"""
        return {
            'ss_sampling_steps': 15,
            'slat_sampling_steps': 15,
            'mesh_simplify_ratio': 0.80,
            'texture_size': 512,
            'enhancement': 'aggressive'
        }
    
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
        ss_sampling_steps: int = 20,  # 최적화: 기본값 30 → 20 (33% 빠름)
        slat_guidance_strength: float = 7.5,
        slat_sampling_steps: int = 20,  # 최적화: 기본값 30 → 20 (33% 빠름)
        mesh_simplify_ratio: float = 0.85,  # 최적화: 기본값 0.95 → 0.85 (더 단순한 메시)
        texture_size: int = 512  # 최적화: 기본값 1024 → 512 (텍스처 처리 75% 빠름)
    ) -> str:
        """
        실제 AI API를 사용하여 3D 모델 생성
        
        성능 최적화 정보:
        - ss_sampling_steps: 20 (기본값 30 → 감소 권장, ~33% 빠름)
        - slat_sampling_steps: 20 (기본값 30 → 감소 권장, ~33% 빠름)
        - mesh_simplify_ratio: 0.85 (기본값 0.95 → 감소, 메시 복잡도 감소)
        - texture_size: 512 (기본값 1024 → 감소, 텍스처 처리 시간 대폭 단축)
        
        Args:
            image_path: 입력 이미지 경로
            output_dir: 생성된 모델을 저장할 디렉토리
            member_id: 사용자 ID (파일명에 사용)
            seed: 랜덤 시드 (기본값: 42)
            ss_guidance_strength: 첫 번째 단계 가이던스 강도 (기본값: 7.5)
            ss_sampling_steps: 첫 번째 단계 샘플링 스텝 수 (최적화: 20 추천)
            slat_guidance_strength: 두 번째 단계 가이던스 강도 (기본값: 7.5)
            slat_sampling_steps: 두 번째 단계 샘플링 스텝 수 (최적화: 20 추천)
            mesh_simplify_ratio: 메시 단순화 비율 (최적화: 0.85 추천)
            texture_size: 텍스처 크기 (최적화: 512 추천, 품질 vs 속도 균형)
            
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
        except requests.exceptions.ConnectionError as ce:
            logger.error(f"3D 모델링 서버 연결 불가: {self.api_base_url} - {str(ce)}")
            raise Model3DServerUnavailableError(
                api_url=self.api_base_url,
                message=f"3D 모델링 서버가 실행 중이지 않습니다."
            )
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
    
    def generate_3d_model_with_validation(
        self,
        image_path: str,
        output_dir: str,
        member_id: int,
        strict_mode: bool = False,
        seed: int = 42,
        ss_guidance_strength: float = 7.5,
        slat_guidance_strength: float = 7.5
    ) -> Dict[str, Any]:
        """
        🚀 품질 검증이 통합된 3D 모델 생성 (권장 메서드)
        
        이미지 품질을 먼저 검증하고, 품질 등급에 따라 최적화된 파라미터로
        3D 모델을 생성합니다.
        
        Args:
            image_path: 입력 이미지 경로
            output_dir: 생성된 모델을 저장할 디렉토리
            member_id: 사용자 ID (파일명에 사용)
            strict_mode: 엄격 모드 (True: 80점 이상 필요)
            seed: 랜덤 시드
            ss_guidance_strength: 첫 번째 단계 가이던스 강도
            slat_guidance_strength: 두 번째 단계 가이던스 강도
            
        Returns:
            Dict: 생성 결과
            {
                'success': bool,
                'model_path': str or None,
                'quality_validation': dict,     # 품질 검증 결과
                'processing_time': float,       # 처리 시간 (초)
                'error': str or None,           # 에러 메시지
                'message': str                  # 사용자 친화적 메시지
            }
        """
        import time
        start_time = time.time()
        
        result = {
            'success': False,
            'model_path': None,
            'quality_validation': {},
            'processing_time': 0.0,
            'error': None,
            'message': ''
        }
        
        try:
            # 1. 이미지 품질 검증
            logger.info("=" * 60)
            logger.info("[STEP1] 이미지 품질 검증")
            logger.info("=" * 60)
            
            quality_result = self.validate_image_quality(image_path, strict_mode)
            result['quality_validation'] = quality_result
            
            # 품질 미달 시 조기 종료
            if not quality_result['can_proceed']:
                result['error'] = 'quality_failed'
                result['message'] = f"[FAIL] 이미지 품질 미달 ({quality_result['score']:.1f}점)"
                
                if quality_result['issues']:
                    result['message'] += f"\n문제점: {', '.join(quality_result['issues'][:2])}"
                if quality_result['recommendations']:
                    result['message'] += f"\n권장사항: {quality_result['recommendations'][0]}"
                
                logger.error(result['message'])
                result['processing_time'] = time.time() - start_time
                return result
            
            # 2. 품질 기반 파라미터 설정
            logger.info("=" * 60)
            logger.info("[STEP2] 품질 기반 파라미터 최적화")
            logger.info("=" * 60)
            
            params = quality_result.get('processing_params', self._get_standard_params())
            logger.info(f"품질 등급: {quality_result['quality_tier']}")
            logger.info(f"적용 파라미터: {params}")
            
            # 다중 객체 경고 로깅
            obj_info = quality_result.get('object_info', {})
            if obj_info.get('detected_objects', 0) > 1:
                logger.warning(f"[WARN] {obj_info['detected_objects']}개 객체 감지됨 - 주 객체 중심으로 처리")
            
            # 3. 3D 모델 생성
            logger.info("=" * 60)
            logger.info("[STEP3] 3D 모델 생성")
            logger.info("=" * 60)
            
            model_path = self.generate_3d_model(
                image_path=image_path,
                output_dir=output_dir,
                member_id=member_id,
                seed=seed,
                ss_guidance_strength=ss_guidance_strength,
                ss_sampling_steps=params.get('ss_sampling_steps', 20),
                slat_guidance_strength=slat_guidance_strength,
                slat_sampling_steps=params.get('slat_sampling_steps', 20),
                mesh_simplify_ratio=params.get('mesh_simplify_ratio', 0.85),
                texture_size=params.get('texture_size', 512)
            )
            
            result['success'] = True
            result['model_path'] = model_path
            result['message'] = f"[OK] 3D 모델 생성 완료 (품질: {quality_result['quality_tier']}, 점수: {quality_result['score']:.1f})"
            
            logger.info("=" * 60)
            logger.info(result['message'])
            logger.info("=" * 60)
            
        except Model3DServerUnavailableError:
            # 3D 서버 연결 불가 예외는 그대로 전파 (rabbitmq_consumer에서 전용 처리)
            raise
        except Exception as e:
            result['error'] = str(e)
            result['message'] = f"[FAIL] 3D 모델 생성 실패: {str(e)}"
            logger.error(result['message'], exc_info=True)
        
        result['processing_time'] = time.time() - start_time
        logger.info(f"총 처리 시간: {result['processing_time']:.2f}초")
        
        return result
    
    def quick_quality_check(self, image_path: str) -> Tuple[bool, float, str]:
        """
        빠른 품질 검사 (3D 모델 생성 전 간단히 확인용)
        
        Args:
            image_path: 이미지 경로
            
        Returns:
            Tuple[bool, float, str]: (통과여부, 점수, 메시지)
        """
        try:
            score = get_image_score(image_path)
            
            if score >= QUALITY_THRESHOLDS['premium']:
                return True, score, f"[PREMIUM] 프리미엄 품질 ({score:.1f}점)"
            elif score >= QUALITY_THRESHOLDS['standard']:
                return True, score, f"[OK] 표준 품질 ({score:.1f}점)"
            elif score >= QUALITY_THRESHOLDS['minimum']:
                return True, score, f"[WARN] 기본 품질 ({score:.1f}점) - 품질 저하 가능"
            else:
                return False, score, f"[FAIL] 품질 미달 ({score:.1f}점) - 재촬영 필요"
                
        except Exception as e:
            logger.warning(f"품질 검사 실패: {e}")
            return True, 0.0, "[WARN] 품질 검사 실패 - 기본 모드로 진행"
    
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
