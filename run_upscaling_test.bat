@echo off
REM 업스케일링 & 3D 모델 품질 테스트 GUI 실행
cd /d "%~dp0"
.venv\Scripts\python.exe upscaling_test_gui.py
pause
