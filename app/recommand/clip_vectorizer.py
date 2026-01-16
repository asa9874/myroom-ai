"""
CLIP 기반 벡터화 및 가구 벡터 데이터베이스 관리

이 모듈은 OpenAI의 CLIP 모델을 사용하여 이미지 및 텍스트를 벡터로 변환하고,
FAISS 라이브러리를 사용하여 벡터 데이터베이스를 관리합니다.

주요 기능:
- 이미지 및 텍스트 임베딩 생성
- FAISS 벡터 데이터베이스 생성 및 관리
- 벡터 데이터베이스 저장 및 로드
"""

import os
import torch
import faiss
import numpy as np
import pickle
import hashlib
from PIL import Image
from transformers import CLIPProcessor, CLIPModel
from typing import List, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class CLIPVectorizer:
    """CLIP 모델을 사용한 이미지 및 텍스트 벡터화"""

    def __init__(self, model_name: str = "openai/clip-vit-base-patch32"):
        """
        CLIP 벡터라이저 초기화

        Args:
            model_name: 사용할 CLIP 모델 이름 (기본값: openai/clip-vit-base-patch32)
        """
        logger.info(f"Loading CLIP model: {model_name}...")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Using device: {self.device}")

        try:
            self.model = CLIPModel.from_pretrained(model_name).to(self.device)
            self.processor = CLIPProcessor.from_pretrained(model_name)
            logger.info("CLIP model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load CLIP model: {e}")
            raise

        self.dimension = 512  # CLIP 벡터 차원
        self.index = faiss.IndexFlatIP(self.dimension)  # Inner Product 사용
        self.metadata: List[Dict] = []

    def _get_image_embedding(self, image: Image.Image) -> Optional[np.ndarray]:
        """
        이미지에서 CLIP 임베딩 추출

        Args:
            image: PIL Image 객체

        Returns:
            정규화된 임베딩 벡터 (float32), 실패시 None
        """
        try:
            inputs = self.processor(
                images=image, return_tensors="pt", padding=True
            ).to(self.device)

            with torch.no_grad():
                features = self.model.get_image_features(**inputs)

            # L2 정규화
            features = features / features.norm(p=2, dim=-1, keepdim=True)
            return features.cpu().numpy().astype("float32")

        except Exception as e:
            logger.error(f"Error processing image: {e}")
            return None

    def _get_text_embedding(self, text: str) -> Optional[np.ndarray]:
        """
        텍스트에서 CLIP 임베딩 추출

        Args:
            text: 임베딩할 텍스트

        Returns:
            정규화된 임베딩 벡터 (float32), 실패시 None
        """
        try:
            inputs = self.processor(text=[text], return_tensors="pt", padding=True).to(
                self.device
            )

            with torch.no_grad():
                features = self.model.get_text_features(**inputs)

            # L2 정규화
            features = features / features.norm(p=2, dim=-1, keepdim=True)
            return features.cpu().numpy().astype("float32")

        except Exception as e:
            logger.error(f"Error processing text: {e}")
            return None

    def add_image_to_database(
        self, image_path: str, furniture_type: str, metadata_dict: Optional[Dict] = None
    ) -> bool:
        """
        단일 이미지를 데이터베이스에 추가 (3D 모델 생성 전 메타데이터와 함께 저장)

        메타데이터 구조:
        - model3d_id: 3D 모델 ID (DB)
        - furniture_type: 가구 타입
        - image_path: 이미지 파일 경로
        - is_shared: 공유 여부
        - member_id: 회원 ID
        - filename: 이미지 파일명

        Args:
            image_path: 이미지 파일 경로
            furniture_type: 가구 타입
            metadata_dict: 추가 메타데이터 (model3d_id, is_shared, member_id 포함)

        Returns:
            성공 여부
        """
        try:
            if not os.path.exists(image_path):
                logger.warning(f"Image not found: {image_path}")
                return False

            image = Image.open(image_path).convert("RGB")
            embedding = self._get_image_embedding(image)

            if embedding is None:
                return False

            # 메타데이터 생성 (기본 정보)
            meta = {
                "furniture_type": furniture_type,
                "image_path": image_path,
                "filename": os.path.basename(image_path),
            }

            # 추가 메타데이터 병합 (model3d_id, is_shared, member_id 등)
            if metadata_dict:
                meta.update(metadata_dict)

            # FAISS 인덱스에 추가 (이미지 임베딩 저장)
            self.index.add(embedding)
            # 메타데이터 저장 (3D 모델 생성 시 참조용)
            self.metadata.append(meta)

            logger.info(f"Added image to vector DB: {image_path}")
            logger.debug(f"Metadata: {meta}")
            return True

        except Exception as e:
            logger.error(f"Error adding image to database: {e}")
            return False

    def build_database(self, data_dir: str) -> bool:
        """
        디렉토리의 모든 이미지로 데이터베이스 구축

        디렉토리 구조:
            data_dir/
            ├── furniture_type1/
            │   ├── image1.jpg
            │   └── image2.jpg
            └── furniture_type2/
                └── image3.jpg

        Args:
            data_dir: 가구 이미지가 있는 루트 디렉토리

        Returns:
            성공 여부
        """
        if not os.path.exists(data_dir):
            logger.error(f"Data directory not found: {data_dir}")
            return False

        logger.info(f"Building database from '{data_dir}'...")

        # 가구 타입별 폴더 찾기
        furniture_folders = [
            f
            for f in os.listdir(data_dir)
            if os.path.isdir(os.path.join(data_dir, f))
        ]

        if not furniture_folders:
            logger.warning("No furniture folders found")
            return False

        total_images = 0
        supported_formats = {".jpg", ".jpeg", ".png", ".gif", ".bmp"}

        for furniture_type in furniture_folders:
            furniture_dir = os.path.join(data_dir, furniture_type)
            images = [
                f
                for f in os.listdir(furniture_dir)
                if os.path.splitext(f)[1].lower() in supported_formats
            ]

            logger.info(
                f"Processing '{furniture_type}': {len(images)} images found"
            )

            for image_file in images:
                image_path = os.path.join(furniture_dir, image_file)
                if self.add_image_to_database(image_path, furniture_type):
                    total_images += 1

        logger.info(f"Database build complete: {total_images} images added")
        return total_images > 0

    def add_images_incrementally(self, data_dir: str) -> bool:
        """
        기존 데이터베이스에 새로운 이미지를 추가

        Args:
            data_dir: 추가할 이미지가 있는 디렉토리

        Returns:
            성공 여부
        """
        if not os.path.exists(data_dir):
            logger.error(f"Data directory not found: {data_dir}")
            return False

        logger.info(f"Adding images from '{data_dir}' to existing database...")

        furniture_folders = [
            f
            for f in os.listdir(data_dir)
            if os.path.isdir(os.path.join(data_dir, f))
        ]

        if not furniture_folders:
            logger.warning("No furniture folders found")
            return False

        initial_count = self.index.ntotal
        supported_formats = {".jpg", ".jpeg", ".png", ".gif", ".bmp"}

        for furniture_type in furniture_folders:
            furniture_dir = os.path.join(data_dir, furniture_type)
            images = [
                f
                for f in os.listdir(furniture_dir)
                if os.path.splitext(f)[1].lower() in supported_formats
            ]

            for image_file in images:
                image_path = os.path.join(furniture_dir, image_file)
                self.add_image_to_database(image_path, furniture_type)

        logger.info(
            f"Added {self.index.ntotal - initial_count} new images to database"
        )
        return self.index.ntotal > initial_count

    def save_database(self, index_path: str, metadata_path: str) -> bool:
        """
        데이터베이스를 파일로 저장

        Args:
            index_path: FAISS 인덱스 저장 경로
            metadata_path: 메타데이터 저장 경로 (pickle)

        Returns:
            성공 여부
        """
        try:
            os.makedirs(os.path.dirname(index_path) or ".", exist_ok=True)
            os.makedirs(os.path.dirname(metadata_path) or ".", exist_ok=True)

            faiss.write_index(self.index, index_path)
            with open(metadata_path, "wb") as f:
                pickle.dump(self.metadata, f)

            logger.info(
                f"Database saved: {index_path}, {metadata_path} ({self.index.ntotal} items)"
            )
            return True

        except Exception as e:
            logger.error(f"Error saving database: {e}")
            return False

    def load_database(self, index_path: str, metadata_path: str) -> bool:
        """
        파일에서 데이터베이스 로드

        Args:
            index_path: FAISS 인덱스 파일 경로
            metadata_path: 메타데이터 파일 경로 (pickle)

        Returns:
            성공 여부
        """
        try:
            logger.info(f"Attempting to load database from: {index_path}")
            
            # 절대 경로로 변환
            abs_index_path = os.path.abspath(index_path)
            abs_metadata_path = os.path.abspath(metadata_path)
            
            logger.info(f"Absolute index path: {abs_index_path}")
            logger.info(f"Absolute metadata path: {abs_metadata_path}")
            
            if not os.path.exists(abs_index_path):
                logger.error(f"[FAILED] Index file not found: {abs_index_path}")
                return False
            
            if not os.path.exists(abs_metadata_path):
                logger.error(f"[FAILED] Metadata file not found: {abs_metadata_path}")
                return False

            logger.info("Loading FAISS index...")
            self.index = faiss.read_index(abs_index_path)
            
            logger.info("Loading metadata...")
            with open(abs_metadata_path, "rb") as f:
                self.metadata = pickle.load(f)

            logger.info(
                f"[SUCCESS] Database loaded successfully: {self.index.ntotal} items from {abs_index_path}"
            )
            return True

        except Exception as e:
            logger.error(f"[ERROR] Error loading database: {e}", exc_info=True)
            return False

    def get_database_info(self) -> Dict:
        """
        데이터베이스 정보 조회

        Returns:
            데이터베이스 정보 딕셔너리
        """
        categories = set()
        for meta in self.metadata:
            categories.add(meta.get("furniture_type", "unknown"))

        return {
            "total_images": self.index.ntotal,
            "vector_dimension": self.dimension,
            "categories": list(categories),
            "category_count": len(categories),
            "device": self.device,
        }
