# Tesla Model Y Inventory Monitor

[![Tesla inventory monitor](https://github.com/LimHyungTae/tesla_car_in_CA/actions/workflows/tesla-monitor.yml/badge.svg)](https://github.com/LimHyungTae/tesla_car_in_CA/actions/workflows/tesla-monitor.yml)

Foster City, California에서 살 중고 Tesla Model Y Long Range AWD를 추적합니다. GitHub Actions가 Mac과 무관하게 Tesla 공식 중고 재고 확인을 시도하고, 성공한 변화 또는 안전하게 보존한 마지막 스냅샷을 모바일 우선 정적 대시보드로 GitHub Pages에 배포합니다.

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

## Historical listing benchmarks

아래는 **과거 관측 당시 숫자가 좋았던 학습용 사례**입니다. 현재 판매 중이라는 뜻이 아니며 Tesla 링크는 이미 만료됐을 수 있습니다. 특히 이 표의 모든 VIN은 BMS 진단이나 Tesla `Battery Health Test`로 확인한 SOH가 없으므로, `좋았던 매물 = 구매 검증이 끝난 차량`으로 읽으면 안 됩니다. `CLEAN`도 당시 feed 표시일 뿐 AutoCheck 원문·title·prior use 확인을 대신하지 않습니다.

| VIN / 관측일 | 당시 최저 기록 | 구성 | 현재 Buy Box로 배우는 점 |
|---|---:|---|---|
| [PF824185 · Tesla](https://www.tesla.com/my/order/7SAYGDEE2PF824185?titleStatus=used&redirect=no#overview) · [이력](https://teslatracker.com/inventory/7SAYGDEE2PF824185)<br>2026-07-12 | **$33,900 · 32,914mi** | 2023 · HW4 · 19\" · White · Fremont | 숫자만 보면 `ULTRA VALUE A`. 낮은 가격이 history/SOH hard gate를 생략하게 해서는 안 되는 사례입니다. |
| [PF824202 · Tesla](https://www.tesla.com/my/order/7SAYGDEE9PF824202?titleStatus=used&redirect=no#overview) · [이력](https://teslatracker.com/inventory/7SAYGDEE9PF824202)<br>2026-07-12 | **$35,300 · 14,279mi** | 2023 · HW4 · 19\" · Black · McClellan Park | `HIGH PRIORITY`의 모범적인 저마일 조합. $39,200에서 $35,300까지 내려온 가격 대기 사례이기도 합니다. |
| [PF828214 · Tesla](https://www.tesla.com/my/order/7SAYGDEE3PF828214?titleStatus=used&redirect=no#overview) · [이력](https://teslatracker.com/inventory/7SAYGDEE3PF828214)<br>2026-07-12 | **$34,700 · 28,543mi** | 2023 · HW4 · 19\" · White · Fremont | 현재 기준 `HIGH PRIORITY`. 가격·마일·보증 여유가 한쪽으로 치우치지 않은 균형 기준입니다. |
| [PA151462 · Tesla](https://www.tesla.com/my/order/7SAYGDEE4PA151462?titleStatus=used&redirect=no#overview) · [이력](https://teslatracker.com/inventory/7SAYGDEE4PA151462)<br>2026-08-17–08-31 | **$34,600 · 32,172mi** | 2023 · HW4 · 19\" · White · Gilroy | 현재 핵심 Buy Box인 `≤$35k · ≤35k mi`에 들어온 실전 기준점. 9월 2일에는 inactive였고 당시에도 AutoCheck/prior use/SOH는 미확인이었습니다. |
| [PF873395 · Tesla](https://www.tesla.com/my/order/7SAYGDEE5PF873395?titleStatus=used&redirect=no#overview) · [이력](https://teslatracker.com/inventory/7SAYGDEE5PF873395)<br>2026-08-21–09-01 | **$35,200 · 33,747mi** | 2023 · HW4 · 19\" · Grey · Fresno | $38,200에서 $35,200까지 하락한 기다림 사례. BUY 가격선까지 $200였지만 Transport가 붙으면 OTD 여유가 작았습니다. |
| [PF886407 · Tesla](https://www.tesla.com/my/order/7SAYGDEE7PF886407?titleStatus=used&redirect=no#overview) · [이력](https://teslatracker.com/inventory/7SAYGDEE7PF886407)<br>2026-08-24–09-01 | **$36,800 · 27,544mi** | 2023 · HW4 · 19\" · Black · McClellan Park | AutoCheck 93, clean title, 사고 미보고, 1-owner lease가 확인된 저마일 WATCH. **$35,500이면 HIGH PRIORITY**라는 가격 알림 기준입니다. SOH/Transport는 미확인입니다. |
| [RF133570 · Tesla](https://www.tesla.com/my/order/7SAYGDEE8RF133570?titleStatus=used&redirect=no#overview) · [이력](https://teslatracker.com/inventory/7SAYGDEE8RF133570)<br>2026-08-20 | **$36,400 · 29,386mi** | 2024 · HW4 · 19\" · Grey · Tow | 품질형 near-miss. $0 Transport여도 추정 OTD가 cap보다 약 $413–613 높아, 연식만 보고 예산을 밀어 올리지 않는 기준이 됐습니다. |
| [PF971563 · Tesla](https://www.tesla.com/my/order/7SAYGDEE8PF971563?titleStatus=used&redirect=no#overview) · [이력](https://teslatracker.com/inventory/7SAYGDEE8PF971563)<br>2026-08-21–09-01 | **$37,100 · 22,851mi** | 2023 · HW4 · 19\" · Black · Colma | 25k mi 미만의 가격 하락 관찰 대상. **$35,000 + 모든 gate 통과 시 ULTRA VALUE B**입니다. |
| [PA154636 · Tesla](https://www.tesla.com/my/order/7SAYGDEE4PA154636?titleStatus=used&redirect=no#overview) · [이력](https://teslatracker.com/inventory/7SAYGDEE4PA154636)<br>2026-08-24–09-01 | **$37,400 · 19,147mi** | 2023 · HW4 · 19\" · Grey · McClellan Park | 기록 중 가장 낮은 마일 사례. **$35,000이면 ULTRA VALUE**지만, 저마일 하나만 보고 $2k 이상 과지불하지 않는 비교 기준입니다. |

유용한 비구매 사례도 남겨 둡니다.

- [PF855716](https://teslatracker.com/inventory/7SAYGDEE8PF855716)은 $32,800 / 46,253mi / HW4 / 19\"로 OTD는 훌륭했지만 preferred 35k mi를 크게 넘었습니다. 싼 가격이 높은 주행거리를 자동으로 상쇄하지는 않습니다.
- [PF875376](https://teslatracker.com/inventory/7SAYGDEE0PF875376)은 $36,300 / 25,738mi / HW4 / 19\"였지만 Blue라 neutral-color gate를 통과하지 못했고 OTD도 초과했습니다. 색상 선호를 바꿀 때만 별도로 재평가할 사례입니다.

새 매물이 나오면 위 차량의 현재 판매 여부를 좇기보다 `가격 × mileage × hard-gate evidence`를 이 기록과 비교합니다. 사람이 참고하는 제3자 이력 링크는 discovery용이며, 최종 availability/가격은 Tesla checkout, 사고·title·prior use는 AutoCheck 원문, SOH는 BMS/Battery Health 근거가 우선합니다.

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

`inventory/api/v4/inventory-results`는 Tesla 웹사이트가 사용하는 내부 재고 경로이지, [Tesla Developer/Fleet API](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-endpoints)에 문서화된 판매 재고 API가 아닙니다. 따라서 Fleet API token을 붙여 해결할 수 없습니다. 2026-09-03 [Actions 실행](https://github.com/LimHyungTae/tesla_car_in_CA/actions/runs/33795417132)과 별도 진단에서 Tesla/Akamai가 GitHub-hosted runner의 홈페이지·재고 페이지·재고 API 요청을 모두 HTTP 403으로 거부했고, 쿼리나 JSON parser 문제는 아니었습니다.

- HTTP 403은 같은 요청을 반복해도 회복될 가능성이 낮아 1회에 중단하고 6시간 cooldown을 적용합니다.
- HTTP 429, 408, 5xx, timeout과 일시적 parser/network 오류만 제한적으로 재시도합니다. `Retry-After`는 최대 60초까지만 반영합니다.
- `force_crawl=true`는 cooldown을 건너뛰므로 장애 확인용으로 반복 실행하지 않습니다.
- 제3자 tracker 링크는 사람이 후보를 확인하는 discovery 용도로만 씁니다. 해당 서비스의 허가 없이 HTML/API를 GitHub Actions의 자동 fallback으로 수집하지 않습니다.

모든 재시도가 실패하거나 응답이 의심스럽게 비면:

- 마지막 정상 `data/inventory.json`을 삭제하거나 빈 배열로 덮지 않습니다.
- 실패 이유와 마지막 attempted/successful 시각을 기록합니다.
- 사용 가능한 이전 inventory가 있으면 source status는 `degraded`, 없으면 `failed`입니다.
- 실패 상태도 dashboard에 배포되며, 차량 수와 카드는 `Current`가 아니라 `Last-known`으로 표시해 오래된 데이터임을 숨기지 않습니다.

GitHub-hosted runner에서 403이 계속되는 동안 이 dashboard는 새 Tesla 재고를 발견할 수 없습니다. 공식 소스만으로 fresh 자동화를 복구하려면 Tesla가 허용하는 네트워크의 always-on self-hosted runner(예: NAS/Raspberry Pi)나 Tesla의 명시적 재고 데이터 사용 허가가 필요합니다. 마지막 스냅샷은 비교 공부에는 쓸 수 있지만, 실제 구매 판단 전에는 Tesla checkout에서 판매 여부와 가격을 다시 확인해야 합니다.

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
| `data/state.json` | 마지막 run/attempt/success, typed source error, cooldown/next due, known·inactive VIN, last-known catalog |
| `data/inventory.json` | 마지막으로 완전히 성공한 active inventory와 판정 |
| `data/history.json` | run 기록과 new/disappeared/reappeared/price/mileage/location/tier events |
| `dashboard/data/inventory.json` | Pages용 active inventory projection |
| `dashboard/data/history.json` | Pages용 event/history projection |
| `dashboard/data/status.json` | `healthy/degraded/failed`, live/last-known mode, 사용자 안내·기술 원인, freshness와 counts |
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
