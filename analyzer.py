# analyzer.py
# SNS 업로드 전 사진 개인정보 검사기 - 분석 로직
# 담당: 메타데이터(GPS) 검사, Gemini 호출, JSON 처리, 위험도 계산
# (화면 문구/주석은 한국어, 점수 계산은 코드로 처리)

import copy
import hashlib
import io
import json

from PIL import Image, ExifTags, ImageOps
from google import genai
from google.genai import types
from dotenv import load_dotenv

# .env의 GEMINI_API_KEY 로드
load_dotenv()

# 사용할 Gemini 모델 (gemini-2.5-flash는 신규 사용자 이용 불가(404)여서 3.8-flash 사용)
MODEL = "gemini-3.8-flash"

# Gemini로 보내기 전 이미지 긴 변의 최대 크기(px) - 속도/비용 절감용
MAX_SIDE = 1024

# Gemini에 보낼 분석 프롬프트
PROMPT = """너는 SNS에 올릴 사진의 개인정보 노출 위험을 검사하는 전문가야.

사진에서 다음 범주의 단서를 찾아줘: 위치(간판, 건물, 랜드마크, 역 이름, 창밖 풍경), 신원(이름, 학교, 교복, 학생증, 명찰), 번호·문서(택배 송장, 차량 번호판, 전화번호, 바코드, 티켓), 생활패턴(여행 중 집 비움 등), 타인(다른 사람 얼굴, 아이), 반사(거울, 안경, 모니터에 비친 정보).

실제로 사진에서 보이는 것만 보고하고, 보이지 않는 것은 지어내지 마.

단정하지 말고 '~로 유추될 수 있음'처럼 근거와 함께 써.

위험 요소는 최대 5개까지만, reason과 fix는 각각 한 문장으로 짧게 써.
reason과 fix는 '~로 유추될 수 있습니다'처럼 단정하지 않는 한국어 표현으로 써.

각 위험 요소에는 사진 속 위치를 "box": [ymin, xmin, ymax, xmax] 로 넣어줘. 좌표는 이미지 전체를 0~1000으로 본 상대 좌표야(Gemini 기본 bounding box 형식).

상자는 항목 전체를 크게 감싸지 말고, 가려야 할 글자나 대상에 딱 맞게 줘.
한 사진에 가릴 곳이 여러 군데면(예: 송장의 이름과 주소와 전화번호) 하나의 항목으로 묶지 말고, 각각을 별도의 위험 요소로 나눠서 항목마다 box를 하나씩 줘. 이렇게 하면 화면에서 "이름 가리기", "주소 가리기"처럼 항목별로 켜고 끌 수 있어.

사진에서 특정 영역을 가리키기 어려운 항목(예: 생활패턴)은 box를 아예 빼.

반드시 아래 JSON 형식으로만 답해:

{"risks": [{"category": "...", "item": "...", "reason": "...", "severity": 1~3, "fix": "...", "box": [ymin, xmin, ymax, xmax]}]}

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

    - EXIF 회전 정보를 반영(exif_transpose)해 화면과 같은 방향으로 맞춘 뒤 보냄.
      (app.py도 같은 방식으로 회전을 반영해 표시하므로 box 좌표가 화면과 일치함)
    - 긴 변이 MAX_SIDE(1024px)보다 크면 비율을 유지하며 축소
    - 전송용 바이트와 실제 mime_type을 함께 반환
    - GPS 등 메타데이터 검사는 호출부에서 '원본' 바이트로 따로 수행
    """
    img = Image.open(io.BytesIO(image_bytes))

    # 회전 정보를 실제 픽셀에 반영 (이 과정에서 EXIF 방향 태그는 사라짐)
    img = ImageOps.exif_transpose(img)

    # 투명도가 있으면 PNG, 아니면 JPEG로 저장
    has_alpha = img.mode in ("RGBA", "LA", "P")

    # 긴 변이 MAX_SIDE를 넘으면 비율 유지 축소
    long_side = max(img.size)
    if long_side > MAX_SIDE:
        scale = MAX_SIDE / long_side
        new_size = (round(img.size[0] * scale), round(img.size[1] * scale))
        img = img.resize(new_size, Image.LANCZOS)

    buf = io.BytesIO()
    if has_alpha:
        out_fmt = "PNG"
        img.save(buf, format=out_fmt)
    else:
        out_fmt = "JPEG"
        img.convert("RGB").save(buf, format=out_fmt, quality=90)

    mime_type = Image.MIME.get(out_fmt, "image/jpeg")
    return buf.getvalue(), mime_type


def _call_gemini(image_bytes):
    """Gemini에 이미지를 보내 위험 요소 JSON(risks 리스트)을 받아 반환.

    60초 안에 응답이 없거나 호출이 실패하면 바로 오류 메시지를 발생시킨다.
    """
    # API 키는 .env의 GEMINI_API_KEY에서 자동으로 읽어옴 (키를 코드에 넣지 않음)
    # Gemini 호출에 60초 타임아웃(ms 단위) 적용 (504 DEADLINE_EXCEEDED 대비)
    client = genai.Client(
        http_options=types.HttpOptions(timeout=60_000),
    )

    # 큰 이미지는 축소하고, 실제 형식에 맞는 mime_type을 사용
    send_bytes, mime_type = _prepare_image_for_gemini(image_bytes)

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=[
                types.Part.from_bytes(data=send_bytes, mime_type=mime_type),
                PROMPT,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                # gemini-3.8-flash는 thinking_level 방식만 지원하며,
                # 'minimal'은 미지원(400)이라 지원되는 가장 낮은 값인 'low'를 사용
                thinking_config=types.ThinkingConfig(thinking_level="low"),
            ),
        )
    except Exception as e:
        # 타임아웃·네트워크·API 오류 등은 바로 사용자용 메시지로 전달
        raise ValueError(f"AI 분석에 실패했습니다. 잠시 후 다시 시도해 주세요. (원인: {e})")

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


# 모자이크 영역 상자를 넓혀줄 비율 (좌표가 조금 빗나갈 수 있어 살짝 여유를 둠)
BOX_PADDING = 0.03


def _box_to_pixels(box, width, height):
    """0~1000 기준 [ymin, xmin, ymax, xmax] 상대 좌표를
    실제 픽셀 (left, top, right, bottom)로 변환하고 10% 넓힌다.
    유효하지 않으면 None 반환.
    """
    if not box or len(box) != 4:
        return None

    try:
        ymin, xmin, ymax, xmax = (float(v) for v in box)
    except (TypeError, ValueError):
        return None

    # 0~1000 상대 좌표 -> 픽셀
    left = xmin / 1000.0 * width
    top = ymin / 1000.0 * height
    right = xmax / 1000.0 * width
    bottom = ymax / 1000.0 * height

    # 혹시 좌표 순서가 뒤집혀 와도 보정
    if right < left:
        left, right = right, left
    if bottom < top:
        top, bottom = bottom, top

    # 상자를 BOX_PADDING(3%)만큼 사방으로 넓힘
    pad_x = (right - left) * BOX_PADDING
    pad_y = (bottom - top) * BOX_PADDING
    left -= pad_x
    right += pad_x
    top -= pad_y
    bottom += pad_y

    # 이미지 경계 안으로 클램프
    left = max(0, int(round(left)))
    top = max(0, int(round(top)))
    right = min(width, int(round(right)))
    bottom = min(height, int(round(bottom)))

    # 너비/높이가 0 이하이면 무효
    if right <= left or bottom <= top:
        return None

    return (left, top, right, bottom)


def _pixelate_region(img, region):
    """지정한 영역(left, top, right, bottom)을 축소 후 확대해 픽셀화한다."""
    crop = img.crop(region)
    w, h = crop.size

    # 영역을 가로·세로 약 20블록으로 쪼개도록 축소 크기 결정 (이전보다 더 촘촘하게)
    # 최소 2px 이상으로 축소해 글자 모양이 남지 않게 함
    small_w = max(2, w // 20)
    small_h = max(2, h // 20)

    # 축소 -> 원래 크기로 확대(최근접 보간)하면 블록 모자이크가 됨
    small = crop.resize((small_w, small_h), Image.NEAREST)
    pixelated = small.resize(crop.size, Image.NEAREST)
    img.paste(pixelated, region)


def _iter_boxes(risk):
    """risk에서 상자 리스트를 꺼낸다.

    - 기본은 "boxes": [[ymin, xmin, ymax, xmax], ...] (줄 단위 여러 개)
    - 예전 형식 호환: 단일 "box"가 있으면 그것도 포함
    """
    boxes = []

    raw = risk.get("boxes")
    if isinstance(raw, list):
        for b in raw:
            if isinstance(b, (list, tuple)) and len(b) == 4:
                boxes.append(b)

    # 하위 호환: 단일 box 키도 지원
    single = risk.get("box")
    if isinstance(single, (list, tuple)) and len(single) == 4:
        boxes.append(single)

    return boxes


def mosaic(image_bytes, risks):
    """boxes 좌표가 있는 위험 영역을 모자이크(픽셀화)한 이미지 바이트를 반환.

    - boxes 형식: [[ymin, xmin, ymax, xmax], ...] (0~1000 상대 좌표, 줄 단위 여러 개)
    - 좌표가 조금 빗나갈 수 있어 각 상자를 3% 넓혀서 가림
    - 가릴 상자가 전혀 없으면 원본을 그대로 반환
    """
    img = Image.open(io.BytesIO(image_bytes))
    # EXIF 회전 정보를 반영해 실제 보이는 방향으로 맞춤
    img = ImageOps.exif_transpose(img)

    out_fmt = (img.format or "JPEG").upper()
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    width, height = img.size

    for risk in risks:
        for box in _iter_boxes(risk):
            region = _box_to_pixels(box, width, height)
            if region:
                _pixelate_region(img, region)

    buf = io.BytesIO()
    if out_fmt in ("JPEG", "JPG"):
        img.convert("RGB").save(buf, format="JPEG", quality=90)
    elif out_fmt == "PNG":
        img.save(buf, format="PNG")
    else:
        # 알 수 없는 포맷은 JPEG로 통일
        img.convert("RGB").save(buf, format="JPEG", quality=90)

    return buf.getvalue()


# ----- 분석 결과 캐시 -----
# 같은 사진(바이트가 동일)을 다시 분석하지 않도록 결과를 메모리에 보관한다.
# 키: 사진 바이트의 SHA-256 해시 / 값: analyze가 돌려준 결과 dict
_CACHE = {}
_CACHE_MAX = 64  # 메모리 무한 증가 방지를 위한 간단한 상한


def _cache_key(image_bytes):
    return hashlib.sha256(image_bytes).hexdigest()


def clear_cache():
    """분석 결과 캐시를 비운다 (필요 시 외부에서 호출)."""
    _CACHE.clear()


def analyze(image_bytes):
    """사진 바이트를 받아 개인정보 노출 위험을 분석한 결과를 반환.

    반환 형식 (app.py와의 약속):
    {
      "overall": "낮음" | "주의" | "높음",
      "risks": [
        {"category": ..., "item": ..., "reason": ..., "severity": 1~3 정수, "fix": ...,
         "box": [ymin, xmin, ymax, xmax]}  # box는 선택: 위치를 특정할 수 없으면 생략
      ]
    }
    - overall은 severity로 코드에서 계산 (AI에게 맡기지 않음)
    - box는 0~1000 비율 좌표. 없거나 형식이 틀리면 app.py가 사용자 직접 지정으로 넘김
    - 같은 사진(바이트 해시 동일)은 재분석하지 않고 캐시된 결과를 돌려준다.
      (실패/예외는 캐시하지 않으므로 다음에 다시 시도할 수 있음)
    """
    # 0) 캐시 확인 - 같은 사진이면 Gemini를 다시 호출하지 않음
    key = _cache_key(image_bytes)
    if key in _CACHE:
        # 호출부가 수정해도 캐시가 오염되지 않도록 복사본을 반환
        return copy.deepcopy(_CACHE[key])

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

    result = {"overall": overall, "risks": risks}

    # 4) 성공한 결과만 캐시에 저장 (상한을 넘으면 가장 오래된 항목 제거)
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = copy.deepcopy(result)

    return result


if __name__ == "__main__":
    # 간단 테스트: test.jpg를 분석해서 결과와 걸린 시간을 출력
    import time

    with open("test.jpg", "rb") as f:
        image_bytes = f.read()

    start = time.perf_counter()
    result = analyze(image_bytes)
    elapsed = time.perf_counter() - start

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n분석에 걸린 시간: {elapsed:.2f}초")

    # 위험 영역을 모자이크 처리해서 test_mosaic.jpg로 저장
    mosaic_bytes = mosaic(image_bytes, result["risks"])
    with open("test_mosaic.jpg", "wb") as f:
        f.write(mosaic_bytes)
    print("모자이크 결과를 test_mosaic.jpg로 저장했습니다.")
