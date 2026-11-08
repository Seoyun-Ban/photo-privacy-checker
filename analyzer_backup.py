# analyzer.py
# SNS 업로드 전 사진 개인정보 검사기 - 분석 로직
# 담당: 메타데이터(GPS) 검사, Gemini 호출, JSON 처리, 위험도 계산
# (화면 문구/주석은 한국어, 점수 계산은 코드로 처리)

import io
import json

from PIL import Image, ExifTags
from google import genai
from google.genai import types
from dotenv import load_dotenv

# .env의 GEMINI_API_KEY 로드
load_dotenv()

# 사용할 Gemini 모델 (기본값: gemini-2.5-flash)
MODEL = "gemini-3.8-flash"

# Gemini로 보내기 전 이미지 긴 변의 최대 크기(px) - 속도/비용 절감용
MAX_SIDE = 1600

# Gemini에 보낼 분석 프롬프트
PROMPT = """너는 SNS에 올릴 사진의 개인정보 노출 위험을 검사하는 전문가야.

사진에서 다음 범주의 단서를 찾아줘: 위치(간판, 건물, 랜드마크, 역 이름, 창밖 풍경), 신원(이름, 학교, 교복, 학생증, 명찰), 번호·문서(택배 송장, 차량 번호판, 전화번호, 바코드, 티켓), 생활패턴(여행 중 집 비움 등), 타인(다른 사람 얼굴, 아이), 반사(거울, 안경, 모니터에 비친 정보).

실제로 사진에서 보이는 것만 보고하고, 보이지 않는 것은 지어내지 마.

단정하지 말고 '~로 유추될 수 있음'처럼 근거와 함께 써.

반드시 아래 JSON 형식으로만 답해:

{"risks": [{"category": "...", "item": "...", "reason": "...", "severity": 1~3, "fix": "..."}]}

위험 요소가 없으면 {"risks": []}"""


def _detect_gps(image_bytes):
    """EXIF 메타데이터에 GPS 정보가 있으면 위험 항목을 반환, 없으면 None.

    주의: GPS 검사는 리사이즈하지 않은 '원본' 바이트로 수행해야
    메타데이터가 보존됩니다.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        exif = img.getexif()
        if not exif:
            return None

        # EXIF에서 GPSInfo 태그 찾기
        gps_tag_id = None
        for tag_id, name in ExifTags.TAGS.items():
            if name == "GPSInfo":
                gps_tag_id = tag_id
                break

        gps_info = exif.get(gps_tag_id) if gps_tag_id is not None else None

        # getexif()에서 GPS가 바로 안 잡힐 경우 IFD로 한 번 더 확인
        if not gps_info:
            try:
                gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)
                gps_info = gps_ifd if gps_ifd else None
            except Exception:
                gps_info = None

        if gps_info:
            return {
                "category": "위치",
                "item": "사진 속 GPS 정보",
                "reason": "사진 메타데이터(EXIF)에 GPS 좌표가 포함되어 있어 촬영 장소가 그대로 드러날 수 있습니다.",
                "severity": 3,
                "fix": "업로드 전 메타데이터(위치 정보)를 제거하세요.",
            }
    except Exception:
        # 메타데이터 읽기 실패는 치명적이지 않으므로 조용히 건너뜀
        return None

    return None


def _prepare_image_for_gemini(image_bytes):
    """Gemini로 보낼 이미지를 준비한다.

    - 긴 변이 MAX_SIDE(1600px)보다 크면 비율을 유지하며 축소
    - 전송용 바이트와 실제 mime_type을 함께 반환
    - 원본은 변경하지 않으며(바이트 그대로 전달 가능), GPS 검사는 호출부에서 원본으로 수행
    """
    img = Image.open(io.BytesIO(image_bytes))

    # 원본 포맷 기준으로 mime_type 결정 (기본값 JPEG)
    fmt = (img.format or "JPEG").upper()
    long_side = max(img.size)

    # 축소가 필요 없으면 원본 바이트를 그대로 전송
    if long_side <= MAX_SIDE:
        mime_type = Image.MIME.get(fmt, "image/jpeg")
        return image_bytes, mime_type

    # 긴 변을 MAX_SIDE에 맞춰 비율 유지 축소
    scale = MAX_SIDE / long_side
    new_size = (round(img.size[0] * scale), round(img.size[1] * scale))
    resized = img.resize(new_size, Image.LANCZOS)

    # 저장 포맷 결정: 투명도가 있으면 PNG, 아니면 JPEG로 재인코딩
    buf = io.BytesIO()
    if resized.mode in ("RGBA", "LA", "P"):
        out_fmt = "PNG"
        resized.save(buf, format=out_fmt)
    else:
        out_fmt = "JPEG"
        resized.convert("RGB").save(buf, format=out_fmt, quality=90)

    mime_type = Image.MIME.get(out_fmt, "image/jpeg")
    return buf.getvalue(), mime_type


def _call_gemini(image_bytes):
    """Gemini에 이미지를 보내 위험 요소 JSON(risks 리스트)을 받아 반환."""
    # API 키는 .env의 GEMINI_API_KEY에서 자동으로 읽어옴 (키를 코드에 넣지 않음)
    client = genai.Client()

    # 큰 이미지는 축소하고, 실제 형식에 맞는 mime_type을 사용
    send_bytes, mime_type = _prepare_image_for_gemini(image_bytes)

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=send_bytes, mime_type=mime_type),
            PROMPT,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            # thinking을 최소로 설정해 응답 속도를 높임
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    text = (response.text or "").strip()

    # 혹시 코드블록(```)으로 감싸져 오면 벗겨냄
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    data = json.loads(text)
    risks = data.get("risks", [])
    if not isinstance(risks, list):
        risks = []
    return risks


def _calc_overall(risks):
    """severity를 바탕으로 종합 위험도를 코드에서 계산."""
    severities = [r.get("severity", 0) for r in risks]
    if any(s == 3 for s in severities):
        return "높음"
    if any(s == 2 for s in severities):
        return "주의"
    return "낮음"


def analyze(image_bytes):
    """사진 바이트를 받아 개인정보 노출 위험을 분석한 결과를 반환.

    반환 형식:
    {
      "overall": "낮음" | "주의" | "높음",
      "risks": [
        {"category": ..., "item": ..., "reason": ..., "severity": 1~3, "fix": ...}
      ]
    }
    """
    risks = []

    # 1) 코드로 메타데이터(GPS) 검사 - 반드시 원본 바이트로 수행
    gps_risk = _detect_gps(image_bytes)
    if gps_risk:
        risks.append(gps_risk)

    # 2) Gemini로 사진 속 단서 분석 (JSON 파싱 실패 시 오류 메시지 전달)
    try:
        gemini_risks = _call_gemini(image_bytes)
        risks.extend(gemini_risks)
    except json.JSONDecodeError:
        raise ValueError("AI 응답을 JSON으로 해석하지 못했습니다. 다시 시도해 주세요.")

    # 3) 종합 위험도는 코드로 계산
    overall = _calc_overall(risks)

    return {"overall": overall, "risks": risks}


if __name__ == "__main__":
    # 간단 테스트: test.jpg를 분석해서 결과를 출력
    with open("test.jpg", "rb") as f:
        image_bytes = f.read()

    result = analyze(image_bytes)
    print(json.dumps(result, ensure_ascii=False, indent=2))
