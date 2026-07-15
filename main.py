from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from bizinfo_fetch import Notice, fetch_bizinfo_notices
from email_notifier import send_html_email

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

CONFIG_PATH = BASE_DIR / "config.yaml"
EXAMPLE_CONFIG_PATH = BASE_DIR / "config.example.yaml"
HTML_OUTPUT_PATH = BASE_DIR / "bizinfo_notice_latest.html"


def load_config() -> dict[str, Any]:
    """config.yaml이 있으면 config.yaml을 사용하고, 없으면 config.example.yaml을 사용합니다."""
    path = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_CONFIG_PATH

    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_seen_ids(path: Path) -> set[str]:
    """이미 이메일로 보낸 공고 ID 목록을 읽습니다."""
    if not path.exists():
        return set()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return set(str(x) for x in data)
        return set()
    except json.JSONDecodeError:
        return set()


def save_seen_ids(path: Path, ids: set[str]) -> None:
    """이번 실행에서 확인한 공고 ID까지 포함해서 저장합니다."""
    path.write_text(
        json.dumps(sorted(ids), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_html_file(html_body: str) -> Path:
    """생성된 HTML 이메일 본문을 파일로 저장하고 파일 경로를 반환합니다."""
    HTML_OUTPUT_PATH.write_text(html_body, encoding="utf-8")
    print(f"[정보] HTML 파일 저장 완료: {HTML_OUTPUT_PATH}")
    return HTML_OUTPUT_PATH


def _period_text(notice: Notice) -> str:
    return notice.period or " ~ ".join(
        x for x in [notice.start_date, notice.end_date] if x
    ) or "-"


def build_text_message(new_notices: list[Notice], old_notices: list[Notice], total_count: int) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "[기업마당 지원사업공고 알림]",
        f"조회시각: {now}",
        f"신규: {len(new_notices)}건 / 기존: {len(old_notices)}건 / 전체: {total_count}건",
        "",
    ]

    if new_notices:
        lines.append("[신규 공고]")
        for idx, notice in enumerate(new_notices, 1):
            lines.extend(
                [
                    f"{idx}. {notice.title}",
                    f"- 분야: {notice.category or '-'}",
                    f"- 소관기관: {notice.organization or '-'}",
                    f"- 수행기관: {notice.execution_org or '-'}",
                    f"- 상태: {notice.status or '-'}",
                    f"- 신청기간: {_period_text(notice)}",
                    f"- 지원대상: {notice.target or '-'}",
                    f"- 링크: {notice.url or '-'}",
                    "",
                ]
            )
    else:
        lines.append("이번 실행에서 새로 확인된 공고는 없습니다.")

    return "\n".join(lines)


def build_html_message(new_notices: list[Notice], old_notices: list[Notice], total_count: int) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    rows: list[str] = []
    for idx, notice in enumerate(new_notices, 1):
        title = html.escape(notice.title or "-")
        category = html.escape(notice.category or "-")
        organization = html.escape(notice.organization or "-")
        execution_org = html.escape(notice.execution_org or "-")
        status = html.escape(notice.status or "-")
        period = html.escape(_period_text(notice))
        target = html.escape(notice.target or "-")
        url = html.escape(notice.url or "")

        link_html = f'<a href="{url}" target="_blank">바로가기</a>' if url else "-"

        rows.append(
            f"""
            <tr>
                <td style="padding:8px;border:1px solid #ddd;text-align:center;">{idx}</td>
                <td style="padding:8px;border:1px solid #ddd;font-weight:600;">{title}</td>
                <td style="padding:8px;border:1px solid #ddd;text-align:center;">{category}</td>
                <td style="padding:8px;border:1px solid #ddd;">{organization}</td>
                <td style="padding:8px;border:1px solid #ddd;">{execution_org}</td>
                <td style="padding:8px;border:1px solid #ddd;text-align:center;">{status}</td>
                <td style="padding:8px;border:1px solid #ddd;text-align:center;white-space:nowrap;">{period}</td>
                <td style="padding:8px;border:1px solid #ddd;">{target}</td>
                <td style="padding:8px;border:1px solid #ddd;text-align:center;">{link_html}</td>
            </tr>
            """
        )

    if not rows:
        rows.append(
            """
            <tr>
                <td colspan="9" style="padding:16px;border:1px solid #ddd;text-align:center;">
                    이번 실행에서 새로 확인된 공고는 없습니다.
                </td>
            </tr>
            """
        )

    return f"""
    <!doctype html>
    <html lang="ko">
    <head>
        <meta charset="utf-8">
        <title>기업마당 지원사업공고 알림</title>
    </head>
    <body style="margin:0;padding:24px;background-color:#f6f7f9;font-family:Arial,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;color:#222;">
        <div style="max-width:1280px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;">
            <div style="padding:24px;background:#243b53;color:#fff;">
                <h2 style="margin:0 0 8px 0;font-size:22px;">기업마당 지원사업공고 알림</h2>
                <p style="margin:0;font-size:14px;opacity:.9;">조회시각: {html.escape(now)}</p>
            </div>

            <div style="padding:20px 24px;border-bottom:1px solid #e5e7eb;">
                <span style="display:inline-block;margin-right:8px;padding:8px 12px;background:#e8f5e9;border-radius:20px;font-weight:600;">신규 {len(new_notices)}건</span>
                <span style="display:inline-block;margin-right:8px;padding:8px 12px;background:#eef2ff;border-radius:20px;font-weight:600;">기존 {len(old_notices)}건</span>
                <span style="display:inline-block;padding:8px 12px;background:#f3f4f6;border-radius:20px;font-weight:600;">전체 {total_count}건</span>
                <p style="margin:14px 0 0 0;color:#555;font-size:14px;">
                    기존 공고는 이미 이전에 발송된 공고입니다. 이 메일에는 신규 공고만 상세 표시합니다.
                    첨부된 HTML 파일을 다운로드하면 같은 내용을 파일로 보관할 수 있습니다.
                </p>
            </div>

            <div style="padding:24px;overflow-x:auto;">
                <h3 style="margin:0 0 12px 0;font-size:18px;">신규 공고 목록</h3>
                <table style="width:100%;border-collapse:collapse;font-size:13px;">
                    <thead>
                        <tr style="background:#f3f4f6;">
                            <th style="padding:8px;border:1px solid #ddd;">번호</th>
                            <th style="padding:8px;border:1px solid #ddd;">공고명</th>
                            <th style="padding:8px;border:1px solid #ddd;">분야</th>
                            <th style="padding:8px;border:1px solid #ddd;">소관기관</th>
                            <th style="padding:8px;border:1px solid #ddd;">수행기관</th>
                            <th style="padding:8px;border:1px solid #ddd;">상태</th>
                            <th style="padding:8px;border:1px solid #ddd;">신청기간</th>
                            <th style="padding:8px;border:1px solid #ddd;">지원대상</th>
                            <th style="padding:8px;border:1px solid #ddd;">링크</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(rows)}
                    </tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """


def run() -> None:
    config = load_config()

    state_config = config.get("state", {})
    seen_path = BASE_DIR / state_config.get("seen_file", "seen_notice_ids.json")
    latest_path = BASE_DIR / state_config.get("latest_file", "latest_notices.json")

    seen_ids = load_seen_ids(seen_path)
    notices = fetch_bizinfo_notices(config)

    new_notices = [n for n in notices if n.notice_id not in seen_ids]
    old_notices = [n for n in notices if n.notice_id in seen_ids]

    subject = f"[기업마당] 신규 공고 {len(new_notices)}건 / 전체 {len(notices)}건"
    html_body = build_html_message(new_notices, old_notices, len(notices))
    text_body = build_text_message(new_notices, old_notices, len(notices))

    html_file_path = save_html_file(html_body)

    print(text_body)
    send_html_email(
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        attachment_path=html_file_path,
    )

    all_ids = seen_ids | {n.notice_id for n in notices}
    save_seen_ids(seen_path, all_ids)

    latest_path.write_text(
        json.dumps([n.to_dict() for n in new_notices], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    run()
