from __future__ import annotations

import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest


@pytest.fixture
def export_zip(tmp_path: Path) -> Path:
    posts_header = (
        "board_id,board_name,post_id,analysis_unit,title,published_at,source_url,"
        "current_category,observed_at_slot_kst,observed_at_actual,views,recommendations,"
        "comments,config_version\n"
    )
    posts = posts_header + "".join(
        [
            "2294,전사,1,hero,히어로 개선 토론,2026-07-16 18:00:00+09,https://www.inven.co.kr/board/maple/2294/1,히어로,2026-07-17 00:20:00+09,2026-07-17 00:20:03+09,500,3,8,abc\n",
            "5974,자유 게시판,2,free,신규 스킬 이야기,2026-07-16 23:00:00+09,https://www.inven.co.kr/board/maple/5974/2,수다,2026-07-17 00:20:00+09,2026-07-17 00:20:03+09,900,7,12,abc\n",
            "2300,질문과 답변,3,qna,장비 질문,2026-07-16 12:00:00+09,https://www.inven.co.kr/board/maple/2300/3,아이템,2026-07-17 00:20:00+09,2026-07-17 00:20:03+09,100,0,0,abc\n",
            "2304,팁과 노하우,4,tips,보스 공략,2026-07-10 12:00:00+09,https://www.inven.co.kr/board/maple/2304/4,보스,2026-07-17 00:20:00+09,2026-07-17 00:20:03+09,2000,20,5,abc\n",
        ]
    )
    members = {
        "latest_post_metrics.csv": posts,
        "cumulative_top50.csv": (
            "analysis_unit,metric,as_of_slot_kst,rank,board_id,post_id,title,source_url,metric_value,config_version\n"
            "free,comments,2026-07-17 00:20:00+09,1,5974,2,신규 스킬 이야기,https://www.inven.co.kr/board/maple/5974/2,12,abc\n"
        ),
        "collection_runs.csv": (
            "id,job_type,scheduled_at_slot_kst,status,config_version,started_at,finished_at,diagnostics\n"
            'one,metadata:free,2026-07-17 00:20:00+09,succeeded,abc,2026-07-17 00:20:00+09,2026-07-17 00:21:00+09,"{}"\n'
            'two,metadata:warrior,2026-07-16 18:20:00+09,failed,abc,2026-07-16 18:20:00+09,2026-07-16 18:21:00+09,"{attempts: 3}"\n'
        ),
        "security_quarantine.csv": "id,source_kind,source_ref,content_hash,findings,risk_score,quarantined_at,review_state,reviewer,note,released_at\n",
    }
    encoded = {name: ("\ufeff" + body).encode("utf-8") for name, body in members.items()}
    manifest = "".join(
        f"{hashlib.sha256(content).hexdigest()}  {name}\n"
        for name, content in encoded.items()
    )
    path = tmp_path / "production.zip"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, content in encoded.items():
            archive.writestr(name, content)
        archive.writestr("SHA256SUMS.txt", manifest)
    return path
