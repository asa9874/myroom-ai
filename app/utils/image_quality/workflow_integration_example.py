"""
이미지 품질 검증 모듈 워크플로우 통합 예시

3D 모델 워크플로우에 이미지 품질 검증을 쉽게 추가하는 방법을 보여줍니다.
"""

import os
import sys
from typing import List, Dict, Any

# 현재 모듈에서 직접 import
from image_quality_helper import (
    quick_validate, 
    detailed_validate,
    validate_images_for_3d_workflow,
    pre_workflow_check,
    batch_pre_workflow_check,
    is_good_for_3d,
    filter_good_images,
    get_image_score
)


class Enhanced3DWorkflow:
    """
    이미지 품질 검증이 통합된 3D 모델링 워크플로우
    """
    
    def __init__(self, enable_quality_check: bool = True, strict_mode: bool = False):
        """
        Args:
            enable_quality_check: 품질 검증 활성화 여부
            strict_mode: 엄격 모드 (80점 이상 통과)
        """
        self.enable_quality_check = enable_quality_check
        self.strict_mode = strict_mode
        self.min_score = 80.0 if strict_mode else 70.0
    
    def process_single_image(self, image_path: str) -> Dict[str, Any]:
        """
        단일 이미지 처리 (품질 검증 + 3D 모델링)
        
        Args:
            image_path: 처리할 이미지 경로
            
        Returns:
            Dict: 처리 결과
        """
        result = {
            'image_path': image_path,
            'quality_check': None,
            'can_proceed': True,
            'processing_status': 'success',
            'messages': []
        }
        
        if self.enable_quality_check:
            print(f"🔍 이미지 품질 검증 중: {os.path.basename(image_path)}")
            
            # 품질 검증 수행
            quality_result = detailed_validate(image_path)
            result['quality_check'] = quality_result
            
            if quality_result['overall_score'] >= self.min_score:
                result['messages'].append(f"✅ 품질 검증 통과 ({quality_result['overall_score']:.1f}점)")
                result['can_proceed'] = True
            else:
                result['messages'].append(f"❌ 품질 검증 실패 ({quality_result['overall_score']:.1f}점)")
                result['can_proceed'] = False
                result['processing_status'] = 'quality_failed'
                
                # 구체적인 문제점 표시
                for issue in quality_result['issues']:
                    result['messages'].append(f"   - 문제: {issue}")
                for rec in quality_result['recommendations']:
                    result['messages'].append(f"   - 권장: {rec}")
                
                return result
        
        # 품질 검증을 통과했거나 비활성화된 경우 3D 모델링 진행
        if result['can_proceed']:
            result['messages'].append("🎯 3D 모델링 워크플로우 시작")
            
            # 실제 3D 모델링 로직이 들어갈 자리
            # 여기서는 시뮬레이션만 수행
            result = self._simulate_3d_processing(result)
        
        return result
    
    def process_multiple_images(self, image_paths: List[str], 
                               auto_filter: bool = True) -> Dict[str, Any]:
        """
        여러 이미지 일괄 처리
        
        Args:
            image_paths: 처리할 이미지 경로들
            auto_filter: 품질 기준 통과한 이미지만 자동 선별
            
        Returns:
            Dict: 일괄 처리 결과
        """
        result = {
            'total_images': len(image_paths),
            'processed_images': [],
            'failed_images': [],
            'summary': {},
            'messages': []
        }
        
        if self.enable_quality_check:
            print(f"📊 {len(image_paths)}개 이미지 일괄 품질 검증 중...")
            
            # 일괄 품질 검증
            validation_result = validate_images_for_3d_workflow(
                image_paths, self.strict_mode
            )
            
            result['validation_summary'] = validation_result
            result['messages'].extend(validation_result['workflow_recommendations'])
            
            if auto_filter:
                # 품질 통과한 이미지만 선별
                valid_paths = [img['path'] for img in validation_result['valid_images']]
                result['messages'].append(f"🔍 품질 검증: {len(valid_paths)}/{len(image_paths)} 이미지 통과")
            else:
                valid_paths = image_paths
        else:
            valid_paths = image_paths
            result['messages'].append("⚠️ 품질 검증이 비활성화되어 모든 이미지를 처리합니다")
        
        # 각 이미지 개별 처리
        for image_path in valid_paths:
            individual_result = self.process_single_image(image_path)
            
            if individual_result['processing_status'] == 'success':
                result['processed_images'].append(individual_result)
            else:
                result['failed_images'].append(individual_result)
        
        # 요약 정보 생성
        result['summary'] = {
            'total': len(image_paths),
            'validated': len(valid_paths) if self.enable_quality_check else len(image_paths),
            'processed': len(result['processed_images']),
            'failed': len(result['failed_images']),
            'success_rate': (len(result['processed_images']) / len(image_paths) * 100) if image_paths else 0
        }
        
        return result
    
    def _simulate_3d_processing(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """3D 모델링 처리 시뮬레이션"""
        # 실제로는 여기서 3D 모델 생성 로직이 실행됩니다
        result['messages'].append("   ⚙️  객체 감지 및 분할...")
        result['messages'].append("   🏗️  3D 메시 생성...")
        result['messages'].append("   🎨 텍스처 매핑...")
        result['messages'].append("   ✨ 3D 모델 완성!")
        
        # 시뮬레이션된 3D 모델 정보
        result['3d_model'] = {
            'vertices': 1234,
            'faces': 2456,
            'texture_size': '512x512',
            'file_size': '2.3MB',
            'quality': 'high' if result.get('quality_check', {}).get('overall_score', 70) >= 80 else 'medium'
        }
        
        return result


def demo_workflow():
    """워크플로우 데모"""
    print("=" * 60)
    print("🚀 Enhanced 3D Workflow Demo")
    print("=" * 60)
    
    # 테스트용 이미지 경로들 (실제 사용 시에는 실제 이미지 경로 사용)
    test_images = [
        "test_image1.jpg",  # 이 경로들은 예시입니다
        "test_image2.png",
        "test_image3.jpg"
    ]
    
    # 1. 기본 모드로 워크플로우 생성
    print("\n1️⃣ 기본 모드 워크플로우")
    workflow = Enhanced3DWorkflow(enable_quality_check=True, strict_mode=False)
    
    print("설정:")
    print(f"  - 품질 검증: {'활성화' if workflow.enable_quality_check else '비활성화'}")
    print(f"  - 최소 점수: {workflow.min_score}점")
    print(f"  - 엄격 모드: {'예' if workflow.strict_mode else '아니오'}")
    
    # 2. 품질 검증 비활성화 모드
    print("\n2️⃣ 품질 검증 비활성화 모드")
    workflow_no_check = Enhanced3DWorkflow(enable_quality_check=False)
    print("  → 모든 이미지를 품질 검증 없이 처리")
    
    # 3. 엄격 모드
    print("\n3️⃣ 엄격 모드 (80점 이상)")
    workflow_strict = Enhanced3DWorkflow(enable_quality_check=True, strict_mode=True)
    print(f"  → 최소 통과 점수: {workflow_strict.min_score}점")
    
    print("\n" + "=" * 60)
    print("💡 실제 사용 예시")
    print("=" * 60)
    print("""
# 1. 간단한 사용법
from workflow_integration import Enhanced3DWorkflow

workflow = Enhanced3DWorkflow(enable_quality_check=True)
result = workflow.process_single_image("furniture_image.jpg")

if result['can_proceed']:
    print("3D 모델링 완료!")
    print(f"모델 품질: {result['3d_model']['quality']}")
else:
    print("품질 문제로 인해 처리 실패")

# 2. 일괄 처리
results = workflow.process_multiple_images([
    "chair1.jpg", "table1.png", "sofa1.jpg"
], auto_filter=True)

print(f"성공률: {results['summary']['success_rate']:.1f}%")

# 3. 빠른 품질 확인만
from app.utils.image_quality_helper import quick_validate

if quick_validate("image.jpg", min_score=75):
    # 3D 모델링 진행
    proceed_with_3d_modeling()
else:
    # 사용자에게 재촬영 요청
    request_better_image()
    """)


def simple_integration_example():
    """기존 코드에 쉽게 통합하는 예시"""
    print("\n" + "=" * 60)
    print("🔧 기존 워크플로우 간단 통합 예시")
    print("=" * 60)
    
    def original_3d_workflow(image_path: str):
        """기존의 3D 모델링 함수 (예시)"""
        print(f"3D 모델링 처리: {image_path}")
        return {"status": "success", "model_path": "output.obj"}
    
    def enhanced_3d_workflow(image_path: str):
        """품질 검증이 추가된 3D 모델링 함수"""
        # 1단계: 품질 검증 (한 줄 추가!)
        if not quick_validate(image_path, min_score=70):
            return {
                "status": "failed", 
                "reason": "image_quality", 
                "message": "이미지 품질이 3D 모델링에 적합하지 않습니다"
            }
        
        # 2단계: 기존 워크플로우 실행
        return original_3d_workflow(image_path)
    
    print("기존 함수에 단 3줄 추가로 품질 검증 기능 통합!")
    print("""
def enhanced_3d_workflow(image_path: str):
    # 추가된 부분 ↓
    if not quick_validate(image_path, min_score=70):
        return {"status": "failed", "reason": "image_quality"}
    
    # 기존 코드 그대로 ↓
    return original_3d_workflow(image_path)
    """)


if __name__ == "__main__":
    demo_workflow()
    simple_integration_example()