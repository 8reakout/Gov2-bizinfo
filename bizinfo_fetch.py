from __future__ import annotations

import json
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import date, datetime
from html import unescape
from typing import Any

import requests


@dataclass
class Notice:
    notice_id: str
    title: str
    category: str = ""
    organization: str = ""
    execution_org: str = ""
    start_date: str = ""
    end_date: str = ""
    period: str = ""
    status: str = ""
    target: str = ""
    url: str = ""
    source_category_code: str = ""
    raw: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


EXCLUDED_ORGANIZATIONS = {
    "대구광역시",
    "경기도",
    "충청남도",
    "전남광주통합특별시",
    "강원특별자치도",
    "경상북도",
    "부산광역시",
    "인천광역시",
    "전북특별자치도",
    "충청북도",
    "울산광역시",
    "대전광역시",
    "경상남도",
    "제주특별자치도"
}


def _normalize_org_name(value: str) -> str:
    """기관명 비교를 위해 공백을 제거합니다."""
    return re.sub(r"\s+", "", value or "")


def _is_excluded_organization(organization: str) -> bool:
    """제외 대상 소관기관이면 True를 반환합니다.

    소관기관 값이 '경기도'처럼 정확히 들어오는 경우뿐 아니라
    '경기도청', '경기도경제과학진흥원'처럼 앞뒤 문구가 붙는 경우도 제외합니다.
    """
    normalized = _normalize_org_name(organization)

    if not normalized:
        return False

    for excluded in EXCLUDED_ORGANIZATIONS:
        excluded_normalized = _normalize_org_name(excluded)

        if normalized == excluded_normalized:
            return True

        if excluded_normalized in normalized:
            return True

    return False


def _first_value(item: dict[str, Any], candidates: list[str]) -> str:
    for key in candidates:
        if key in item and item[key] not in (None, ""):
            return str(item[key]).strip()
    return ""


def _dig_items(data: Any) -> list[dict[str, Any]]:
    """기업마당 JSON 응답에서 item 리스트를 유연하게 찾아냅니다."""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]

    if not isinstance(data, dict):
        return []

    paths = [
        ["jsonArray", "item"],
        ["channel", "item"],
        ["rss", "channel", "item"],
        ["response", "body", "items", "item"],
        ["items", "item"],
        ["items"],
        ["data"],
        ["result"],
        ["list"],
    ]

    for path in paths:
        cur: Any = data
        for key in path:
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                cur = None
                break

        if cur is None:
            continue

        if isinstance(cur, dict):
            return [cur]

        if isinstance(cur, list):
            return [x for x in cur if isinstance(x, dict)]

    for value in data.values():
        found = _dig_items(value)
        if found:
            return found

    return []


def _parse_xml_items(xml_text: str) -> list[dict[str, Any]]:
    """기업마당 RSS/XML 응답을 list[dict] 형태로 변환합니다."""
    root = ET.fromstring(xml_text)
    items: list[dict[str, Any]] = []

    for item_el in root.findall(".//item"):
        item: dict[str, Any] = {}

        for child in list(item_el):
            tag = child.tag.split("}")[-1]
            value = "".join(child.itertext()).strip()
            item[tag] = unescape(value)

        if item:
            items.append(item)

    return items


def _normalize_url(value: str) -> str:
    value = (value or "").strip()

    if not value:
        return ""

    value = unescape(value)

    if value.startswith("//"):
        return "https:" + value

    if value.startswith("/"):
        return "https://www.bizinfo.go.kr" + value

    if value.startswith("www."):
        return "https://" + value

    return value


def _normalize_date(value: str) -> str:
    value = (value or "").strip()

    if not value:
        return ""

    value = value.replace(".", "-").replace("/", "-")

    if re.fullmatch(r"\d{8}", value):
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value

    return value


def _split_period(value: str) -> tuple[str, str, str]:
    """신청기간 문자열에서 시작일/종료일/원문기간을 분리합니다."""
    value = (value or "").strip()

    if not value:
        return "", "", ""

    value = unescape(value)
    value = value.replace("&nbsp;", " ")
    value = value.replace("~", " ~ ")
    value = re.sub(r"\s+", " ", value).strip()

    if "상시" in value:
        return "", "", "상시 접수"

    dates = re.findall(r"\d{4}[.\-/]?\d{2}[.\-/]?\d{2}", value)

    if len(dates) >= 2:
        start = _normalize_date(dates[0])
        end = _normalize_date(dates[1])
        return start, end, f"{start} ~ {end}"

    if len(dates) == 1:
        one = _normalize_date(dates[0])
        return "", one, one

    return "", "", value


def _parse_date(value: str) -> date | None:
    value = _normalize_date(value)

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _infer_status(period: str, end_date: str) -> str:
    if "상시" in (period or ""):
        return "상시접수"

    end = _parse_date(end_date)

    if end is None:
        return "확인 필요"

    return "모집중" if end >= date.today() else "마감"


def _is_active_notice(period: str, end_date: str) -> bool:
    if "상시" in (period or ""):
        return True

    end = _parse_date(end_date)

    if end is None:
        return True

    return end >= date.today()


def _build_params(config: dict[str, Any], category_code: str, page_index: int) -> dict[str, Any]:
    bcfg = config["bizinfo"]
    params = dict(bcfg.get("params", {}))

    crtfc_key = os.getenv("BIZINFO_CRTFC_KEY") or bcfg.get("crtfc_key", "")

    if not crtfc_key:
        raise ValueError("BIZINFO_CRTFC_KEY가 비어 있습니다. .env 또는 GitHub Secrets를 확인하세요.")

    # 요청 조건 고정 반영: 분야별 최대 10페이지, 1페이지당 20건
    params["searchCnt"] = 20
    params["pageUnit"] = 20
    params["pageIndex"] = page_index

    params["crtfcKey"] = crtfc_key
    params["dataType"] = bcfg.get("data_type", "json")
    params["searchLclasId"] = category_code

    return params

def request_with_retry(api_url: str, params: dict, max_retries: int = 3) -> requests.Response:
    """기업마당 API 요청 실패 시 재시도합니다."""
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(
                api_url,
                params=params,
                timeout=30,
                headers={
                    "User-Agent": "Mozilla/5.0 GovMonitoringBot/1.0",
                    "Accept": "application/json, text/plain, */*",
                },
            )
            response.raise_for_status()
            return response

        except requests.exceptions.ConnectTimeout as exc:
            last_error = exc
            print(f"[경고] 기업마당 API 연결 시간 초과: {attempt}/{max_retries}회 재시도")

        except requests.exceptions.ReadTimeout as exc:
            last_error = exc
            print(f"[경고] 기업마당 API 응답 시간 초과: {attempt}/{max_retries}회 재시도")

        except requests.exceptions.RequestException as exc:
            last_error = exc
            print(f"[경고] 기업마당 API 요청 실패: {attempt}/{max_retries}회 재시도 - {exc}")

        time.sleep(5 * attempt)

    raise RuntimeError(f"기업마당 API 요청이 {max_retries}회 모두 실패했습니다: {last_error}")


def _fetch_category(config: dict[str, Any], category_name: str, category_code: str) -> list[Notice]:
    bcfg = config["bizinfo"]
    api_url = bcfg.get("api_url", "").strip()

    if not api_url:
        raise ValueError("config.yaml의 bizinfo.api_url 값이 비어 있습니다.")

    max_pages = 10
    notices: list[Notice] = []
    active_only = bool(bcfg.get("active_only", True))

    for page_index in range(1, max_pages + 1):
        params = _build_params(config, category_code, page_index)

        print(
            f"[정보] 기업마당 {category_name} 분야 API 호출 시작: "
            f"pageIndex={params['pageIndex']}, pageUnit={params['pageUnit']}, searchCnt={params['searchCnt']}"
        )

        response = request_with_retry(api_url, params)

        text = response.text.strip()

        try:
            data = response.json()
            items = _dig_items(data)
        except Exception:
            if text.startswith("<"):
                items = _parse_xml_items(text)
            else:
                raise RuntimeError(
                    "기업마당 API 응답이 JSON/XML 형식이 아닙니다. "
                    "API 인증키/파라미터를 확인하세요. 응답 앞부분: " + text[:300]
                )

        print(f"[정보] 기업마당 {category_name} 분야 pageIndex={page_index} 응답 item 수: {len(items)}")

        if not items:
            print(f"[정보] 기업마당 {category_name} 분야 pageIndex={page_index}에 공고가 없어 조회를 중단합니다.")
            break

        page_notice_count = 0

        for item in items:
            notice_id = _first_value(
                item,
                [
                    "pblancId",
                    "pblanc_id",
                    "seq",
                    "id",
                ],
            )

            title = _first_value(
                item,
                [
                    "pblancNm",
                    "pblanc_nm",
                    "title",
                    "name",
                    "지원사업명",
                ],
            )

            category = (
                _first_value(
                    item,
                    [
                        "pldirSportRealmLclasCodeNm",
                        "pldir_sport_realm_lclas_code_nm",
                        "lcategory",
                        "category",
                        "지원분야",
                    ],
                )
                or category_name
            )

            organization = _first_value(
                item,
                [
                    "jrsdInsttNm",
                    "jrsd_instt_nm",
                    "author",
                    "소관기관",
                    "소관부처",
                    "소관부처·지자체",
                    "organization",
                ],
            )

            if _is_excluded_organization(organization):
                continue

            execution_org = _first_value(
                item,
                [
                    "excInsttNm",
                    "exc_instt_nm",
                    "excInsttName",
                    "excInstt",
                    "사업수행기관",
                    "수행기관",
                    "execution_org",
                    "agency",
                ],
            )

            target = _first_value(
                item,
                [
                    "trgetNm",
                    "trget_nm",
                    "지원대상",
                    "target",
                ],
            )

            url = _normalize_url(
                _first_value(
                    item,
                    [
                        "pblancUrl",
                        "pblanc_url",
                        "link",
                        "url",
                    ],
                )
            )

            period_raw = _first_value(
                item,
                [
                    "reqstDt",
                    "reqstBeginEndDe",
                    "reqstPd",
                    "reqstBeginEndDt",
                    "신청기간",
                    "period",
                ],
            )

            start_date, end_date, period = _split_period(period_raw)
            status = _infer_status(period, end_date)

            if category not in {"기술", "창업", "기타"}:
                continue

            if active_only and not _is_active_notice(period, end_date):
                continue

            if not title:
                continue

            if not notice_id:
                notice_id = f"{title}|{end_date}|{url}"

            notices.append(
                Notice(
                    notice_id=notice_id,
                    title=title,
                    category=category,
                    organization=organization,
                    execution_org=execution_org,
                    start_date=start_date,
                    end_date=end_date,
                    period=period,
                    status=status,
                    target=target,
                    url=url,
                    source_category_code=category_code,
                    raw=item,
                )
            )
            page_notice_count += 1

        print(f"[정보] 기업마당 {category_name} 분야 pageIndex={page_index} 변환 후 공고 수: {page_notice_count}")

    deduped: dict[str, Notice] = {}
    for notice in notices:
        deduped[notice.notice_id] = notice

    return list(deduped.values())

def fetch_bizinfo_notices(config: dict[str, Any]) -> list[Notice]:
    """기술/창업/기타 분야의 기업마당 지원사업 공고를 조회합니다.

    특정 분야 API 호출이 실패해도 전체 프로그램이 종료되지 않도록 처리합니다.
    """
    categories = config["bizinfo"].get("categories", [])

    if not categories:
        raise ValueError("config.yaml의 bizinfo.categories 값이 비어 있습니다.")

    deduped: dict[str, Notice] = {}
    failed_categories: list[str] = []

    for category in categories:
        name = str(category.get("name", "")).strip()
        code = str(category.get("code", "")).strip()

        if not name or not code:
            continue

        try:
            print(f"[정보] 기업마당 {name} 분야 조회 시작")
            category_notices = _fetch_category(config, name, code)

            for notice in category_notices:
                deduped[notice.notice_id] = notice

            print(f"[정보] 기업마당 {name} 분야 조회 성공: {len(category_notices)}건")

        except Exception as exc:
            failed_categories.append(name)
            print(f"[경고] 기업마당 {name} 분야 조회 실패: {exc}")
            continue

    if failed_categories:
        print(f"[경고] 조회 실패 분야: {', '.join(failed_categories)}")

    return sorted(
        deduped.values(),
        key=lambda n: (n.end_date or "9999-12-31", n.title),
    )