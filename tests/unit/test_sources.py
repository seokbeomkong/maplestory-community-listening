from __future__ import annotations

import importlib
import importlib.util
from types import ModuleType

import pytest


def _sources_module() -> ModuleType:
    assert importlib.util.find_spec("maple_monitor.sources") is not None, (
        "the allow-listed source registry is missing"
    )
    return importlib.import_module("maple_monitor.sources")


def test_source_registry_has_the_exact_production_definitions() -> None:
    sources = _sources_module()

    assert tuple(
        (
            source.key,
            source.board_id,
            source.name,
            source.kind,
            source.fixed_analysis_unit,
        )
        for source in sources.SOURCES
    ) == (
        ("warrior", 2294, "전사", "job", None),
        ("magician", 2295, "마법사", "job", None),
        ("archer", 2296, "궁수", "job", None),
        ("thief", 2297, "도적", "job", None),
        ("pirate", 2298, "해적", "job", None),
        ("free", 5974, "자유 게시판", "free", "free"),
        ("qna", 2300, "질문과 답변", "info", "qna"),
        ("tips", 2304, "팁과 노하우", "info", "tips"),
    )
    assert sources.source_for_board(5974).key == "free"


def test_job_analysis_units_match_the_complete_stable_mapping() -> None:
    sources = _sources_module()

    assert sources.JOB_ANALYSIS_UNITS == {
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


def test_source_lookup_rejects_non_integer_and_unknown_board_ids() -> None:
    sources = _sources_module()

    for board_id in (True, 9999):
        with pytest.raises((TypeError, ValueError), match="board"):
            sources.source_for_board(board_id)


def test_analysis_units_are_stable_and_exclusions_fail_closed() -> None:
    sources = _sources_module()

    assert sources.analysis_unit_for(sources.source_for_board(2294), "히어로") == "hero"
    assert sources.analysis_unit_for(sources.source_for_board(2294), "팁/정보") is None
    assert sources.analysis_unit_for(sources.source_for_board(2294), "핑크빈") is None
    assert sources.analysis_unit_for(sources.source_for_board(2298), "예티") is None
    assert sources.analysis_unit_for(sources.source_for_board(5974), "수다") == "free"
    assert sources.analysis_unit_for(sources.source_for_board(2300), "아이템") == "qna"
    assert sources.analysis_unit_for(sources.source_for_board(2304), "사냥") == "tips"


def test_analysis_category_normalization_uses_nfkc_and_surrounding_trim() -> None:
    sources = _sources_module()

    warrior = sources.source_for_board(2294)
    assert sources.analysis_unit_for(warrior, "  히어로  ") == "hero"
    assert sources.analysis_unit_for(warrior, "아크（불독）") is None
    magician = sources.source_for_board(2295)
    assert sources.analysis_unit_for(magician, "아크（불독）") == "arch_mage_fire_poison"
    assert sources.analysis_unit_for(magician, "알 수 없음") is None
