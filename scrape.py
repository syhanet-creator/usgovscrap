#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
미합중국 중앙부처(연방정부 기관) 보도자료 스크랩 + 한글 자동번역 스크립트
====================================================================
각 기관 공식 사이트에서 최근 7일 보도자료를 수집한 뒤, 제목을 한글로
자동 번역하여 data.json 으로 저장합니다.

주의: 이 스크립트는 사용자 컴퓨터(로컬)에서 실행해야 합니다.
      (미국 정부 웹사이트 접속 및 번역 서비스 접속이 필요합니다.)

사용법:
    pip install requests beautifulsoup4 lxml deep-translator --break-system-packages
    python scrape.py

결과: data.json 파일이 생성되며, index.html 로 결과를 볼 수 있습니다.
"""

import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

try:
    import requests
    from bs4 import BeautifulSoup, NavigableString
except ImportError:
    print("필요한 패키지가 없습니다. 다음 명령으로 설치하세요:")
    print("  pip install requests beautifulsoup4 lxml deep-translator --break-system-packages")
    sys.exit(1)

try:
    from deep_translator import GoogleTranslator, MyMemoryTranslator
    TRANSLATOR_AVAILABLE = True
except ImportError:
    TRANSLATOR_AVAILABLE = False

# 세션 중 구글 번역이 한 번이라도 막히면(요청 과다 등) 이후로는 바로
# MyMemory로 전환해 매 기관마다 실패-재시도로 시간을 낭비하지 않는다.
GOOGLE_TRANSLATE_BROKEN = False

# Gemini API 키는 코드에 적지 말고 환경변수로만 전달한다 (저장소에 올라가면 안 됨).
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_ITEMS_PER_AGENCY = 12
PERIOD_DAYS = 7

# 기관별 설정: key, 한글명, 영문명, 대표색, 목록 페이지, 수집 전략, (선택) RSS 주소
AGENCIES = [
    dict(key="white_house", name_ko="백악관", name_en="The White House",
         color="#1f3a5f",
         list_url="https://www.whitehouse.gov/briefing-room/statements-releases/",
         strategy="time_tag"),
    dict(key="state", name_ko="국무부", name_en="Department of State",
         color="#0b3d91",
         list_url="https://www.state.gov/press-releases/",
         strategy="state"),
    dict(key="treasury", name_ko="재무부", name_en="Department of the Treasury",
         color="#0a6847",
         list_url="https://home.treasury.gov/news/press-releases",
         strategy="treasury"),
    dict(key="war", name_ko="국방부(전쟁부)", name_en="Department of War",
         color="#3c4a3e",
         list_url="https://www.war.gov/News/Releases/",
         rss_url="https://www.war.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=800&Site=945&max=30",
         strategy="rss"),
    dict(key="justice", name_ko="법무부", name_en="Department of Justice",
         color="#4b2e83",
         list_url="https://www.justice.gov/news",
         rss_url="https://www.justice.gov/news/rss?m=1",
         strategy="rss"),
    dict(key="interior", name_ko="내무부", name_en="Department of the Interior",
         color="#6b4423",
         list_url="https://www.doi.gov/news",
         strategy="time_tag"),
    dict(key="agriculture", name_ko="농무부", name_en="Department of Agriculture",
         color="#2e7d32",
         list_url="https://www.usda.gov/about-usda/news/press-releases",
         strategy="time_tag"),
    dict(key="commerce", name_ko="상무부", name_en="Department of Commerce",
         color="#00537a",
         list_url="https://www.commerce.gov/news",
         strategy="time_tag"),
    dict(key="labor", name_ko="노동부", name_en="Department of Labor",
         color="#8a5a00",
         list_url="https://www.dol.gov/newsroom/releases",
         strategy="time_tag"),
    dict(key="hhs", name_ko="보건복지부", name_en="Dept. of Health and Human Services",
         color="#0f6e84",
         list_url="https://www.hhs.gov/press-room/index.html",
         rss_url="https://www.hhs.gov/rss/news.xml",
         strategy="rss"),
    dict(key="hud", name_ko="주택도시개발부", name_en="Dept. of Housing and Urban Development",
         color="#7a1f3d",
         list_url="https://www.hud.gov/press",
         strategy="time_tag"),
    dict(key="transportation", name_ko="교통부", name_en="Department of Transportation",
         color="#154360",
         list_url="https://www.transportation.gov/briefing-room",
         strategy="time_tag"),
    dict(key="energy", name_ko="에너지부", name_en="Department of Energy",
         color="#b8860b",
         list_url="https://www.energy.gov/news",
         strategy="time_tag"),
    dict(key="education", name_ko="교육부", name_en="Department of Education",
         color="#5a2d82",
         list_url="https://www.ed.gov/about/news",
         strategy="time_tag"),
    dict(key="dhs", name_ko="국토안보부", name_en="Dept. of Homeland Security",
         color="#00274d",
         list_url="https://www.dhs.gov/news-releases",
         strategy="dhs"),
    dict(key="va", name_ko="보훈부", name_en="Dept. of Veterans Affairs",
         color="#003462",
         list_url="https://news.va.gov/",
         strategy="time_tag"),
    dict(key="epa", name_ko="환경보호청", name_en="Environmental Protection Agency",
         color="#00693e",
         list_url="https://www.epa.gov/newsreleases",
         strategy="link_only"),
]


def parse_date(raw):
    """다양한 형식의 날짜 문자열/ISO datetime을 date 객체로 변환. 실패 시 None."""
    if not raw:
        return None
    raw = raw.strip()
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except Exception:
        pass
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except Exception:
            pass
    try:
        return parsedate_to_datetime(raw).date()
    except Exception:
        pass
    m = re.search(r"([A-Z][a-z]+ \d{1,2}, \d{4})", raw)
    if m:
        try:
            return datetime.strptime(m.group(1), "%B %d, %Y").date()
        except Exception:
            pass
    return None


def to_abs_url(base_url, href):
    if not href:
        return href
    if href.startswith("http"):
        return href
    m = re.match(r"(https?://[^/]+)", base_url)
    origin = m.group(1) if m else base_url
    return origin + href if href.startswith("/") else origin + "/" + href


def fetch_html(session, url):
    resp = session.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def extract_rss(session, agency):
    resp = session.get(agency["rss_url"], headers=HEADERS, timeout=20)
    resp.raise_for_status()
    # 반드시 XML 파서를 써야 한다: html.parser는 RSS의 <link>텍스트</link>를
    # HTML의 자기닫힘 <link> 태그로 오인해 내용(URL)을 통째로 잃어버린다.
    soup = BeautifulSoup(resp.content, "xml")
    items = []
    for it in soup.find_all("item"):
        title_tag = it.find("title")
        link_tag = it.find("link")
        date_tag = it.find("pubDate")
        title = title_tag.get_text(strip=True) if title_tag else ""
        link = link_tag.get_text(strip=True) if link_tag else ""
        if not title or not link:
            continue
        items.append({
            "title": title,
            "url": link,
            "date": parse_date(date_tag.get_text(strip=True) if date_tag else ""),
        })
    return items


_DATE_REGEXES = [
    re.compile(r"\d{1,2}/\d{1,2}/\d{4}"),
    re.compile(r"[A-Z][a-z]+ \d{1,2},\s*\d{4}"),
    re.compile(r"\d{4}-\d{2}-\d{2}"),
]


def _count_date_like(text):
    return sum(len(p.findall(text)) for p in _DATE_REGEXES)


def _climb_for_link(seed):
    """날짜 노드(<time> 태그 또는 날짜 형식의 텍스트)에서 부모로 한 단계씩
    올라가며 그 컨테이너 안의 제목 링크를 찾는다. <h1~h4> 안의 링크를
    우선하고(카테고리/태그 배지 링크 오탐 방지), 컨테이너 안에 날짜가
    2개 이상 섞이면(=다른 항목과 섞임) 더 올라가지 않는다."""
    container = seed.parent if isinstance(seed, NavigableString) else seed
    heading_link = None
    fallback_link = None
    for _ in range(10):
        if container.parent is None:
            break
        container = container.parent
        if _count_date_like(container.get_text(" ", strip=True)) > 1:
            break
        heading = container.find(["h1", "h2", "h3", "h4"])
        if heading:
            a = heading.find("a", href=True)
            if a and len(a.get_text(strip=True)) > 10:
                heading_link = a
                break
        for cand in container.find_all("a", href=True):
            text = cand.get_text(strip=True)
            if len(text) > 15 and (
                fallback_link is None
                or len(text) > len(fallback_link.get_text(strip=True))
            ):
                fallback_link = cand
    return heading_link or fallback_link


def extract_time_tag(soup, base_url, max_items=25):
    """제목 근처의 날짜를 실마리로 삼는 범용 전략.
    최신 정부 사이트(WordPress/Drupal 등)의 공통 마크업 패턴을 활용한다.
    1) 먼저 <time datetime=...> 태그를 찾는다 (WordPress에서 흔함).
    2) 없으면 "08/30/2026"·"September 18, 2026" 같은 날짜 형식의
       텍스트 노드를 직접 찾는다 (Drupal 등에서 흔함).
    """
    results = []
    seen = set()
    seeds = []  # (seed_node, date_raw_text)

    for t in soup.find_all("time"):
        seeds.append((t, t.get("datetime") or t.get_text(strip=True)))

    if not seeds:
        for s in soup.find_all(string=True):
            text = s.strip()
            if not text or len(text) > 30:
                continue
            for pat in _DATE_REGEXES:
                m = pat.search(text)
                if m:
                    seeds.append((s, m.group(0)))
                    break

    for seed, date_raw in seeds:
        link = _climb_for_link(seed)
        if not link:
            continue
        href = to_abs_url(base_url, link["href"])
        if href in seen:
            continue
        seen.add(href)
        results.append({
            "title": link.get_text(strip=True),
            "url": href,
            "date": parse_date(date_raw),
        })
        if len(results) >= max_items:
            break
    return results


def extract_state(soup, base_url, max_items=25):
    results = []
    seen = set()
    for li in soup.select("li.collection-result"):
        a = li.select_one("a.collection-result__link")
        if not a:
            continue
        href = to_abs_url(base_url, a.get("href", ""))
        if not href or href in seen:
            continue
        seen.add(href)
        full_text = li.get_text(" ", strip=True)
        results.append({
            "title": a.get_text(strip=True),
            "url": href,
            "date": parse_date(full_text),
        })
        if len(results) >= max_items:
            break
    return results


def extract_treasury(soup, base_url, max_items=25):
    results = []
    seen = set()
    for a in soup.find_all("a", href=re.compile(r"/news/press-releases/[a-z0-9]+/?$", re.I)):
        text = a.get_text(strip=True)
        if len(text) < 15:
            continue
        href = to_abs_url(base_url, a["href"])
        if href in seen:
            continue
        seen.add(href)
        container = a.find_parent(["li", "div", "article"]) or a
        results.append({
            "title": text,
            "url": href,
            "date": parse_date(container.get_text(" ", strip=True)),
        })
        if len(results) >= max_items:
            break
    return results


def extract_dhs(soup, base_url, max_items=25):
    results = []
    seen = set()
    for a in soup.find_all("a", href=re.compile(r"/news/\d{4}/\d{2}/\d{2}/")):
        text = a.get_text(strip=True)
        if len(text) < 15:
            continue
        href = to_abs_url(base_url, a["href"])
        if href in seen:
            continue
        seen.add(href)
        m = re.search(r"/news/(\d{4})/(\d{2})/(\d{2})/", href)
        date = None
        if m:
            try:
                date = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
            except Exception:
                date = None
        results.append({"title": text, "url": href, "date": date})
        if len(results) >= max_items:
            break
    return results


def extract_generic_link(soup, base_url, max_items=25):
    """모든 전용 전략이 실패했을 때 쓰는 최후 수단.
    <main> 영역으로 범위를 좁히고, 기사 상세 페이지처럼 보이는(경로에
    연도 또는 긴 slug가 포함된) 링크만 수집해 메뉴/사이드바 오탐을 줄인다."""
    results = []
    seen = set()
    scope = soup.find("main") or soup
    article_like = re.compile(r"/(19|20)\d{2}/|/[a-z0-9-]{25,}(/|$)", re.I)
    for a in scope.find_all("a", href=True):
        text = a.get_text(strip=True)
        href = a["href"]
        if len(text) < 25 or not article_like.search(href):
            continue
        abs_href = to_abs_url(base_url, href)
        if abs_href in seen:
            continue
        seen.add(abs_href)
        results.append({"title": text, "url": abs_href, "date": None})
        if len(results) >= max_items:
            break
    return results


def fetch_agency_items(session, agency):
    strategy = agency["strategy"]
    items = []

    if strategy == "link_only":
        return items

    try:
        if strategy == "rss":
            items = extract_rss(session, agency)
        else:
            soup = fetch_html(session, agency["list_url"])
            if strategy == "state":
                items = extract_state(soup, agency["list_url"])
            elif strategy == "treasury":
                items = extract_treasury(soup, agency["list_url"])
            elif strategy == "dhs":
                items = extract_dhs(soup, agency["list_url"])
            else:  # time_tag (기본/범용)
                items = extract_time_tag(soup, agency["list_url"])

            if not items:
                # 범용 전략으로 재시도
                items = extract_time_tag(soup, agency["list_url"])
            if not items:
                items = extract_generic_link(soup, agency["list_url"])
    except Exception as e:
        print(f"  [경고] {agency['name_ko']} 수집 실패: {e}")
        return []

    return items


def filter_recent(items, days=PERIOD_DAYS, max_items=MAX_ITEMS_PER_AGENCY):
    cutoff = datetime.now().date() - timedelta(days=days)
    # 날짜를 전혀 못 읽어온 경우에만 "목록 순서=최신순"으로 가정해 상위 항목을
    # 보여준다. 날짜를 알아냈는데 전부 7일보다 오래됐다면, 그건 최근
    # 보도자료가 없다는 뜻이므로 억지로 오래된 항목을 채우지 않는다.
    if not any(it["date"] for it in items):
        return items[:max_items]
    recent = [it for it in items if it["date"] and it["date"] >= cutoff]
    recent.sort(key=lambda it: it["date"], reverse=True)
    return recent[:max_items]


def gemini_translate(titles):
    """Gemini API로 제목 목록을 한 번에 한글 번역. 실패하면 None."""
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent")
    prompt = (
        "다음은 미국 연방정부 기관 보도자료의 영어 제목 목록(JSON 배열)이다. "
        "각 제목을 자연스러운 한국어 보도자료 제목으로 번역하라. "
        "기관·인명·법안 번호 등 고유명사는 널리 쓰이는 한국어 표기가 있으면 그것을, "
        "없으면 원문을 병기하지 말고 음역하라. "
        "입력과 같은 길이·같은 순서의 JSON 문자열 배열만 출력하라.\n\n"
        + json.dumps(titles, ensure_ascii=False)
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {"type": "ARRAY", "items": {"type": "STRING"}},
            "temperature": 0.2,
        },
    }
    try:
        resp = requests.post(url, json=body, timeout=60,
                             headers={"x-goog-api-key": GEMINI_API_KEY})
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        out = json.loads(text)
        if isinstance(out, list) and len(out) == len(titles):
            return [str(x) for x in out]
        print("  [경고] Gemini 응답 개수가 입력과 달라 다른 번역기로 전환합니다.")
    except Exception as e:
        print(f"  [경고] Gemini 번역 실패, 다른 번역기로 전환합니다: {e}")
    return None


def gemini_summary(agencies):
    """수집한 보도자료 제목 전체로 '오늘의 주요 뉴스 요약 + 부처별 움직임 전망'을 생성."""
    lines = []
    for a in agencies:
        for it in a["items"]:
            lines.append(f"[{a['name_ko']}] {it['date']} {it['title_en']} / {it['title_ko']}")
    if len(lines) < 5:
        return None

    prompt = (
        "너는 미국 정치·행정을 다루는 한국어 뉴스 에디터다. 아래는 미국 연방정부 부처가 "
        "최근 7일간 낸 보도자료 제목 목록이다(제목만 있고 본문은 없다).\n"
        "1) headline: 이번 주 전체 흐름을 한 문장으로.\n"
        "2) top_news: 가장 중요한 뉴스 3~5개. 각 항목에 title(짧은 제목), detail(1~2문장 요약), "
        "agencies(관련 부처 한글명 배열).\n"
        "3) outlook: 부처별 향후 움직임 전망 3~5개. 각 항목에 agency, forecast(1~2문장), "
        "basis(근거가 된 제목의 한글 표현).\n"
        "규칙: 목록에 없는 사실을 지어내지 말고, 전망은 제목에서 읽히는 추세에 근거해 "
        "'~할 가능성이 있다'처럼 단정하지 않는 어투로 쓴다. 모두 자연스러운 한국어로.\n\n"
        + "\n".join(lines)
    )
    string = {"type": "STRING"}
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "headline": string,
                    "top_news": {"type": "ARRAY", "items": {
                        "type": "OBJECT",
                        "properties": {
                            "title": string, "detail": string,
                            "agencies": {"type": "ARRAY", "items": string},
                        },
                        "required": ["title", "detail", "agencies"],
                    }},
                    "outlook": {"type": "ARRAY", "items": {
                        "type": "OBJECT",
                        "properties": {
                            "agency": string, "forecast": string, "basis": string,
                        },
                        "required": ["agency", "forecast", "basis"],
                    }},
                },
                "required": ["headline", "top_news", "outlook"],
            },
            "temperature": 0.4,
        },
    }
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent")
    try:
        resp = requests.post(url, json=body, timeout=120,
                             headers={"x-goog-api-key": GEMINI_API_KEY})
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        summary = json.loads(text)
        summary["model"] = GEMINI_MODEL
        return summary
    except Exception as e:
        print(f"  [경고] AI 요약 생성 실패: {e}")
        return None


def translate_titles(titles):
    """제목 목록을 한글로 번역. GEMINI_API_KEY가 있으면 Gemini를 우선 사용하고,
    실패하면 구글 번역 → MyMemory 순으로 전환한다. 모두 실패하면 원문을 그대로 둔다."""
    global GOOGLE_TRANSLATE_BROKEN
    if not titles:
        return []
    if GEMINI_API_KEY:
        translated = gemini_translate(titles)
        if translated:
            return translated
    if not TRANSLATOR_AVAILABLE:
        return list(titles)

    if not GOOGLE_TRANSLATE_BROKEN:
        try:
            return GoogleTranslator(source="en", target="ko").translate_batch(titles)
        except Exception as e:
            print(f"  [안내] 구글 번역 불가(요청 과다 등), MyMemory 번역으로 전환합니다: {e}")
            GOOGLE_TRANSLATE_BROKEN = True

    out = []
    for t in titles:
        translated = t
        try:
            translated = MyMemoryTranslator(source="en-US", target="ko-KR").translate(t)
        except Exception:
            pass
        out.append(translated or t)
        time.sleep(0.3)
    return out


def main():
    print("=" * 60)
    print("미합중국 중앙부처 보도자료 스크랩 + 한글 번역 시작")
    print("=" * 60)

    if not TRANSLATOR_AVAILABLE:
        print("\n[안내] deep-translator 패키지가 없어 번역 없이 원문으로 저장합니다.")
        print("       pip install deep-translator 로 설치 후 다시 실행하면 번역됩니다.\n")

    session = requests.Session()
    result = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "period_days": PERIOD_DAYS,
        "translation_available": TRANSLATOR_AVAILABLE or bool(GEMINI_API_KEY),
        "agencies": [],
    }

    for agency in AGENCIES:
        print(f"[수집] {agency['name_ko']} ({agency['name_en']}) ...")
        entry = {
            "key": agency["key"],
            "name_ko": agency["name_ko"],
            "name_en": agency["name_en"],
            "color": agency["color"],
            "list_url": agency["list_url"],
            "items": [],
            "note": "",
        }

        if agency["strategy"] == "link_only":
            entry["note"] = "자동 접속 차단(봇 감지)으로 목록 페이지 링크만 제공합니다."
            result["agencies"].append(entry)
            continue

        try:
            raw_items = fetch_agency_items(session, agency)
            recent = filter_recent(raw_items)

            if not recent:
                entry["note"] = "최근 7일간 새 보도자료를 찾지 못했거나 사이트 구조 변경으로 수집에 실패했습니다."
            else:
                titles_en = [it["title"] for it in recent]
                titles_ko = translate_titles(titles_en)
                for it, ko in zip(recent, titles_ko):
                    entry["items"].append({
                        "title_en": it["title"],
                        "title_ko": ko,
                        "url": it["url"],
                        "date": it["date"].strftime("%Y-%m-%d") if it["date"] else "",
                    })
                print(f"  -> {len(entry['items'])}건 수집/번역 완료")
        except Exception as e:
            entry["note"] = f"수집 오류: {e}"
            print(f"  -> 오류: {e}")
            traceback.print_exc()

        result["agencies"].append(entry)
        time.sleep(0.3)

    if GEMINI_API_KEY:
        print("[AI 요약] Gemini로 오늘의 주요 뉴스/전망 생성 중...")
        summary = gemini_summary(result["agencies"])
        if summary:
            result["ai_summary"] = summary

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("완료! data.json 파일이 생성되었습니다.")
    print("index.html 을 브라우저로 열어 결과를 확인하세요.")
    print("=" * 60)


if __name__ == "__main__":
    main()
