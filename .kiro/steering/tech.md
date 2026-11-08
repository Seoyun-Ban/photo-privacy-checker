# 기술 스택
- Python 3 + Streamlit 단일 웹앱
- 사진 분석: Gemini API (google-genai 패키지), 키는 .env의 GEMINI_API_KEY
- 이미지 처리·메타데이터: Pillow
- .env와 가상환경 폴더는 .gitignore에 포함

# 파일 구조 (각자 담당 파일만 수정)
- app.py: 화면 (업로드, 결과 카드, 디자인)
- analyzer.py: 분석 로직 (메타데이터 검사, Gemini 호출, JSON 처리, 위험도 계산)

# 규칙
- 주석과 화면 문구는 한국어
- 데모가 바로 돌아가는 것이 최우선, 과도한 추상화나 파일 분리 금지
- 시간·점수 계산은 코드로 처리하고 AI에게 맡기지 않음
- Gemini 응답은 JSON으로 받고, 파싱 실패 시 오류 메시지를 화면에 표시
