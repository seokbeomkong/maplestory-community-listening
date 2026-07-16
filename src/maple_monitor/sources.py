from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Final, Literal


@dataclass(frozen=True)
class SourceDefinition:
    key: str
    board_id: int
    name: str
    kind: Literal["job", "free", "info"]
    fixed_analysis_unit: str | None


SOURCES: Final = (
    SourceDefinition("warrior", 2294, "전사", "job", None),
    SourceDefinition("magician", 2295, "마법사", "job", None),
    SourceDefinition("archer", 2296, "궁수", "job", None),
    SourceDefinition("thief", 2297, "도적", "job", None),
    SourceDefinition("pirate", 2298, "해적", "job", None),
    SourceDefinition("free", 5974, "자유 게시판", "free", "free"),
    SourceDefinition("qna", 2300, "질문과 답변", "info", "qna"),
    SourceDefinition("tips", 2304, "팁과 노하우", "info", "tips"),
)

JOB_ANALYSIS_UNITS: Final = {
    2294: {
        "히어로": "hero",
        "팔라딘": "paladin",
        "다크나이트": "dark_knight",
        "소울마스터": "soul_master",
        "아란": "aran",
        "데몬슬레이어": "demon_slayer",
        "미하일": "mihile",
        "카이저": "kaiser",
        "데몬어벤져": "demon_avenger",
        "제로": "zero",
        "블래스터": "blaster",
        "아델": "adele",
        "렌": "len",
        "기타": "warrior_other",
    },
    2295: {
        "아크(불독)": "arch_mage_fire_poison",
        "아크(썬콜)": "arch_mage_ice_lightning",
        "비숍": "bishop",
        "플레임위자드": "flame_wizard",
        "에반": "evan",
        "배틀메이지": "battle_mage",
        "루미너스": "luminous",
        "키네시스": "kinesis",
        "일리움": "illium",
        "라라": "lara",
        "레테": "lete",
        "기타": "magician_other",
    },
    2296: {
        "보우마스터": "bowmaster",
        "신궁": "marksman",
        "윈드브레이커": "wind_archer",
        "와일드헌터": "wild_hunter",
        "메르세데스": "mercedes",
        "패스파인더": "pathfinder",
        "카인": "kain",
        "기타": "archer_other",
    },
    2297: {
        "나이트로드": "night_lord",
        "섀도어": "shadower",
        "나이트워커": "night_walker",
        "듀얼블레이드": "dual_blade",
        "괴도팬텀": "phantom",
        "카데나": "cadena",
        "호영": "hoyoung",
        "칼리": "khali",
        "기타": "thief_other",
    },
    2298: {
        "메카닉": "mechanic",
        "바이퍼": "buccaneer",
        "캡틴": "corsair",
        "스트라이커": "thunder_breaker",
        "캐논슈터": "cannon_shooter",
        "엔젤릭버스터": "angelic_buster",
        "제논": "xenon",
        "은월": "shade",
        "아크": "ark",
        "기타": "pirate_other",
    },
}

_SOURCES_BY_BOARD: Final = {source.board_id: source for source in SOURCES}


def source_for_board(board_id: int) -> SourceDefinition:
    if isinstance(board_id, bool) or not isinstance(board_id, int):
        raise TypeError("board_id must be an integer")
    try:
        return _SOURCES_BY_BOARD[board_id]
    except KeyError:
        raise ValueError("unsupported board") from None


def analysis_unit_for(source: SourceDefinition, category: str) -> str | None:
    if not isinstance(source, SourceDefinition):
        raise TypeError("source must be a SourceDefinition")
    if not isinstance(category, str):
        raise TypeError("category must be a string")
    normalized_category = unicodedata.normalize("NFKC", category).strip()
    if source.kind != "job":
        return source.fixed_analysis_unit
    return JOB_ANALYSIS_UNITS[source.board_id].get(normalized_category)
