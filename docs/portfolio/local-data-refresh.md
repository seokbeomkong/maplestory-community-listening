# 로컬 데이터 자동 갱신

## 공개 대시보드 원클릭 갱신

저장소가 깨끗한 상태에서 다음 명령 하나를 실행하면 VPS 다운로드, 증분 분석, 산출물
검증, 공개 스냅숏 교체, Git 커밋과 `main` 브랜치 업로드까지 순서대로 처리한다.

저장소 루트에서 실행한다. 스크립트가 현재 로컬 HEAD와 원격 `main`이 정확히 같은
시작점인지 확인하므로, 작업 브랜치 이름이 다르더라도 다른 커밋이 공개 브랜치에 섞이지
않는다. detached HEAD 상태는 허용하지 않는다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\publish-public-dashboard.ps1
```

실행 계획과 경로만 확인하고 네트워크·파일·Git 변경을 만들지 않으려면 `-PlanOnly`를
사용한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\publish-public-dashboard.ps1 -PlanOnly
```

스크립트는 다음 조건을 모두 통과한 경우에만 공개 데이터를 커밋한다.

1. 시작 시 Git 작업 폴더에 기존 변경이 없다.
2. named branch 상태이며 로컬 HEAD가 최신 `origin/main`과 정확히 일치한다.
3. VPS Export Release의 체크섬 검증이 성공한다.
4. 분석 manifest가 완료 상태이며 이번 실행에서 받은 ZIP 이름과 SHA-256이 일치한다.
5. `manifest.json`, `semantic_posts.csv`, `semantic_comments.csv`가 모두 존재한다.
6. 분석 도중 저장소가 변경되지 않았으며 Git에는 `portfolio_data` 변경만 추가한다.

커밋 전에 실패하면 공개 데이터 변경을 원래 상태로 복원한다. GitHub 전송만 실패한
경우에는 생성된 로컬 커밋을 보존한다. 단순 네트워크 오류는 오류 메시지의 `git push`
명령으로 전송만 재시도한다. 원격 `main`이 먼저 변경된 경우에는 새 원격 이력을 확인한
뒤 해당 데이터 커밋을 최신 `main`에 cherry-pick하고 다시 전송한다. GitHub `main`
업데이트 후 Streamlit Community Cloud가 같은 공개 링크를 자동으로 다시 배포한다.

## 권장 구조

`MAPLE_EXPORT_PATH`를 특정 파일이 아니라 다운로드 폴더로 설정한다. 대시보드는 폴더의
완료된 `production-*.zip` 가운데 파일명 기준 최신 ZIP을 선택하고 체크섬과 스키마를
검증한다. 실행 중에는 30초마다 새 릴리스를 확인하며, 변경이 있으면 전체 화면을 다시
계산한다. 다운로드 중인 `.partial` 파일은 선택하지 않는다.

```text
VPS 읽기 전용 export
  → 체크섬 검증 다운로드
  → 로컬 exports 폴더에 원자적 ZIP 게시
  → 최신 ZIP 체크섬 검증
  → 댓글·추천·조회 상위 글의 본문·댓글 증분 수집
  → domain-lexicon-v1 주제·의도·감성 추론
  → digest가 일치하는 분석물 원자적 게시
  → 대시보드가 ZIP·분석물 변경을 30초 내 감지
```

따라서 새 ZIP을 받을 때마다 코드를 수정하거나 분석을 수동 실행할 필요가 없다. 실행
스크립트는 30초마다 새 ZIP을 확인하고, 이미 완료된 동일 digest는 즉시 건너뛰며 변경된
릴리스만 상세 수집·추론한다.

## 한 번에 실행

```powershell
Set-Location "C:\Users\tjrqj\Documents\Maplestory\.worktrees\maple-inven-monitor-v1"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-local-dashboard.ps1
```

수동으로 나눠 실행할 때도 파일 하나가 아니라 폴더를 지정하고 분석물을 먼저 갱신한다.

```powershell
$env:MAPLE_EXPORT_PATH = "C:\Users\tjrqj\Documents\Maplestory\exports"
$env:MAPLE_ANALYSIS_ROOT = "C:\Users\tjrqj\Documents\Maplestory\exports\analysis"
.\.venv\Scripts\python.exe -m maple_monitor.cli analyze-export `
  --export-path $env:MAPLE_EXPORT_PATH --analysis-root $env:MAPLE_ANALYSIS_ROOT
.\.venv\Scripts\python.exe -m streamlit run src\maple_monitor\dashboard\export_app.py
```

대시보드를 켜 둔 상태에서 아래 다운로드 명령을 실행하면 새 ZIP이 게시된 뒤 최대 30초
안에 분석 작업이 시작된다. 첫 상세 수집은 요청 간격 때문에 수 분이 걸릴 수 있고, 완료된
분석물이 게시되면 다음 30초 확인 주기에 화면이 바뀐다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\download-production-data.ps1
```

## 다운로드까지 자동화하려면

로컬 PC가 켜져 있고 SSH 키가 비대화식으로 동작한다면 Windows 작업 스케줄러로 다운로드
스크립트를 매일 실행할 수 있다. PowerShell의 `Register-ScheduledTask`는 실행 파일과
스크립트 작업을 등록하고, `New-ScheduledTaskTrigger`는 일별 또는 로그인 시점 트리거를
구성한다.

```powershell
$repo = "C:\Users\tjrqj\Documents\Maplestory"
$script = Join-Path $repo "scripts\download-production-data.ps1"
$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments
$trigger = New-ScheduledTaskTrigger -Daily -At "09:00"
Register-ScheduledTask -TaskName "MapleStory production export" `
  -Action $action -Trigger $trigger `
  -Description "Download and verify the latest MapleStory dashboard export"
```

등록 전에는 다운로드 명령이 암호 입력 없이 성공하는지 확인한다. 실패한 다운로드는
`.partial` 상태로 정리되고 기존 정상 ZIP에는 영향을 주지 않는다.

## NLP·멀티모달 분석의 갱신 원칙

대시보드 실행 중에 모델을 다시 학습시키지는 않는다. 학습과 서빙을 분리한다.

1. 라벨 체계나 충분한 신규 골드 데이터가 생길 때만 오프라인에서 모델을 재학습한다.
2. 승인된 모델은 버전이 붙은 고정 아티팩트로 저장한다.
3. 새 Export Release에는 배치 추론만 실행하고 결과를 릴리스 ID와 모델 버전으로 저장한다.
4. 대시보드는 원시 지표와 해당 릴리스의 추론 결과만 읽는다.
5. 데이터 분포·확률 보정·라벨별 성능이 기준을 벗어날 때 재학습을 검토한다.

이 구조는 다운로드할 때마다 비싼 재학습을 반복하지 않으면서 분석 재현성과 모델 버전
추적을 유지한다.

## 더 효율적인 대안

- **현재 권장안 — 로컬 폴더 감지:** 구현과 보안 부담이 가장 작고, VPS 데이터베이스를
  외부에 노출하지 않는다.
- **공유 포트폴리오 — VPS 또는 별도 서버에서 Streamlit 운영:** 다운로드 단계를 없애고
  항상 같은 링크를 제공할 수 있다. 인증, HTTPS, 리소스 제한과 원본 데이터 비공개가
  선행되어야 한다.
- **규모 확장 — 객체 저장소와 최신 릴리스 manifest:** 검증 ZIP과 `latest.json`을 저장소에
  게시하고 앱이 manifest를 폴링한다. 여러 사용자·여러 배포 환경에는 유리하지만 현재
  개인 로컬 분석에는 과한 인프라다.
- **비권장 — 로컬 대시보드가 VPS PostgreSQL에 직접 접속:** SSH 터널과 DB 수명주기,
  네트워크 장애가 화면에 결합되고 운영 DB 노출 면적도 커진다.

참고: [Streamlit fragments](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment),
[Streamlit caching](https://docs.streamlit.io/develop/concepts/architecture/caching),
[Microsoft Register-ScheduledTask](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/register-scheduledtask)
