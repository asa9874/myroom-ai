"""
다중 객체 테스트용 이미지 생성기

여러 가구나 객체가 포함된 이미지를 생성해서 
다중 객체 감지 기능을 테스트합니다.
"""

import os
from PIL import Image, ImageDraw
import numpy as np


def create_multi_object_images(output_dir="multi_object_test"):
    """다양한 객체 개수의 테스트 이미지 생성"""
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    print(f"다중 객체 테스트 이미지 생성: {os.path.abspath(output_dir)}")
    
    def create_furniture(draw, x, y, furniture_type="chair", size="medium"):
        """가구 객체 그리기"""
        if size == "small":
            scale = 0.7
        elif size == "large":
            scale = 1.3
        else:
            scale = 1.0
        
        w, h = int(100 * scale), int(120 * scale)
        
        if furniture_type == "chair":
            # 의자
            color = (139, 69, 19)
            draw.rectangle([x, y, x+w, y+h], fill=color, outline=(101, 67, 33), width=2)
            draw.rectangle([x+10, y+h-30, x+w-10, y+h], fill=(160, 82, 45), width=1)
            # 다리들
            leg_w = 8
            draw.rectangle([x+10, y+h, x+10+leg_w, y+h+20], fill=(101, 67, 33))
            draw.rectangle([x+w-20, y+h, x+w-20+leg_w, y+h+20], fill=(101, 67, 33))
            
        elif furniture_type == "table":
            # 테이블
            color = (160, 82, 45)
            draw.rectangle([x, y+h//2, x+w, y+h//2+15], fill=color, outline=(139, 69, 19), width=2)
            # 테이블 다리
            leg_w = 6
            draw.rectangle([x+5, y+h//2+15, x+5+leg_w, y+h+10], fill=(139, 69, 19))
            draw.rectangle([x+w-15, y+h//2+15, x+w-15+leg_w, y+h+10], fill=(139, 69, 19))
            
        elif furniture_type == "lamp":
            # 램프
            color = (200, 200, 100)
            # 갓
            draw.ellipse([x+w//4, y, x+3*w//4, y+h//3], fill=color, outline=(180, 180, 80), width=2)
            # 기둥
            draw.rectangle([x+w//2-3, y+h//3, x+w//2+3, y+h-10], fill=(100, 100, 100))
            # 받침
            draw.ellipse([x+w//4, y+h-15, x+3*w//4, y+h], fill=(120, 120, 120), outline=(100, 100, 100), width=1)
    
    # 1. 단일 객체 (기준)
    print("1️⃣ 단일 객체 이미지...")
    img1 = Image.new('RGB', (600, 400), color=(240, 240, 240))
    draw1 = ImageDraw.Draw(img1)
    create_furniture(draw1, 250, 140, "chair", "large")
    img1.save(os.path.join(output_dir, "01_single_object.jpg"), quality=95)
    
    # 2. 두 개 객체 - 주 객체가 명확한 경우
    print("2️⃣ 주 객체가 명확한 2개 객체...")
    img2 = Image.new('RGB', (600, 400), color=(240, 240, 240))
    draw2 = ImageDraw.Draw(img2)
    create_furniture(draw2, 200, 100, "chair", "large")  # 큰 의자
    create_furniture(draw2, 450, 200, "lamp", "small")   # 작은 램프
    img2.save(os.path.join(output_dir, "02_main_object_clear.jpg"), quality=95)
    
    # 3. 두 개 객체 - 크기가 비슷한 경우
    print("3️⃣ 크기가 비슷한 2개 객체...")
    img3 = Image.new('RGB', (600, 400), color=(240, 240, 240))
    draw3 = ImageDraw.Draw(img3)
    create_furniture(draw3, 150, 140, "chair", "medium")
    create_furniture(draw3, 350, 140, "table", "medium")
    img3.save(os.path.join(output_dir, "03_similar_size_objects.jpg"), quality=95)
    
    # 4. 세 개 객체
    print("4️⃣ 3개 객체...")
    img4 = Image.new('RGB', (600, 400), color=(240, 240, 240))
    draw4 = ImageDraw.Draw(img4)
    create_furniture(draw4, 100, 100, "chair", "medium")
    create_furniture(draw4, 250, 100, "table", "medium")
    create_furniture(draw4, 450, 150, "lamp", "small")
    img4.save(os.path.join(output_dir, "04_three_objects.jpg"), quality=95)
    
    # 5. 많은 객체들 (복잡한 씬)
    print("5️⃣ 복잡한 씬 (5개 객체)...")
    img5 = Image.new('RGB', (600, 400), color=(240, 240, 240))
    draw5 = ImageDraw.Draw(img5)
    create_furniture(draw5, 50, 50, "chair", "small")
    create_furniture(draw5, 200, 50, "table", "medium")
    create_furniture(draw5, 400, 80, "chair", "small")
    create_furniture(draw5, 500, 200, "lamp", "small")
    create_furniture(draw5, 100, 250, "chair", "small")
    img5.save(os.path.join(output_dir, "05_complex_scene.jpg"), quality=95)
    
    # 6. 주 객체가 불분명한 경우 (모든 객체가 작음)
    print("6️⃣ 주 객체 불분명...")
    img6 = Image.new('RGB', (600, 400), color=(240, 240, 240))
    draw6 = ImageDraw.Draw(img6)
    create_furniture(draw6, 100, 100, "lamp", "small")
    create_furniture(draw6, 250, 120, "lamp", "small") 
    create_furniture(draw6, 400, 110, "lamp", "small")
    img6.save(os.path.join(output_dir, "06_unclear_main_object.jpg"), quality=95)
    
    # 7. 겹치는 객체들
    print("7️⃣ 겹치는 객체들...")
    img7 = Image.new('RGB', (600, 400), color=(240, 240, 240))
    draw7 = ImageDraw.Draw(img7)
    create_furniture(draw7, 200, 120, "chair", "large")
    create_furniture(draw7, 280, 140, "table", "medium")  # 의자와 겹침
    img7.save(os.path.join(output_dir, "07_overlapping_objects.jpg"), quality=95)
    
    # 8. 배경에 작은 객체들이 많은 경우
    print("8️⃣ 주 객체 + 배경 소품들...")
    img8 = Image.new('RGB', (600, 400), color=(240, 240, 240))
    draw8 = ImageDraw.Draw(img8)
    create_furniture(draw8, 200, 100, "chair", "large")  # 주 객체
    # 배경 소품들
    create_furniture(draw8, 50, 300, "lamp", "small")
    create_furniture(draw8, 500, 50, "lamp", "small")
    create_furniture(draw8, 520, 300, "lamp", "small")
    img8.save(os.path.join(output_dir, "08_main_with_accessories.jpg"), quality=95)
    
    print(f"\n✅ 8개의 다중 객체 테스트 이미지 생성 완료!")
    print(f"📁 위치: {os.path.abspath(output_dir)}")
    
    print(f"\n📋 테스트 시나리오:")
    print("  01_single_object.jpg        - 단일 객체 (기준)")
    print("  02_main_object_clear.jpg    - 주 객체 명확 (큰 의자 + 작은 램프)")  
    print("  03_similar_size_objects.jpg - 비슷한 크기 객체들")
    print("  04_three_objects.jpg        - 3개 객체")
    print("  05_complex_scene.jpg        - 복잡한 씬 (5개 객체)")
    print("  06_unclear_main_object.jpg  - 주 객체 불분명")
    print("  07_overlapping_objects.jpg  - 겹치는 객체들")
    print("  08_main_with_accessories.jpg- 주 객체 + 배경 소품")
    
    return output_dir


if __name__ == "__main__":
    create_multi_object_images()
    
    print(f"\n🎯 테스트 방법:")
    print("python test_real_images.py")
    print("→ real_test_images 폴더에 생성된 이미지들을 넣고 테스트")
    print("\n또는:")
    print("python image_quality_validator.py multi_object_test/")
    print("→ 직접 다중 객체 이미지들 테스트")