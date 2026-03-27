#!/usr/bin/env python3
"""trimesh 및 모듈 로드 테스트"""

import sys
import os

print("=" * 60)
print(f"Python executable: {sys.executable}")
print(f"Python version: {sys.version}")
print(f"Current working directory: {os.getcwd()}")
print("=" * 60)

# trimesh 직접 테스트
print("\n[1] trimesh 직접 import 테스트")
try:
    import trimesh
    print(f"✓ trimesh imported successfully")
    print(f"  Version: {trimesh.__version__}")
    print(f"  Location: {trimesh.__file__}")
except ImportError as e:
    print(f"✗ trimesh import failed: {e}")
    sys.exit(1)

# numpy 테스트 (trimesh 의존성)
print("\n[2] numpy 테스트")
try:
    import numpy as np
    print(f"✓ numpy imported successfully")
    print(f"  Version: {np.__version__}")
except ImportError as e:
    print(f"✗ numpy import failed: {e}")

# 모델 로드 테스트
print("\n[3] .glb 파일 로드 테스트")
glb_path = r"C:\Users\asa\Desktop\data\chair\upscaling_test\pre\model3d_999_20260327_095447.glb"
if os.path.exists(glb_path):
    print(f"File exists: {glb_path}")
    print(f"File size: {os.path.getsize(glb_path)} bytes")
    
    try:
        loaded = trimesh.load(glb_path)
        print(f"Loaded type: {type(loaded).__name__}")
        
        # Scene vs Mesh 처리
        if isinstance(loaded, trimesh.Scene):
            print(f"✓ Scene detected, merging geometries...")
            meshes = []
            for geom in loaded.geometry.values():
                if isinstance(geom, trimesh.Trimesh):
                    meshes.append(geom)
            
            if meshes:
                mesh = trimesh.util.concatenate(meshes)
                print(f"  Merged {len(meshes)} meshes")
            else:
                import numpy as np
                mesh = trimesh.Trimesh(vertices=np.array([]), faces=np.array([]))
                print(f"  Scene is empty")
        else:
            mesh = loaded
        
        print(f"✓ Mesh loaded successfully!")
        print(f"  Vertices: {len(mesh.vertices)}")
        print(f"  Faces: {len(mesh.faces)}")
        print(f"  Bounds: {mesh.bounds}")
    except Exception as e:
        print(f"✗ Mesh load failed: {type(e).__name__}: {e}")
else:
    print(f"✗ File not found: {glb_path}")

# Model3DQualityEvaluator 테스트
print("\n[4] Model3DQualityEvaluator 테스트")
try:
    from app.utils.model3d_evaluator import Model3DQualityEvaluator, TRIMESH_AVAILABLE
    print(f"✓ Model3DQualityEvaluator imported successfully")
    print(f"  TRIMESH_AVAILABLE global: {TRIMESH_AVAILABLE}")
    
    evaluator = Model3DQualityEvaluator()
    print(f"  Evaluator trimesh_available: {evaluator.trimesh_available}")
    
except Exception as e:
    print(f"✗ Model3DQualityEvaluator import failed: {type(e).__name__}: {e}")

print("\n" + "=" * 60)
print("테스트 완료")
print("=" * 60)
