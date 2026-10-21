# -*- coding: utf-8 -*-
"""
어제의 박스오피스 (KOBIS 일별 박스오피스 API)
- 인증키는 Streamlit 비밀 금고(secrets)의 KOBIS_KEY에서만 읽어옵니다.
- '어제'는 서버 시계가 아니라 한국 시간(KST) 기준으로 계산합니다.
"""

from datetime import datetime, timedelta, timezone

import altair as alt          # 막대그래프(스트림릿에 기본 포함되어 있음)
import pandas as pd
import requests
import streamlit as st

# ─────────────────────────────────────────────
# 기본 설정
# ─────────────────────────────────────────────
API_URL = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
    "boxoffice/searchDailyBoxOfficeList.json"
)

# 한국 시간대(UTC+9). 한국은 서머타임이 없어서 +9시간 고정이면 충분합니다.
KST = timezone(timedelta(hours=9))

st.set_page_config(page_title="어제의 박스오피스", page_icon="🎬", layout="wide")


# ─────────────────────────────────────────────
# 함수 1: 한국 시간 기준 '어제' 날짜 구하기
# ─────────────────────────────────────────────
def get_yesterday_kst():
    """배포 서버 시계(보통 UTC)와 상관없이, 한국 시간 기준 어제 날짜를 돌려줍니다."""
    now_kst = datetime.now(KST)                 # 지금 한국 시각
    return (now_kst - timedelta(days=1)).date()  # 하루 전 날짜


# ─────────────────────────────────────────────
# 함수 2: 비밀 금고에서 인증키 꺼내기
# ─────────────────────────────────────────────
def load_api_key():
    """secrets에서 KOBIS_KEY를 읽어옵니다. 없으면 None."""
    try:
        key = str(st.secrets["KOBIS_KEY"]).strip()
    except (KeyError, FileNotFoundError):
        return None
    return key or None


# ─────────────────────────────────────────────
# 함수 3: KOBIS API 호출 (10분간 결과 저장 → 새로고침해도 API를 덜 부름)
# 실패하면 예외(오류)를 일으키는데, 실패한 결과는 저장되지 않습니다.
# ※ 오류 메시지에는 인증키가 들어 있는 주소가 섞일 수 있어서,
#   화면에는 원본 오류 문장을 그대로 보여주지 않습니다.
# ─────────────────────────────────────────────
class KobisError(Exception):
    """우리가 직접 만든 오류. kind에 오류 종류가 들어갑니다."""

    def __init__(self, kind):
        super().__init__(kind)
        self.kind = kind


@st.cache_data(ttl=600, show_spinner=False)
def fetch_box_office(_key, target_dt):
    # _key 처럼 밑줄로 시작하는 인자는 캐시 구분값에서 제외됩니다(날짜만 구분).
    try:
        resp = requests.get(
            API_URL,
            params={"key": _key, "targetDt": target_dt},
            timeout=10,
        )
    except requests.exceptions.Timeout:
        raise KobisError("timeout")
    except requests.exceptions.RequestException:
        raise KobisError("network")

    if resp.status_code != 200:
        raise KobisError("http")

    try:
        data = resp.json()
    except ValueError:
        raise KobisError("bad_json")

    # 인증키가 틀려도 상태코드는 200이고, 대신 faultInfo 상자가 옵니다.
    if "faultInfo" in data:
        raise KobisError("fault")

    result = data.get("boxOfficeResult")
    if not isinstance(result, dict):
        raise KobisError("bad_json")

    movies = result.get("dailyBoxOfficeList") or []
    if len(movies) == 0:
        raise KobisError("empty")

    return movies


# ─────────────────────────────────────────────
# 오류 종류별 한국어 안내문
# ─────────────────────────────────────────────
ERROR_GUIDE = {
    "no_key": (
        "인증키(KOBIS_KEY)를 찾을 수 없어요.",
        "Streamlit Cloud 앱 설정(Settings) → Secrets에 아래처럼 입력했는지 확인하세요.\n\n"
        "`KOBIS_KEY = \"발급받은_인증키\"`\n\n"
        "(내 컴퓨터에서 실행 중이라면 `.streamlit/secrets.toml` 파일에 넣어야 해요.)",
    ),
    "timeout": (
        "KOBIS 서버가 제때 응답하지 않았어요.",
        "잠시 후 다시 시도해 보세요. 계속 안 되면 KOBIS 사이트가 점검 중인지 확인해 보세요.",
    ),
    "network": (
        "KOBIS 서버에 연결하지 못했어요.",
        "네트워크 상태나 KOBIS 사이트 점검 여부를 확인하고, 잠시 후 다시 시도해 보세요.",
    ),
    "http": (
        "KOBIS 서버가 정상 응답을 주지 않았어요.",
        "잠시 후 다시 시도해 보세요. 계속되면 KOBIS 사이트 공지(점검 여부)를 확인해 보세요.",
    ),
    "bad_json": (
        "받은 응답을 해석할 수 없었어요.",
        "KOBIS 쪽 응답 형식이 바뀌었거나 일시적인 오류일 수 있어요. 잠시 후 다시 시도하고, "
        "계속되면 API 문서의 응답 구조를 다시 확인해 보세요.",
    ),
    "fault": (
        "KOBIS가 요청을 거절했어요. (오류 안내 상자가 도착했습니다)",
        "① Secrets의 KOBIS_KEY 값이 정확한지(앞뒤 공백, 따옴표, 복사 누락)\n\n"
        "② 인증키가 정상 발급·승인된 상태인지\n\n"
        "③ 하루 호출 가능 횟수를 넘기지 않았는지\n\n"
        "를 KOBIS 오픈API 사이트에서 확인해 보세요.",
    ),
    "empty": (
        "해당 날짜의 영화 목록이 비어 있어요.",
        "아직 어제 집계가 끝나지 않았을 수 있어요. 잠시 후 다시 시도해 보세요. "
        "그래도 비어 있으면 KOBIS 사이트에서 같은 날짜 데이터가 있는지 확인해 보세요.",
    ),
}


def show_error(kind):
    """오류 종류에 맞는 안내문을 화면에 보여주고, 그 아래 코드는 실행하지 않습니다."""
    title, tip = ERROR_GUIDE.get(kind, ERROR_GUIDE["bad_json"])
    st.error(title)
    st.info(tip)
    st.stop()  # 여기서 화면 그리기를 멈춥니다(빈 화면 대신 안내문만 남음)


# ─────────────────────────────────────────────
# 화면 시작
# ─────────────────────────────────────────────
st.title("🎬 어제의 박스오피스")

yesterday = get_yesterday_kst()
target_dt = yesterday.strftime("%Y%m%d")  # 예: 20261020 (yyyymmdd 여덟 자리)
st.caption(f"조회 날짜: {yesterday.strftime('%Y년 %m월 %d일')} (한국 시간 기준) · 출처: 영화진흥위원회 KOBIS")

# 1) 인증키 확인
api_key = load_api_key()
if api_key is None:
    show_error("no_key")

# 2) 데이터 가져오기
try:
    with st.spinner("박스오피스를 불러오는 중..."):
        movies = fetch_box_office(api_key, target_dt)
except KobisError as e:
    show_error(e.kind)
except Exception:
    # 예상하지 못한 오류도 빈 화면 대신 안내합니다.
    show_error("bad_json")

# 3) 표 만들기 (숫자 값이 전부 문자열로 오므로 숫자로 바꿔 줍니다)
df = pd.DataFrame(movies)

# 혹시 빠진 칸이 있어도 앱이 죽지 않도록 없는 열은 빈 값으로 채웁니다.
needed = ["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]
for col in needed:
    if col not in df.columns:
        df[col] = None

for col in ["rank", "audiCnt", "audiAcc", "scrnCnt"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")  # 숫자로 못 바꾸면 빈 값(NaN)

df = df.sort_values("rank").reset_index(drop=True)

# 4) 1위 영화: 지표 카드 세 장
st.subheader("🥇 어제의 1위")
top = df.iloc[0]


def fmt(num, unit=""):
    """숫자를 1,234 형태로. 값이 없으면 '-'."""
    return "-" if pd.isna(num) else f"{int(num):,}{unit}"


c1, c2, c3 = st.columns(3)
c1.metric("영화명", str(top["movieNm"]))
c2.metric("어제 관객수", fmt(top["audiCnt"], "명"))
c3.metric("누적 관객수", fmt(top["audiAcc"], "명"))

# 5) 관객수 상위 5편 막대그래프
st.subheader("📊 관객수 상위 5편")
top5 = df.dropna(subset=["audiCnt"]).nlargest(5, "audiCnt")
if top5.empty:
    st.info("관객수 정보가 없어 그래프를 그릴 수 없어요.")
else:
    chart = (
        alt.Chart(top5)
        .mark_bar()
        .encode(
            x=alt.X("movieNm:N", sort="-y", title="영화명", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("audiCnt:Q", title="어제 관객수(명)"),
            tooltip=[
                alt.Tooltip("movieNm:N", title="영화명"),
                alt.Tooltip("audiCnt:Q", title="관객수", format=","),
            ],
        )
    )
    st.altair_chart(chart, use_container_width=True)

# 6) 전체 순위 표
st.subheader("📋 전체 순위")
table = pd.DataFrame(
    {
        "순위": df["rank"].apply(fmt),
        "영화명": df["movieNm"],
        "개봉일": df["openDt"].fillna("-").replace("", "-"),
        "관객수": df["audiCnt"].apply(fmt),
        "누적관객": df["audiAcc"].apply(fmt),
        "스크린수": df["scrnCnt"].apply(fmt),
    }
)
st.dataframe(table, hide_index=True, use_container_width=True)
