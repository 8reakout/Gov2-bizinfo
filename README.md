# Bizinfo Email Scheduler

기업마당 지원사업공고 API에서 `기술`, `창업`, `기타` 분야 공고를 조회한 뒤 HTML 이메일로 발송하는 프로그램입니다.

## 기능

- 기업마당 지원사업정보 API 호출
- 지원분야 `기술(02)`, `창업(06)`, `기타(09)`만 조회
- 신청기간이 지난 공고 제외
- 신규 공고 / 기존 공고 구분
- 신규 공고만 HTML 표 형태로 상세 표시
- 동일한 HTML 파일을 `bizinfo_notice_latest.html`로 저장
- 이메일 본문 + HTML 첨부파일 발송
- GitHub Actions로 매주 월요일 10:00 KST 자동 실행

## GitHub Secrets

Repository Settings → Secrets and variables → Actions → New repository secret에서 아래 값을 등록합니다.

```text
BIZINFO_CRTFC_KEY
SMTP_HOST
SMTP_PORT
SMTP_USE_TLS
SMTP_USER
SMTP_PASSWORD
MAIL_FROM
MAIL_TO
MAIL_CC
```

Gmail을 사용하는 경우 `SMTP_PASSWORD`에는 일반 로그인 비밀번호가 아니라 Google 앱 비밀번호를 넣습니다.

## 로컬 실행

```powershell
copy .env.example .env
copy config.example.yaml config.yaml
python -m pip install -r requirements.txt
python main.py
```

`.env`에는 실제 값을 넣습니다.

```env
BIZINFO_CRTFC_KEY=실제_기업마당_API_인증키
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USER=보내는메일@gmail.com
SMTP_PASSWORD=Google_앱비밀번호
MAIL_FROM=보내는메일@gmail.com
MAIL_TO=받는사람1@company.com,받는사람2@company.com
MAIL_CC=
```

## 생성 파일

실행하면 아래 파일이 생성됩니다.

```text
bizinfo_notice_latest.html
```

이 파일은 이메일에 첨부되며, 로컬에서도 브라우저로 열어볼 수 있습니다.

## GitHub Actions 테스트

`.github/workflows/bizinfo_email_notice.yml`에서 아래 cron을 사용하면 30분마다 테스트할 수 있습니다.

```yaml
cron: "*/30 * * * *"
```

운영 시에는 아래 값으로 되돌립니다.

```yaml
cron: "0 1 * * 1"
```

이는 한국시간 매주 월요일 10:00입니다.

## 주의

- `.env`와 `config.yaml`은 GitHub에 올리지 않습니다.
- `config.example.yaml`과 `.env.example`에는 실제 인증키나 비밀번호를 넣지 않습니다.
- `seen_notice_ids.json`은 기존/신규 공고 구분을 위해 GitHub에 유지합니다.
- `bizinfo_notice_latest.html`과 `latest_notices.json`은 실행 결과물이므로 GitHub에 올리지 않습니다.
