from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.models import (
    ActType,
    BranchNode,
    CharacterState,
    ConsistencyIssue,
    EndingCondition,
    FactStability,
    SceneCard,
    StoryFact,
    StoryProject,
    StoryStateMemory,
    UnifyProposal,
    UnifyReport,
)


def test_scene_card_creation():
    scene = SceneCard(
        scene_id="s1",
        act=ActType.RISE,
        branch_id="root",
        pov_character_id="hero",
        objective="탈출",
        conflict="적의 추격",
        outcome="탈출 성공",
    )
    assert scene.scene_id == "s1"
    assert scene.reachable_endings == []
    assert scene.full_text is None
    assert scene.user_modified is False
    assert scene.order_index == 0


def test_scene_card_user_modified():
    scene = SceneCard(
        scene_id="s1",
        act=ActType.TURN,
        branch_id="root",
        pov_character_id="hero",
        objective="obj",
        conflict="con",
        outcome="out",
        user_modified=True,
        order_index=5,
    )
    assert scene.user_modified is True
    assert scene.order_index == 5


def test_branch_node_creation():
    node = BranchNode(
        branch_id="b1",
        parent_branch_id=None,
        label="시작",
        decision_prompt="결정하라",
        expected_consequence="변화",
    )
    assert node.merge_target_id is None
    assert node.scene_ids == []


def test_story_state_memory_window():
    mem = StoryStateMemory()
    for i in range(12):
        mem.add_scene_to_window(f"scene-{i}")
    assert len(mem.recent_scene_window) == 8
    assert mem.recent_scene_window[0] == "scene-4"
    assert mem.recent_scene_window[-1] == "scene-11"


def test_story_project_defaults():
    project = StoryProject(
        project_id="p1",
        title="테스트",
        genre="판타지",
        tone="밝음",
        narrative_viewpoint="1인칭",
        style_preset="간결",
    )
    assert project.branches == {}
    assert project.scenes == {}
    assert project.endings == {}
    assert project.memory.tension_score == 0.0


def test_ending_condition_defaults():
    ec = EndingCondition(ending_id="e1", title="해피엔딩")
    assert ec.required_facts == {}
    assert ec.prohibited_facts == {}
    assert ec.minimum_tension_score == 0.0


def test_unify_proposal_creation():
    p = UnifyProposal(
        proposal_id="p1",
        issue_id="i1",
        severity="high",
        description="사실 충돌",
        scene_ids=["s1", "s2"],
        proposed_fix="수정 텍스트",
        fix_type="fact_correction",
        auto_fixable=True,
    )
    assert p.user_choice is None
    assert p.auto_fixable is True


def test_unify_report_defaults():
    r = UnifyReport()
    assert r.issues == []
    assert r.proposals == []
    assert r.orphaned_hooks == []
    assert r.chronology_issues == []
