"""
이미지 품질 검증 모듈

3D 모델 워크플로우를 위한 이미지 품질 검증 시스템
"""

# 직접 실행할 때와 패키지로 import할 때 모두 호환되도록 처리
try:
    from .image_quality_validator import ImageQualityValidator, ImageQualityResult
    from .image_quality_helper import (
        quick_validate,
        detailed_validate,
        validate_images_for_3d_workflow,
        pre_workflow_check,
        batch_pre_workflow_check,
        is_good_for_3d,
        filter_good_images,
        get_image_score,
        get_validator,
        set_validation_config,
        reset_validator
    )
except ImportError:
    from image_quality_validator import ImageQualityValidator, ImageQualityResult
    from image_quality_helper import (
        quick_validate,
        detailed_validate,
        validate_images_for_3d_workflow,
        pre_workflow_check,
        batch_pre_workflow_check,
        is_good_for_3d,
        filter_good_images,
        get_image_score,
        get_validator,
        set_validation_config,
        reset_validator
    )

__version__ = "1.0.0"
__author__ = "MyRoom AI Team"

__all__ = [
    # 주요 클래스
    "ImageQualityValidator",
    "ImageQualityResult",
    
    # 편의 함수들
    "quick_validate",
    "detailed_validate", 
    "validate_images_for_3d_workflow",
    "pre_workflow_check",
    "batch_pre_workflow_check",
    "is_good_for_3d",
    "filter_good_images",
    "get_image_score",
    
    # 설정 함수들
    "get_validator",
    "set_validation_config", 
    "reset_validator"
]