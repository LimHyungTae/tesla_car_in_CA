# Tesla Model Y Inventory Monitor

[![Tesla inventory monitor](https://github.com/LimHyungTae/tesla_car_in_CA/actions/workflows/tesla-monitor.yml/badge.svg)](https://github.com/LimHyungTae/tesla_car_in_CA/actions/workflows/tesla-monitor.yml)

Foster City, California에서 살 중고 Tesla Model Y Long Range AWD를 추적합니다. GitHub Actions가 Mac과 무관하게 Tesla 공식 중고 재고를 확인하고, 변화를 저장한 뒤 모바일 우선 정적 대시보드를 GitHub Pages에 배포합니다.

- Dashboard: <https://limhyungtae.github.io/tesla_car_in_CA/>
- Actions: <https://github.com/LimHyungTae/tesla_car_in_CA/actions/workflows/tesla-monitor.yml>
- Current report baseline: [`0902_candidates_v2.html`](./0902_candidates_v2.html)

## Buy Box

공통 필수조건은 2023년식 이상 Model Y Long Range AWD, HW4, 19인치, neutral color, 50,000mi 미만, Tesla 중고 재고, clean title, 알려진 사고·damage 없음, rental/fleet/commercial/taxi/rideshare 이력 없음입니다. Battery Health/SOH나 이력 근거가 빠졌다면 가격 조건을 만족해도 `VERIFY FIRST`입니다.

| Opportunity | Price | Mileage |
|---|---:|---:|
| ULTRA VALUE A | ≤ $34,000 | ≤ 35,000mi |
| ULTRA VALUE B | ≤ $35,000 | ≤ 25,000mi |
| HIGH PRIORITY | ≤ $35,500 | ≤ 30,000mi |
| BUY | ≤ $35,000 | ≤ 35,000mi |

판정의 유일한 설정 원본은 [`config/buy-box.json`](./config/buy-box.json)입니다. OTD 추정은 `(차량가 + 확인된 taxable Transport) × 1.09375 + $600–800`이며, Transport를 모르면 $0 시나리오를 보여주되 반드시 `Transport not verified`로 표시합니다. Tesla checkout의 실제 세금·등록비·Transport가 최종값입니다.

## 1. Repository 준비

이 저장소는 이미 구성되어 있습니다. 새 환경에서 이어서 작업하려면 다음처럼 clone합니다.

```bash
git clone https://github.com/LimHyungTae/tesla_car_in_CA.git
cd tesla_car_in_CA
```

별도 저장소로 복제할 때는 GitHub에서 public repository를 만든 뒤 `origin`을 새 URL로 바꿉니다. Pages와 예약 실행은 workflow가 기본 브랜치에 있어야 동작합니다.

## 2. GitHub Pages 설정

GitHub에서 **Settings → Pages → Build and deployment → Source → GitHub Actions**를 선택합니다. Workflow는 공식 `configure-pages`, `upload-pages-artifact`, `deploy-pages` 액션을 사용하며 `github-pages` environment에 배포합니다. 배포 URL은 deploy job의 `page_url` output과 위 Dashboard 링크에서 확인할 수 있습니다.

공식 안내: [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)

## 3. Actions 권한 설정

**Settings → Actions → General → Workflow permissions**에서 **Read and write permissions**를 선택합니다. Workflow 자체도 최소 권한을 명시합니다.

- `contents: write`: 상태 JSON bot commit
- `pages: write`: Pages 배포
- `id-token: write`: Pages OIDC 배포

Branch protection을 추가한다면 `tesla-monitor-bot`의 `data/` push가 거절되지 않는지 확인합니다. 동시 실행은 `tesla-monitor` concurrency group 하나로 직렬화되고, 진행 중 실행은 취소하지 않습니다.

## 4. 첫 manual run

1. GitHub **Actions** 탭에서 **Tesla inventory monitor**를 선택합니다.
2. **Run workflow**를 누릅니다.
3. 첫 실행은 `force_crawl: true`를 선택합니다.
4. `Test, crawl and package dashboard`와 `Deploy dashboard to GitHub Pages`가 끝난 뒤 environment URL을 엽니다.

`force_crawl=false`는 평상시와 같은 cadence gate를 적용합니다. `true`는 시간 gate만 건너뛰며 source safety나 BUY gate를 우회하지 않습니다.

## 5. Cron과 실제 crawl cadence

`.github/workflows/tesla-monitor.yml`은 매시간 UTC `07, 22, 37, 52`분에 runner를 깨웁니다.

```text
7,22,37,52 * * * *
```

이는 실행 기회이며 실제 crawl 주기는 아닙니다. Python은 마지막 successful crawl을 읽고 America/Los_Angeles 현지 시각에 따라 결정합니다.

- 00:00–04:59: 약 15분
- 05:00–23:59: 약 30분
- 아직 due가 아니면 정상 `skipped`

GitHub 예약 실행은 지연되거나 드물게 누락될 수 있으므로 정각을 피했습니다. 예약 workflow는 default branch에서만 실행됩니다. 자세한 제약은 [GitHub scheduled events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)를 참고하세요.

## 6. PDT/PST 처리

고정 UTC offset을 쓰지 않습니다. `zoneinfo.ZoneInfo("America/Los_Angeles")`로 현지 시간대를 변환하므로 PDT/PST와 spring-forward/fall-back을 자동 처리합니다. 저장 timestamp는 비교가 명확하도록 UTC ISO-8601을 사용하고, UI는 Los Angeles 시간으로 렌더링합니다.

## 7. Tesla 403/429 및 parser failure

크롤러는 timeout, 제한된 재시도, exponential backoff, HTTP 403/429/5xx, 잘못된 JSON과 예상하지 못한 응답 구조를 처리합니다. CAPTCHA 풀이, fingerprint 위장, proxy rotation 같은 우회는 하지 않습니다.

모든 재시도가 실패하거나 응답이 의심스럽게 비면:

- 마지막 정상 `data/inventory.json`을 삭제하거나 빈 배열로 덮지 않습니다.
- 실패 이유와 마지막 attempted/successful 시각을 기록합니다.
- 사용 가능한 이전 inventory가 있으면 source status는 `degraded`, 없으면 `failed`입니다.
- 실패 상태도 dashboard에 배포되므로 오래된 데이터임을 숨기지 않습니다.

## 8. 설정 변경

- [`config/buy-box.json`](./config/buy-box.json): 차량 hard gates, BUY/HIGH PRIORITY/ULTRA VALUE, OTD, tie-break weights
- [`config/monitor.json`](./config/monitor.json): timezone/cadence, Tesla endpoint, ZIP/radius, timeout/retry/backoff, neutral colors, $300 price-drop alert, 파일 경로

threshold를 바꾸면 Python과 Node 테스트를 함께 갱신합니다. crawler나 dashboard에 별도 숫자를 하드코딩해 config와 경쟁시키지 않습니다.

## 9. Local test와 실행

Python 3.11+와 Node.js 20+를 권장합니다.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
npm test
python -m tesla_monitor.cli --force
```

시간대 스케줄만 재현하려면 `--now`를 함께 사용할 수 있습니다. Unit test는 fixture client를 사용하며 Tesla 네트워크 상태에 의존하지 않습니다.

```bash
python -m tesla_monitor.cli --now 2026-09-02T00:10:00-07:00
```

## 10. 상태 데이터 구조

GitHub-hosted runner는 stateless이므로 상태를 public repository에 JSON으로 commit합니다.

| File | 역할 |
|---|---|
| `data/state.json` | 마지막 run/attempt/success, cadence, known·inactive VIN, last-known catalog |
| `data/inventory.json` | 마지막으로 완전히 성공한 active inventory와 판정 |
| `data/history.json` | run 기록과 new/disappeared/reappeared/price/mileage/location/tier events |
| `dashboard/data/inventory.json` | Pages용 active inventory projection |
| `dashboard/data/history.json` | Pages용 event/history projection |
| `dashboard/data/status.json` | `healthy/degraded/failed`, 실패 이유, freshness와 counts |
| `dashboard/data/buy-box.json` | Pages가 읽는 Buy Box 설정 projection |
| `dashboard/data/monitor.json` | Pages가 읽는 change/history 표시 설정 projection |

생성된 상태·재고 데이터가 달라졌을 때만 `tesla-monitor-bot <actions@users.noreply.github.com>`이 `Update Tesla inventory <timestamp>` 형식으로 commit합니다. Workflow trigger는 `schedule`과 `workflow_dispatch`뿐이므로 이 push가 다시 workflow를 시작하지 않습니다.

## 11. Public repository 주의점

위 JSON과 commit history, VIN, 가격, 위치, 관찰 시각은 모두 공개됩니다. Tesla/AutoCheck cookie, GitHub token, 주소·면허·금융 신청 정보, checkout session URL 같은 개인정보나 secret을 config/state/dashboard에 넣지 마세요. 필요한 secret은 GitHub Actions secret에만 보관하되 현재 monitor는 별도 secret이 필요하지 않습니다.

## 12. Claude Code와 Codex에서 이어가기

- Codex는 `AGENTS.md`와 `.agents/skills/tesla-buy-box/SKILL.md`를 사용합니다.
- Claude Code는 `CLAUDE.md`와 `.claude/skills/tesla-buy-box/SKILL.md`를 사용합니다.
- `.agents/skills/tesla-buy-box`는 `.claude/skills/tesla-buy-box`를 가리키는 symlink라 두 도구가 같은 규칙을 읽습니다.

```text
$tesla-buy-box 모니터 상태를 진단하고 테스트해줘
/tesla-buy-box 오늘 재고와 Buy Box 판정을 확인해줘
```

연구·판정·배포 자동화까지만 허용됩니다. 차량 예약, deposit, financing 신청, 판매자 연락은 별도 명시적 요청 없이는 수행하지 않습니다.
