import os
import torch
import faiss
import numpy as np
from PIL import Image
from transformers import CLIPProcessor, CLIPModel
import pickle
import hashlib


class ImageVectorizer:
    """
    가구 이미지 DB를 벡터화하여 FAISS 인덱스 생성
    """
    
    def __init__(self, model_name="openai/clip-vit-base-patch32"):
        print(f"[ImageVectorizer] Loading CLIP model: {model_name}...")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = CLIPModel.from_pretrained(model_name).to(self.device)
        self.processor = CLIPProcessor.from_pretrained(model_name)

        # 벡터 DB 초기화 (CLIP output dim: 512)
        self.dimension = 512
        self.index = faiss.IndexFlatIP(self.dimension)
        self.metadata = []  # 각 벡터와 매핑되는 메타데이터 {'furniture_type': str, 'image_path': str}

    def _get_image_embedding(self, image):
        """이미지 객체를 정규화된 벡터로 반환"""
        try:
            inputs = self.processor(images=image, return_tensors="pt", padding=True).to(self.device)
            with torch.no_grad():
                features = self.model.get_image_features(**inputs)

            # 벡터 정규화 (L2 Norm)
            features = features / features.norm(p=2, dim=-1, keepdim=True)
            return features.cpu().numpy().astype('float32')
        except Exception as e:
            print(f"[Error] 이미지 처리 오류: {e}")
            return None

    def build_database(self, data_dir="./data"):
        """
        data_dir 내의 가구 데이터셋을 순회하여 벡터 DB 구축
        
        디렉토리 구조:
        data/
        ├── bed/
        │   ├── bed1.jpg
        │   └── bed2.jpg
        ├── chair/
        │   ├── chair1.jpg
        │   └── chair2.jpg
        └── sofa/
            └── sofa1.jpg
        
        Args:
            data_dir: 가구 데이터셋의 루트 디렉토리 경로
        """
        if not os.path.exists(data_dir):
            print(f"[Error] '{data_dir}' 디렉토리가 없습니다.")
            return

        print(f"[DB Build] '{data_dir}'에서 데이터베이스 구축 중...")

        # 가구 폴더 찾기 (예: bed, chair, sofa 등)
        furniture_folders = [f for f in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, f))]

        if not furniture_folders:
            print("[Warning] 가구 데이터셋이 없습니다.")
            return

        vectors_list = []
        metadata_list = []
        seen_hashes = set()  # 중복 이미지 제거 용도

        for folder in furniture_folders:
            folder_path = os.path.join(data_dir, folder)
            furniture_type = folder.replace('_dataset', '').replace(' dataset', '')

            print(f"[DB Build] Processing {furniture_type}...")
            files = [f for f in os.listdir(folder_path) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]

            for file in files:
                path = os.path.join(folder_path, file)
                try:
                    image = Image.open(path).convert("RGB")
                    img_hash = hashlib.sha256(image.tobytes()).hexdigest()

                    # 중복 이미지 스킵
                    if img_hash in seen_hashes:
                        print(f"[Skip] 중복 이미지: {path}")
                        continue

                    seen_hashes.add(img_hash)

                    vec = self._get_image_embedding(image)
                    if vec is not None:
                        vectors_list.append(vec)
                        metadata_list.append({'furniture_type': furniture_type, 'image_path': path})
                except Exception as e:
                    print(f"[Error] {path} 처리 오류: {e}")

        if vectors_list:
            # numpy array로 변환하여 차원 맞추기 (N, 512)
            database_matrix = np.vstack(vectors_list)
            self.index.add(database_matrix)
            self.metadata = metadata_list
            print(f"[DB Build] 완료: 총 {self.index.ntotal}개의 이미지가 인덱싱되었습니다.")
        else:
            print("[Warning] DB 구축 실패: 처리된 이미지가 없습니다.")

    def save_database(self, index_path="furniture_index.faiss", metadata_path="furniture_metadata.pkl"):
        """벡터 DB와 메타데이터를 파일로 저장"""
        faiss.write_index(self.index, index_path)
        with open(metadata_path, 'wb') as f:
            pickle.dump(self.metadata, f)
        print(f"[DB Save] 완료: {index_path}, {metadata_path}")

    def load_database(self, index_path="furniture_index.faiss", metadata_path="furniture_metadata.pkl"):
        """저장된 벡터 DB와 메타데이터를 로드"""
        if os.path.exists(index_path) and os.path.exists(metadata_path):
            self.index = faiss.read_index(index_path)
            with open(metadata_path, 'rb') as f:
                self.metadata = pickle.load(f)
            print(f"[DB Load] 완료: 총 {self.index.ntotal}개의 이미지가 로드되었습니다.")
        else:
            print("[Warning] 저장된 DB 파일을 찾을 수 없습니다.")

    def search_similar(self, query_image_path, furniture_type=None, top_k=5):
        """
        쿼리 이미지와 유사한 가구 검색
        
        Args:
            query_image_path: 쿼리 이미지 경로
            furniture_type: 가구 타입 필터 (선택사항)
            top_k: 반환할 결과 개수
            
        Returns:
            유사도 기준 정렬된 결과 리스트
        """
        print(f"[Search] 유사 이미지 검색 중: {query_image_path}")
        if furniture_type:
            print(f"[Search] 필터링: {furniture_type}")

        try:
            query_image = Image.open(query_image_path).convert("RGB")
            query_vector = self._get_image_embedding(query_image)
        except Exception as e:
            print(f"[Error] 쿼리 이미지 로드 오류 {query_image_path}: {e}")
            return []

        if query_vector is None or self.index.ntotal == 0:
            return []

        # 검색
        D, I = self.index.search(query_vector, self.index.ntotal)

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


# --- 실행 예시 ---
if __name__ == "__main__":
    vectorizer = ImageVectorizer()

    # DB 구축 (처음 실행 시)
    vectorizer.build_database("./data")
    vectorizer.save_database()

    # 다음 부터는 저장된 DB 로드
    # vectorizer.load_database()

    # 검색 예시 (쿼리 이미지 경로 지정)
    query_image = "query_image.jpg"
    if os.path.exists(query_image):
        # 전체 검색
        results = vectorizer.search_similar(query_image, top_k=3)
        print("\n=== 전체 검색 결과 ===")
        for res in results:
            print(f"{res['furniture_type']}: {res['image_path']} (유사도: {res['similarity']:.4f})")

        # 특정 가구 타입으로 검색 (예: chair)
        chair_results = vectorizer.search_similar(query_image, furniture_type="chair", top_k=3)
        print("\n=== 의자 검색 결과 ===")
        for res in chair_results:
            print(f"{res['furniture_type']}: {res['image_path']} (유사도: {res['similarity']:.4f})")
    else:
        print("[Error] 쿼리 이미지를 찾을 수 없습니다. 이미지 경로를 지정하세요.")
