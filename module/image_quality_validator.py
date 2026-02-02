"""
이미지 품질 검증 모듈

3D 모델 워크플로우에서 사용할 이미지의 품질을 검증합니다.
- 객체가 잘린 부분 없이 완전히 포함되어 있는지 확인
- 이미지의 선명도(블러 정도) 검증
- 객체의 가시성과 크기 적절성 검증
- 조명과 대비 검증

이 모듈은 독립적으로 사용 가능하며, 워크플로우에 쉽게 통합할 수 있습니다.
"""

import cv2
import numpy as np
from PIL import Image
import torch
from ultralytics import YOLO
from typing import Dict, List, Tuple, Optional, Any
import logging
import os

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ImageQualityResult:
    """이미지 품질 검증 결과를 담는 클래스"""
    
    def __init__(self):
        self.is_valid = False
        self.overall_score = 0.0  # 0-100 점수
        self.issues = []  # 발견된 문제점들
        self.recommendations = []  # 개선 권장사항
        self.details = {}  # 상세 분석 결과


class ImageQualityValidator:
    """
    이미지 품질 검증기
    
    3D 모델링에 적합한 이미지인지 다양한 기준으로 검증합니다.
    """
    
    def __init__(self, model_path: str = "yolov8n.pt", min_confidence: float = 0.5):
        """
        검증기 초기화
        
        Args:
            model_path: YOLO 모델 경로
            min_confidence: 최소 신뢰도 임계값
        """
        self.min_confidence = min_confidence
        self.model = None
        
        # YOLO 모델 로드 (선택적)
        if os.path.exists(model_path):
            try:
                self.model = YOLO(model_path)
                logger.info(f"YOLO model loaded from {model_path}")
            except Exception as e:
                logger.warning(f"Failed to load YOLO model: {e}")
                self.model = None
        else:
            logger.warning(f"YOLO model not found at {model_path}")
            
        # 검증 기준 설정
        self.blur_threshold = 100.0  # Laplacian 분산 임계값
        self.min_object_ratio = 0.1  # 이미지 대비 최소 객체 비율
        self.max_object_ratio = 0.9  # 이미지 대비 최대 객체 비율
        self.min_brightness = 30    # 최소 밝기
        self.max_brightness = 225   # 최대 밝기
        self.edge_margin_ratio = 0.05  # 가장자리 여백 비율

    def validate_image(self, image_path: str) -> ImageQualityResult:
        """
        이미지 품질 종합 검증
        
        Args:
            image_path: 검증할 이미지 파일 경로
            
        Returns:
            ImageQualityResult: 검증 결과
        """
        result = ImageQualityResult()
        
        try:
            # 이미지 로드
            image = cv2.imread(image_path)
            if image is None:
                raise ValueError(f"Cannot load image from {image_path}")
                
            pil_image = Image.open(image_path)
            
            # 각각의 품질 검증 수행
            blur_score = self._check_blur(image)
            brightness_score = self._check_brightness(image)
            contrast_score = self._check_contrast(image)
            object_score, object_info = self._check_object_completeness(image)
            composition_score = self._check_composition(image)
            
            # 종합 점수 계산
            scores = {
                'blur': blur_score,
                'brightness': brightness_score,
                'contrast': contrast_score,
                'object': object_score,
                'composition': composition_score
            }
            
            # 가중 평균으로 종합 점수 계산
            weights = {
                'blur': 0.3,      # 선명도가 가장 중요
                'brightness': 0.2,
                'contrast': 0.2,
                'object': 0.2,    # 객체 완전성도 중요
                'composition': 0.1
            }
            
            result.overall_score = sum(scores[key] * weights[key] for key in scores)
            result.details = scores
            result.details['object_info'] = object_info  # 객체 상세 정보 추가
            
            # 문제점과 권장사항 수집
            self._collect_issues_and_recommendations(result, scores, object_info)
            
            # 유효성 판단 (70점 이상)
            result.is_valid = result.overall_score >= 70.0
            
            logger.info(f"Image quality validation completed. Score: {result.overall_score:.1f}")
            
        except Exception as e:
            logger.error(f"Error during image validation: {e}")
            result.is_valid = False
            result.overall_score = 0.0
            result.issues.append(f"Validation failed: {str(e)}")
            
        return result

    def _check_blur(self, image: np.ndarray) -> float:
        """
        이미지 선명도 검증 (블러 검사)
        
        Returns:
            float: 선명도 점수 (0-100)
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        # Laplacian 분산을 0-100 점수로 변환
        if laplacian_var >= self.blur_threshold * 2:
            score = 100.0
        elif laplacian_var >= self.blur_threshold:
            score = 50.0 + (laplacian_var - self.blur_threshold) / self.blur_threshold * 50.0
        else:
            score = (laplacian_var / self.blur_threshold) * 50.0
            
        return min(100.0, max(0.0, score))

    def _check_brightness(self, image: np.ndarray) -> float:
        """
        이미지 밝기 검증
        
        Returns:
            float: 밝기 점수 (0-100)
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        mean_brightness = np.mean(gray)
        
        if self.min_brightness <= mean_brightness <= self.max_brightness:
            # 적정 밝기 범위 내
            optimal_brightness = (self.min_brightness + self.max_brightness) / 2
            deviation = abs(mean_brightness - optimal_brightness) / optimal_brightness
            score = 100.0 - (deviation * 100.0)
        else:
            # 너무 어둡거나 밝음
            if mean_brightness < self.min_brightness:
                score = (mean_brightness / self.min_brightness) * 50.0
            else:
                score = (255 - mean_brightness) / (255 - self.max_brightness) * 50.0
                
        return min(100.0, max(0.0, score))

    def _check_contrast(self, image: np.ndarray) -> float:
        """
        이미지 대비 검증
        
        Returns:
            float: 대비 점수 (0-100)
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        contrast = np.std(gray)
        
        # 대비를 0-100 점수로 변환 (표준편차 기준)
        if contrast >= 50:
            score = 100.0
        elif contrast >= 25:
            score = 50.0 + (contrast - 25) / 25 * 50.0
        else:
            score = (contrast / 25) * 50.0
            
        return min(100.0, max(0.0, score))

    def _check_object_completeness(self, image: np.ndarray) -> Tuple[float, Dict[str, Any]]:
        """
        객체 완전성 검증 (잘림 여부 확인 + 다중 객체 처리)
        
        Returns:
            Tuple[float, Dict]: (객체 완전성 점수, 상세 정보)
        """
        object_info = {
            'detected_objects': 0,
            'is_single_object': True,
            'main_object_ratio': 0.0,
            'multiple_objects_penalty': 0.0,
            'warning_messages': []
        }
        
        if self.model is None:
            # YOLO 모델이 없는 경우 기본 검증
            score = self._check_object_completeness_basic(image)
            return score, object_info
        
        try:
            # YOLO를 사용한 객체 검출
            results = self.model(image, conf=self.min_confidence)
            detected_boxes = results[0].boxes
            
            if len(detected_boxes) == 0:
                # 객체가 감지되지 않음
                object_info['warning_messages'].append("객체가 감지되지 않았습니다")
                return 20.0, object_info
            
            h, w = image.shape[:2]
            img_area = w * h
            object_info['detected_objects'] = len(detected_boxes)
            
            # 여러 객체 감지 시 처리
            if len(detected_boxes) > 1:
                object_info['is_single_object'] = False
                
                # 객체 크기별로 정렬 (큰 것부터)
                boxes_with_area = []
                for box in detected_boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    area = (x2 - x1) * (y2 - y1)
                    boxes_with_area.append((box, area))
                
                boxes_with_area.sort(key=lambda x: x[1], reverse=True)
                
                # 가장 큰 객체와 나머지 객체들의 크기 비교
                main_box, main_area = boxes_with_area[0]
                main_ratio = main_area / img_area
                object_info['main_object_ratio'] = main_ratio
                
                # 주 객체가 전체 이미지의 50% 이상이면 괜찮음
                if main_ratio >= 0.5:
                    object_info['warning_messages'].append(
                        f"주 객체가 명확하지만 {len(detected_boxes)}개 객체가 감지되었습니다"
                    )
                    # 어느정도 허용, 약간의 감점
                    object_info['multiple_objects_penalty'] = min(len(detected_boxes) * 5, 20)
                else:
                    # 주 객체가 불분명함
                    object_info['warning_messages'].append(
                        f"주 객체가 불분명합니다 ({len(detected_boxes)}개 객체 감지, 최대 객체 비율: {main_ratio:.1%})"
                    )
                    object_info['multiple_objects_penalty'] = min(len(detected_boxes) * 15, 50)
                
                # 가장 큰 객체를 기준으로 평가
                main_score = self._evaluate_single_object(main_box, w, h, img_area)
            else:
                # 단일 객체
                object_info['warning_messages'].append("단일 객체가 잘 감지되었습니다")
                main_score = self._evaluate_single_object(detected_boxes[0], w, h, img_area)
                main_box_coords = detected_boxes[0].xyxy[0].cpu().numpy()
                x1, y1, x2, y2 = main_box_coords
                object_info['main_object_ratio'] = (x2-x1) * (y2-y1) / img_area
            
            # 여러 객체 페널티 적용
            final_score = main_score - object_info['multiple_objects_penalty']
            return max(0.0, final_score), object_info
            
        except Exception as e:
            logger.warning(f"Error in object detection: {e}")
            score = self._check_object_completeness_basic(image)
            object_info['warning_messages'].append(f"객체 감지 오류: {str(e)}")
            return score, object_info
    
    def _evaluate_single_object(self, box, w: int, h: int, img_area: int) -> float:
        """단일 객체에 대한 평가"""
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
        
        # 객체가 이미지 경계에 닿아있는지 확인
        margin = min(w, h) * self.edge_margin_ratio
        is_complete = (
            x1 > margin and y1 > margin and 
            x2 < (w - margin) and y2 < (h - margin)
        )
        
        # 객체 크기 적절성 확인
        obj_area = (x2 - x1) * (y2 - y1)
        obj_ratio = obj_area / img_area
        
        size_score = 100.0
        if obj_ratio < self.min_object_ratio:
            size_score = (obj_ratio / self.min_object_ratio) * 100.0
        elif obj_ratio > self.max_object_ratio:
            size_score = 100.0 - ((obj_ratio - self.max_object_ratio) / (1.0 - self.max_object_ratio)) * 50.0
        
        completeness_score = 100.0 if is_complete else 50.0
        return (size_score + completeness_score) / 2

    def _check_object_completeness_basic(self, image: np.ndarray) -> float:
        """
        기본적인 객체 완전성 검증 (YOLO 없이)
        
        Returns:
            float: 기본 완전성 점수 (0-100)
        """
        # 가장자리 픽셀들의 활성도를 확인하여 잘림 여부 추정
        h, w = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # 가장자리 영역 정의
        margin = int(min(h, w) * 0.05)
        edges = [
            gray[:margin, :],      # 상단
            gray[-margin:, :],     # 하단
            gray[:, :margin],      # 좌측
            gray[:, -margin:]      # 우측
        ]
        
        # 각 가장자리의 활성도 계산
        edge_activities = []
        for edge in edges:
            activity = np.std(edge)  # 표준편차로 활성도 측정
            edge_activities.append(activity)
        
        # 가장자리 활성도가 높으면 객체가 잘렸을 가능성이 높음
        avg_activity = np.mean(edge_activities)
        center_activity = np.std(gray[h//4:3*h//4, w//4:3*w//4])
        
        if center_activity > 0:
            edge_ratio = avg_activity / center_activity
            score = 100.0 - min(edge_ratio * 50.0, 80.0)  # 최대 80점 감점
        else:
            score = 50.0  # 중앙 활성도가 0인 경우
            
        return max(20.0, score)  # 최소 20점 보장

    def _check_composition(self, image: np.ndarray) -> float:
        """
        이미지 구도 검증
        
        Returns:
            float: 구도 점수 (0-100)
        """
        h, w = image.shape[:2]
        
        # 종횡비 검증
        aspect_ratio = w / h
        ideal_ratios = [1.0, 4/3, 3/2, 16/9]  # 일반적인 좋은 종횡비들
        
        ratio_score = 50.0
        for ideal_ratio in ideal_ratios:
            deviation = abs(aspect_ratio - ideal_ratio) / ideal_ratio
            if deviation < 0.1:  # 10% 이내 편차
                ratio_score = 100.0
                break
            elif deviation < 0.3:  # 30% 이내 편차
                ratio_score = max(ratio_score, 80.0)
        
        # 해상도 적절성 검증
        total_pixels = w * h
        if total_pixels >= 1920 * 1080:  # Full HD 이상
            resolution_score = 100.0
        elif total_pixels >= 1280 * 720:  # HD 이상
            resolution_score = 80.0
        elif total_pixels >= 640 * 480:  # VGA 이상
            resolution_score = 60.0
        else:
            resolution_score = 30.0
        
        return (ratio_score + resolution_score) / 2

    def _collect_issues_and_recommendations(self, result: ImageQualityResult, scores: Dict[str, float], object_info: Dict[str, Any] = None):
        """문제점과 권장사항 수집"""
        
        if scores['blur'] < 70:
            result.issues.append("이미지가 흐릿합니다")
            result.recommendations.append("더 선명한 이미지를 촬영하거나 카메라 초점을 맞춰주세요")
        
        if scores['brightness'] < 70:
            if scores['brightness'] < 30:
                result.issues.append("이미지가 너무 어둡습니다")
                result.recommendations.append("조명을 개선하거나 노출을 높여주세요")
            else:
                result.issues.append("이미지가 너무 밝습니다")
                result.recommendations.append("조명을 줄이거나 노출을 낮춰주세요")
        
        if scores['contrast'] < 70:
            result.issues.append("이미지의 대비가 부족합니다")
            result.recommendations.append("배경과 객체 간의 대비를 높여주세요")
        
        # 객체 관련 이슈 처리
        if scores['object'] < 70:
            if object_info and not object_info['is_single_object']:
                result.issues.append(f"{object_info['detected_objects']}개 객체가 감지되었습니다")
                if object_info['main_object_ratio'] < 0.5:
                    result.recommendations.append("주 객체가 더 명확하게 나오도록 촬영해주세요")
                else:
                    result.recommendations.append("가능하면 단일 객체만 프레임에 포함되도록 촬영해주세요")
            else:
                result.issues.append("객체가 잘렸거나 크기가 부적절합니다")
                result.recommendations.append("객체 전체가 프레임 안에 들어오도록 촬영하고, 적절한 거리를 유지해주세요")
        
        if scores['composition'] < 70:
            result.issues.append("이미지 구도나 해상도가 부적절합니다")
            result.recommendations.append("적절한 종횡비와 고해상도로 촬영해주세요")
        
        # 객체 정보의 경고 메시지 추가
        if object_info and object_info.get('warning_messages'):
            for warning in object_info['warning_messages']:
                if "감지되지 않았습니다" in warning:
                    result.issues.append("객체가 명확하게 감지되지 않았습니다")
                    result.recommendations.append("객체가 더 명확하게 보이도록 배경과 대비를 높여주세요")

    def validate_batch(self, image_paths: List[str]) -> List[Tuple[str, ImageQualityResult]]:
        """
        여러 이미지 일괄 검증
        
        Args:
            image_paths: 검증할 이미지 파일 경로들
            
        Returns:
            List[Tuple[str, ImageQualityResult]]: (파일경로, 검증결과) 튜플의 리스트
        """
        results = []
        for image_path in image_paths:
            try:
                result = self.validate_image(image_path)
                results.append((image_path, result))
                logger.info(f"Validated {image_path}: {result.overall_score:.1f} points")
            except Exception as e:
                logger.error(f"Failed to validate {image_path}: {e}")
                error_result = ImageQualityResult()
                error_result.is_valid = False
                error_result.issues.append(f"Validation error: {str(e)}")
                results.append((image_path, error_result))
        
        return results

    def get_validation_summary(self, results: List[Tuple[str, ImageQualityResult]]) -> Dict[str, Any]:
        """
        검증 결과 요약 생성
        
        Args:
            results: validate_batch의 결과
            
        Returns:
            Dict: 검증 요약 정보
        """
        valid_count = sum(1 for _, result in results if result.is_valid)
        total_count = len(results)
        avg_score = np.mean([result.overall_score for _, result in results]) if results else 0.0
        
        return {
            'total_images': total_count,
            'valid_images': valid_count,
            'invalid_images': total_count - valid_count,
            'success_rate': (valid_count / total_count * 100) if total_count > 0 else 0.0,
            'average_score': avg_score,
            'recommendations': self._get_common_recommendations(results)
        }

    def _get_common_recommendations(self, results: List[Tuple[str, ImageQualityResult]]) -> List[str]:
        """공통 권장사항 추출"""
        recommendation_counts = {}
        
        for _, result in results:
            for rec in result.recommendations:
                recommendation_counts[rec] = recommendation_counts.get(rec, 0) + 1
        
        # 빈도순으로 정렬하여 상위 권장사항 반환
        common_recs = sorted(recommendation_counts.items(), key=lambda x: x[1], reverse=True)
        return [rec for rec, count in common_recs if count > len(results) * 0.3]  # 30% 이상 등장한 권장사항


def main():
    """테스트 및 사용 예시"""
    import sys
    import glob
    
    # 검증기 초기화
    validator = ImageQualityValidator()
    
    if len(sys.argv) < 2:
        print("Usage: python image_quality_validator.py <image_path_or_directory>")
        print("Example: python image_quality_validator.py test_image.jpg")
        print("Example: python image_quality_validator.py ./images/")
        return
    
    input_path = sys.argv[1]
    
    # 단일 파일인지 디렉토리인지 확인
    if os.path.isfile(input_path):
        # 단일 이미지 검증
        print(f"\n=== 이미지 품질 검증: {input_path} ===")
        result = validator.validate_image(input_path)
        
        print(f"검증 결과: {'✅ 통과' if result.is_valid else '❌ 실패'}")
        print(f"종합 점수: {result.overall_score:.1f}/100")
        print(f"세부 점수: {result.details}")
        
        if result.issues:
            print("\n발견된 문제점:")
            for issue in result.issues:
                print(f"  - {issue}")
        
        if result.recommendations:
            print("\n개선 권장사항:")
            for rec in result.recommendations:
                print(f"  - {rec}")
                
    elif os.path.isdir(input_path):
        # 디렉토리 내 모든 이미지 검증
        print(f"\n=== 디렉토리 일괄 검증: {input_path} ===")
        
        # 일반적인 이미지 확장자 찾기
        image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.tiff', '*.webp']
        image_paths = []
        for ext in image_extensions:
            image_paths.extend(glob.glob(os.path.join(input_path, ext)))
            image_paths.extend(glob.glob(os.path.join(input_path, ext.upper())))
        
        if not image_paths:
            print("지원하는 이미지 파일을 찾을 수 없습니다.")
            return
        
        print(f"총 {len(image_paths)}개의 이미지를 검증합니다...")
        results = validator.validate_batch(image_paths)
        
        # 결과 출력
        print("\n=== 개별 검증 결과 ===")
        for img_path, result in results:
            status = "✅ 통과" if result.is_valid else "❌ 실패"
            filename = os.path.basename(img_path)
            print(f"{filename}: {status} ({result.overall_score:.1f}점)")
        
        # 요약 정보 출력
        summary = validator.get_validation_summary(results)
        print(f"\n=== 검증 요약 ===")
        print(f"총 이미지: {summary['total_images']}개")
        print(f"통과: {summary['valid_images']}개")
        print(f"실패: {summary['invalid_images']}개")
        print(f"성공률: {summary['success_rate']:.1f}%")
        print(f"평균 점수: {summary['average_score']:.1f}점")
        
        if summary['recommendations']:
            print(f"\n공통 권장사항:")
            for rec in summary['recommendations']:
                print(f"  - {rec}")
    else:
        print(f"오류: '{input_path}'는 유효한 파일이나 디렉토리가 아닙니다.")


if __name__ == "__main__":
    main()