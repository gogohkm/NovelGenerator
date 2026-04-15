from __future__ import annotations

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.models import (
    ActType,
    BranchNode,
    EndingCondition,
    FactStability,
    SceneCard,
    StoryFact,
    StoryProject,
)
from core.persistence import load_project, save_project


def _make_full_project() -> StoryProject:
    project = StoryProject(
        project_id="test-001",
        title="테스트 소설",
        genre="SF",
        tone="긴장",
        narrative_viewpoint="3인칭",
        style_preset="리듬감",
        world_rules=["시간 역행 불가", "AI 실체 없음"],
        hard_constraints=["200장면 이내"],
    )
    project.branches["root"] = BranchNode(
        branch_id="root",
        parent_branch_id=None,
        label="시작",
        decision_prompt="선택",
        expected_consequence="결과",
    )
    project.branches["root-A"] = BranchNode(
        branch_id="root-A",
        parent_branch_id="root",
        label="분기 A",
        decision_prompt="돌파",
        expected_consequence="충돌",
        scene_ids=["scene-0001"],
    )
    project.acts = {act: [] for act in ActType}
    project.acts[ActType.RISE] = ["scene-0001"]
    project.scenes["scene-0001"] = SceneCard(
        scene_id="scene-0001",
        act=ActType.RISE,
        branch_id="root-A",
        pov_character_id="hero",
        objective="탈출",
        conflict="적",
        outcome="성공",
        setup_hooks=["hook1"],
        summary="요약 텍스트",
        full_text="본문 텍스트",
        reachable_endings=["e1"],
        user_modified=True,
        order_index=3,
    )
    project.endings["e1"] = EndingCondition(
        ending_id="e1",
        title="해피엔딩",
        required_facts={"hero_alive": "true"},
        minimum_tension_score=0.5,
        theme_alignment_hint="희망",
    )
    project.memory.global_bible["hero_alive"] = StoryFact(
        key="hero_alive",
        value="true",
        source_scene_id="scene-0001",
        stability=FactStability.IMMUTABLE,
    )
    project.memory.tension_score = 0.6
    project.memory.recent_scene_window = ["scene-0001"]

    return project


def test_save_load_round_trip():
    original = _make_full_project()

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name

    try:
        save_project(original, path)
        loaded = load_project(path)

        assert loaded.project_id == original.project_id
        assert loaded.title == original.title
        assert loaded.genre == original.genre
        assert loaded.world_rules == original.world_rules
        assert loaded.hard_constraints == original.hard_constraints

        assert set(loaded.branches.keys()) == set(original.branches.keys())
        assert loaded.branches["root-A"].parent_branch_id == "root"
        assert loaded.branches["root-A"].scene_ids == ["scene-0001"]

        assert "scene-0001" in loaded.scenes
        scene = loaded.scenes["scene-0001"]
        assert scene.act == ActType.RISE
        assert scene.full_text == "본문 텍스트"
        assert scene.reachable_endings == ["e1"]
        assert scene.user_modified is True
        assert scene.order_index == 3

        assert "e1" in loaded.endings
        assert loaded.endings["e1"].required_facts == {"hero_alive": "true"}
        assert loaded.endings["e1"].minimum_tension_score == 0.5

        assert "hero_alive" in loaded.memory.global_bible
        assert loaded.memory.global_bible["hero_alive"].stability == FactStability.IMMUTABLE
        assert loaded.memory.tension_score == 0.6
        assert loaded.memory.recent_scene_window == ["scene-0001"]
    finally:
        os.unlink(path)


def test_empty_project_round_trip():
    project = StoryProject(
        project_id="empty",
        title="빈 프로젝트",
        genre="미정",
        tone="중립",
        narrative_viewpoint="1인칭",
        style_preset="기본",
    )

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name

    try:
        save_project(project, path)
        loaded = load_project(path)
        assert loaded.project_id == "empty"
        assert loaded.scenes == {}
        assert loaded.branches == {}
    finally:
        os.unlink(path)


def test_old_format_compatibility():
    """user_modified/order_index 없는 구 형식 파일도 기본값으로 정상 로드된다."""
    import json
    old_data = {
        "project": {
            "project_id": "old",
            "title": "구형",
            "genre": "판타지",
            "tone": "밝음",
            "narrative_viewpoint": "1인칭",
            "style_preset": "간결",
            "world_rules": [],
            "hard_constraints": [],
            "acts": {"gi": ["s1"]},
            "branches": {},
            "scenes": {
                "s1": {
                    "scene_id": "s1",
                    "act": "gi",
                    "branch_id": "root",
                    "pov_character_id": "hero",
                    "objective": "o",
                    "conflict": "c",
                    "outcome": "r",
                }
            },
            "endings": {},
            "memory": {"global_bible": {}, "act_summaries": {}, "recent_scene_window": [], "character_states": {}, "tension_score": 0.0},
        },
        "enums": {
            "ActType": {"RISE": "gi"},
            "FactStability": {"IMMUTABLE": "immutable"},
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w", encoding="utf-8") as f:
        json.dump(old_data, f, ensure_ascii=False)
        path = f.name

    try:
        loaded = load_project(path)
        scene = loaded.scenes["s1"]
        assert scene.user_modified is False
        assert scene.order_index == 0
        assert scene.reachable_endings == []
    finally:
        os.unlink(path)
