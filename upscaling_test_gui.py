#!/usr/bin/env python3
"""
업스케일링 & 3D 모델 품질 테스트 - 독립 실행형 GUI

기존 mainApp 없이 독립적으로 실행 가능한 GUI입니다.
명령줄에서 직접 실행: python upscaling_test_gui.py

워크플로우:
[1단계] 원본 이미지 3D 모델 생성 → [품질평가]
[2단계] 이미지 업스케일 (realesrgan-x4plus)
[3단계] 업스케일 이미지 3D 모델 생성 → [품질평가]
[4단계] 비교 분석 & 로그 저장
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# 프로젝트 경로 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 필수 모듈 import
from app.utils.model3d_generator import Model3DGenerator
from app.utils.model3d_evaluator import Model3DQualityEvaluator
from app.utils.model3d_logger import Model3DLogger
from app.utils.upscaler import create_upscaler

import customtkinter as ctk
from PIL import Image as PILImage


class UpscalingTestApp:
    """업스케일링 & 3D 품질 테스트 GUI"""
    
    # 색상 테마
    BG_PRIMARY = "#0f1013"
    BG_CARD = "#151820"
    BG_INPUT = "#1a1f27"
    TEXT_PRIMARY = "#f5f7fa"
    TEXT_SECONDARY = "#b8bec9"
    TEXT_MUTED = "#8e97a7"
    ACCENT = "#2e3440"
    SUCCESS = "#22c55e"
    DANGER = "#ef4444"
    
    def __init__(self):
        """앱 초기화"""
        self.root = ctk.CTk()
        self.root.title("업스케일링 & 3D 품질 테스트")
        self.root.geometry("900x700")
        self.root.configure(fg_color=self.BG_PRIMARY)
        
        # 상태
        self.running = False
        self.selected_image = None
        
        # 핵심 모듈
        self.model3d_gen = Model3DGenerator()
        self.evaluator = Model3DQualityEvaluator()
        self.logger = Model3DLogger()
        self.upscaler = create_upscaler()
        
        print(f"[GUI INIT] Evaluator trimesh_available: {self.evaluator.trimesh_available}")
        
        # UI 구축
        self._build_ui()
    
    def _build_ui(self):
        """UI 구축"""
        # 메인 프레임
        main_frame = ctk.CTkFrame(self.root, fg_color=self.BG_PRIMARY)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 제목
        title = ctk.CTkLabel(
            main_frame,
            text="🚀 업스케일링 & 3D 모델 품질 테스트",
            font=("맑은 고딕", 18, "bold"),
            text_color=self.TEXT_PRIMARY
        )
        title.pack(pady=10)
        
        # 이미지 선택 영역
        select_frame = ctk.CTkFrame(main_frame, fg_color=self.BG_CARD, corner_radius=8)
        select_frame.pack(fill="x", padx=10, pady=10)
        
        select_label = ctk.CTkLabel(
            select_frame,
            text="📷 이미지 선택",
            font=("맑은 고딕", 13, "bold"),
            text_color=self.TEXT_PRIMARY
        )
        select_label.pack(anchor="w", padx=10, pady=(10, 5))
        
        button_frame = ctk.CTkFrame(select_frame, fg_color="transparent")
        button_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkButton(
            button_frame,
            text="이미지 선택",
            command=self._select_image,
            fg_color=self.ACCENT,
            hover_color="#3a4150",
            width=120
        ).pack(side="left", padx=5)
        
        self.image_label = ctk.CTkLabel(
            button_frame,
            text="(선택됨)",
            text_color=self.TEXT_MUTED,
            font=("맑은 고딕", 10)
        )
        self.image_label.pack(side="left", padx=5, fill="x", expand=True)
        
        # 실행 버튼
        button_frame2 = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame2.pack(fill="x", padx=10, pady=10)
        
        self.run_btn = ctk.CTkButton(
            button_frame2,
            text="▶️  테스트 시작",
            command=self._start_test,
            fg_color=self.SUCCESS,
            hover_color="#16a34a"
        )
        self.run_btn.pack(side="left", padx=5)
        
        # 로그 영역
        log_frame = ctk.CTkFrame(main_frame, fg_color=self.BG_CARD, corner_radius=8)
        log_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        log_label = ctk.CTkLabel(
            log_frame,
            text="📋 실행 로그",
            font=("맑은 고딕", 13, "bold"),
            text_color=self.TEXT_PRIMARY
        )
        log_label.pack(anchor="w", padx=10, pady=(10, 5))
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=20,
            width=100,
            bg=self.BG_INPUT,
            fg=self.TEXT_PRIMARY,
            insertbackground=self.TEXT_PRIMARY
        )
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 태그 설정
        self.log_text.tag_config("info", foreground=self.TEXT_SECONDARY)
        self.log_text.tag_config("success", foreground=self.SUCCESS)
        self.log_text.tag_config("error", foreground=self.DANGER)
        self.log_text.tag_config("title", foreground=self.TEXT_PRIMARY, font=("맑은 고딕", 11, "bold"))
    
    def _select_image(self):
        """이미지 선택"""
        filename = filedialog.askopenfilename(
            title="이미지 선택",
            filetypes=[("이미지 파일", "*.jpg *.png *.bmp"), ("모든 파일", "*.*")]
        )
        if filename:
            self.selected_image = filename
            self.image_label.configure(text=os.path.basename(filename))
            self._log(f"✓ 이미지 선택됨: {filename}", "success")
    
    def _start_test(self):
        """테스트 시작"""
        if not self.selected_image:
            messagebox.showwarning("경고", "이미지를 선택해주세요")
            return
        
        if not os.path.exists(self.selected_image):
            messagebox.showerror("오류", "선택한 이미지 파일이 없습니다")
            return
        
        if self.running:
            messagebox.showinfo("알림", "이미 실행 중입니다")
            return
        
        # 스레드에서 실행
        thread = threading.Thread(target=self._execute_test, daemon=True)
        thread.start()
    
    def _execute_test(self):
        """테스트 실행"""
        self.running = True
        self.run_btn.configure(state="disabled")
        
        try:
            self._log("=" * 80, "title")
            self._log("[시작] 업스케일링 & 3D 모델 품질 테스트", "title")
            self._log("=" * 80, "title")
            self._log(f"이미지: {os.path.basename(self.selected_image)}\n")
            
            # 1단계: 원본 이미지 3D 모델 생성
            self._log("[1단계] 원본 이미지 3D 모델 생성 중...\n")
            output_dir = os.path.join(os.path.dirname(self.selected_image), "upscaling_test")
            os.makedirs(output_dir, exist_ok=True)
            
            pre_model_result = self.model3d_gen.generate_3d_model_with_validation(
                image_path=self.selected_image,
                output_dir=os.path.join(output_dir, "pre"),
                member_id=999,
                strict_mode=False
            )
            
            if not pre_model_result['success']:
                self._log(f"✗ 실패: {pre_model_result['message']}", "error")
                return
            
            self._log(f"✓ 완료: {pre_model_result['message']}", "success")
            pre_model_path = pre_model_result['model_path']
            self._log(f"  저장: {pre_model_path}\n")
            
            # 2단계: 원본 3D 모델 품질 평가
            self._log("[2단계] 원본 3D 모델 품질 평가 중...\n")
            pre_eval_result = self.evaluator.evaluate(pre_model_path, "pre-upscale")
            self._log_eval_result(pre_eval_result, "pre-upscale")
            
            # 평가 결과 저장
            self.logger.log_evaluation(pre_eval_result, "pre")
            self._log(f"  ✓ 평가 결과 저장\n")
            
            # 3단계: 이미지 업스케일
            self._log("[3단계] 이미지 업스케일 중...\n")
            upscaled_path = os.path.join(output_dir, "upscaled.png")
            upscale_meta = self.upscaler.upscale(self.selected_image, upscaled_path)
            
            if not upscale_meta['success']:
                self._log(f"✗ 실패: {upscale_meta.get('error')}", "error")
                return
            
            self._log(f"✓ 완료", "success")
            self._log(f"  엔진: {upscale_meta['engine']}")
            self._log(f"  원본: {upscale_meta['original_size']} → {upscale_meta['upscaled_size']}")
            self._log(f"  시간: {upscale_meta['processing_time_sec']:.2f}초")
            self._log(f"  저장: {upscaled_path}\n")
            
            # 4단계: 업스케일 이미지 3D 모델 생성
            self._log("[4단계] 업스케일 이미지 3D 모델 생성 중...\n")
            post_model_result = self.model3d_gen.generate_3d_model_with_validation(
                image_path=upscaled_path,
                output_dir=os.path.join(output_dir, "post"),
                member_id=999,
                strict_mode=False
            )
            
            if not post_model_result['success']:
                self._log(f"✗ 실패: {post_model_result['message']}", "error")
                return
            
            self._log(f"✓ 완료: {post_model_result['message']}", "success")
            post_model_path = post_model_result['model_path']
            self._log(f"  저장: {post_model_path}\n")
            
            # 5단계: 업스케일 3D 모델 품질 평가
            self._log("[5단계] 업스케일 3D 모델 품질 평가 중...\n")
            post_eval_result = self.evaluator.evaluate(post_model_path, "post-upscale")
            self._log_eval_result(post_eval_result, "post-upscale")
            
            # 평가 결과 저장
            self.logger.log_evaluation(post_eval_result, "post")
            self._log(f"  ✓ 평가 결과 저장\n")
            
            # 6단계: 비교 분석
            self._log("[6단계] 3D 모델 비교 분석 중...\n")
            comparison_result = self.evaluator.compare(pre_eval_result, post_eval_result)
            self._log_comparison_result(comparison_result)
            
            # 비교 결과 저장
            log_path = self.logger.log_comparison(comparison_result)
            self._log(f"  ✓ 비교 결과 저장: {os.path.basename(log_path)}\n")
            
            # 완료
            self._log("=" * 80, "title")
            self._log("[완료] 테스트 완료", "title")
            self._log("=" * 80, "title")
            messagebox.showinfo("완료", "테스트가 완료되었습니다!")
            
        except Exception as e:
            self._log(f"[오류] {str(e)}", "error")
            import traceback
            self._log(traceback.format_exc(), "error")
        
        finally:
            self.running = False
            self.run_btn.configure(state="normal")
    
    def _log_eval_result(self, result: Dict[str, Any], label: str):
        """평가 결과 출력"""
        quality = result.get('overall_quality', 0)
        level = result.get('quality_level', 'unknown')
        
        self._log(f"  품질 점수: {quality:.1f}/100 ({level})")
        
        metrics = result.get('metrics', {})
        
        if 'mesh_quality' in metrics:
            mesh = metrics['mesh_quality']
            self._log(f"    · 메시: {mesh.get('mesh_score', 0):.1f} (vertex={mesh.get('vertex_count', 0)}, face={mesh.get('face_count', 0)})")
        
        if 'texture_quality' in metrics:
            texture = metrics['texture_quality']
            self._log(f"    · 텍스처: {texture.get('texture_score', 0):.1f} (해상도={texture.get('texture_resolution', 0)})")
        
        if 'geometry_accuracy' in metrics:
            geometry = metrics['geometry_accuracy']
            self._log(f"    · 기하학: {geometry.get('accuracy_score', 0):.1f}")
        
        self._log("")
    
    def _log_comparison_result(self, result: Dict[str, Any]):
        """비교 결과 출력"""
        improvement = result.get('improvement', {})
        
        self._log("  개선도:", "info")
        
        mesh_delta = improvement.get('mesh_quality_delta', 0)
        self._log(f"    · 메시: {mesh_delta:+.1f}")
        
        texture_delta = improvement.get('texture_quality_delta', 0)
        self._log(f"    · 텍스처: {texture_delta:+.1f}")
        
        geometry_delta = improvement.get('geometry_accuracy_delta', 0)
        self._log(f"    · 기하학: {geometry_delta:+.1f}")
        
        overall_improvement = improvement.get('overall_improvement', 0)
        self._log(f"    · 통합 개선도: {overall_improvement:+.1f}%", "success" if overall_improvement > 0 else "error")
        
        # 파일 크기
        file_size_comp = result.get('file_size_comparison', {})
        size_delta = file_size_comp.get('size_delta', 0)
        self._log(f"  파일 크기 변화: {size_delta / 1024 / 1024:+.2f}MB")
    
    def _log(self, message: str, tag: str = "info"):
        """로그 출력"""
        self.log_text.config(state="normal")
        self.log_text.insert("end", message + "\n", tag)
        self.log_text.see("end")
        self.log_text.config(state="normal")
        self.log_text.update()
    
    def run(self):
        """앱 실행"""
        self.root.mainloop()


def main():
    """메인 함수"""
    app = UpscalingTestApp()
    app.run()


if __name__ == "__main__":
    main()
