"""
이미지 품질 검증 모듈 테스트 스크립트

이 스크립트는 image_quality_validator.py 모듈을 독립적으로 테스트합니다.
"""

import os
import sys
import tempfile
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance

# 현재 모듈에서 직접 import
from image_quality_validator import ImageQualityValidator, ImageQualityResult


def create_test_images():
    """테스트용 이미지들을 생성합니다"""
    
    # 임시 디렉토리 생성
    temp_dir = tempfile.mkdtemp(prefix="image_quality_test_")
    print(f"테스트 이미지들을 생성합니다: {temp_dir}")
    
    # 기본 테스트 이미지 생성 (좋은 품질)
    def create_good_image():
        img = Image.new('RGB', (800, 600), color='white')
        # 중앙에 컬러풀한 사각형 객체 그리기
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.rectangle([200, 150, 600, 450], fill=(100, 150, 200), outline=(50, 100, 150), width=3)
        draw.rectangle([250, 200, 550, 400], fill=(200, 100, 150), outline=(150, 50, 100), width=2)
        return img
    
    # 1. 좋은 품질의 이미지
    good_img = create_good_image()
    good_path = os.path.join(temp_dir, "good_quality.jpg")
    good_img.save(good_path, "JPEG", quality=95)
    
    # 2. 흐린 이미지 (블러)
    blur_img = create_good_image().filter(ImageFilter.GaussianBlur(radius=5))
    blur_path = os.path.join(temp_dir, "blurred.jpg")
    blur_img.save(blur_path, "JPEG", quality=95)
    
    # 3. 어두운 이미지
    dark_img = ImageEnhance.Brightness(create_good_image()).enhance(0.3)
    dark_path = os.path.join(temp_dir, "dark.jpg")
    dark_img.save(dark_path, "JPEG", quality=95)
    
    # 4. 너무 밝은 이미지
    bright_img = ImageEnhance.Brightness(create_good_image()).enhance(2.5)
    bright_path = os.path.join(temp_dir, "bright.jpg")
    bright_img.save(bright_path, "JPEG", quality=95)
    
    # 5. 대비가 낮은 이미지
    low_contrast_img = ImageEnhance.Contrast(create_good_image()).enhance(0.3)
    low_contrast_path = os.path.join(temp_dir, "low_contrast.jpg")
    low_contrast_img.save(low_contrast_path, "JPEG", quality=95)
    
    # 6. 객체가 잘린 이미지 (가장자리에 객체)
    cropped_img = Image.new('RGB', (800, 600), color='white')
    from PIL import ImageDraw
    draw = ImageDraw.Draw(cropped_img)
    # 객체가 이미지 경계에 닿도록 그리기
    draw.rectangle([0, 0, 300, 300], fill=(100, 150, 200), outline=(50, 100, 150), width=3)
    draw.rectangle([700, 500, 800, 600], fill=(200, 100, 150), outline=(150, 50, 100), width=2)
    cropped_path = os.path.join(temp_dir, "cropped_object.jpg")
    cropped_img.save(cropped_path, "JPEG", quality=95)
    
    # 7. 해상도가 낮은 이미지
    low_res_img = create_good_image().resize((200, 150))
    low_res_path = os.path.join(temp_dir, "low_resolution.jpg")
    low_res_img.save(low_res_path, "JPEG", quality=95)
    
    return temp_dir, [
        ("good_quality.jpg", "좋은 품질"),
        ("blurred.jpg", "흐린 이미지"),
        ("dark.jpg", "어두운 이미지"),
        ("bright.jpg", "밝은 이미지"), 
        ("low_contrast.jpg", "낮은 대비"),
        ("cropped_object.jpg", "잘린 객체"),
        ("low_resolution.jpg", "낮은 해상도")
    ]


def test_single_validation():
    """단일 이미지 검증 테스트"""
    print("\n" + "="*60)
    print("단일 이미지 검증 테스트")
    print("="*60)
    
    temp_dir, test_cases = create_test_images()
    validator = ImageQualityValidator()
    
    for filename, description in test_cases:
        image_path = os.path.join(temp_dir, filename)
        print(f"\n--- {description} ({filename}) ---")
        
        try:
            result = validator.validate_image(image_path)
            
            print(f"검증 결과: {'✅ 통과' if result.is_valid else '❌ 실패'}")
            print(f"종합 점수: {result.overall_score:.1f}/100")
            
            # 세부 점수 출력
            if result.details:
                print("세부 점수:")
                for category, score in result.details.items():
                    print(f"  - {category}: {score:.1f}")
            
            # 발견된 문제점
            if result.issues:
                print("문제점:")
                for issue in result.issues:
                    print(f"  • {issue}")
            
            # 권장사항
            if result.recommendations:
                print("권장사항:")
                for rec in result.recommendations:
                    print(f"  • {rec}")
                    
        except Exception as e:
            print(f"❌ 오류 발생: {e}")
    
    # 임시 파일 정리
    import shutil
    shutil.rmtree(temp_dir)
    print(f"\n테스트 완료! 임시 파일들을 정리했습니다.")


def test_batch_validation():
    """일괄 검증 테스트"""
    print("\n" + "="*60)
    print("일괄 이미지 검증 테스트")
    print("="*60)
    
    temp_dir, test_cases = create_test_images()
    validator = ImageQualityValidator()
    
    # 모든 테스트 이미지 경로 수집
    image_paths = [os.path.join(temp_dir, filename) for filename, _ in test_cases]
    
    print(f"총 {len(image_paths)}개의 이미지를 일괄 검증합니다...\n")
    
    try:
        results = validator.validate_batch(image_paths)
        
        # 개별 결과 출력
        print("개별 검증 결과:")
        for img_path, result in results:
            filename = os.path.basename(img_path)
            status = "✅ 통과" if result.is_valid else "❌ 실패"
            print(f"  {filename}: {status} ({result.overall_score:.1f}점)")
        
        # 요약 정보
        summary = validator.get_validation_summary(results)
        print(f"\n검증 요약:")
        print(f"  총 이미지: {summary['total_images']}개")
        print(f"  통과: {summary['valid_images']}개")
        print(f"  실패: {summary['invalid_images']}개")
        print(f"  성공률: {summary['success_rate']:.1f}%")
        print(f"  평균 점수: {summary['average_score']:.1f}점")
        
        if summary['recommendations']:
            print(f"\n공통 권장사항:")
            for rec in summary['recommendations']:
                print(f"  • {rec}")
                
    except Exception as e:
        print(f"❌ 일괄 검증 오류: {e}")
    
    # 임시 파일 정리
    import shutil
    shutil.rmtree(temp_dir)
    print(f"\n테스트 완료! 임시 파일들을 정리했습니다.")


def test_validator_configuration():
    """검증기 설정 테스트"""
    print("\n" + "="*60)
    print("검증기 설정 테스트")
    print("="*60)
    
    # 다양한 설정으로 검증기 생성 테스트
    try:
        # 기본 설정
        validator1 = ImageQualityValidator()
        print("✅ 기본 설정 검증기 생성 성공")
        
        # 사용자 정의 설정
        validator2 = ImageQualityValidator(
            model_path="nonexistent_model.pt",  # 존재하지 않는 모델 경로
            min_confidence=0.7
        )
        print("✅ 사용자 정의 설정 검증기 생성 성공 (모델 없어도 동작)")
        
        # 설정 확인
        print(f"\n검증기 설정:")
        print(f"  최소 신뢰도: {validator2.min_confidence}")
        print(f"  블러 임계값: {validator2.blur_threshold}")
        print(f"  최소 객체 비율: {validator2.min_object_ratio}")
        print(f"  최대 객체 비율: {validator2.max_object_ratio}")
        print(f"  YOLO 모델 로드됨: {'Yes' if validator2.model else 'No'}")
        
    except Exception as e:
        print(f"❌ 설정 테스트 오류: {e}")


def test_error_handling():
    """오류 처리 테스트"""
    print("\n" + "="*60)
    print("오류 처리 테스트")  
    print("="*60)
    
    validator = ImageQualityValidator()
    
    # 존재하지 않는 파일
    print("1. 존재하지 않는 파일 테스트:")
    try:
        result = validator.validate_image("nonexistent_file.jpg")
        print(f"   검증 결과: {'통과' if result.is_valid else '실패'}")
        print(f"   점수: {result.overall_score}")
        print(f"   문제점: {result.issues}")
    except Exception as e:
        print(f"   ❌ 예외 발생: {e}")
    
    # 빈 리스트 일괄 검증
    print("\n2. 빈 리스트 일괄 검증 테스트:")
    try:
        results = validator.validate_batch([])
        summary = validator.get_validation_summary(results)
        print(f"   검증된 이미지 수: {len(results)}")
        print(f"   요약 - 총 이미지: {summary['total_images']}")
        print(f"   요약 - 성공률: {summary['success_rate']:.1f}%")
    except Exception as e:
        print(f"   ❌ 예외 발생: {e}")
    
    # 잘못된 파일 형식
    print("\n3. 잘못된 파일 형식 테스트:")
    try:
        # 임시 텍스트 파일 생성
        temp_file = tempfile.mktemp(suffix=".txt")
        with open(temp_file, 'w') as f:
            f.write("This is not an image")
        
        result = validator.validate_image(temp_file)
        print(f"   검증 결과: {'통과' if result.is_valid else '실패'}")
        print(f"   점수: {result.overall_score}")
        print(f"   문제점: {result.issues}")
        
        # 임시 파일 정리
        os.unlink(temp_file)
        
    except Exception as e:
        print(f"   ❌ 예외 발생: {e}")


def performance_test():
    """성능 테스트"""
    print("\n" + "="*60)
    print("성능 테스트")
    print("="*60)
    
    import time
    
    temp_dir, test_cases = create_test_images()
    validator = ImageQualityValidator()
    
    # 단일 이미지 성능 테스트
    test_image = os.path.join(temp_dir, "good_quality.jpg")
    
    print("단일 이미지 검증 성능:")
    times = []
    for i in range(5):
        start_time = time.time()
        result = validator.validate_image(test_image)
        end_time = time.time()
        elapsed = end_time - start_time
        times.append(elapsed)
        print(f"  시도 {i+1}: {elapsed:.3f}초 (점수: {result.overall_score:.1f})")
    
    avg_time = sum(times) / len(times)
    print(f"  평균 처리 시간: {avg_time:.3f}초")
    
    # 일괄 처리 성능 테스트
    image_paths = [os.path.join(temp_dir, filename) for filename, _ in test_cases]
    
    print(f"\n일괄 검증 성능 ({len(image_paths)}개 이미지):")
    start_time = time.time()
    results = validator.validate_batch(image_paths)
    end_time = time.time()
    
    total_time = end_time - start_time
    avg_per_image = total_time / len(image_paths)
    
    print(f"  총 처리 시간: {total_time:.3f}초")
    print(f"  이미지당 평균: {avg_per_image:.3f}초")
    print(f"  처리량: {len(image_paths)/total_time:.1f} 이미지/초")
    
    # 임시 파일 정리
    import shutil
    shutil.rmtree(temp_dir)


def main():
    """모든 테스트 실행"""
    print("이미지 품질 검증 모듈 테스트 시작!")
    
    try:
        # 1. 설정 테스트
        test_validator_configuration()
        
        # 2. 단일 검증 테스트
        test_single_validation()
        
        # 3. 일괄 검증 테스트
        test_batch_validation()
        
        # 4. 오류 처리 테스트
        test_error_handling()
        
        # 5. 성능 테스트
        performance_test()
        
        print("\n" + "="*60)
        print("🎉 모든 테스트가 완료되었습니다!")
        print("="*60)
        print("\n사용법:")
        print("1. 단일 이미지 검증:")
        print("   from app.utils.image_quality_validator import ImageQualityValidator")
        print("   validator = ImageQualityValidator()")
        print("   result = validator.validate_image('image.jpg')")
        print("   print(f'점수: {result.overall_score}, 통과: {result.is_valid}')")
        print("\n2. 여러 이미지 일괄 검증:")
        print("   results = validator.validate_batch(['img1.jpg', 'img2.jpg'])")
        print("   summary = validator.get_validation_summary(results)")
        print("   print(f'성공률: {summary[\"success_rate\"]}%')")
        print("\n3. 명령줄에서 직접 사용:")
        print("   python app/utils/image_quality_validator.py image.jpg")
        print("   python app/utils/image_quality_validator.py ./images/")
        
    except KeyboardInterrupt:
        print("\n\n테스트가 중단되었습니다.")
    except Exception as e:
        print(f"\n\n❌ 테스트 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()