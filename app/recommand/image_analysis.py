"""
이미지 분석 및 AI 기반 추천 모듈

YOLO를 사용한 객체 감지, BLIP를 사용한 이미지 설명 생성,
그리고 Gemini AI를 사용한 지능형 가구 추천을 수행합니다.

주요 기능:
- YOLO를 사용한 가구 객체 감지
- BLIP를 사용한 이미지 속성 추출 (스타일, 색상, 재질)
- Gemini AI를 사용한 추천 이유 생성
"""

import os
import logging
from typing import Dict, List, Tuple, Optional
from PIL import Image
import torch

try:
    from ultralytics import YOLO
    from transformers import BlipProcessor, BlipForQuestionAnswering
    import google.genai as genai
except ImportError as e:
    print(f"Warning: Some modules not available: {e}")

logger = logging.getLogger(__name__)


class ImageAnalyzer:
    """이미지 분석 및 AI 기반 추천을 위한 클래스"""

    def __init__(self, google_api_key: Optional[str] = None, primary_model: str = None, fallback_models: List[str] = None):
        """
        이미지 분석기 초기화

        Args:
            google_api_key: Google Gemini API 키 (환경변수에서도 로드 가능)
            primary_model: 주 사용 모델 (기본값: gemini-2.0-flash)
            fallback_models: 폴백 모델 목록
        """
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Using device: {self.device}")
        
        # 모델 설정 (google-genai 패키지용)
        self.primary_model = primary_model or os.getenv('GEMINI_PRIMARY_MODEL') or 'gemini-2.5-flash'
        self.fallback_models = fallback_models or [
            'gemini-2.5-flash',
            'gemini-2.5-pro',
            'gemini-3-flash',
        ]
        self.available_models = [self.primary_model] + [m for m in self.fallback_models if m != self.primary_model]
        logger.info(f"[INFO] Gemini models configured - Primary: {self.primary_model}, Fallbacks: {self.fallback_models}")

        # YOLO 모델 로드
        logger.info("Loading YOLOv8 Object Detection model...")
        try:
            self.yolo_model = YOLO("yolov8n.pt")
            logger.info("YOLOv8 model loaded successfully")
        except Exception as e:
            logger.warning(f"Failed to load YOLOv8: {e}")
            self.yolo_model = None

        # BLIP 모델 로드
        logger.info("Loading BLIP VQA model...")
        try:
            self.blip_processor = BlipProcessor.from_pretrained(
                "Salesforce/blip-vqa-base"
            )
            self.blip_model = BlipForQuestionAnswering.from_pretrained(
                "Salesforce/blip-vqa-base"
            ).to(self.device)
            logger.info("BLIP model loaded successfully")
        except Exception as e:
            logger.warning(f"Failed to load BLIP: {e}")
            self.blip_model = None
            self.blip_processor = None

        # Gemini AI 초기화
        self.gemini_model = None
        api_key = google_api_key or os.getenv("GOOGLE_API_KEY")

        if api_key:
            try:
                # google-genai 패키지 사용
                self.gemini_model = genai.Client(api_key=api_key)
                logger.info("Gemini AI configured successfully")
            except Exception as e:
                logger.warning(f"Failed to configure Gemini: {e}")
        else:
            logger.warning("Google API Key not provided. Gemini recommendations disabled.")

    def _ask_blip_question(self, image: Image.Image, question: str) -> str:
        """
        BLIP 모델에 이미지에 대한 질문

        Args:
            image: PIL Image 객체
            question: 질문 텍스트

        Returns:
            모델의 응답 텍스트
        """
        if self.blip_model is None or self.blip_processor is None:
            logger.warning("BLIP model not available")
            return "Unknown"

        try:
            inputs = self.blip_processor(image, question, return_tensors="pt").to(
                self.device
            )
            out = self.blip_model.generate(**inputs, max_length=50)
            response = self.blip_processor.decode(out[0], skip_special_tokens=True)
            return response
        except Exception as e:
            logger.error(f"Error in BLIP question answering: {e}")
            return "Unknown"

    def detect_furniture_objects(self, image_path: str) -> Tuple[List[str], List[Dict]]:
        """
        YOLO를 사용한 이미지의 가구 객체 감지

        Args:
            image_path: 이미지 파일 경로

        Returns:
            (감지된 객체명 리스트, 상세 감지 정보 리스트)
        """
        if self.yolo_model is None:
            logger.warning("YOLO model not available")
            return [], []

        try:
            results = self.yolo_model(image_path, verbose=False)
            detected_items = []
            detected_names = []

            for result in results:
                for box in result.boxes:
                    class_name = result.names[int(box.cls)]
                    confidence = float(box.conf)

                    # 신뢰도 0.3 이상만 포함
                    if confidence > 0.3:
                        detected_items.append(
                            {
                                "name": class_name,
                                "confidence": confidence,
                                "bbox": box.xyxy.tolist(),
                            }
                        )
                        if class_name not in detected_names:
                            detected_names.append(class_name)

            logger.info(f"Detected {len(detected_names)} furniture objects")
            return detected_names, detected_items

        except Exception as e:
            logger.error(f"Error in YOLO detection: {e}")
            return [], []

    def extract_room_attributes(
        self, image_path: str, detected_items: List[str]
    ) -> Tuple[str, str, str]:
        """
        BLIP를 사용한 방의 속성 추출 (스타일, 색상, 재질)

        Args:
            image_path: 이미지 파일 경로
            detected_items: YOLO로 감지된 객체명 리스트

        Returns:
            (스타일, 색상, 재질) 튜플
        """
        if not os.path.exists(image_path):
            logger.error(f"Image not found: {image_path}")
            return "Modern", "Neutral", "Mixed"

        try:
            image = Image.open(image_path).convert("RGB")

            # 방의 전체 스타일 분석
            style = self._ask_blip_question(image, "What is the style of this room?")

            # 색상 분석
            color = self._ask_blip_question(
                image, "What is the dominant color scheme in this room?"
            )

            # 재질 분석
            material = self._ask_blip_question(
                image, "What materials are visible in this room?"
            )

            logger.info(
                f"Room attributes extracted - Style: {style}, Color: {color}, Material: {material}"
            )
            return style, color, material

        except Exception as e:
            logger.error(f"Error extracting room attributes: {e}")
            return "Modern", "Neutral", "Mixed"

    def generate_recommendation_query(
        self,
        room_context: Dict,
        detected_furniture: List[str],
        target_category: str,
    ) -> Tuple[str, str]:
        """
        Gemini AI를 사용한 추천 쿼리 및 이유 생성
        모델 선택 및 자동 폴백 기능 포함

        Args:
            room_context: 방의 속성 정보 (style, color, material)
            detected_furniture: 감지된 가구 목록
            target_category: 추천할 가구 카테고리

        Returns:
            (추천 이유, 검색 쿼리) 튜플
        """
        if self.gemini_model is None:
            logger.warning("Gemini model not available")
            return "No reasoning available", target_category

        # Gemini에게 물어볼 프롬프트 구성
        furniture_str = ", ".join(detected_furniture) if detected_furniture else "None"

        prompt = f"""
Based on the room analysis:
- Style: {room_context.get('style', 'Unknown')}
- Color: {room_context.get('color', 'Unknown')}
- Material: {room_context.get('material', 'Unknown')}
- Existing Furniture: {furniture_str}

Provide a recommendation for a {target_category} that would fit well.
Format your response as:
1. Reasoning: [explanation]
2. Search Query: [specific description for searching furniture]
"""

        # 모델 선택 및 재시도 로직
        for model_idx, model in enumerate(self.available_models):
            try:
                logger.info(f"[Model {model_idx + 1}/{len(self.available_models)}] Calling Gemini API with model: {model}")
                
                # google-genai API 호출
                response = self.gemini_model.models.generate_content(
                    model=model,
                    contents=prompt
                )
                
                logger.info(f"[SUCCESS] Gemini API response received from {model}: {response.text[:100]}...")
                response_text = response.text

                # 응답 파싱
                lines = response_text.split("\n")
                reasoning = "Professional recommendation"
                search_query = f"{room_context.get('style', 'modern')} {target_category}"

                for line in lines:
                    if "Reasoning:" in line or "reasoning:" in line:
                        reasoning = line.split(":", 1)[1].strip()
                    elif "Search Query:" in line or "search query:" in line:
                        search_query = line.split(":", 1)[1].strip()

                logger.info(f"[SUCCESS] Generated recommendation - Reasoning: {reasoning[:50]}... with model: {model}")
                return reasoning, search_query

            except Exception as e:
                error_code = getattr(e, 'code', 'UNKNOWN')
                logger.warning(f"[Model {model_idx + 1}/{len(self.available_models)}] Error with '{model}': {error_code} - {str(e)[:100]}")
                
                # 마지막 모델도 실패한 경우
                if model_idx == len(self.available_models) - 1:
                    logger.error(f"[FAILED] All {len(self.available_models)} models failed. Using fallback response.")
                    return "Professional recommendation", f"{room_context.get('style', 'modern')} {target_category}"
                else:
                    logger.info(f"[RETRY] Trying next model ({model_idx + 2}/{len(self.available_models)})...")
                    continue
        
        # 루프를 벗어난 경우 (정상적인 반환이 없음)
        logger.warning("Unexpected flow: Using default values")
        return "Professional recommendation", f"{room_context.get('style', 'modern')} {target_category}"

    def analyze_image_comprehensive(
        self, image_path: str, target_category: str = "chair"
    ) -> Dict:
        """
        이미지의 종합적인 분석 (YOLO + BLIP + Gemini)

        Args:
            image_path: 이미지 파일 경로
            target_category: 추천할 가구 카테고리

        Returns:
            분석 결과 딕셔너리
        """
        logger.info(f"Starting comprehensive image analysis: {image_path}")

        # 1. YOLO로 가구 객체 감지
        detected_names, detected_items = self.detect_furniture_objects(image_path)

        # 2. BLIP로 방의 속성 추출
        style, color, material = self.extract_room_attributes(image_path, detected_names)

        # 3. Gemini로 추천 생성
        room_context = {"style": style, "color": color, "material": material}
        reasoning, search_query = self.generate_recommendation_query(
            room_context, detected_names, target_category
        )

        return {
            "room_analysis": {
                "style": style,
                "color": color,
                "material": material,
                "detected_furniture": detected_names,
                "detected_count": len(detected_items),
                "detailed_detections": detected_items,
            },
            "recommendation": {
                "target_category": target_category,
                "reasoning": reasoning,
                "search_query": search_query,
            },
        }
