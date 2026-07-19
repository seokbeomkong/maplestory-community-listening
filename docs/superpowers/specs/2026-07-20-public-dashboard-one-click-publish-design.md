# 공개 대시보드 원클릭 배포 설계

## 목적

사용자가 PowerShell 명령 하나로 VPS의 최신 Export Release를 내려받고, 로컬 의미 분석을
갱신한 뒤, 검증된 공개용 스냅숏을 GitHub `main`에 올려 Streamlit Community Cloud를
재배포한다.

## 선택한 방식

명시적으로 실행하는 로컬 배포 스크립트를 사용한다. Windows 작업 스케줄러는 사용자의
확인 없이 GitHub를 갱신할 수 있고, GitHub Actions는 로컬 SSH 자격 증명과 분석 환경을
별도로 이전해야 하므로 이번 범위에서 제외한다.

## 데이터 흐름

```text
VPS export → 체크섬 검증 다운로드 → 증분 분석 → manifest/ZIP digest 검증
→ 임시 공개 번들 생성 → portfolio_data 교체 → 전용 Git 커밋 → origin/main push
```

## 안전 조건

- 기존 사용자 변경과 섞이지 않도록 시작 시 깨끗한 Git 작업 폴더를 요구한다.
- 현재 브랜치와 원격 대상 브랜치가 같은 이름·같은 HEAD인지 fetch 후 확인한다.
- `-PlanOnly`는 경로와 단계만 JSON으로 출력하며 네트워크와 파일 변경을 만들지 않는다.
- manifest의 `complete`, `source_archive`, `source_sha256`을 원본 ZIP과 비교한다.
- 커밋 대상은 `portfolio_data`로 제한한다.
- 분석 이후 저장소 상태를 다시 확인하고 검증된 Git index tree를 기록한다. 생성된 커밋의
  부모, tree, 변경 경로가 모두 예상값과 일치할 때만 전송한다.
- 커밋 전 오류는 공개 데이터 변경을 복원한다.
- push 오류 뒤에는 로컬 커밋을 보존하여 데이터 손실 없이 전송만 재시도할 수 있게 한다.

## 검증

PowerShell 시험 모드의 무부작용과 전체 단계, 필수 분석 파일, digest 검증, Git 범위 제한을
pytest로 확인한다. 전체 단위·대시보드 테스트와 Ruff를 최종 검증으로 사용한다.
