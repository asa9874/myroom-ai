import os
import torch
import faiss
import numpy as np
import json
import pickle
from PIL import Image
from transformers import CLIPProcessor, CLIPModel, BlipProcessor, BlipForQuestionAnswering
from ultralytics import YOLO
import google.generativeai as genai
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()


class FurnitureVectorizer:
    """
    가구 추천 시스템을 위한 벡터화 엔진
    - CLIP: 이미지 임베딩
    - BLIP: VQA (시각적 질문 답변)
    - YOLO: 객체 감지
    - Gemini: LLM 기반 디자인 조언
    """
    
    def __init__(self, model_name="openai/clip-vit-base-patch32", google_api_key=None):
        """
        Args:
            model_name: CLIP 모델 이름
            google_api_key: Google API Key (None이면 .env에서 로드)
        """
        print(f"[Vectorizer] Loading CLIP model: {model_name}...")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = CLIPModel.from_pretrained(model_name).to(self.device)
        self.processor = CLIPProcessor.from_pretrained(model_name)

        print("[Vectorizer] Loading BLIP VQA model...")
        self.blip_processor = BlipProcessor.from_pretrained("Salesforce/blip-vqa-base")
        self.blip_model = BlipForQuestionAnswering.from_pretrained("Salesforce/blip-vqa-base").to(self.device)

        print("[Vectorizer] Loading YOLOv8 Object Detection model...")
        self.yolo_model = YOLO("yolov8n.pt")

        # Google API Key 설정
        api_key = google_api_key or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            print("[Warning] Google API Key를 찾을 수 없습니다. .env 파일을 확인하세요.")
        else:
            try:
                genai.configure(api_key=api_key)
                self.gemini_model = genai.GenerativeModel(
                    model_name="gemini-2.0-flash",
                    system_instruction="You are a professional interior designer. Your goal is to create visual harmony based on room context."
                )
                print("[Vectorizer] Gemini AI 연결 성공!")
            except Exception as e:
                print(f"[Vectorizer] Gemini 설정 오류: {e}")
                self.gemini_model = None

        self.dimension = 512
        self.index = faiss.IndexFlatIP(self.dimension)
        self.metadata = []

    def _get_image_embedding(self, image):
        """이미지를 512차원 CLIP 임베딩으로 변환"""
        try:
            inputs = self.processor(images=image, return_tensors="pt", padding=True).to(self.device)
            with torch.no_grad():
                features = self.model.get_image_features(**inputs)
            features = features / features.norm(p=2, dim=-1, keepdim=True)
            return features.cpu().numpy().astype('float32')
        except Exception as e:
            print(f"[Error] 이미지 처리 오류: {e}")
            return None

    def _get_text_embedding(self, text):
        """텍스트를 512차원 CLIP 임베딩으로 변환"""
        try:
            inputs = self.processor(text=[text], return_tensors="pt", padding=True).to(self.device)
            with torch.no_grad():
                features = self.model.get_text_features(**inputs)
            features = features / features.norm(p=2, dim=-1, keepdim=True)
            return features.cpu().numpy().astype('float32')
        except Exception as e:
            print(f"[Error] 텍스트 처리 오류: {e}")
            return None

    def load_database(self, index_path="furniture_index.faiss", metadata_path="furniture_metadata.pkl"):
        """기존 FAISS 인덱스와 메타데이터 로드"""
        if os.path.exists(index_path) and os.path.exists(metadata_path):
            self.index = faiss.read_index(index_path)
            with open(metadata_path, 'rb') as f:
                self.metadata = pickle.load(f)
            print(f"[DB] 로드 완료: 총 {self.index.ntotal}개의 이미지가 로드되었습니다.")
            return True
        else:
            print("[Warning] 저장된 DB 파일을 찾을 수 없습니다.")
            return False

    def search_similar(self, query_image_path=None, text_query=None, furniture_type=None, top_k=5):
        """
        쿼리 이미지 또는 텍스트로 유사한 가구 검색
        
        Args:
            query_image_path: 쿼리 이미지 경로
            text_query: 텍스트 쿼리 (예: "white leather sofa")
            furniture_type: 가구 타입 필터 (예: "sofa", "chair")
            top_k: 반환할 결과 개수
            
        Returns:
            유사도 기준 정렬된 결과 리스트
        """
        if query_image_path:
            try:
                query_vector = self._get_image_embedding(Image.open(query_image_path).convert("RGB"))
            except:
                return []
        elif text_query:
            query_vector = self._get_text_embedding(text_query)
        else:
            return []

        if query_vector is None or self.index.ntotal == 0:
            return []

        D, I = self.index.search(query_vector, min(self.index.ntotal, top_k * 2))

        results = []
        for i in range(len(I[0])):
            idx = I[0][i]
            score = D[0][i]
            meta = self.metadata[idx]

            if furniture_type and meta['furniture_type'] != furniture_type:
                continue

            results.append({
                'image_path': meta['image_path'],
                'furniture_type': meta['furniture_type'],
                'similarity': float(score)
            })

            if len(results) >= top_k:
                break

        return results

    def detect_and_crop_objects(self, image_path):
        """
        YOLO를 사용하여 이미지에서 가구 객체 감지 및 자르기
        
        Args:
            image_path: 입력 이미지 경로
            
        Returns:
            감지된 객체 정보 리스트
        """
        try:
            results = self.yolo_model(image_path)
            detected_objects = []

            # COCO 클래스 중 가구 관련 ID
            target_classes = [56, 57, 59, 60, 74, 75]  # chair, sofa, bed, table, etc.

            for r in results:
                boxes = r.boxes
                for box in boxes:
                    cls_id = int(box.cls[0])
                    if cls_id in target_classes:
                        label_name = self.yolo_model.names[cls_id]
                        x1, y1, x2, y2 = box.xyxy[0].tolist()

                        orig_img = Image.open(image_path).convert("RGB")
                        crop = orig_img.crop((x1, y1, x2, y2))

                        detected_objects.append({
                            "label": label_name,
                            "box": (x1, y1, x2, y2),
                            "image": crop
                        })
            return detected_objects
        except Exception as e:
            print(f"[Error] YOLO 감지 오류: {e}")
            return []

    def get_image_attributes(self, image_path):
        """
        이미지 분석: 스타일, 색상, 재질 추출 및 객체 감지
        
        Args:
            image_path: 분석할 이미지 경로
            
        Returns:
            (style, color, material, detailed_names, detected_items)
        """
        try:
            image = Image.open(image_path).convert("RGB")

            # 1. 글로벌 컨텍스트 (VQA)
            questions = {
                "style": "What is the interior design style of this room?",
                "color": "What is the dominant color of this room?",
                "material": "What is the main material of the furniture?"
            }
            answers = {}
            for key, question in questions.items():
                inputs = self.blip_processor(image, question, return_tensors="pt").to(self.device)
                with torch.no_grad():
                    out = self.blip_model.generate(**inputs)
                answers[key] = self.blip_processor.decode(out[0], skip_special_tokens=True)

            # 2. 객체 감지 (YOLO)
            detected_items = self.detect_and_crop_objects(image_path)

            # 3. 로컬 컨텍스트 분석 (객체별 VQA)
            detailed_objects = []
            for item in detected_items:
                if item['image'].size[0] < 30 or item['image'].size[1] < 30:
                    continue

                local_q = f"What is the color and material of this {item['label']}?"
                inputs = self.blip_processor(item['image'], local_q, return_tensors="pt").to(self.device)
                with torch.no_grad():
                    out = self.blip_model.generate(**inputs)

                desc = self.blip_processor.decode(out[0], skip_special_tokens=True)
                detailed_name = f"{desc} {item['label']}"
                detailed_objects.append(detailed_name)
                item['description'] = desc

            return answers['style'], answers['color'], answers['material'], detailed_objects, detected_items

        except Exception as e:
            print(f"[Error] 이미지 분석 오류: {e}")
            return "modern", "white", "wood", [], []

    def ask_llm_designer(self, global_context, local_objects, target_category):
        """
        Gemini LLM을 사용한 디자인 조언 요청
        
        Args:
            global_context: 방의 전체 스타일, 색상, 재질 정보
            local_objects: 기존 가구 목록
            target_category: 추천받을 가구 카테고리
            
        Returns:
            (reasoning, search_query) - 디자인 조언과 CLIP 검색 쿼리
        """
        if not self.gemini_model:
            fallback_query = f"{global_context.get('color', 'white')} {global_context.get('style', 'modern')} {target_category}"
            return "AI 분석이 불가능합니다. 기본값으로 추천합니다.", fallback_query

        try:
            objects_str = ", ".join(local_objects) if local_objects else "Empty room"

            prompt = f"""
            Analyze the user's room context and existing furniture to recommend the best style for a new item.

            [Room Info]
            - Overall Style: {global_context.get('style', 'modern')}
            - Dominant Color: {global_context.get('color', 'white')}
            - Main Material: {global_context.get('material', 'wood')}

            [Existing Furniture]
            {objects_str}

            [User Wants to Buy]
            {target_category}

            Based on the existing furniture, suggest the best design for the '{target_category}'.
            If the room has heavy materials (leather), suggest something lighter. If it's too plain, suggest a point color.

            output must be a JSON object with this schema:
            {{
                "reasoning": "A polite explanation in Korean (2-3 sentences)",
                "search_query": "English search query for CLIP (Format: Color Material Style Category)"
            }}
            """

            response = self.gemini_model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )

            result = json.loads(response.text)
            reasoning = result.get('reasoning', "디자인 조언을 생성하지 못했습니다.")
            search_query = result.get('search_query', f"{global_context.get('color', 'white')} {global_context.get('style', 'modern')} {target_category}")

            return reasoning, search_query

        except Exception as e:
            print(f"[Error] Gemini 오류: {e}")
            fallback_query = f"{global_context.get('color', 'white')} {global_context.get('style', 'modern')} {target_category}"
            return "AI 분석 중 오류가 발생했습니다. 기본값으로 추천합니다.", fallback_query
