# 📸 업로드 전 사진 개인정보 검사기

SNS에 사진을 올리기 전, 사진 속에 숨은 개인정보 단서를 AI가 찾아 주고
모자이크·블러로 안전하게 가린 뒤 바로 공유할 수 있는 서비스입니다.

🔗 **[배포 주소](https://photo-privacy-checher-6jgd26xsjhrl56hczqvdku.streamlit.app/)**: 배포주소

## 문제
얼굴 모자이크 앱은 있지만, 택배 송장·간판·교복·반사된 화면처럼
조합하면 위치나 신원이 드러나는 단서는 사람이 놓치기 쉽습니다.

## 주요 기능
- 사진 속 GPS 메타데이터 검사
- AI가 위치·신원·번호·생활패턴·타인·반사 단서를 찾고 근거와 수정 방법 제시
- 위험 요소 자동 모자이크 + 사용자가 직접 상자 이동·크기 조절·강도 조절
- 편집한 사진 다운로드 및 공유

## 기술 스택
- Python, Streamlit
- Gemini API (사진 분석)
- Pillow (메타데이터·이미지 처리)
- Kiro (AI 기반 개발)

## 실행 방법
1. `pip install -r requirements.txt`
2. `.env` 파일에 `GEMINI_API_KEY=발급받은키` 입력
3. `python -m streamlit run app.py`