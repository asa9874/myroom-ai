"""
🧪 통합 워크플로우 테스트

품질 검증이 통합된 3D 모델 생성 워크플로우를 테스트합니다.
실제 API 호출 없이 품질 검증 + 파라미터 결정 로직을 테스트할 수 있습니다.
"""

import os
import sys
import tempfile
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from PIL import Image
import numpy as np


def create_test_images():
    """테스트용 이미지 생성"""
    test_dir = project_root / "test_images"
    test_dir.mkdir(exist_ok=True)
    
    images = {}
    
    # 1. 고품질 이미지 (깨끗한 배경 + 중앙 객체)
    print("📷 테스트 이미지 생성 중...")
    
    # 고품질: 밝은 배경 + 뚜렷한 객체
    img_high = Image.new('RGB', (800, 800), (245, 245, 245))
    pixels = np.array(img_high)
    # 중앙에 큰 가구 모양의 객체 (갈색 사각형)
    pixels[200:600, 200:600] = [139, 90, 43]  # 갈색
    pixels[180:220, 180:620] = [100, 60, 30]  # 상단 테두리
    images['high_quality'] = Image.fromarray(pixels)
    images['high_quality'].save(test_dir / "test_high_quality.jpg", quality=95)
    
    # 2. 중간 품질 이미지
    img_mid = Image.new('RGB', (600, 600), (200, 200, 200))
    pixels = np.array(img_mid)
    pixels[100:500, 100:500] = [150, 100, 50]  # 갈색 객체
    images['medium_quality'] = Image.fromarray(pixels)
    images['medium_quality'].save(test_dir / "test_medium_quality.jpg", quality=85)
    
    # 3. 낮은 품질 이미지 (흐림 효과)
    from PIL import ImageFilter
    img_low = images['medium_quality'].copy()
    img_low = img_low.filter(ImageFilter.GaussianBlur(radius=3))
    images['low_quality'] = img_low
    images['low_quality'].save(test_dir / "test_low_quality.jpg", quality=70)
    
    # 4. 아주 낮은 품질 이미지 (매우 흐림 + 어두움)
    img_bad = Image.new('RGB', (400, 400), (50, 50, 50))  # 어두운 배경
    img_bad = img_bad.filter(ImageFilter.GaussianBlur(radius=5))
    images['bad_quality'] = img_bad
    images['bad_quality'].save(test_dir / "test_bad_quality.jpg", quality=50)
    
    print(f"✅ 테스트 이미지 생성 완료: {test_dir}")
    
    return {
        'high': str(test_dir / "test_high_quality.jpg"),
        'medium': str(test_dir / "test_medium_quality.jpg"),
        'low': str(test_dir / "test_low_quality.jpg"),
        'bad': str(test_dir / "test_bad_quality.jpg")
    }


def test_quality_validation():
    """품질 검증 기능만 테스트"""
    print("\n" + "=" * 70)
    print("🔍 테스트 1: 품질 검증 기능")
    print("=" * 70)
    
    from app.utils.image_quality import detailed_validate, quick_validate, get_image_score
    
    images = create_test_images()
    
    results = {}
    for name, path in images.items():
        print(f"\n📷 {name} 이미지 검증 중...")
        
        # 빠른 검증 (bool 반환) + 점수 별도 조회
        is_good = quick_validate(path)
        score = get_image_score(path)
        print(f"   빠른 검증: {score:.1f}점 - {'✅ 통과' if is_good else '❌ 실패'}")
        
        # 상세 검증
        detail_result = detailed_validate(path)
        print(f"   상세 검증: {detail_result['overall_score']:.1f}점")
        scores = detail_result.get('scores', {})
        print(f"   - 흐림: {scores.get('blur_score', 0):.1f}")
        print(f"   - 밝기: {scores.get('brightness_score', 0):.1f}")
        print(f"   - 대비: {scores.get('contrast_score', 0):.1f}")
        
        results[name] = {
            'quick_score': score,
            'detail_score': detail_result['overall_score'],
            'passed': is_good
        }
    
    print("\n📊 검증 결과 요약:")
    print("-" * 50)
    for name, result in results.items():
        status = "✅ 통과" if result['passed'] else "❌ 거부"
        print(f"   {name:15}: {result['quick_score']:5.1f}점 {status}")
    
    return results


def test_generator_validation():
    """Model3DGenerator의 품질 검증 메서드 테스트"""
    print("\n" + "=" * 70)
    print("🔧 테스트 2: Generator 품질 검증 메서드")
    print("=" * 70)
    
    from app.utils.model3d_generator import Model3DGenerator
    
    # Generator 인스턴스 생성 (API는 사용하지 않음)
    generator = Model3DGenerator(api_base_url="http://dummy-url")
    
    images = create_test_images()
    
    print("\n📍 일반 모드 테스트:")
    for name, path in images.items():
        result = generator.validate_image_quality(path, strict_mode=False)
        status = "✅ 진행가능" if result['can_proceed'] else "❌ 거부됨"
        print(f"   {name:15}: {result['score']:.1f}점 [{result['quality_tier']:8}] {status}")
        if not result['can_proceed'] and result['issues']:
            print(f"                    → 문제: {result['issues'][0]}")
    
    print("\n📍 엄격 모드 테스트 (프리미엄 품질 필요):")
    for name, path in images.items():
        result = generator.validate_image_quality(path, strict_mode=True)
        status = "✅ 진행가능" if result['can_proceed'] else "❌ 거부됨"
        print(f"   {name:15}: {result['score']:.1f}점 [{result['quality_tier']:8}] {status}")


def test_quick_quality_check():
    """빠른 품질 검사 메서드 테스트"""
    print("\n" + "=" * 70)
    print("⚡ 테스트 3: 빠른 품질 검사")
    print("=" * 70)
    
    from app.utils.model3d_generator import Model3DGenerator
    
    generator = Model3DGenerator(api_base_url="http://dummy-url")
    images = create_test_images()
    
    for name, path in images.items():
        passed, score, message = generator.quick_quality_check(path)
        print(f"   {name:15}: {message}")


def test_workflow_simulation():
    """실제 워크플로우 시뮬레이션 (API 호출 제외)"""
    print("\n" + "=" * 70)
    print("🚀 테스트 4: 워크플로우 시뮬레이션")
    print("=" * 70)
    
    from app.utils.model3d_generator import Model3DGenerator, QUALITY_THRESHOLDS
    
    generator = Model3DGenerator(api_base_url="http://dummy-url")
    images = create_test_images()
    
    print(f"\n📋 품질 기준:")
    print(f"   - 프리미엄: {QUALITY_THRESHOLDS['premium']}점 이상")
    print(f"   - 표준: {QUALITY_THRESHOLDS['standard']}점 이상")
    print(f"   - 최소: {QUALITY_THRESHOLDS['minimum']}점 이상")
    
    print("\n📍 각 이미지에 대한 워크플로우 시뮬레이션:")
    for name, path in images.items():
        print(f"\n{'=' * 50}")
        print(f"🖼️ 이미지: {name}")
        print(f"{'=' * 50}")
        
        # 품질 검증
        quality_result = generator.validate_image_quality(path, strict_mode=False)
        
        print(f"   점수: {quality_result['score']:.1f}점")
        print(f"   등급: {quality_result['quality_tier']}")
        print(f"   진행 가능: {'예' if quality_result['can_proceed'] else '아니오'}")
        
        if quality_result['can_proceed']:
            params = quality_result.get('processing_params', {})
            print(f"\n   🔧 적용될 파라미터:")
            print(f"      - 샘플링 단계: {params.get('ss_sampling_steps', 'N/A')}")
            print(f"      - 메시 간소화: {params.get('mesh_simplify_ratio', 'N/A')}")
            print(f"      - 텍스처 크기: {params.get('texture_size', 'N/A')}")
            print(f"   → 3D 모델 생성이 진행됩니다.")
        else:
            print(f"\n   ❌ 거부 사유:")
            for issue in quality_result.get('issues', []):
                print(f"      - {issue}")
            if quality_result.get('recommendations'):
                print(f"   💡 권장사항: {quality_result['recommendations'][0]}")


def test_with_real_images():
    """실제 이미지로 테스트 (module/test_images 폴더에 이미지가 있는 경우)"""
    print("\n" + "=" * 70)
    print("📸 테스트 5: 실제 이미지 테스트 (있는 경우)")
    print("=" * 70)
    
    real_image_dir = project_root / "module" / "test_images"
    
    if not real_image_dir.exists():
        print(f"   ℹ️ {real_image_dir} 폴더가 없습니다.")
        print("   실제 이미지 테스트를 건너뜁니다.")
        return
    
    # 이미지 파일 찾기
    image_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
    real_images = [
        f for f in real_image_dir.iterdir() 
        if f.suffix.lower() in image_extensions
    ]
    
    if not real_images:
        print("   ℹ️ 테스트할 실제 이미지가 없습니다.")
        return
    
    from app.utils.model3d_generator import Model3DGenerator
    
    generator = Model3DGenerator(api_base_url="http://dummy-url")
    
    print(f"\n   📁 {len(real_images)}개의 실제 이미지 발견\n")
    
    for img_path in real_images:
        print(f"   🖼️ {img_path.name}")
        
        result = generator.validate_image_quality(str(img_path), strict_mode=False)
        
        tier_emoji = {
            'premium': '🏆',
            'standard': '✅',
            'basic': '⚠️',
            'rejected': '❌'
        }
        
        emoji = tier_emoji.get(result['quality_tier'], '❓')
        status = "진행 가능" if result['can_proceed'] else "거부됨"
        
        print(f"      {emoji} {result['score']:.1f}점 [{result['quality_tier']}] - {status}")
        
        if result.get('object_info', {}).get('detected_objects', 0) > 1:
            print(f"      ⚠️ 다중 객체 감지: {result['object_info']['detected_objects']}개")
        
        print()


def main():
    """모든 테스트 실행"""
    print("\n" + "=" * 70)
    print("🧪 품질 검증 통합 워크플로우 테스트")
    print("=" * 70)
    print("이 테스트는 실제 3D 생성 API를 호출하지 않습니다.")
    print("품질 검증 로직과 파라미터 결정 로직만 테스트합니다.")
    
    try:
        # 1. 품질 검증 기능 테스트
        test_quality_validation()
        
        # 2. Generator 검증 메서드 테스트
        test_generator_validation()
        
        # 3. 빠른 품질 검사 테스트
        test_quick_quality_check()
        
        # 4. 워크플로우 시뮬레이션
        test_workflow_simulation()
        
        # 5. 실제 이미지 테스트 (있는 경우)
        test_with_real_images()
        
        print("\n" + "=" * 70)
        print("✅ 모든 테스트 완료!")
        print("=" * 70)
        print("\n💡 실제 3D 모델 생성을 테스트하려면:")
        print("   from app.utils.model3d_generator import create_generator")
        print("   generator = create_generator()")
        print("   result = generator.generate_3d_model_with_validation(")
        print("       image_path='이미지경로',")
        print("       output_dir='출력폴더',")
        print("       member_id=1")
        print("   )")
        
    except ImportError as e:
        print(f"\n❌ Import 오류: {e}")
        print("의존성을 확인해주세요: pip install pillow numpy opencv-python")
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
