"""
실제 이미지 품질 검증 테스트

real_test_images 폴더에 있는 실제 사진들을 대상으로 
이미지 품질 검증을 수행합니다.
"""

import os
import sys
import glob
from typing import List, Dict, Any
from image_quality_validator import ImageQualityValidator, ImageQualityResult
from image_quality_helper import (
    quick_validate, 
    detailed_validate,
    validate_images_for_3d_workflow,
    filter_good_images,
    get_image_score
)


class RealImageTester:
    """실제 이미지 품질 검증 테스터"""
    
    def __init__(self, image_dir: str = "real_test_images"):
        """
        Args:
            image_dir: 실제 이미지가 들어있는 디렉토리
        """
        self.image_dir = image_dir
        self.supported_formats = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp']
        self.validator = None
        
    def find_images(self) -> List[str]:
        """디렉토리에서 지원하는 이미지 파일들을 찾습니다"""
        if not os.path.exists(self.image_dir):
            print(f"❌ 디렉토리가 존재하지 않습니다: {self.image_dir}")
            return []
        
        image_files = []
        for ext in self.supported_formats:
            # 소문자만 검색 후 실제 파일과 매칭
            pattern = os.path.join(self.image_dir, f"*{ext}")
            found_files = glob.glob(pattern)
            image_files.extend(found_files)
            
            # 대문자 확장자도 별도로 검색 (중복 방지)
            if ext != ext.upper():
                pattern_upper = os.path.join(self.image_dir, f"*{ext.upper()}")
                found_upper = glob.glob(pattern_upper)
                image_files.extend(found_upper)
        
        # 중복 제거 및 정렬 (경로 정규화로 중복 확실히 제거)
        image_files = sorted(list(set(os.path.normpath(f) for f in image_files)))
        return image_files
    
    def run_basic_test(self) -> Dict[str, Any]:
        """기본 품질 검증 테스트"""
        print("🔍 기본 품질 검증 테스트")
        print("=" * 60)
        
        image_files = self.find_images()
        if not image_files:
            return {"error": "이미지 파일을 찾을 수 없습니다"}
        
        print(f"📁 검색된 이미지: {len(image_files)}개")
        print()
        
        results = []
        passed = 0
        failed = 0
        
        for img_path in image_files:
            filename = os.path.basename(img_path)
            print(f"🖼️  검증 중: {filename}")
            
            try:
                # 빠른 검증
                is_valid = quick_validate(img_path, min_score=70)
                score = get_image_score(img_path)
                
                status = "✅ 통과" if is_valid else "❌ 실패"
                print(f"   결과: {status} ({score:.1f}점)")
                
                if is_valid:
                    passed += 1
                else:
                    failed += 1
                    # 상세 정보 표시
                    detail = detailed_validate(img_path)
                    if detail['issues']:
                        main_issue = detail['issues'][0]
                        print(f"   주요 문제: {main_issue}")
                
                results.append({
                    'filename': filename,
                    'path': img_path,
                    'is_valid': is_valid,
                    'score': score
                })
                
            except Exception as e:
                print(f"   ❌ 오류: {str(e)}")
                failed += 1
                results.append({
                    'filename': filename,
                    'path': img_path,
                    'is_valid': False,
                    'score': 0.0,
                    'error': str(e)
                })
        
        print()
        print("📊 결과 요약:")
        print(f"   총 이미지: {len(image_files)}개")
        print(f"   통과: {passed}개")
        print(f"   실패: {failed}개")
        print(f"   성공률: {(passed/len(image_files)*100):.1f}%")
        
        return {
            'total': len(image_files),
            'passed': passed,
            'failed': failed,
            'success_rate': passed/len(image_files)*100 if image_files else 0,
            'results': results
        }
    
    def run_detailed_test(self) -> Dict[str, Any]:
        """상세 품질 검증 테스트"""
        print("\n🔬 상세 품질 검증 테스트")
        print("=" * 60)
        
        image_files = self.find_images()
        if not image_files:
            return {"error": "이미지 파일을 찾을 수 없습니다"}
        
        detailed_results = []
        
        for img_path in image_files:
            filename = os.path.basename(img_path)
            print(f"\n📋 상세 분석: {filename}")
            print("-" * 40)
            
            try:
                result = detailed_validate(img_path)
                
                print(f"종합 점수: {result['overall_score']:.1f}/100")
                print(f"검증 결과: {'✅ 통과' if result['is_valid'] else '❌ 실패'}")
                
                if result['scores']:
                    print("세부 점수:")
                    for category, score in result['scores'].items():
                        # object_info는 딕셔너리이므로 제외
                        if category == 'object_info':
                            continue
                            
                        category_name = {
                            'blur': '선명도',
                            'brightness': '밝기',
                            'contrast': '대비',
                            'object': '객체완전성',
                            'composition': '구도'
                        }.get(category, category)
                        print(f"  - {category_name}: {score:.1f}")
                
                # 객체 정보 별도 표시
                if result['scores'].get('object_info'):
                    obj_info = result['scores']['object_info']
                    if obj_info['detected_objects'] > 0:
                        print(f"객체 정보:")
                        print(f"  - 감지된 객체: {obj_info['detected_objects']}개")
                        if not obj_info['is_single_object']:
                            print(f"  - 주 객체 비율: {obj_info['main_object_ratio']:.1%}")
                            print(f"  - 다중 객체 페널티: -{obj_info['multiple_objects_penalty']:.1f}점")
                        
                        if obj_info.get('warning_messages'):
                            for warning in obj_info['warning_messages'][:1]:  # 주요 경고 1개만
                                print(f"  💡 {warning}")
                
                if result['issues']:
                    print("발견된 문제:")
                    for issue in result['issues']:
                        print(f"  • {issue}")
                
                if result['recommendations']:
                    print("개선 권장사항:")
                    for rec in result['recommendations'][:2]:  # 주요 권장사항만
                        print(f"  💡 {rec}")
                
                detailed_results.append({
                    'filename': filename,
                    'path': img_path,
                    'result': result
                })
                
            except Exception as e:
                print(f"❌ 분석 실패: {str(e)}")
                detailed_results.append({
                    'filename': filename,
                    'path': img_path,
                    'error': str(e)
                })
        
        return {'detailed_results': detailed_results}
    
    def run_3d_workflow_test(self) -> Dict[str, Any]:
        """3D 워크플로우 적합성 테스트"""
        print("\n🎯 3D 워크플로우 적합성 테스트")
        print("=" * 60)
        
        image_files = self.find_images()
        if not image_files:
            return {"error": "이미지 파일을 찾을 수 없습니다"}
        
        # 3D 워크플로우 검증
        result = validate_images_for_3d_workflow(image_files, strict_mode=False)
        
        print(f"🏗️  3D 모델링 준비 상태: {'✅ 준비완료' if result['ready_for_3d'] else '❌ 준비미완료'}")
        print()
        
        if result['valid_images']:
            print("✅ 3D 모델링 가능한 이미지:")
            for img_info in result['valid_images']:
                filename = os.path.basename(img_info['path'])
                print(f"   📷 {filename} ({img_info['score']:.1f}점)")
        
        if result['invalid_images']:
            print("\n❌ 품질 개선이 필요한 이미지:")
            for img_info in result['invalid_images']:
                filename = os.path.basename(img_info['path'])
                print(f"   📷 {filename} ({img_info['score']:.1f}점)")
                if 'issues' in img_info and img_info['issues']:
                    main_issue = img_info['issues'][0]
                    print(f"      └ 주요 문제: {main_issue}")
        
        if result['workflow_recommendations']:
            print("\n💡 워크플로우 권장사항:")
            for rec in result['workflow_recommendations']:
                print(f"   {rec}")
        
        # 요약 정보
        summary = result.get('summary', {})
        if summary:
            print(f"\n📊 요약:")
            print(f"   총 이미지: {summary.get('total_images', 0)}개")
            print(f"   유효한 이미지: {summary.get('valid_images', 0)}개")
            print(f"   무효한 이미지: {summary.get('invalid_images', 0)}개")
            print(f"   성공률: {summary.get('success_rate', 0):.1f}%")
        
        return result
    
    def create_report(self, output_file: str = "quality_report.txt") -> str:
        """검증 결과 리포트 생성"""
        print(f"\n📝 상세 리포트 생성 중: {output_file}")
        
        image_files = self.find_images()
        if not image_files:
            return "이미지 파일을 찾을 수 없습니다"
        
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("이미지 품질 검증 리포트")
        report_lines.append("=" * 80)
        report_lines.append(f"검증 일시: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"검증 디렉토리: {os.path.abspath(self.image_dir)}")
        report_lines.append(f"총 이미지 수: {len(image_files)}개")
        report_lines.append("")
        
        passed_count = 0
        total_score = 0
        
        for i, img_path in enumerate(image_files, 1):
            filename = os.path.basename(img_path)
            report_lines.append(f"{i}. {filename}")
            report_lines.append("-" * 60)
            
            try:
                result = detailed_validate(img_path)
                total_score += result['overall_score']
                
                if result['is_valid']:
                    passed_count += 1
                    status = "✅ 통과"
                else:
                    status = "❌ 실패"
                
                report_lines.append(f"검증 결과: {status}")
                report_lines.append(f"종합 점수: {result['overall_score']:.1f}/100")
                
                if result['scores']:
                    report_lines.append("세부 점수:")
                    for category, score in result['scores'].items():
                        category_name = {
                            'blur': '선명도',
                            'brightness': '밝기', 
                            'contrast': '대비',
                            'object': '객체완전성',
                            'composition': '구도'
                        }.get(category, category)
                        report_lines.append(f"  - {category_name}: {score:.1f}")
                
                if result['issues']:
                    report_lines.append("발견된 문제:")
                    for issue in result['issues']:
                        report_lines.append(f"  • {issue}")
                
                if result['recommendations']:
                    report_lines.append("개선 권장사항:")
                    for rec in result['recommendations']:
                        report_lines.append(f"  💡 {rec}")
                        
            except Exception as e:
                report_lines.append(f"❌ 검증 실패: {str(e)}")
            
            report_lines.append("")
        
        # 최종 요약
        avg_score = total_score / len(image_files) if image_files else 0
        success_rate = (passed_count / len(image_files) * 100) if image_files else 0
        
        report_lines.append("=" * 80)
        report_lines.append("최종 요약")
        report_lines.append("=" * 80)
        report_lines.append(f"총 이미지: {len(image_files)}개")
        report_lines.append(f"통과한 이미지: {passed_count}개")
        report_lines.append(f"실패한 이미지: {len(image_files) - passed_count}개")
        report_lines.append(f"성공률: {success_rate:.1f}%")
        report_lines.append(f"평균 점수: {avg_score:.1f}점")
        
        # 파일로 저장
        report_content = "\n".join(report_lines)
        report_path = os.path.join(self.image_dir, output_file)
        
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report_content)
            print(f"✅ 리포트 저장 완료: {report_path}")
        except Exception as e:
            print(f"❌ 리포트 저장 실패: {e}")
        
        return report_content


def main():
    """메인 실행 함수"""
    print("📷 실제 이미지 품질 검증 테스터")
    print("=" * 80)
    
    # 테스터 초기화
    tester = RealImageTester("real_test_images")
    
    # 이미지 찾기
    images = tester.find_images()
    
    if not images:
        print("❌ real_test_images 폴더에 이미지가 없습니다!")
        print()
        print("📋 사용법:")
        print("1. real_test_images 폴더에 검증하고 싶은 이미지들을 넣어주세요")
        print("2. 지원 형식: .jpg, .jpeg, .png, .bmp, .tiff, .webp")
        print("3. 다시 이 스크립트를 실행해주세요")
        print()
        print("💡 예시:")
        print("   real_test_images/")
        print("   ├── chair1.jpg")
        print("   ├── table1.png")
        print("   └── sofa1.jpeg")
        return
    
    print(f"📁 발견된 이미지: {len(images)}개")
    print()
    
    # 사용자 선택 메뉴
    while True:
        print("🎯 테스트 옵션을 선택하세요:")
        print("1. 기본 품질 검증 (빠른 테스트)")
        print("2. 상세 품질 검증 (세부 분석)")
        print("3. 3D 워크플로우 적합성 테스트")
        print("4. 전체 테스트 + 리포트 생성")
        print("5. 종료")
        print()
        
        choice = input("선택 (1-5): ").strip()
        
        if choice == '1':
            tester.run_basic_test()
        elif choice == '2':
            tester.run_detailed_test()
        elif choice == '3':
            tester.run_3d_workflow_test()
        elif choice == '4':
            print("\n🚀 전체 테스트 실행 중...")
            tester.run_basic_test()
            tester.run_detailed_test()
            tester.run_3d_workflow_test()
            tester.create_report()
        elif choice == '5':
            print("\n👋 테스트를 종료합니다.")
            break
        else:
            print("❌ 잘못된 선택입니다. 1-5 중에서 선택해주세요.")
        
        print("\n" + "-" * 80 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 사용자에 의해 중단되었습니다.")
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()