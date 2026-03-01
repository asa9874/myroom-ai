"""
이미지 품질 검증 모듈 통합 유틸리티

3D 모델 워크플로우에 이미지 품질 검증 기능을 쉽게 통합할 수 있는 
간편한 인터페이스를 제공합니다.
"""

import os
import logging
from typing import Dict, Any, Optional, List, Union

# 직접 실행할 때와 패키지로 import할 때 모두 호환되도록 처리
try:
    from .image_quality_validator import ImageQualityValidator, ImageQualityResult
except ImportError:
    from image_quality_validator import ImageQualityValidator, ImageQualityResult

logger = logging.getLogger(__name__)

# 글로벌 검증기 인스턴스 (재사용을 위해)
_validator_instance = None


def get_validator(model_path: Optional[str] = None, min_confidence: float = 0.5) -> ImageQualityValidator:
    """
    검증기 인스턴스를 가져옵니다 (싱글톤 패턴)
    
    Args:
        model_path: YOLO 모델 경로 (기본값: "yolov8n.pt")
        min_confidence: 최소 신뢰도
        
    Returns:
        ImageQualityValidator: 검증기 인스턴스
    """
    global _validator_instance
    
    if _validator_instance is None:
        if model_path is None:
            # 프로젝트 루트에서 YOLO 모델 찾기
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            model_path = os.path.join(project_root, "yolov8n.pt")
        
        _validator_instance = ImageQualityValidator(model_path, min_confidence)
        logger.info("Image quality validator initialized")
    
    return _validator_instance


def quick_validate(image_path: str, min_score: float = 70.0) -> bool:
    """
    이미지 품질을 빠르게 검증합니다 (간단한 통과/실패만 반환)
    
    Args:
        image_path: 검증할 이미지 경로
        min_score: 최소 통과 점수 (기본값: 70.0)
        
    Returns:
        bool: 품질 검증 통과 여부
    """
    try:
        validator = get_validator()
        result = validator.validate_image(image_path)
        return result.overall_score >= min_score
    except Exception as e:
        logger.error(f"Quick validation failed for {image_path}: {e}")
        return False


def detailed_validate(image_path: str) -> Dict[str, Any]:
    """
    이미지 품질을 상세하게 검증합니다
    
    Args:
        image_path: 검증할 이미지 경로
        
    Returns:
        Dict: 상세 검증 결과
        {
            'is_valid': bool,
            'overall_score': float,
            'scores': dict,
            'issues': list,
            'recommendations': list
        }
    """
    try:
        validator = get_validator()
        result = validator.validate_image(image_path)
        
        return {
            'is_valid': result.is_valid,
            'overall_score': result.overall_score,
            'scores': result.details,
            'issues': result.issues,
            'recommendations': result.recommendations
        }
    except Exception as e:
        logger.error(f"Detailed validation failed for {image_path}: {e}")
        return {
            'is_valid': False,
            'overall_score': 0.0,
            'scores': {},
            'issues': [f"Validation error: {str(e)}"],
            'recommendations': ['Please check if the image file is valid and accessible']
        }


def validate_images_for_3d_workflow(image_paths: List[str], 
                                   strict_mode: bool = False) -> Dict[str, Any]:
    """
    3D 모델링 워크플로우를 위한 이미지 품질 검증
    
    Args:
        image_paths: 검증할 이미지 경로들
        strict_mode: 엄격 모드 (True: 80점 이상 통과, False: 70점 이상 통과)
        
    Returns:
        Dict: 워크플로우 검증 결과
        {
            'ready_for_3d': bool,
            'valid_images': list,
            'invalid_images': list,
            'summary': dict,
            'workflow_recommendations': list
        }
    """
    min_score = 80.0 if strict_mode else 70.0
    
    try:
        validator = get_validator()
        results = validator.validate_batch(image_paths)
        
        valid_images = []
        invalid_images = []
        
        for img_path, result in results:
            if result.overall_score >= min_score:
                valid_images.append({
                    'path': img_path,
                    'score': result.overall_score
                })
            else:
                invalid_images.append({
                    'path': img_path,
                    'score': result.overall_score,
                    'issues': result.issues,
                    'recommendations': result.recommendations
                })
        
        # 워크플로우 준비 상태 판단
        ready_for_3d = len(valid_images) > 0 and len(invalid_images) == 0
        
        # 요약 정보
        summary = validator.get_validation_summary(results)
        
        # 워크플로우 특화 권장사항
        workflow_recommendations = _get_workflow_recommendations(
            valid_images, invalid_images, strict_mode
        )
        
        return {
            'ready_for_3d': ready_for_3d,
            'valid_images': valid_images,
            'invalid_images': invalid_images,
            'summary': summary,
            'workflow_recommendations': workflow_recommendations
        }
        
    except Exception as e:
        logger.error(f"3D workflow validation failed: {e}")
        return {
            'ready_for_3d': False,
            'valid_images': [],
            'invalid_images': [{'path': path, 'error': str(e)} for path in image_paths],
            'summary': {'error': str(e)},
            'workflow_recommendations': [
                'Please check if all image files are valid and accessible',
                'Ensure the image quality validator is properly configured'
            ]
        }


def _get_workflow_recommendations(valid_images: List[Dict], 
                                invalid_images: List[Dict], 
                                strict_mode: bool) -> List[str]:
    """3D 워크플로우를 위한 특화된 권장사항 생성"""
    recommendations = []
    
    if not valid_images:
        recommendations.append("🚫 3D 모델링을 시작할 수 있는 품질의 이미지가 없습니다.")
        recommendations.append("[TIP] 먼저 고품질의 이미지를 촬영해주세요.")
    elif len(invalid_images) > 0:
        recommendations.append(f"⚠️  {len(invalid_images)}개의 이미지가 품질 기준에 미달입니다.")
        recommendations.append("🔄 문제가 있는 이미지들을 재촬영하거나 개선해주세요.")
    else:
        recommendations.append("✅ 모든 이미지가 3D 모델링에 적합한 품질을 가지고 있습니다.")
    
    if len(valid_images) == 1:
        recommendations.append("💡 더 나은 3D 모델을 위해 다양한 각도의 추가 이미지를 고려해보세요.")
    elif len(valid_images) > 1:
        recommendations.append(f"📷 {len(valid_images)}개의 고품질 이미지로 정밀한 3D 모델링이 가능합니다.")
    
    if strict_mode:
        recommendations.append("🎯 엄격 모드가 적용되었습니다 (80점 이상 통과).")
    
    return recommendations


def pre_workflow_check(image_path: str, workflow_type: str = "3d_modeling") -> Dict[str, Any]:
    """
    워크플로우 시작 전 이미지 사전 검사
    
    Args:
        image_path: 검증할 이미지 경로
        workflow_type: 워크플로우 타입 ("3d_modeling", "general")
        
    Returns:
        Dict: 사전 검사 결과
    """
    result = detailed_validate(image_path)
    
    if workflow_type == "3d_modeling":
        # 3D 모델링 특화 기준 적용
        critical_issues = []
        
        # 선명도가 매우 중요
        if result['scores'].get('blur', 0) < 60:
            critical_issues.append("이미지가 너무 흐립니다 - 3D 모델링에 부적합")
        
        # 객체 완전성이 중요
        if result['scores'].get('object', 0) < 50:
            critical_issues.append("객체가 불완전합니다 - 3D 모델링에 필요한 전체 형태를 볼 수 없음")
        
        result['critical_issues'] = critical_issues
        result['3d_ready'] = len(critical_issues) == 0 and result['is_valid']
        
        if result['3d_ready']:
            result['workflow_message'] = "✅ 3D 모델링 워크플로우를 시작할 수 있습니다."
        else:
            result['workflow_message'] = "❌ 이미지 품질을 개선한 후 3D 모델링을 시작해주세요."
    
    return result


def batch_pre_workflow_check(image_paths: List[str], 
                           workflow_type: str = "3d_modeling",
                           auto_filter: bool = True) -> Dict[str, Any]:
    """
    여러 이미지에 대한 워크플로우 사전 검사 및 자동 필터링
    
    Args:
        image_paths: 검증할 이미지 경로들
        workflow_type: 워크플로우 타입
        auto_filter: 품질 기준을 통과한 이미지만 자동 선별
        
    Returns:
        Dict: 일괄 사전 검사 결과
    """
    results = []
    approved_images = []
    rejected_images = []
    
    for image_path in image_paths:
        check_result = pre_workflow_check(image_path, workflow_type)
        results.append({
            'path': image_path,
            'result': check_result
        })
        
        if workflow_type == "3d_modeling":
            if check_result.get('3d_ready', False):
                approved_images.append(image_path)
            else:
                rejected_images.append({
                    'path': image_path,
                    'issues': check_result.get('critical_issues', []),
                    'score': check_result['overall_score']
                })
        else:
            if check_result['is_valid']:
                approved_images.append(image_path)
            else:
                rejected_images.append({
                    'path': image_path,
                    'issues': check_result['issues'],
                    'score': check_result['overall_score']
                })
    
    return {
        'total_checked': len(image_paths),
        'approved': approved_images,
        'rejected': rejected_images,
        'approval_rate': len(approved_images) / len(image_paths) * 100 if image_paths else 0,
        'detailed_results': results,
        'ready_for_workflow': len(approved_images) > 0,
        'recommended_images': approved_images if auto_filter else image_paths
    }


# 편의 함수들 (더 간단한 사용을 위해)

def is_good_for_3d(image_path: str) -> bool:
    """이미지가 3D 모델링에 적합한지 간단히 확인"""
    return pre_workflow_check(image_path, "3d_modeling").get('3d_ready', False)


def filter_good_images(image_paths: List[str], for_3d: bool = True) -> List[str]:
    """품질이 좋은 이미지들만 필터링하여 반환"""
    workflow_type = "3d_modeling" if for_3d else "general"
    result = batch_pre_workflow_check(image_paths, workflow_type, auto_filter=True)
    return result['approved']


def get_image_score(image_path: str) -> float:
    """이미지의 품질 점수만 간단히 반환"""
    result = detailed_validate(image_path)
    return result['overall_score']


def crop_main_object(image_path: str, output_path: str, padding_ratio: float = 0.05) -> bool:
    """
    이미지에서 YOLO로 주 객체를 감지한 뒤 크롭하여 저장합니다.

    감지된 객체가 여러 개일 경우 면적이 가장 큰 객체를 주 객체로 선택하며,
    padding_ratio 만큼 여백을 추가합니다.
    YOLO 모델이 없거나 객체가 감지되지 않으면 False 를 반환합니다.

    Args:
        image_path: 원본 이미지 경로
        output_path: 크롭된 이미지를 저장할 경로
        padding_ratio: 바운딩박스 여백 비율 (기본값: 0.05 = 5%)

    Returns:
        bool: 크롭 성공 여부
    """
    try:
        validator = get_validator()
        return validator.crop_main_object(image_path, output_path, padding_ratio)
    except Exception as e:
        logger.error(f"crop_main_object 실패: {e}")
        return False


# 설정 함수들

def set_validation_config(blur_threshold: Optional[float] = None,
                         brightness_range: Optional[tuple] = None,
                         min_object_ratio: Optional[float] = None):
    """검증 기준 설정 변경"""
    global _validator_instance
    if _validator_instance:
        if blur_threshold is not None:
            _validator_instance.blur_threshold = blur_threshold
        if brightness_range is not None:
            _validator_instance.min_brightness, _validator_instance.max_brightness = brightness_range
        if min_object_ratio is not None:
            _validator_instance.min_object_ratio = min_object_ratio
        logger.info("Validation configuration updated")


def reset_validator():
    """검증기 인스턴스 리셋 (새로운 설정으로 다시 초기화하려면 사용)"""
    global _validator_instance
    _validator_instance = None
    logger.info("Validator instance reset")