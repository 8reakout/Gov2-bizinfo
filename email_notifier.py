from __future__ import annotations

import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


def _split_recipients(value: str) -> list[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


def send_html_email(
    subject: str,
    html_body: str,
    text_body: str = "",
    attachment_path: Path | None = None,
) -> None:
    """HTML 이메일을 발송하고, 필요하면 HTML 파일을 첨부합니다."""
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes", "y"}
    mail_from = os.getenv("MAIL_FROM", smtp_user)
    mail_to = os.getenv("MAIL_TO", "")
    mail_cc = os.getenv("MAIL_CC", "")

    if not smtp_host:
        raise ValueError("SMTP_HOST 값이 없습니다. .env 또는 GitHub Secrets를 확인하세요.")
    if not smtp_user:
        raise ValueError("SMTP_USER 값이 없습니다. .env 또는 GitHub Secrets를 확인하세요.")
    if not smtp_password:
        raise ValueError("SMTP_PASSWORD 값이 없습니다. .env 또는 GitHub Secrets를 확인하세요.")
    if not mail_to:
        raise ValueError("MAIL_TO 값이 없습니다. .env 또는 GitHub Secrets를 확인하세요.")

    to_recipients = _split_recipients(mail_to)
    cc_recipients = _split_recipients(mail_cc)
    recipients = to_recipients + cc_recipients

    if not recipients:
        raise ValueError("메일 수신자가 없습니다. MAIL_TO 또는 MAIL_CC 값을 확인하세요.")

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = ", ".join(to_recipients)

    if cc_recipients:
        msg["Cc"] = ", ".join(cc_recipients)

    body_part = MIMEMultipart("alternative")

    if not text_body:
        text_body = (
            "기업마당 지원사업공고 알림입니다.\n\n"
            "HTML 메일을 지원하는 환경에서 본문을 확인하거나, 첨부된 HTML 파일을 다운로드해 확인하세요."
        )

    body_part.attach(MIMEText(text_body, "plain", "utf-8"))
    body_part.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(body_part)

    if attachment_path and attachment_path.exists():
        file_bytes = attachment_path.read_bytes()
        attachment = MIMEApplication(file_bytes, _subtype="html")
        attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename=attachment_path.name,
        )
        msg.attach(attachment)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        if smtp_use_tls:
            server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(mail_from, recipients, msg.as_string())
