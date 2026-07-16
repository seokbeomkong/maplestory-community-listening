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


def test_source_registry_has_the_exact_production_board_order() -> None:
    sources = _sources_module()

    assert [source.board_id for source in sources.SOURCES] == [
        2294,
        2295,
        2296,
        2297,
        2298,
        5974,
        2300,
        2304,
    ]
    assert sources.source_for_board(5974).key == "free"


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
