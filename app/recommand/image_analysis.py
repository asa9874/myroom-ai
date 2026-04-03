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
import tempfile
import re
from urllib.parse import urlparse
from typing import Dict, List, Tuple, Optional
from PIL import Image
import torch
import requests

try:
    from ultralytics import YOLO
    from transformers import BlipProcessor, BlipForQuestionAnswering, pipeline
    import google.genai as genai
except ImportError as e:
    print(f"Warning: Some modules not available: {e}")

logger = logging.getLogger(__name__)


YOLO_CLASS_KO_MAP = {
    "person": "사람",
    "bicycle": "자전거",
    "car": "자동차",
    "motorcycle": "오토바이",
    "airplane": "비행기",
    "bus": "버스",
    "train": "기차",
    "truck": "트럭",
    "boat": "보트",
    "traffic light": "신호등",
    "fire hydrant": "소화전",
    "stop sign": "정지 표지판",
    "parking meter": "주차요금계",
    "bench": "벤치",
    "bird": "새",
    "cat": "고양이",
    "dog": "개",
    "horse": "말",
    "sheep": "양",
    "cow": "소",
    "elephant": "코끼리",
    "bear": "곰",
    "zebra": "얼룩말",
    "giraffe": "기린",
    "backpack": "백팩",
    "umbrella": "우산",
    "handbag": "핸드백",
    "tie": "넥타이",
    "suitcase": "여행가방",
    "frisbee": "프리스비",
    "skis": "스키",
    "snowboard": "스노보드",
    "sports ball": "스포츠 공",
    "kite": "연",
    "baseball bat": "야구배트",
    "baseball glove": "야구글러브",
    "skateboard": "스케이트보드",
    "surfboard": "서핑보드",
    "tennis racket": "테니스 라켓",
    "bottle": "병",
    "wine glass": "와인잔",
    "cup": "컵",
    "fork": "포크",
    "knife": "칼",
    "spoon": "숟가락",
    "bowl": "그릇",
    "banana": "바나나",
    "apple": "사과",
    "sandwich": "샌드위치",
    "orange": "오렌지",
    "broccoli": "브로콜리",
    "carrot": "당근",
    "hot dog": "핫도그",
    "pizza": "피자",
    "donut": "도넛",
    "cake": "케이크",
    "chair": "의자",
    "couch": "소파",
    "potted plant": "화분",
    "bed": "침대",
    "dining table": "식탁",
    "toilet": "변기",
    "tv": "TV",
    "laptop": "노트북",
    "mouse": "마우스",
    "remote": "리모컨",
    "keyboard": "키보드",
    "cell phone": "휴대폰",
    "book": "책",
    "clock": "시계",
    "vase": "화병",
    "microwave": "전자레인지",
    "oven": "오븐",
    "toaster": "토스터",
    "sink": "싱크대",
    "refrigerator": "냉장고",
    "scissors": "가위",
    "teddy bear": "테디베어",
    "hair drier": "헤어드라이어",
    "toothbrush": "칫솔",
}


BLIP_TERM_KO_MAP = {
    "minimalist": "미니멀",
    "minimal": "미니멀",
    "modern": "모던",
    "contemporary": "컨템포러리",
    "classic": "클래식",
    "vintage": "빈티지",
    "scandinavian": "스칸디나비안",
    "industrial": "인더스트리얼",
    "bohemian": "보헤미안",
    "rustic": "러스틱",
    "white": "화이트",
    "black": "블랙",
    "gray": "그레이",
    "grey": "그레이",
    "beige": "베이지",
    "ivory": "아이보리",
    "cream": "크림",
    "brown": "브라운",
    "blue": "블루",
    "green": "그린",
    "red": "레드",
    "yellow": "옐로우",
    "neutral": "중립",
    "warm": "웜",
    "cool": "쿨",
    "wooden": "목재",
    "wood": "목재",
    "oak": "오크",
    "walnut": "월넛",
    "pine": "파인",
    "metal": "금속",
    "steel": "스틸",
    "iron": "철",
    "glass": "유리",
    "plastic": "플라스틱",
    "leather": "가죽",
    "fabric": "패브릭",
    "cotton": "코튼",
    "stone": "석재",
    "marble": "대리석",
    "mixed": "혼합",
}


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

        # BLIP 응답용 경량 번역 모델 로드 (EN -> KO)
        self.translation_model_name = os.getenv(
            "BLIP_TRANSLATION_MODEL", "Helsinki-NLP/opus-mt-en-ko"
        )
        self.translation_pipeline = None
        logger.info("Loading BLIP translation model (EN->KO)...")
        try:
            translator_device = 0 if self.device == "cuda" else -1
            self.translation_pipeline = pipeline(
                "translation_en_to_ko",
                model=self.translation_model_name,
                device=translator_device,
            )
            logger.info(
                f"BLIP translation model loaded successfully: {self.translation_model_name}"
            )
        except Exception as e:
            logger.warning(f"Failed to load translation_en_to_ko pipeline: {e}")
            try:
                translator_device = 0 if self.device == "cuda" else -1
                self.translation_pipeline = pipeline(
                    "translation",
                    model=self.translation_model_name,
                    device=translator_device,
                )
                logger.info(
                    f"BLIP translation model loaded with generic translation task: {self.translation_model_name}"
                )
            except Exception as fallback_error:
                logger.warning(f"Failed to load translation model: {fallback_error}")

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

    def _to_korean_furniture_category(self, class_name: str) -> str:
        """YOLO 클래스명을 한글 카테고리로 변환"""
        if not class_name:
            return "기타"

        normalized = class_name.strip().lower()
        return YOLO_CLASS_KO_MAP.get(normalized, class_name)

    def _translate_to_korean(self, text: str) -> str:
        """영문 텍스트를 한국어로 번역 (번역 모델 실패 시 원문 유지)"""
        if text is None:
            return "알 수 없음"

        source_text = str(text).strip()
        if not source_text:
            return "알 수 없음"

        if source_text.lower() in {"unknown", "none", "n/a"}:
            return "알 수 없음"

        translated_text = ""
        if self.translation_pipeline is None:
            translated_text = source_text
        else:
            try:
                translated = self.translation_pipeline(source_text, max_length=128)
                if translated and isinstance(translated, list):
                    translated_text = translated[0].get("translation_text", "").strip()
            except Exception as e:
                logger.warning(f"Failed to translate BLIP output '{source_text}': {e}")

        candidate = translated_text or source_text
        keyword_translated = self._keyword_translate_en_to_ko(candidate)

        if keyword_translated:
            return keyword_translated

        return source_text

    @staticmethod
    def _contains_korean(text: str) -> bool:
        if not text:
            return False
        return re.search(r"[가-힣]", text) is not None

    def _keyword_translate_en_to_ko(self, text: str) -> str:
        """번역 모델이 영문을 그대로 반환하는 경우를 대비한 키워드 치환"""
        if not text:
            return text

        translated = text
        for en_term in sorted(BLIP_TERM_KO_MAP.keys(), key=len, reverse=True):
            ko_term = BLIP_TERM_KO_MAP[en_term]
            translated = re.sub(
                rf"\b{re.escape(en_term)}\b",
                ko_term,
                translated,
                flags=re.IGNORECASE,
            )

        if self._contains_korean(translated):
            return translated

        return translated

    @staticmethod
    def _is_url(path_or_url: str) -> bool:
        if not path_or_url:
            return False
        lowered = str(path_or_url).lower()
        return lowered.startswith("http://") or lowered.startswith("https://")

    def _resolve_localhost_url_to_file(self, image_url: str) -> Optional[str]:
        """localhost URL이면 워크스페이스 내 파일 경로로 우선 해석"""
        try:
            parsed = urlparse(image_url)
        except Exception:
            return None

        host = (parsed.hostname or "").lower()
        if host not in {"localhost", "127.0.0.1"}:
            return None

        filename = os.path.basename(parsed.path or "")
        if not filename:
            return None

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        candidates = [
            os.path.join(project_root, "uploads", filename),
            os.path.join(project_root, "uploads", "images", filename),
            os.path.join(project_root, "uploads", "models", filename),
            os.path.join(project_root, filename),
            os.path.join(project_root, "data", filename),
            os.path.join(project_root, "test_images", filename),
        ]

        for candidate in candidates:
            if os.path.exists(candidate):
                logger.info(f"Resolved localhost image URL to local file: {candidate}")
                return candidate

        # 고정 경로에서 찾지 못하면 uploads 하위 전체에서 파일명을 탐색
        uploads_root = os.path.join(project_root, "uploads")
        if os.path.isdir(uploads_root):
            for root, _dirs, files in os.walk(uploads_root):
                if filename in files:
                    discovered = os.path.join(root, filename)
                    logger.info(
                        f"Resolved localhost image URL via recursive search: {discovered}"
                    )
                    return discovered

        return None

    def _prepare_image_for_analysis(
        self, image_path_or_url: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """분석 가능한 로컬 이미지 경로를 반환 (임시파일 사용 시 cleanup 경로 포함)"""
        if not image_path_or_url:
            return None, None, "이미지 경로가 비어 있습니다"

        source = str(image_path_or_url).strip()
        if not source:
            return None, None, "이미지 경로가 비어 있습니다"

        # 이미 로컬 파일이면 그대로 사용
        if not self._is_url(source):
            if os.path.exists(source):
                return source, None, None
            logger.error(f"Image not found: {source}")
            return None, None, f"이미지 파일을 찾을 수 없습니다: {source}"

        # localhost URL은 서버 호출 대신 로컬 파일 해석 우선
        local_candidate = self._resolve_localhost_url_to_file(source)
        if local_candidate:
            return local_candidate, None, None

        # 외부 URL 또는 로컬 해석 실패 시 직접 다운로드
        try:
            response = requests.get(source, timeout=10)
            response.raise_for_status()

            suffix = os.path.splitext(urlparse(source).path or "")[1] or ".jpg"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                tmp_file.write(response.content)
                temp_path = tmp_file.name

            logger.info(f"Downloaded image URL to temp file: {temp_path}")
            return temp_path, temp_path, None
        except Exception as e:
            logger.error(f"Failed to fetch image URL '{source}': {e}")
            return None, None, f"이미지 URL에 접근할 수 없습니다: {source}"

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
                    class_name_en = result.names[int(box.cls)]
                    class_name_ko = self._to_korean_furniture_category(class_name_en)
                    confidence = float(box.conf)

                    # 신뢰도 0.3 이상만 포함
                    if confidence > 0.3:
                        detected_items.append(
                            {
                                "name": class_name_ko,
                                "name_en": class_name_en,
                                "confidence": confidence,
                                "bbox": box.xyxy.tolist(),
                            }
                        )
                        if class_name_ko not in detected_names:
                            detected_names.append(class_name_ko)

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
            return "모던", "중립", "혼합"

        try:
            image = Image.open(image_path).convert("RGB")

            # 방의 전체 스타일 분석
            style_en = self._ask_blip_question(image, "What is the style of this room?")

            # 색상 분석
            color_en = self._ask_blip_question(
                image, "What is the dominant color scheme in this room?"
            )

            # 재질 분석
            material_en = self._ask_blip_question(
                image, "What materials are visible in this room?"
            )

            # BLIP 영문 응답을 경량 번역 모델로 한국어 변환
            style = self._translate_to_korean(style_en)
            color = self._translate_to_korean(color_en)
            material = self._translate_to_korean(material_en)

            logger.info(
                "Room attributes extracted - "
                f"Style: {style} (raw: {style_en}), "
                f"Color: {color} (raw: {color_en}), "
                f"Material: {material} (raw: {material_en})"
            )
            return style, color, material

        except Exception as e:
            logger.error(f"Error extracting room attributes: {e}")
            return "모던", "중립", "혼합"

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
            return "추천 사유를 생성할 수 없습니다", target_category

        # Gemini에게 물어볼 프롬프트 구성
        furniture_str = ", ".join(detected_furniture) if detected_furniture else "없음"

        prompt = f"""You are an expert interior designer. Based on the room analysis provided below, recommend a specific {target_category} that perfectly harmonizes with the space.

            [Room Context]
            - Interior Style: {room_context.get('style', 'Unknown')}
            - Dominant Color: {room_context.get('color', 'Unknown')}
            - Key Materials: {room_context.get('material', 'Unknown')}
            - Existing Furniture: {furniture_str}

            [Task & Constraints]
            1. Reasoning: Write 2-3 sentences in professional KOREAN explaining WHY this specific {target_category} fits. You MUST consider the room's style, color, materials, and how it pairs with the 'Existing Furniture'.
            2. Search Query: Provide a highly relevant, concise ENGLISH search query optimized for a 3D asset database or e-commerce search (e.g., Style + Color + Material + Category).
            3. STRICT FORMATTING: Do NOT use any Markdown formatting (no **, *, -, or #). You MUST respond EXACTLY in the format below, with no additional conversational text.

            Reasoning: [Your detailed reasoning in Korean]
            Search Query: [Highly relevant keywords for {target_category} in English]

            Example:
            Reasoning: 이 공간은 화이트 톤의 모던한 스타일로, 기존의 패브릭 소파 및 우드 테이블과 자연스럽게 어울리려면 미니멀한 디자인이 적합합니다. 따라서 깔끔한 마감의 화이트 철제 프레임이 적용된 가구를 배치하면 공간의 통일성을 유지하면서도 세련된 포인트를 줄 수 있습니다.
            Search Query: Modern white steel frame {target_category} minimal design
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

                # 응답 파싱 - 마크다운 제거 및 강화된 파싱
                response_text = response_text.replace("**", "").strip()  # 마크다운 별표 제거
                
                lines = response_text.split("\n")
                reasoning = None
                search_query = None

                for line in lines:
                    line = line.strip()
                    if not line:  # 빈 줄 스킵
                        continue
                    
                    if line.startswith("Reasoning:"):
                        reasoning = line.replace("Reasoning:", "").strip()
                    elif line.startswith("reasoning:"):
                        reasoning = line.replace("reasoning:", "").strip()
                    elif line.startswith("추천이유:"):
                        reasoning = line.replace("추천이유:", "").strip()
                    elif line.startswith("Search Query:"):
                        search_query = line.replace("Search Query:", "").strip()
                    elif line.startswith("search query:"):
                        search_query = line.replace("search query:", "").strip()
                    elif line.startswith("검색쿼리:"):
                        search_query = line.replace("검색쿼리:", "").strip()

                # 기본값 설정
                if not reasoning or reasoning == "**":
                    reasoning = (
                        f"이 {target_category}은(는) 방의 {room_context.get('color', '중립')} 톤과 "
                        f"{room_context.get('style', '모던')} 스타일에 잘 어울립니다."
                    )
                
                if not search_query or search_query == "**":
                    search_query = f"{room_context.get('style', 'modern')} {room_context.get('color', 'white')} {target_category}"

                logger.info(f"[SUCCESS] Generated recommendation - Reasoning: {reasoning[:50]}... with model: {model}")
                return reasoning, search_query

            except Exception as e:
                error_code = getattr(e, 'code', 'UNKNOWN')
                logger.warning(f"[Model {model_idx + 1}/{len(self.available_models)}] Error with '{model}': {error_code} - {str(e)[:100]}")
                
                # 마지막 모델도 실패한 경우
                if model_idx == len(self.available_models) - 1:
                    logger.error(f"[FAILED] All {len(self.available_models)} models failed. Using fallback response.")
                    return "전문가 추천을 생성하지 못했습니다", f"{room_context.get('style', 'modern')} {target_category}"
                else:
                    logger.info(f"[RETRY] Trying next model ({model_idx + 2}/{len(self.available_models)})...")
                    continue
        
        # 루프를 벗어난 경우 (정상적인 반환이 없음)
        logger.warning("Unexpected flow: Using default values")
        return "전문가 추천을 생성하지 못했습니다", f"{room_context.get('style', 'modern')} {target_category}"

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

        # URL/로컬 경로를 분석 가능한 파일로 준비
        prepared_image_path, cleanup_path, prepare_error = self._prepare_image_for_analysis(image_path)
        image_source_ok = prepared_image_path is not None

        if not prepared_image_path:
            logger.warning(f"Unable to prepare image source: {image_path}")
            detected_names, detected_items = [], []
            style, color, material = "알 수 없음", "알 수 없음", "알 수 없음"
            reasoning = "이미지를 불러오지 못해 추천 사유를 생성할 수 없습니다."
            search_query = target_category or "가구"
        else:
            # 1. YOLO로 가구 객체 감지
            detected_names, detected_items = self.detect_furniture_objects(prepared_image_path)

            # 2. BLIP로 방의 속성 추출
            style, color, material = self.extract_room_attributes(prepared_image_path, detected_names)

            # 3. Gemini로 추천 생성
            room_context = {"style": style, "color": color, "material": material}
            reasoning, search_query = self.generate_recommendation_query(
                room_context, detected_names, target_category
            )

        # 임시 다운로드 파일 정리
        if cleanup_path and os.path.exists(cleanup_path):
            try:
                os.remove(cleanup_path)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp image file '{cleanup_path}': {e}")

        return {
            "room_analysis": {
                "style": style,
                "color": color,
                "material": material,
                "detected_furniture": detected_names,
                "detected_count": len(detected_items),
                "detailed_detections": detected_items,
                "image_source_ok": image_source_ok,
                "image_error": prepare_error,
                "source_image": prepared_image_path,
            },
            "recommendation": {
                "target_category": target_category,
                "reasoning": reasoning,
                "search_query": search_query,
            },
        }
