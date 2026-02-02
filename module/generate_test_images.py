"""
테스트용 이미지 생성기

이미지 품질 검증 모듈의 테스트용 이미지들을 생성해서 저장합니다.
생성된 이미지들을 직접 확인하실 수 있습니다.
"""

import os
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance


def create_sample_images(output_dir="test_images"):
    """
    다양한 품질의 테스트 이미지들을 생성합니다.
    
    Args:
        output_dir: 이미지를 저장할 디렉토리
    """
    # 출력 디렉토리 생성
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    print(f"테스트 이미지를 생성합니다: {os.path.abspath(output_dir)}")
    
    def create_base_image():
        """기본 테스트 이미지 생성"""
        # 800x600 흰 배경
        img = Image.new('RGB', (800, 600), color=(240, 240, 240))
        draw = ImageDraw.Draw(img)
        
        # 중앙에 가구처럼 보이는 객체들 그리기
        # 의자 모양
        draw.rectangle([250, 200, 550, 500], fill=(139, 69, 19), outline=(101, 67, 33), width=3)  # 의자 등받이
        draw.rectangle([270, 400, 530, 480], fill=(160, 82, 45), outline=(101, 67, 33), width=2)  # 의자 좌석
        draw.rectangle([280, 480, 300, 550], fill=(101, 67, 33), width=2)  # 다리1
        draw.rectangle([320, 480, 340, 550], fill=(101, 67, 33), width=2)  # 다리2
        draw.rectangle([460, 480, 480, 550], fill=(101, 67, 33), width=2)  # 다리3
        draw.rectangle([500, 480, 520, 550], fill=(101, 67, 33), width=2)  # 다리4
        
        # 장식적 요소
        draw.ellipse([350, 250, 450, 350], fill=(205, 133, 63), outline=(139, 69, 19), width=2)
        
        return img
    
    # 1. 좋은 품질의 이미지
    print("1️⃣ 기본 품질 이미지 생성...")
    good_img = create_base_image()
    good_img.save(os.path.join(output_dir, "01_good_quality.jpg"), "JPEG", quality=95)
    
    # 2. 흐린 이미지 (블러)
    print("2️⃣ 흐린 이미지 생성...")
    blur_img = create_base_image().filter(ImageFilter.GaussianBlur(radius=5))
    blur_img.save(os.path.join(output_dir, "02_blurred.jpg"), "JPEG", quality=95)
    
    # 3. 어두운 이미지
    print("3️⃣ 어두운 이미지 생성...")
    dark_img = ImageEnhance.Brightness(create_base_image()).enhance(0.3)
    dark_img.save(os.path.join(output_dir, "03_dark.jpg"), "JPEG", quality=95)
    
    # 4. 너무 밝은 이미지
    print("4️⃣ 밝은 이미지 생성...")
    bright_img = ImageEnhance.Brightness(create_base_image()).enhance(2.5)
    bright_img.save(os.path.join(output_dir, "04_bright.jpg"), "JPEG", quality=95)
    
    # 5. 대비가 낮은 이미지
    print("5️⃣ 낮은 대비 이미지 생성...")
    low_contrast_img = ImageEnhance.Contrast(create_base_image()).enhance(0.3)
    low_contrast_img.save(os.path.join(output_dir, "05_low_contrast.jpg"), "JPEG", quality=95)
    
    # 6. 객체가 잘린 이미지
    print("6️⃣ 잘린 객체 이미지 생성...")
    cropped_img = Image.new('RGB', (800, 600), color=(240, 240, 240))
    draw = ImageDraw.Draw(cropped_img)
    # 객체가 이미지 경계에 걸치도록 배치
    draw.rectangle([0, 0, 400, 300], fill=(139, 69, 19), outline=(101, 67, 33), width=3)
    draw.rectangle([600, 400, 800, 600], fill=(160, 82, 45), outline=(101, 67, 33), width=2)
    cropped_img.save(os.path.join(output_dir, "06_cropped_object.jpg"), "JPEG", quality=95)
    
    # 7. 낮은 해상도 이미지
    print("7️⃣ 낮은 해상도 이미지 생성...")
    low_res_img = create_base_image().resize((200, 150))
    low_res_img.save(os.path.join(output_dir, "07_low_resolution.jpg"), "JPEG", quality=95)
    
    # 8. 추가: 매우 흐린 이미지
    print("8️⃣ 매우 흐린 이미지 생성...")
    very_blur_img = create_base_image().filter(ImageFilter.GaussianBlur(radius=10))
    very_blur_img.save(os.path.join(output_dir, "08_very_blurred.jpg"), "JPEG", quality=95)
    
    # 9. 추가: 노이즈가 있는 이미지
    print("9️⃣ 노이즈 이미지 생성...")
    import numpy as np
    base_array = np.array(create_base_image())
    noise = np.random.normal(0, 25, base_array.shape).astype(np.uint8)
    noisy_array = np.clip(base_array.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    noisy_img = Image.fromarray(noisy_array)
    noisy_img.save(os.path.join(output_dir, "09_noisy.jpg"), "JPEG", quality=95)
    
    # 10. 추가: 고품질 이미지 (비교용)
    print("🔟 고품질 이미지 생성...")
    high_quality_img = create_base_image()
    # 약간의 선명화 효과
    sharpened = high_quality_img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
    sharpened.save(os.path.join(output_dir, "10_high_quality.jpg"), "JPEG", quality=100)
    
    print(f"\n✅ 총 10개의 테스트 이미지가 생성되었습니다!")
    print(f"📁 저장 위치: {os.path.abspath(output_dir)}")
    print("\n📋 생성된 이미지 목록:")
    print("  01_good_quality.jpg    - 기본 품질 (비교 기준)")
    print("  02_blurred.jpg         - 흐린 이미지 (블러)")
    print("  03_dark.jpg            - 어두운 이미지")
    print("  04_bright.jpg          - 밝은 이미지")
    print("  05_low_contrast.jpg    - 낮은 대비")
    print("  06_cropped_object.jpg  - 잘린 객체")
    print("  07_low_resolution.jpg  - 낮은 해상도")
    print("  08_very_blurred.jpg    - 매우 흐린 이미지")
    print("  09_noisy.jpg           - 노이즈가 있는 이미지")
    print("  10_high_quality.jpg    - 고품질 이미지")
    
    return output_dir


def test_generated_images(image_dir="test_images"):
    """
    생성된 이미지들을 품질 검증 모듈로 테스트
    """
    try:
        from image_quality_validator import ImageQualityValidator
        
        print(f"\n🔍 생성된 이미지들을 품질 검증 모듈로 테스트합니다...")
        
        validator = ImageQualityValidator()
        
        # 이미지 파일들 찾기
        image_files = [f for f in os.listdir(image_dir) if f.endswith('.jpg')]
        image_files.sort()
        
        print(f"\n📊 검증 결과:")
        print("=" * 80)
        
        for img_file in image_files:
            img_path = os.path.join(image_dir, img_file)
            result = validator.validate_image(img_path)
            
            status = "✅ 통과" if result.is_valid else "❌ 실패"
            print(f"{img_file:<25} {status} ({result.overall_score:.1f}점)")
            
            # 주요 문제점 표시
            if result.issues:
                main_issues = result.issues[:2]  # 주요 문제점 2개만
                for issue in main_issues:
                    print(f"{'':27} └ {issue}")
        
        print("=" * 80)
        
    except ImportError:
        print("⚠️ 품질 검증 모듈을 찾을 수 없습니다.")
        print("이미지는 생성되었으니 직접 확인해보세요!")


if __name__ == "__main__":
    print("🎨 이미지 품질 검증용 테스트 이미지 생성기")
    print("=" * 60)
    
    # 이미지 생성
    output_directory = create_sample_images()
    
    # 선택적으로 품질 테스트 실행
    try:
        test_generated_images(output_directory)
    except Exception as e:
        print(f"\n⚠️ 품질 테스트 실행 중 오류: {e}")
        print("이미지는 정상적으로 생성되었으니 직접 확인해보세요!")
    
    print(f"\n🎯 사용법:")
    print(f"  1. {output_directory} 폴더에서 이미지들을 직접 확인")
    print(f"  2. 품질 검증 테스트: python image_quality_validator.py {output_directory}/01_good_quality.jpg")
    print(f"  3. 전체 폴더 테스트: python image_quality_validator.py {output_directory}")