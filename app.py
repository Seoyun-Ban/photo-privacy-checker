import base64
import html
import io
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageFilter, ImageOps


# ----- 임시 분석 함수 (analyzer.py 완성 전까지만 사용) -----
def fake_analyze(image_bytes):
    """product.md 형식의 예시 결과를 돌려주는 데모용 함수 (실제 사진을 분석하지 않음)"""
    time.sleep(1.0)  # 분석 중 화면을 확인할 수 있도록 잠깐 대기
    # box: [ymin, xmin, ymax, xmax] (0~1000 비율 좌표, 선택 항목)
    # 데모의 box는 예시 위치일 뿐 실제 사진 속 위치가 아님
    risks = [
        {
            "category": "위치",
            "item": "송장 속 주소",
            "reason": "송장에 적힌 주소가 읽힐 수 있어 사는 곳이 유추될 수 있습니다.",
            "severity": 3,
            "fix": "주소 부분을 모자이크하거나 송장을 떼고 촬영하세요.",
            "box": [380, 470, 470, 760],
        },
        {
            "category": "신원",
            "item": "송장 속 이름",
            "reason": "받는 사람 이름이 보여 신원이 유추될 수 있습니다.",
            "severity": 3,
            "fix": "이름 부분을 가린 뒤 올리세요.",
            "box": [300, 470, 370, 680],
        },
        {
            "category": "번호·문서",
            "item": "운송장 번호·바코드",
            "reason": "운송장 번호로 배송 정보가 조회될 수 있습니다.",
            "severity": 2,
            "fix": "바코드와 번호 부분을 가려 주세요.",
            "box": [490, 470, 600, 700],
        },
        {
            "category": "위치",
            "item": "창밖 간판",
            "reason": "창밖에 보이는 상호 간판으로 촬영 장소가 특정될 수 있습니다.",
            "severity": 1,
            "fix": "간판 부분을 모자이크하거나 사진을 잘라 내고 올리세요.",
        },
    ]
    # 종합 위험도는 severity로 계산 (진짜 analyzer.py에서도 코드로 계산)
    top = max((r["severity"] for r in risks), default=0)
    overall = "높음" if top >= 3 else "주의" if top == 2 else "낮음"
    return {"overall": overall, "risks": risks}


# ============================================================
# [연결 지점] 진짜 분석 기능으로 바꿀 때는 아래 한 줄을
#     from analyzer import analyze
# 로 바꾸면 됩니다. (데모 표시는 자동으로 사라집니다)
# ============================================================
from analyzer import analyze

IS_DEMO = analyze is fake_analyze

# 사진 저장/자동 삭제 문구는 실제 처리 방식이 확인된 경우에만 True로 변경
STORAGE_GUARANTEED = False

MAX_BYTES = 10 * 1024 * 1024  # 최대 10MB
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


# ----- 색상 설정 -----
OVERALL_STYLE = {
    "낮음": {
        "color": "#079455", "bg": "#EFFBF4", "border": "#C6EFD5",
        "track": "#CDEFD9", "fill": "#1F9D57", "level": 1,
        "msg": "눈에 띄는 위험 단서가 적은 것으로 보입니다. 올리기 전에 한 번 더 확인해 보세요.",
    },
    "주의": {
        "color": "#DC6803", "bg": "#FFF8EE", "border": "#FBE2C0",
        "track": "#FBE3C4", "fill": "#F08C00", "level": 2,
        "msg": "단서가 조합되면 위치나 신원이 유추될 수 있습니다. 수정 방법을 확인해 보세요.",
    },
    "높음": {
        "color": "#D92D20", "bg": "#FFF3F2", "border": "#FCD5D2",
        "track": "#F8D4D4", "fill": "#E5484D", "level": 3,
        "msg": "위치나 신원이 드러날 수 있는 단서가 있습니다. 수정 후 올리는 것을 권장합니다.",
    },
}

SEVERITY_STYLE = {
    1: {"label": "낮음", "color": "#079455", "bg": "#EAF8F0", "border": "#C6EFD5"},
    2: {"label": "주의", "color": "#DC6803", "bg": "#FFF4E5", "border": "#FBE2C0"},
    3: {"label": "높음", "color": "#D92D20", "bg": "#FEECEB", "border": "#FCD5D2"},
}


# ----- 아이콘 (SVG) -----
ICON_PATHS = {
    "shield": '<path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6l8-3z"/><path d="M9 12l2 2 4-4"/>',
    "upload": '<path d="M12 16V4"/><path d="M7 9l5-5 5 5"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 9"/>',
    "scan": '<path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3"/><circle cx="12" cy="12" r="3"/>',
    "lock": '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    "check": '<path d="M5 12l5 5 9-10"/>',
    "warn": '<path d="M12 4l9 16H3L12 4z"/><path d="M12 10v4"/><path d="M12 17h.01"/>',
    "chevron": '<path d="M6 9l6 6 6-6"/>',
    "alert": '<circle cx="12" cy="12" r="9"/><path d="M12 8v5"/><path d="M12 16h.01"/>',
}


def icon(name, size=16, stroke=2):
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        f"{ICON_PATHS[name]}</svg>"
    )


# ----- 스타일 -----
CSS = """
<style>
@import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css");

:root {--pl-blue:#246BFD; --pl-navy:#172033; --pl-sub:#5A6478; --pl-muted:#8A94A6; --pl-line:#E6EBF2; --pl-bg:#F6F8FB;}

.stApp {background: var(--pl-bg); color: var(--pl-navy);}
.stApp *:not([data-testid="stIconMaterial"]) {
  font-family: "Pretendard Variable", Pretendard, -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo",
               "Noto Sans KR", "Malgun Gothic", sans-serif;
}
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
#MainMenu, footer {display: none !important;}
[data-testid="stMain"] {overflow-x: hidden;}
[data-testid="stMainBlockContainer"], .block-container {max-width: 1180px; padding: 0 24px 0 24px;}

/* 헤더 · 푸터 (화면 전체 너비) */
.pl-header, .pl-footer {width: 100vw; position: relative; left: 50%; margin-left: -50vw; background: #fff;}
.pl-header {border-bottom: 1px solid var(--pl-line);}
.pl-header-inner {max-width: 1180px; margin: 0 auto; padding: 18px 24px; display: flex;
  align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;}
.pl-brand {display: flex; align-items: center; gap: 12px;}
.pl-logo {width: 40px; height: 40px; border-radius: 11px; background: var(--pl-blue); color: #fff;
  display: inline-flex; align-items: center; justify-content: center; box-shadow: 0 6px 14px rgba(36,107,253,.28);}
.pl-brand-name {font-size: 18px; font-weight: 700; color: var(--pl-navy); letter-spacing: -0.01em;}
.pl-header-right {display: flex; align-items: center; gap: 12px; flex-wrap: wrap;}
.pl-header-note {display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: #4A5568;}
.pl-header-note svg {color: var(--pl-blue);}
.pl-demo-pill {font-size: 12px; font-weight: 700; color: #B45309; background: #FFF7E6;
  border: 1px solid #FBE3B8; padding: 5px 12px; border-radius: 999px;}
.pl-footer {margin-top: 72px; border-top: 1px solid var(--pl-line); padding: 28px 24px;
  text-align: center; font-size: 12px; color: var(--pl-muted); line-height: 1.6;}

/* 업로드 전 · 소개 */
.pl-hero {text-align: center; padding: 56px 0 36px 0;}
.pl-chip {display: inline-flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 700;
  color: var(--pl-blue); background: #EEF4FF; border: 1px solid #D6E3FF; padding: 6px 14px; border-radius: 999px;}
.pl-hero-title {font-size: 44px; font-weight: 800; line-height: 1.3; letter-spacing: -0.02em;
  color: var(--pl-navy); margin: 22px 0 18px 0;}
.pl-hero-title span {color: var(--pl-blue);}
.pl-hero-desc {font-size: 16px; line-height: 1.7; color: var(--pl-sub); margin: 0;}

/* 업로드 카드 */
.st-key-upload_card {max-width: 860px; margin: 0 auto; background: #fff; border: 1px solid var(--pl-line);
  border-radius: 24px; padding: 22px; box-shadow: 0 12px 40px rgba(23,32,51,.07);}
.st-key-drop_wrap {position: relative;}
.pl-drop {border: 1.5px dashed #D3DBE7; border-radius: 18px; padding: 60px 24px; text-align: center;
  background: linear-gradient(180deg, #FBFCFE 0%, #F7F9FC 100%); transition: border-color .15s, background .15s;}
.st-key-drop_wrap:hover .pl-drop {border-color: var(--pl-blue); background: #F7FAFF;}
.pl-drop-icon {width: 56px; height: 56px; margin: 0 auto 20px auto; border-radius: 14px; background: #fff;
  border: 1px solid var(--pl-line); box-shadow: 0 6px 16px rgba(23,32,51,.08); color: var(--pl-blue);
  display: flex; align-items: center; justify-content: center;}
.pl-drop-title {font-size: 17px; font-weight: 700; color: var(--pl-navy);}
.pl-drop-sub {font-size: 13px; color: var(--pl-muted); margin: 6px 0 18px 0;}
.pl-drop-btn {display: inline-block; background: #EAF1FF; color: var(--pl-blue); font-size: 14px;
  font-weight: 700; padding: 10px 18px; border-radius: 10px;}
.pl-drop-hint {font-size: 12px; color: #9AA4B5; margin-top: 18px;}

/* 실제 업로더는 디자인 위에 투명하게 덮어서 클릭·드래그를 받음 */
.st-key-drop_wrap [class*="st-key-upmain_"], .st-key-replace_wrap [class*="st-key-upswap_"] {
  position: absolute !important; inset: 0; z-index: 4; opacity: 0; margin: 0;}
[class*="st-key-upmain_"] [data-testid="stFileUploader"], [class*="st-key-upswap_"] [data-testid="stFileUploader"],
[class*="st-key-upmain_"] [data-testid="stFileUploader"] > div, [class*="st-key-upswap_"] [data-testid="stFileUploader"] > div,
[class*="st-key-upmain_"] section, [class*="st-key-upswap_"] section {height: 100%;}
[class*="st-key-upmain_"] [data-testid="stFileUploaderDropzone"], [class*="st-key-upswap_"] [data-testid="stFileUploaderDropzone"] {
  height: 100%; min-height: 100%; padding: 0; position: relative; cursor: pointer;}
[class*="st-key-upmain_"] [data-testid="stFileUploaderDropzone"] button,
[class*="st-key-upswap_"] [data-testid="stFileUploaderDropzone"] button {
  position: absolute; inset: 0; width: 100%; height: 100%; cursor: pointer;}

/* 사진 선택 후 */
.st-key-selected_panel {background: #F5F7FB; border-radius: 18px; padding: 20px;}
.st-key-preview_wrap {position: relative;}
.pl-preview {width: 100%; height: 300px; object-fit: cover; border-radius: 14px; display: block;}
.st-key-remove_btn {position: absolute !important; top: 10px; right: 10px; width: auto !important; z-index: 3;}
.st-key-remove_btn button {width: 30px; height: 30px; min-height: 30px; padding: 0; border-radius: 50%;
  background: rgba(55,60,70,.78); color: #fff; border: none;}
.st-key-remove_btn button:hover {background: rgba(30,34,42,.9); color: #fff;}
.st-key-remove_btn button p {font-size: 13px; line-height: 1;}
.pl-file-icon {width: 40px; height: 40px; border-radius: 10px; background: #EAF1FF; color: var(--pl-blue);
  display: flex; align-items: center; justify-content: center;}
.pl-file-name {font-size: 17px; font-weight: 700; color: var(--pl-navy); margin: 18px 0 6px 0;
  word-break: break-all; line-height: 1.4;}
.pl-file-meta {font-size: 12px; color: var(--pl-muted); margin-bottom: 8px;}
.st-key-replace_wrap {position: relative;}
.pl-replace {text-align: center; font-size: 13px; color: #4A5568; text-decoration: underline;
  text-underline-offset: 3px; padding: 2px 0;}

/* 주요 버튼 */
.st-key-analyze_btn button, .st-key-reanalyze_btn button {background: var(--pl-blue); border: none;
  border-radius: 12px; min-height: 50px; color: #fff; box-shadow: 0 8px 20px rgba(36,107,253,.28);}
.st-key-analyze_btn button:hover, .st-key-reanalyze_btn button:hover {background: #1A5BE6; color: #fff;}
.st-key-analyze_btn button:disabled {background: #9DBBFE; color: #fff; box-shadow: none;}
.st-key-analyze_btn button p, .st-key-reanalyze_btn button p {font-size: 15px; font-weight: 700;}
.st-key-back_btn button {padding: 0; min-height: 0; color: #4A5568;}
.st-key-back_btn button p {font-size: 13px; font-weight: 600;}
.st-key-back_btn button:hover {color: var(--pl-blue);}

/* 오류 안내 */
.pl-alert {display: flex; align-items: flex-start; gap: 8px; background: #FEF2F2; border: 1px solid #FBD5D5;
  color: #B42318; border-radius: 12px; padding: 12px 14px; font-size: 13px; line-height: 1.6;}
.pl-alert svg {flex: none; margin-top: 2px;}

/* 3단계 안내 */
.pl-steps {max-width: 860px; margin: 36px auto 0 auto; padding: 0 12px; display: grid;
  grid-template-columns: repeat(3, 1fr); gap: 24px;}
.pl-step {display: flex; align-items: flex-start; gap: 12px;}
.pl-step-num {flex: none; width: 26px; height: 26px; border-radius: 7px; background: #EAEFF6; color: var(--pl-sub);
  font-size: 11px; font-weight: 700; display: flex; align-items: center; justify-content: center;}
.pl-step-title {font-size: 14px; font-weight: 700; color: var(--pl-navy);}
.pl-step-desc {font-size: 12px; color: var(--pl-muted); margin-top: 4px;}

/* 결과 화면 */
.st-key-result_page {max-width: 1080px; margin: 40px auto 0 auto;}
.pl-result-head {display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; flex-wrap: wrap;}
.pl-result-title {font-size: 34px; font-weight: 800; color: var(--pl-navy); letter-spacing: -0.02em; margin: 6px 0 8px 0;}
.pl-result-sub {font-size: 14px; color: var(--pl-sub);}
.pl-result-side {display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--pl-muted);}
.pl-demo-note {display: inline-block; margin-top: 14px; background: #FFF7E6; border: 1px solid #FBE3B8;
  color: #92400E; font-size: 13px; border-radius: 10px; padding: 9px 14px; line-height: 1.6;}
.pl-shot {position: relative; background: #fff; border: 1px solid var(--pl-line); border-radius: 18px;
  padding: 10px; box-shadow: 0 6px 20px rgba(23,32,51,.06);}
.pl-shot img {width: 100%; aspect-ratio: 1 / 0.92; object-fit: cover; border-radius: 12px; display: block;}
.pl-shot-badge {position: absolute; top: 20px; left: 20px; display: inline-flex; align-items: center; gap: 5px;
  background: rgba(255,255,255,.94); border-radius: 8px; padding: 5px 10px; font-size: 12px; font-weight: 700; color: var(--pl-navy);}
.pl-overall {border: 1px solid; border-radius: 18px; padding: 22px 22px 20px 22px; margin-top: 16px;}
.pl-overall-top {display: flex; justify-content: space-between; align-items: flex-start;}
.pl-overall-label {font-size: 12px; font-weight: 700;}
.pl-overall-value {font-size: 30px; font-weight: 800; margin-top: 6px; letter-spacing: -0.02em;}
.pl-overall-icon {width: 38px; height: 38px; border-radius: 10px; border: 1px solid;
  display: flex; align-items: center; justify-content: center;}
.pl-gauge {height: 6px; border-radius: 999px; margin: 16px 0 14px 0; overflow: hidden;}
.pl-gauge span {display: block; height: 100%; border-radius: 999px;}
.pl-overall-msg {font-size: 13px; line-height: 1.7; color: var(--pl-sub);}
.pl-list-head {display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;}
.pl-list-title {font-size: 18px; font-weight: 800; color: var(--pl-navy);}
.pl-count {font-size: 12px; font-weight: 700; color: var(--pl-blue); background: #EAF1FF; padding: 4px 10px; border-radius: 999px;}

/* 위험 항목 (펼침/접힘) */
.pl-risk {background: #fff; border: 1px solid var(--pl-line); border-radius: 16px; margin-bottom: 12px;
  box-shadow: 0 1px 2px rgba(23,32,51,.04); overflow: hidden;}
.pl-risk[open] {box-shadow: 0 8px 24px rgba(23,32,51,.08);}
.pl-risk summary {list-style: none; cursor: pointer; display: flex; align-items: center; gap: 12px; padding: 18px 20px;}
.pl-risk summary::-webkit-details-marker {display: none;}
.pl-risk summary:focus-visible {outline: 2px solid var(--pl-blue); outline-offset: -2px; border-radius: 16px;}
.pl-dot {flex: none; width: 8px; height: 8px; border-radius: 50%;}
.pl-risk-title {flex: 1; min-width: 0;}
.pl-risk-cat {font-size: 11px; font-weight: 600; color: var(--pl-muted);}
.pl-risk-item {font-size: 16px; font-weight: 700; color: var(--pl-navy); margin-top: 2px; line-height: 1.4;}
.pl-badge {flex: none; font-size: 11px; font-weight: 700; padding: 3px 9px; border-radius: 999px; border: 1px solid;}
.pl-chev {flex: none; color: #8A94A6; display: flex; transition: transform .2s;}
.pl-risk[open] .pl-chev {transform: rotate(180deg);}
.pl-risk-body {border-top: 1px solid #EEF1F5; padding: 16px 20px 20px 20px;}
.pl-reason {font-size: 14px; line-height: 1.7; color: #4A5568; margin-bottom: 14px;}
.pl-fix {display: flex; gap: 12px; background: #F1F5FF; border-radius: 12px; padding: 14px 16px;}
.pl-fix-icon {flex: none; width: 22px; height: 22px; border-radius: 50%; background: var(--pl-blue); color: #fff;
  display: flex; align-items: center; justify-content: center;}
.pl-fix-title {font-size: 13px; font-weight: 700; color: var(--pl-blue); margin-bottom: 2px;}
.pl-fix-text {font-size: 13px; line-height: 1.6; color: #4A5568;}
.pl-empty {background: #fff; border: 1px solid var(--pl-line); border-radius: 16px; padding: 28px 20px;
  text-align: center; font-size: 14px; color: var(--pl-sub);}

/* 다시 분석 안내 카드 */
.st-key-cta_card {background: #FAFBFE; border: 1px solid var(--pl-line); border-radius: 18px; padding: 22px;
  box-shadow: 0 1px 2px rgba(23,32,51,.04); margin-top: 4px;}
.pl-cta {display: flex; gap: 12px; align-items: flex-start;}
.pl-cta-icon {flex: none; color: var(--pl-blue); margin-top: 1px;}
.pl-cta-title {font-size: 15px; font-weight: 700; color: var(--pl-navy);}
.pl-cta-desc {font-size: 13px; color: var(--pl-sub); margin-top: 4px; line-height: 1.6;}

/* 모자이크 · 블러 편집 카드 */
.st-key-edit_card {background: #fff; border: 1px solid var(--pl-line); border-radius: 20px; padding: 24px;
  box-shadow: 0 6px 20px rgba(23,32,51,.06); margin-top: 28px;}
.pl-edit-head {margin-bottom: 16px;}
.pl-edit-title {display: flex; align-items: center; gap: 8px; font-size: 18px; font-weight: 800; color: var(--pl-navy);}
.pl-edit-title svg {color: var(--pl-blue);}
.pl-edit-sub {font-size: 13px; color: var(--pl-sub); margin-top: 6px; line-height: 1.6;}
.st-key-edit_card [data-testid="stImage"] img {border-radius: 14px; border: 1px solid var(--pl-line);}
.pl-edit-caption {font-size: 12px; color: var(--pl-muted); margin-top: 6px; line-height: 1.6;}
.pl-ctrl-label {font-size: 13px; font-weight: 700; color: var(--pl-navy); margin: 4px 0 8px 0;}
.pl-ctrl-help {font-size: 12px; color: var(--pl-sub); margin: 4px 0 8px 0; line-height: 1.6;}
.pl-region-name {font-size: 13px; font-weight: 700; color: var(--pl-navy); margin-top: 8px;}
.pl-region-name span {font-weight: 500; color: var(--pl-muted);}
.st-key-edit_card [data-testid="stButtonGroup"] button[aria-checked="true"],
.st-key-edit_card [data-testid="stButtonGroup"] button[kind$="Active"] {
  background: #EAF1FF; border-color: var(--pl-blue); color: var(--pl-blue);}
.st-key-edit_card [data-testid="stExpander"] details {border-radius: 12px; border-color: var(--pl-line);}
.st-key-sel_all_btn button, .st-key-sel_none_btn button, [class*="st-key-nobox_"] button {
  border-radius: 10px; border-color: var(--pl-line); min-height: 38px;}
.st-key-sel_all_btn button p, .st-key-sel_none_btn button p, [class*="st-key-nobox_"] button p {font-size: 13px; font-weight: 600;}
.st-key-add_manual_btn button {color: var(--pl-blue); padding: 0; min-height: 0;}
.st-key-add_manual_btn button p {font-size: 13px; font-weight: 700;}

/* 다운로드 · 공유 버튼 (휴대폰에서도 나란히) */
.st-key-share_row {margin-top: 16px;}
.st-key-share_row [data-testid="stHorizontalBlock"] {flex-wrap: nowrap !important; gap: 10px;}
.st-key-share_row [data-testid="stColumn"] {min-width: 0 !important; width: 50% !important; flex: 1 1 0 !important;}
.st-key-download_btn button {background: var(--pl-blue); border: none; border-radius: 12px; min-height: 44px; height: 44px;
  color: #fff; box-shadow: 0 8px 20px rgba(36,107,253,.22);}
.st-key-download_btn button:hover {background: #1A5BE6; color: #fff;}
.st-key-download_btn button p {font-size: 15px; font-weight: 700;}
.st-key-share_row iframe {display: block;}
.st-key-cta_card {margin-top: 16px;}

/* 휴대폰 화면 */
@media (max-width: 640px) {
  .st-key-edit_card {padding: 16px; border-radius: 18px;}
  [data-testid="stMainBlockContainer"], .block-container {padding: 0 16px;}
  .pl-header-inner {padding: 14px 16px;}
  .pl-logo {width: 34px; height: 34px; border-radius: 10px;}
  .pl-brand-name {font-size: 16px;}
  .pl-hero {padding: 36px 0 24px 0;}
  .pl-hero-title {font-size: 30px; margin: 18px 0 14px 0;}
  .pl-hero-desc {font-size: 14px;}
  .st-key-upload_card {padding: 14px; border-radius: 20px;}
  .st-key-selected_panel {padding: 14px;}
  .pl-drop {padding: 40px 16px;}
  .pl-preview {height: 240px;}
  .pl-steps {grid-template-columns: 1fr; gap: 14px; margin-top: 28px;}
  .st-key-result_page {margin-top: 24px;}
  .pl-result-title {font-size: 26px;}
  .pl-risk summary {padding: 16px;}
  .pl-risk-body {padding: 14px 16px 16px 16px;}
  .pl-footer {margin-top: 48px;}
}
</style>
"""


# ----- 사진 위 영역 편집기 (Streamlit Components v2, 별도 파일 없이 app.py 안에 작성) -----
BOX_EDITOR_CSS = """
.be-root {text-align: center; user-select: none; -webkit-user-select: none;}
.be-frame {position: relative; display: inline-block; max-width: 100%; line-height: 0;}
.be-img {display: block; max-width: 100%; max-height: 620px; width: auto; height: auto; pointer-events: none;
  border-radius: 14px; border: 1px solid #E6EBF2; box-sizing: border-box;}
.be-layer {position: absolute; inset: 0;}
.be-box {position: absolute; box-sizing: border-box; border: 2px solid #246BFD; border-radius: 4px;
  background: rgba(36,107,253,.08); cursor: move; touch-action: none; outline: none;}
.be-box:focus-visible, .be-box.active {border-color: #0B4FE0; box-shadow: 0 0 0 3px rgba(36,107,253,.35);}
.be-label {position: absolute; left: -2px; top: -22px; max-width: 220px; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; background: #246BFD; color: #fff; font-size: 11px; font-weight: 700; line-height: 1;
  padding: 5px 7px; border-radius: 4px 4px 4px 0; pointer-events: none;}
.be-box.top .be-label {top: auto; bottom: -22px; border-radius: 0 4px 4px 4px;}
.be-h {position: absolute; width: 14px; height: 14px; background: #fff; border: 2px solid #246BFD;
  border-radius: 50%; box-sizing: border-box; touch-action: none;}
.be-h::after {content: ""; position: absolute; inset: -10px;}  /* 손가락으로 잡기 쉽게 터치 영역 확대 */
.be-h[data-h="nw"] {left: -8px; top: -8px; cursor: nwse-resize;}
.be-h[data-h="ne"] {right: -8px; top: -8px; cursor: nesw-resize;}
.be-h[data-h="sw"] {left: -8px; bottom: -8px; cursor: nesw-resize;}
.be-h[data-h="se"] {right: -8px; bottom: -8px; cursor: nwse-resize;}
.be-h[data-h="n"] {left: calc(50% - 7px); top: -8px; cursor: ns-resize;}
.be-h[data-h="s"] {left: calc(50% - 7px); bottom: -8px; cursor: ns-resize;}
.be-h[data-h="w"] {left: -8px; top: calc(50% - 7px); cursor: ew-resize;}
.be-h[data-h="e"] {right: -8px; top: calc(50% - 7px); cursor: ew-resize;}
.be-root.view .be-layer {display: none;}
"""

BOX_EDITOR_JS = """
export default function(component) {
  const { data, setStateValue, parentElement } = component;
  let root = parentElement.querySelector(".be-root");
  if (!root) {
    root = document.createElement("div");
    root.className = "be-root";
    root.innerHTML = '<div class="be-frame"><img class="be-img" alt="가림 처리 미리보기" draggable="false"><div class="be-layer"></div></div>';
    parentElement.appendChild(root);
  }
  if (root._dragging) return;  // 드래그 중에는 화면을 다시 그리지 않음

  const img = root.querySelector(".be-img");
  const layer = root.querySelector(".be-layer");
  if (img.getAttribute("src") !== data.img) img.setAttribute("src", data.img);
  root.classList.toggle("view", !data.edit);

  const MIN = 2;  // 최소 크기(%)
  const boxes = (data.boxes || []).map(b => ({ id: b.id, label: b.label, v: b.box.slice() }));
  const clamp = (n, lo, hi) => Math.min(Math.max(n, lo), hi);
  let timer = null;

  function commit(now) {
    clearTimeout(timer);
    const send = () => {
      const out = {};
      boxes.forEach(b => { out[b.id] = b.v.map(n => Math.round(n * 10) / 10); });
      setStateValue("boxes", out);
    };
    if (now) send(); else timer = setTimeout(send, 450);
  }

  function place(el, v) {
    el.style.left = v[0] + "%";
    el.style.top = v[1] + "%";
    el.style.width = (v[2] - v[0]) + "%";
    el.style.height = (v[3] - v[1]) + "%";
    el.classList.toggle("top", v[1] < 6);
  }

  layer.innerHTML = "";
  boxes.forEach(b => {
    const el = document.createElement("div");
    el.className = "be-box";
    el.tabIndex = 0;
    el.setAttribute("role", "group");
    el.setAttribute("aria-label", b.label + " 가림 영역. 방향키로 이동, Shift+방향키로 크기 조절");
    el.innerHTML = '<span class="be-label"></span>' +
      ["nw", "n", "ne", "e", "se", "s", "sw", "w"].map(h => '<span class="be-h" data-h="' + h + '"></span>').join("");
    el.querySelector(".be-label").textContent = b.label;
    place(el, b.v);
    layer.appendChild(el);
    el.addEventListener("focus", () => { root._focus = b.id; });
    if (root._focus === b.id) el.focus({ preventScroll: true });  // 다시 그린 뒤에도 키보드 포커스 유지

    el.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      e.stopPropagation();
      el.focus({ preventScroll: true });
      const handle = e.target.dataset && e.target.dataset.h ? e.target.dataset.h : "move";
      const rect = layer.getBoundingClientRect();
      const start = { x: e.clientX, y: e.clientY, v: b.v.slice() };
      root._dragging = true;
      el.classList.add("active");
      el.setPointerCapture(e.pointerId);

      const onMove = (ev) => {
        const dx = (ev.clientX - start.x) / rect.width * 100;
        const dy = (ev.clientY - start.y) / rect.height * 100;
        let [x0, y0, x1, y1] = start.v;
        if (handle === "move") {
          const w = x1 - x0, h = y1 - y0;
          x0 = clamp(x0 + dx, 0, 100 - w); y0 = clamp(y0 + dy, 0, 100 - h);
          x1 = x0 + w; y1 = y0 + h;
        } else {
          if (handle.includes("w")) x0 = clamp(x0 + dx, 0, x1 - MIN);
          if (handle.includes("e")) x1 = clamp(x1 + dx, x0 + MIN, 100);
          if (handle.includes("n")) y0 = clamp(y0 + dy, 0, y1 - MIN);
          if (handle.includes("s")) y1 = clamp(y1 + dy, y0 + MIN, 100);
        }
        b.v = [x0, y0, x1, y1];
        place(el, b.v);
      };
      const onUp = () => {
        el.removeEventListener("pointermove", onMove);
        el.removeEventListener("pointerup", onUp);
        el.removeEventListener("pointercancel", onUp);
        el.classList.remove("active");
        root._dragging = false;
        commit(true);
      };
      el.addEventListener("pointermove", onMove);
      el.addEventListener("pointerup", onUp);
      el.addEventListener("pointercancel", onUp);
    });

    // 키보드: 방향키 이동, Shift+방향키 크기 조절
    el.addEventListener("keydown", (e) => {
      const step = 1;
      const keys = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
      if (!keys[e.key]) return;
      e.preventDefault();
      const [dx, dy] = keys[e.key];
      let [x0, y0, x1, y1] = b.v;
      if (e.shiftKey) {
        x1 = clamp(x1 + dx, x0 + MIN, 100); y1 = clamp(y1 + dy, y0 + MIN, 100);
      } else {
        const w = x1 - x0, h = y1 - y0;
        x0 = clamp(x0 + dx, 0, 100 - w); y0 = clamp(y0 + dy, 0, 100 - h);
        x1 = x0 + w; y1 = y0 + h;
      }
      b.v = [x0, y0, x1, y1];
      place(el, b.v);
      commit(false);
    });
  });
}
"""

# ----- 5단계 점 슬라이더 -----
LEVEL_DOTS_CSS = """
.ld {padding: 6px 4px 0 4px; user-select: none; -webkit-user-select: none;}
.ld-track {position: relative; height: 28px; cursor: pointer; touch-action: none; outline: none;}
.ld-line, .ld-fill {position: absolute; left: 7px; right: 7px; top: 12px; height: 4px; border-radius: 999px; background: #E6EBF2;}
.ld-fill {right: auto; background: #246BFD;}
.ld-dot {position: absolute; top: 8px; width: 12px; height: 12px; margin-left: -6px; border-radius: 50%;
  background: #fff; border: 2px solid #C9D3E2; box-sizing: border-box;}
.ld-dot.on {border-color: #246BFD; background: #246BFD;}
.ld-thumb {position: absolute; top: 3px; width: 22px; height: 22px; margin-left: -11px; border-radius: 50%;
  background: #fff; border: 3px solid #246BFD; box-sizing: border-box; box-shadow: 0 2px 6px rgba(36,107,253,.35);
  transition: left .12s;}
.ld-track:focus-visible .ld-thumb {box-shadow: 0 0 0 4px rgba(36,107,253,.3);}
.ld-labels {position: relative; height: 18px; margin-top: 4px; font-size: 12px; color: #8A94A6;}
.ld-labels span {position: absolute; transform: translateX(-50%); white-space: nowrap;}
.ld-labels span.on {color: #246BFD; font-weight: 700;}
"""

LEVEL_DOTS_JS = """
export default function(component) {
  const { data, setStateValue, parentElement } = component;
  const N = 5;
  const pos = (v) => "calc(7px + (100% - 14px) * " + ((v - 1) / (N - 1)) + ")";
  let root = parentElement.querySelector(".ld");
  if (!root) {
    root = document.createElement("div");
    root.className = "ld";
    let dots = "", labels = "";
    for (let i = 1; i <= N; i++) {
      dots += '<span class="ld-dot" data-v="' + i + '" style="left:' + pos(i) + '"></span>';
      labels += '<span data-v="' + i + '" style="left:' + pos(i) + '">' + i + '</span>';
    }
    root.innerHTML =
      '<div class="ld-track" tabindex="0" role="slider" aria-label="가림 강도" aria-valuemin="1" aria-valuemax="5">' +
      '<span class="ld-line"></span><span class="ld-fill"></span>' + dots + '<span class="ld-thumb"></span></div>' +
      '<div class="ld-labels">' + labels + '</div>';
    parentElement.appendChild(root);
  }
  const track = root.querySelector(".ld-track");
  const fill = root.querySelector(".ld-fill");
  const thumb = root.querySelector(".ld-thumb");
  let value = Math.min(Math.max(parseInt(data.value) || 3, 1), N);

  function draw(v) {
    thumb.style.left = pos(v);
    fill.style.width = "calc((100% - 14px) * " + ((v - 1) / (N - 1)) + ")";
    root.querySelectorAll(".ld-dot").forEach(d => d.classList.toggle("on", +d.dataset.v <= v));
    root.querySelectorAll(".ld-labels span").forEach(s => s.classList.toggle("on", +s.dataset.v === v));
    track.setAttribute("aria-valuenow", v);
    track.setAttribute("aria-valuetext", v + "단계");
  }
  function pick(clientX) {
    const r = track.getBoundingClientRect();
    const ratio = (clientX - r.left - 7) / Math.max(r.width - 14, 1);
    return Math.min(Math.max(Math.round(ratio * (N - 1)) + 1, 1), N);
  }
  function set(v, send) {
    if (v === value && !send) return;
    value = v; draw(v);
    if (send) setStateValue("value", v);
  }

  track.onpointerdown = (e) => {
    e.preventDefault();
    track.focus({ preventScroll: true });
    track.setPointerCapture(e.pointerId);
    set(pick(e.clientX), false);
    track.onpointermove = (ev) => set(pick(ev.clientX), false);
    track.onpointerup = track.onpointercancel = () => {
      track.onpointermove = null;
      set(value, true);
    };
  };
  track.onkeydown = (e) => {
    const map = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1 };
    if (e.key in map) { e.preventDefault(); set(Math.min(Math.max(value + map[e.key], 1), N), true); }
    else if (e.key === "Home") { e.preventDefault(); set(1, true); }
    else if (e.key === "End") { e.preventDefault(); set(N, true); }
  };
  draw(value);
}
"""

box_editor = st.components.v2.component(
    "privacy_lens_box_editor", css=BOX_EDITOR_CSS, js=BOX_EDITOR_JS,
)
level_dots = st.components.v2.component(
    "privacy_lens_level_dots", css=LEVEL_DOTS_CSS, js=LEVEL_DOTS_JS,
)


# ----- 공통 도우미 -----
def esc(text):
    """분석 결과 문구를 HTML에 넣기 전에 안전하게 변환"""
    return html.escape(str(text))


def render(markup):
    """줄 앞 공백과 빈 줄을 없애 마크다운이 코드블록으로 오해하지 않게 함"""
    cleaned = "\n".join(line.strip() for line in markup.splitlines() if line.strip())
    st.markdown(cleaned, unsafe_allow_html=True)


def format_size(size):
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    return f"{max(size // 1024, 1)} KB"


WORK_MAX = 2560  # 편집·저장용 사진의 최대 변 길이(px)


def make_work_image(img):
    """회전 정보(EXIF)를 반영하고 RGB로 바꾼 편집용 사진"""
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    img.thumbnail((WORK_MAX, WORK_MAX))
    return img


def to_jpeg(img, quality=92):
    """JPEG로 저장 (exif를 넘기지 않으므로 GPS 등 메타데이터가 포함되지 않음)"""
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def make_preview(work):
    """화면 표시용 작은 미리보기(base64)"""
    small = work.copy()
    small.thumbnail((1200, 1200))
    return base64.b64encode(to_jpeg(small, 85)).decode("ascii")


def load_photo(uploaded):
    """업로드 파일 검사: 용량, 형식, 손상 여부"""
    data = uploaded.getvalue()
    if len(data) > MAX_BYTES:
        raise ValueError("사진 용량이 10MB를 넘습니다. 더 작은 사진을 선택해 주세요.")
    try:
        img = Image.open(io.BytesIO(data))
        fmt = img.format
        img.load()
    except Exception:
        raise ValueError("사진 파일을 열 수 없습니다. JPG, PNG, WEBP 사진을 선택해 주세요.")
    if fmt not in ALLOWED_FORMATS:
        raise ValueError("지원하지 않는 형식입니다. JPG, PNG, WEBP 사진만 올릴 수 있습니다.")
    return make_photo(uploaded.name, data, make_work_image(img))


def make_photo(name, data, work):
    """세션에 보관하는 사진 정보 (메모리에만 두고 파일로 저장하지 않음)"""
    return {"name": name, "bytes": data, "size": len(data), "work": work, "preview": make_preview(work)}


def normalize_result(result):
    """analyze 결과 형식 확인 후 화면에서 쓰기 좋게 정리"""
    if not isinstance(result, dict) or not isinstance(result.get("risks"), list):
        raise ValueError("분석 결과 형식이 올바르지 않습니다.")
    overall = result.get("overall")
    if overall not in OVERALL_STYLE:
        raise ValueError("종합 위험도 값이 올바르지 않습니다.")
    risks = []
    for r in result["risks"]:
        if not isinstance(r, dict):
            continue
        try:
            sev = int(r.get("severity", 2))
        except (TypeError, ValueError):
            sev = 2
        risks.append({
            "category": r.get("category", "기타"),
            "item": r.get("item", ""),
            "reason": r.get("reason", ""),
            "severity": min(max(sev, 1), 3),
            "fix": r.get("fix", ""),
            "box": parse_box(r.get("box")),
        })
    risks.sort(key=lambda r: r["severity"], reverse=True)
    return {"overall": overall, "risks": risks}


def parse_box(box):
    """box([ymin, xmin, ymax, xmax], 0~1000)가 올바르면 정수 목록, 아니면 None"""
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    try:
        y0, x0, y1, x1 = (min(max(int(round(float(v))), 0), 1000) for v in box)
    except (TypeError, ValueError):
        return None
    if y1 - y0 < 5 or x1 - x0 < 5:
        return None
    return [y0, x0, y1, x1]


# ----- 상태 관리 -----
ss = st.session_state
for key, value in {
    "photo": None, "result": None, "upload_error": None,
    "analyze_error": None, "analyzing": False, "nonce": 0,
    "edit_ver": 0, "regions": [], "mask_level": 3,
}.items():
    ss.setdefault(key, value)


# ----- 모자이크 편집 상태 -----
# 가릴 영역(region)은 ss.regions에 % 좌표로 보관하고, 사진 위 편집기에서 바뀐 값을 받아 갱신
# 새 결과가 나오면 edit_ver를 올려 이전 위젯 값과 섞이지 않게 함
def sel_key():
    return f"sel_{ss.edit_ver}"


def editor_key():
    return f"boxed_{ss.edit_ver}"


def add_region(label, box, manual):
    """가릴 영역 추가. box는 [ymin, xmin, ymax, xmax] (0~1000) -> [x0, y0, x1, y1] (%)로 저장"""
    rid = f"r{len(ss.regions)}"
    y0, x0, y1, x1 = box
    ss.regions.append({"id": rid, "label": label, "manual": manual,
                       "box": [x0 / 10, y0 / 10, x1 / 10, y1 / 10]})
    return rid


def sync_boxes():
    """사진 위 편집기에서 영역을 옮기거나 크기를 바꾸면 호출됨"""
    state = ss.get(editor_key()) or {}
    moved = state.get("boxes") or {}
    for r in ss.regions:
        b = moved.get(r["id"])
        if isinstance(b, list) and len(b) == 4:
            x0, y0, x1, y1 = (min(max(float(v), 0.0), 100.0) for v in b)
            if x1 - x0 >= 1 and y1 - y0 >= 1:
                r["box"] = [x0, y0, x1, y1]


def sync_level():
    """5단계 강도 슬라이더 값 반영"""
    value = (ss.get("level_dots") or {}).get("value")
    if value in (1, 2, 3, 4, 5):
        ss.mask_level = value


def init_editor(result):
    """분석 결과의 box로 자동 모자이크 영역을 만들고 전부 선택(기본값)"""
    ss.edit_ver += 1
    ss.regions = []
    ids = [add_region(r["item"], r["box"], False) for r in result["risks"] if r["box"]]
    ss[sel_key()] = ids


def select_all_regions():
    ss[sel_key()] = [r["id"] for r in ss.regions]


def clear_regions():
    ss[sel_key()] = []


def add_manual_region(label):
    """위치 정보가 없거나 AI가 놓친 부분을 직접 가리기 (가운데에 기본 영역 생성)"""
    rid = add_region(label, [350, 350, 650, 650], True)
    ss[sel_key()] = list(ss.get(sel_key(), [])) + [rid]


def selected_regions():
    chosen = set(ss.get(sel_key(), []) or [])
    return [r for r in ss.regions if r["id"] in chosen]


def selected_boxes():
    """선택된 영역의 % 좌표 목록 [(이름, x0, y0, x1, y1), ...]"""
    return [(r["label"], *r["box"]) for r in selected_regions()]


# 강도 1~5단계: 모자이크는 짧은 변을 몇 칸으로 나눌지, 블러는 짧은 변 대비 반지름 비율
STRENGTH = {
    1: {"cells": 18, "blur": 0.04},
    2: {"cells": 12, "blur": 0.08},
    3: {"cells": 8, "blur": 0.13},
    4: {"cells": 5, "blur": 0.19},
    5: {"cells": 3, "blur": 0.28},
}


def apply_masks(img, boxes, mode, level):
    """선택 영역에 모자이크 또는 블러 적용 (원본은 그대로 두고 새 이미지 반환)"""
    out = img.copy()
    W, H = out.size
    conf = STRENGTH.get(level, STRENGTH[3])
    for _, x0, y0, x1, y1 in boxes:
        box = (int(x0 / 100 * W), int(y0 / 100 * H), int(x1 / 100 * W), int(y1 / 100 * H))
        w, h = box[2] - box[0], box[3] - box[1]
        if w < 2 or h < 2:
            continue
        region = out.crop(box)
        if mode == "블러":
            radius = max(3, min(w, h) * conf["blur"])
            region = region.filter(ImageFilter.GaussianBlur(radius))
        else:
            cell = max(3, min(w, h) // conf["cells"])
            small = region.resize((max(1, w // cell), max(1, h // cell)), Image.BILINEAR)
            region = small.resize((w, h), Image.NEAREST)
        out.paste(region, box)
    return out


def current_edit():
    """현재 설정으로 만든 수정본 사진"""
    mode = ss.get("mask_mode") or "모자이크"
    return apply_masks(ss.photo["work"], selected_boxes(), mode, ss.get("mask_level", 3))


def reanalyze_edited():
    """수정본으로 사진을 바꾸고 바로 다시 분석"""
    data = to_jpeg(current_edit())
    stem = Path(ss.photo["name"]).stem.removeprefix("수정본_")
    ss.photo = make_photo(f"수정본_{stem}.jpg", data, Image.open(io.BytesIO(data)).convert("RGB"))
    ss.result = None
    ss.analyze_error = None
    ss.analyzing = True


def reset_all():
    """처음 화면으로 (사진·결과·오류 모두 비움)"""
    ss.photo = None
    ss.result = None
    ss.upload_error = None
    ss.analyze_error = None
    ss.analyzing = False


def start_analysis():
    ss.analyzing = True
    ss.analyze_error = None


def accept_upload(uploaded):
    """새 사진 받기: 업로더를 비우고, 정상 사진이면 이전 결과 초기화"""
    ss.nonce += 1
    try:
        photo = load_photo(uploaded)
    except ValueError as e:
        ss.upload_error = str(e)
        return
    ss.photo = photo
    ss.result = None
    ss.upload_error = None
    ss.analyze_error = None


def show_alert(message):
    render(f'<div class="pl-alert" role="alert">{icon("alert", 16)}<span>{esc(message)}</span></div>')


# ----- 공통 영역 -----
def show_header():
    right = ""
    if IS_DEMO:
        right += '<span class="pl-demo-pill">데모 모드 · 예시 결과</span>'
    if STORAGE_GUARANTEED:
        right += f'<span class="pl-header-note">{icon("lock", 14)}업로드된 사진은 저장되지 않습니다</span>'
    render(
        f"""
        <div class="pl-header"><div class="pl-header-inner">
        <div class="pl-brand"><span class="pl-logo">{icon("shield", 20)}</span>
        <span class="pl-brand-name">Privacy Lens</span></div>
        <div class="pl-header-right">{right}</div>
        </div></div>
        """
    )


def show_footer():
    render(
        """
        <div class="pl-footer">
        AI 분석 결과는 참고용이며, 모든 개인정보 노출을 완벽하게 탐지하지 못할 수 있습니다.
        </div>
        """
    )


# ----- 업로드 화면 (업로드 전 · 사진 선택 후 · 분석 중 · 오류) -----
def show_upload_view():
    render(
        f"""
        <div class="pl-hero">
        <span class="pl-chip">{icon("scan", 14)}AI 개인정보 노출 점검</span>
        <div class="pl-hero-title" role="heading" aria-level="1">올리기 전, 사진 속<br><span>개인정보를 확인하세요</span></div>
        <p class="pl-hero-desc">무심코 찍힌 주소, 이름, 위치 단서를 AI가 찾아<br>안전하게 공유할 수 있도록 알려드려요.</p>
        </div>
        """
    )

    with st.container(key="upload_card"):
        if ss.photo is None:
            show_dropzone()
        else:
            show_selected()

        if ss.upload_error:
            show_alert(ss.upload_error)
        if ss.analyze_error:
            show_alert(ss.analyze_error)

    render(
        """
        <div class="pl-steps">
        <div class="pl-step"><span class="pl-step-num">01</span><div>
        <div class="pl-step-title">사진 업로드</div><div class="pl-step-desc">공유하려는 사진을 선택해요</div></div></div>
        <div class="pl-step"><span class="pl-step-num">02</span><div>
        <div class="pl-step-title">AI 위험 분석</div><div class="pl-step-desc">노출 가능한 단서를 찾아요</div></div></div>
        <div class="pl-step"><span class="pl-step-num">03</span><div>
        <div class="pl-step-title">안전하게 수정</div><div class="pl-step-desc">항목별 해결 방법을 확인해요</div></div></div>
        </div>
        """
    )


def show_dropzone():
    with st.container(key="drop_wrap"):
        render(
            f"""
            <div class="pl-drop">
            <div class="pl-drop-icon">{icon("upload", 22)}</div>
            <div class="pl-drop-title">사진을 여기에 끌어다 놓으세요</div>
            <div class="pl-drop-sub">또는 클릭해서 파일 선택</div>
            <span class="pl-drop-btn">사진 선택하기</span>
            <div class="pl-drop-hint">JPG, PNG, WEBP · 최대 10MB</div>
            </div>
            """
        )
        uploaded = st.file_uploader(
            "사진 선택하기", key=f"upmain_{ss.nonce}", label_visibility="collapsed"
        )
    if uploaded is not None:
        accept_upload(uploaded)
        st.rerun()


def show_selected():
    photo = ss.photo
    with st.container(key="selected_panel"):
        left, right = st.columns([2, 3], gap="large", vertical_alignment="center")

        with left:
            with st.container(key="preview_wrap"):
                render(f'<img class="pl-preview" src="data:image/jpeg;base64,{photo["preview"]}" alt="선택한 사진 미리보기">')
                st.button("✕", key="remove_btn", help="사진 삭제", on_click=reset_all, disabled=ss.analyzing)

        with right:
            status = "분석 중" if ss.analyzing else "분석 준비 완료"
            render(
                f"""
                <div class="pl-file-icon">{icon("image", 18)}</div>
                <div class="pl-file-name">{esc(photo["name"])}</div>
                <div class="pl-file-meta">{format_size(photo["size"])} · {status}</div>
                """
            )
            st.button(
                "분석 중입니다…" if ss.analyzing else "개인정보 노출 분석하기",
                key="analyze_btn", type="primary", width="stretch",
                icon=":material/center_focus_weak:",
                disabled=ss.analyzing, on_click=start_analysis,
            )

            with st.container(key="replace_wrap"):
                render('<div class="pl-replace">다른 사진 선택</div>')
                swap = st.file_uploader(
                    "다른 사진 선택", key=f"upswap_{ss.nonce}",
                    label_visibility="collapsed", disabled=ss.analyzing,
                )

            if ss.analyzing:
                run_analysis()

    if swap is not None:
        accept_upload(swap)
        st.rerun()


def run_analysis():
    """분석 실행 (버튼은 이미 비활성 상태라 중복 요청이 막힘)"""
    text = "예시 결과를 불러오는 중입니다…" if IS_DEMO else "사진 속 단서를 분석하는 중입니다…"
    with st.spinner(text):
        try:
            ss.result = normalize_result(analyze(ss.photo["bytes"]))
            init_editor(ss.result)
        except Exception as e:
            ss.result = None
            ss.analyze_error = f"분석 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요. ({e})"
        finally:
            ss.analyzing = False
    st.rerun()


# ----- 결과 화면 -----
def show_result_view():
    result = ss.result
    risks = result["risks"]
    count = len(risks)

    with st.container(key="result_page"):
        st.button("← 다른 사진 분석하기", key="back_btn", type="tertiary", on_click=reset_all)

        if IS_DEMO:
            sub = f"예시 결과로 개인정보 노출 가능성이 있는 단서 {count}개를 보여 드립니다."
        elif count:
            sub = f"사진에서 개인정보 노출 가능성이 있는 단서 {count}개를 찾았습니다."
        else:
            sub = "사진에서 개인정보 노출 가능성이 있는 단서를 찾지 못했습니다."
        side = ""
        if STORAGE_GUARANTEED:
            side = f'<div class="pl-result-side">{icon("lock", 13)}분석 완료 후 사진은 자동 삭제됩니다</div>'
        demo_note = ""
        if IS_DEMO:
            demo_note = (
                '<div class="pl-demo-note">데모 화면입니다. 업로드한 사진을 실제로 분석한 결과가 아니라 '
                "미리 준비한 예시 결과입니다.</div>"
            )
        render(
            f"""
            <div class="pl-result-head">
            <div><div class="pl-result-title" role="heading" aria-level="1">분석 결과</div>
            <div class="pl-result-sub">{esc(sub)}</div></div>
            {side}
            </div>
            {demo_note}
            """
        )

        left, right = st.columns([1, 1.9], gap="large")
        with left:
            show_photo_and_overall(result["overall"])
        with right:
            show_risk_list(risks)

        show_editor(risks)


# ----- 모자이크 · 블러 편집 -----
def show_editor(risks):
    with st.container(key="edit_card"):
        render(
            f"""
            <div class="pl-edit-head">
            <div class="pl-edit-title" role="heading" aria-level="2">{icon("scan", 18)}사진 안전하게 수정하기</div>
            <div class="pl-edit-sub">발견된 위치는 자동으로 가려집니다. 가릴 범위를 고르고 위치와 크기를 직접 고칠 수 있어요.</div>
            </div>
            """
        )
        if IS_DEMO:
            render(
                '<div class="pl-demo-note" style="margin:0 0 16px 0;">데모: 가릴 영역의 위치는 예시 값입니다. '
                "사진 속 실제 위치와 다를 수 있으니 사진 위 상자를 끌어서 맞춰 주세요.</div>"
            )

        left, right = st.columns([1.25, 1], gap="large")
        with right:
            show_edit_controls(risks)
        with left:
            edited = current_edit()
            show_box_editor(edited)
            count = len(selected_regions())
            hint = " · 상자를 끌어 옮기고, 모서리를 끌어 크기를 바꾸세요" if count and ss.get("show_outline", True) else ""
            render(f'<div class="pl-edit-caption">가리는 영역 {count}곳{hint}</div>')

        # 공유는 위험도가 '낮음'이거나, 사용자가 모자이크/블러를 적용(가림 영역 선택)한 뒤에만 활성화
        masked = len(selected_regions()) > 0
        can_share = ss.result["overall"] == "낮음" or masked
        show_save_share(edited, can_share)

    with st.container(key="cta_card"):
        render(
            f"""
            <div class="pl-cta"><span class="pl-cta-icon">{icon("shield", 20)}</span><div>
            <div class="pl-cta-title">사진을 수정한 뒤 다시 확인해 보세요</div>
            <div class="pl-cta-desc">위에서 가린 사진으로 다시 분석해 남은 단서가 있는지 확인할 수 있습니다.</div>
            </div></div>
            """
        )
        st.button("수정한 사진 다시 분석하기", key="reanalyze_btn", type="primary",
                  width="stretch", on_click=reanalyze_edited)


def show_edit_controls(risks):
    labels = {r["id"]: r["label"] for r in ss.regions}

    render('<div class="pl-ctrl-label">가릴 범위</div>')
    if ss.regions:
        st.pills(
            "가릴 범위", options=list(labels), key=sel_key(), selection_mode="multi",
            format_func=lambda rid: f"{labels[rid]} 가리기", label_visibility="collapsed",
        )
        c1, c2 = st.columns(2, gap="small")
        c1.button("전체 가리기", key="sel_all_btn", width="stretch", on_click=select_all_regions)
        c2.button("선택 해제", key="sel_none_btn", width="stretch", on_click=clear_regions)
    else:
        render('<div class="pl-ctrl-help">자동으로 가릴 위치 정보가 없습니다. 아래에서 직접 영역을 추가해 주세요.</div>')

    # 위치 정보(box)가 없는 항목은 직접 지정하도록 안내
    added = {r["label"] for r in ss.regions}
    no_box = [r for r in risks if not r["box"] and r["item"] not in added]
    if no_box:
        render('<div class="pl-ctrl-help">위치를 찾지 못한 항목은 직접 영역을 지정해 주세요.</div>')
        for i, r in enumerate(no_box):
            st.button(f"＋ {r['item']} 직접 지정", key=f"nobox_{ss.edit_ver}_{i}",
                      width="stretch", on_click=add_manual_region, args=(r["item"],))
    st.button("＋ 다른 영역 직접 추가", key="add_manual_btn", type="tertiary",
              on_click=add_manual_region, args=(f"직접 추가 {sum(r['manual'] for r in ss.regions) + 1}",))

    render('<div class="pl-ctrl-label">가리는 방식</div>')
    st.segmented_control("가리는 방식", ["모자이크", "블러"], key="mask_mode", default="모자이크",
                         label_visibility="collapsed")
    render('<div class="pl-ctrl-label" style="margin-top:14px;">강도</div>')
    level_dots(
        data={"value": ss.mask_level},
        default={"value": ss.mask_level},
        key="level_dots",
        on_value_change=sync_level,
    )
    st.toggle("편집 상자 표시", value=True, key="show_outline",
              help="끄면 가려진 결과만 볼 수 있습니다. 저장되는 사진에는 상자가 들어가지 않습니다.")


def show_box_editor(edited):
    """가려진 미리보기 위에 상자를 겹쳐 그리고, 드래그로 옮기거나 크기를 바꿀 수 있게 함"""
    small = edited.copy()
    small.thumbnail((1400, 1400))
    src = "data:image/jpeg;base64," + base64.b64encode(to_jpeg(small, 85)).decode("ascii")
    boxes = [{"id": r["id"], "label": r["label"], "box": r["box"]} for r in selected_regions()]
    box_editor(
        data={"img": src, "boxes": boxes, "edit": bool(ss.get("show_outline", True))},
        key=editor_key(),
        on_boxes_change=sync_boxes,
    )


def show_save_share(edited):
    """다운로드와 공유 버튼을 나란히 배치.

    can_share=True일 때만 공유 버튼을 활성화한다.
    (위험도 '낮음'이거나 사용자가 모자이크/블러를 적용한 경우)
    """
    data = to_jpeg(edited)
    stem = Path(ss.photo["name"]).stem.removeprefix("수정본_")
    filename = f"privacy-lens_{stem}.jpg"
    with st.container(key="share_row"):
        c1, c2 = st.columns(2, gap="small")
        with c1:
            st.download_button("사진 다운로드", data=data, file_name=filename, mime="image/jpeg",
                               key="download_btn", type="primary", width="stretch",
                               icon=":material/download:", on_click="ignore")
        with c2:
            if can_share:
                components.html(share_button_html(data, filename), height=50)
            else:
                # 위험 요소가 남아 있고 아직 가리지 않은 경우: 공유 비활성 + 안내
                components.html(share_disabled_html(), height=50)
    if can_share:
        render(
            '<div class="pl-edit-caption">다운로드·공유되는 사진에는 GPS 같은 촬영 정보(메타데이터)가 포함되지 않습니다.</div>'
        )
    else:
        render(
            '<div class="pl-edit-caption">공유하려면 위험 요소를 먼저 가려 주세요. '
            '다운로드·공유되는 사진에는 GPS 같은 촬영 정보(메타데이터)가 포함되지 않습니다.</div>'
        )


def share_button_html(data, filename):
    """휴대폰 공유 시트(Web Share API)를 여는 버튼. 지원하지 않는 환경이면 다운로드로 안내.

    공유 버튼은 Streamlit components.html의 iframe 안에서 실행된다.
    Web Share API는 'web-share' Permissions Policy로 게이트되며,
    서드파티 iframe에서는 iframe에 allow="web-share"가 있어야 동작한다.
    Streamlit은 allow 속성을 직접 주지 않으므로, 같은 오리진(srcdoc)인 점을 이용해
    iframe(window.frameElement)에 allow="web-share"를 직접 설정해 자기 문서에 권한을 부여한다.
    """
    b64 = base64.b64encode(data).decode("ascii")
    name = html.escape(filename, quote=True)
    return f"""
<style>
html, body {{margin:0; padding:0; background:transparent;}}
button {{width:100%; height:44px; border-radius:12px; border:1px solid #246BFD; background:#fff; color:#246BFD;
  font-size:15px; font-weight:700; cursor:pointer; display:flex; align-items:center; justify-content:center; gap:6px;
  font-family:"Pretendard Variable", Pretendard, -apple-system, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;}}
button:hover {{background:#F1F5FF;}}
button:focus-visible {{outline:2px solid #246BFD; outline-offset:2px;}}
</style>
<button id="share" type="button" aria-label="수정한 사진 공유하기">
<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4"/></svg>
공유하기</button>
<script>
(function() {{
  // 안내 문구는 버튼 자리에 표시 (iframe 높이가 고정이라 아래 줄에 쓰면 잘림)
  function say(t) {{ var b = document.getElementById("share"); b.textContent = t; b.style.fontSize = "12px"; b.style.fontWeight = "600"; }}

  // 같은 오리진이면 자기 iframe에 web-share 권한을 부여해 iframe 제약을 푼다
  try {{
    var fe = window.frameElement;
    if (fe) {{
      var allow = fe.getAttribute("allow") || "";
      if (allow.indexOf("web-share") === -1) {{
        fe.setAttribute("allow", (allow ? allow + "; " : "") + "web-share");
      }}
    }}
  }} catch (e) {{ /* 크로스오리진이면 접근 불가 - 아래 share 시도에서 처리 */ }}

  // 이미지를 File로 만들어 navigator.share({{files}})로 공유
  var bin = atob("{b64}"), bytes = new Uint8Array(bin.length);
  for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  var file = null;
  try {{ file = new File([bytes], "{name}", {{type: "image/jpeg"}}); }} catch (e) {{}}

  document.getElementById("share").addEventListener("click", function() {{
    var nav = window.navigator;
    // 파일 공유를 지원하지 않는 브라우저면 다운로드로 대신하도록 안내
    if (!file || !nav.share || !nav.canShare || !nav.canShare({{files: [file]}})) {{
      say("이 브라우저에서는 바로 공유가 안 돼요. 다운로드 후 공유해 주세요.");
      return;
    }}
    nav.share({{files: [file]}}).catch(function(e) {{
      if (e && e.name !== "AbortError") say("공유하지 못했어요. 다운로드 후 공유해 주세요.");
    }});
  }});
}})();
</script>
"""


def share_disabled_html():
    """공유를 아직 쓸 수 없을 때 보여주는 비활성 버튼 (위험 요소를 먼저 가리도록 안내)"""
    return """
<style>
html, body {margin:0; padding:0; background:transparent;}
button {width:100%; height:44px; border-radius:12px; border:1px solid #E6EBF2; background:#F2F4F8; color:#9AA4B5;
  font-size:13px; font-weight:600; cursor:not-allowed; display:flex; align-items:center; justify-content:center; gap:6px;
  font-family:"Pretendard Variable", Pretendard, -apple-system, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;}
</style>
<button type="button" disabled aria-label="공유 비활성화. 위험 요소를 먼저 가려 주세요">
위험 요소를 먼저 가려 주세요</button>
"""


def show_photo_and_overall(overall):
    style = OVERALL_STYLE[overall]
    badge = "예시 결과" if IS_DEMO else "분석 완료"
    fill = style["level"] / 3 * 100  # 3단계 위험도를 막대 길이로 표시 (정확도 수치 아님)
    mark = icon("check", 18) if overall == "낮음" else icon("warn", 18)
    render(
        f"""
        <div class="pl-shot">
        <span class="pl-shot-badge">{icon("scan", 13)}{badge}</span>
        <img src="data:image/jpeg;base64,{ss.photo["preview"]}" alt="분석한 사진">
        </div>
        <div class="pl-overall" style="background:{style['bg']}; border-color:{style['border']};">
        <div class="pl-overall-top"><div>
        <div class="pl-overall-label" style="color:{style['color']};">종합 위험도</div>
        <div class="pl-overall-value" style="color:{style['color']};">{esc(overall)}</div>
        </div>
        <span class="pl-overall-icon" style="color:{style['color']}; border-color:{style['border']}; background:#fff;">{mark}</span>
        </div>
        <div class="pl-gauge" style="background:{style['track']};" aria-hidden="true">
        <span style="width:{fill:.0f}%; background:{style['fill']};"></span></div>
        <div class="pl-overall-msg">{style['msg']}</div>
        </div>
        """
    )


def show_risk_list(risks):
    cards = ""
    for i, r in enumerate(risks):
        sev = SEVERITY_STYLE[r["severity"]]
        is_open = " open" if i == 0 else ""  # 가장 위험한 항목은 펼쳐서 표시
        cards += f"""
        <details class="pl-risk"{is_open}>
        <summary>
        <span class="pl-dot" style="background:{sev['color']};"></span>
        <span class="pl-risk-title">
        <span class="pl-risk-cat">{esc(r['category'])}</span>
        <div class="pl-risk-item">{esc(r['item'])}</div>
        </span>
        <span class="pl-badge" style="color:{sev['color']}; background:{sev['bg']}; border-color:{sev['border']};">{sev['label']}</span>
        <span class="pl-chev">{icon("chevron", 16)}</span>
        </summary>
        <div class="pl-risk-body">
        <div class="pl-reason">{esc(r['reason'])}</div>
        <div class="pl-fix"><span class="pl-fix-icon">{icon("check", 13, 3)}</span><div>
        <div class="pl-fix-title">이렇게 수정해 보세요</div>
        <div class="pl-fix-text">{esc(r['fix'])}</div>
        </div></div>
        </div>
        </details>
        """
    if not risks:
        cards = '<div class="pl-empty">눈에 띄는 위험 요소가 발견되지 않았습니다.</div>'
    render(
        f"""
        <div class="pl-list-head"><span class="pl-list-title">발견된 위험 요소</span>
        <span class="pl-count">총 {len(risks)}개</span></div>
        {cards}
        """
    )


# ----- 화면 시작 -----
st.set_page_config(page_title="Privacy Lens", page_icon="🛡️", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

show_header()
if ss.photo is not None and ss.result is not None:
    show_result_view()
else:
    show_upload_view()
show_footer()
