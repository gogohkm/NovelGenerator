from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.consistency import ConsistencyChecker, RewriteImpactAnalyzer, UnifyEngine
from core.generation_loop import RuleCheckResult
from core.llm_adapter import MockUnifyHelper, RuleBasedMockGenerator
from core.models import (
    ActType,
    BranchNode,
    ConsistencyIssue,
    FactStability,
    SceneCard,
    StoryFact,
    StoryProject,
    StoryStateMemory,
)


def _make_project() -> StoryProject:
    project = StoryProject(
        project_id="test",
        title="테스트",
        genre="판타지",
        tone="진지",
        narrative_viewpoint="3인칭",
        style_preset="간결",
        world_rules=["마법은 대가를 치른다", "죽은 자는 되살릴 수 없다"],
    )
    project.branches["root"] = BranchNode(
        branch_id="root",
        parent_branch_id=None,
        label="시작",
        decision_prompt="결정",
        expected_consequence="결과",
    )
    project.acts = {act: [] for act in ActType}
    return project


def test_no_fact_conflicts():
    project = _make_project()
    project.memory.global_bible["key1"] = StoryFact(
        key="key1", value="a", source_scene_id="s1", stability=FactStability.MUTABLE,
    )
    checker = ConsistencyChecker()
    assert checker.check_fact_conflicts(project) == []


def test_marker_based_rule_violation():
    project = _make_project()
    scene = SceneCard(
        scene_id="s1",
        act=ActType.RISE,
        branch_id="root",
        pov_character_id="hero",
        objective="obj",
        conflict="con",
        outcome="out",
        full_text="여기서 RULE_BREAK::마법은 대가를 치른다 위반 발생",
    )
    project.scenes["s1"] = scene

    checker = ConsistencyChecker()
    issues = checker.check_world_rule_violations(project)
    assert len(issues) == 1
    assert "마법은 대가를 치른다" in issues[0].message


def test_no_rule_violation():
    project = _make_project()
    scene = SceneCard(
        scene_id="s1",
        act=ActType.RISE,
        branch_id="root",
        pov_character_id="hero",
        objective="obj",
        conflict="con",
        outcome="out",
        full_text="평화로운 장면입니다.",
    )
    project.scenes["s1"] = scene

    checker = ConsistencyChecker()
    issues = checker.check_world_rule_violations(project)
    assert issues == []


class FakeRuleChecker:
    def __init__(self, violations: dict[str, bool]):
        self._violations = violations

    def check_rule_violation(self, rule: str, scene_text: str) -> RuleCheckResult:
        violated = self._violations.get(rule, False)
        return RuleCheckResult(violated=violated, confidence=0.9, explanation="fake")


def test_llm_rule_checker_integration():
    project = _make_project()
    scene = SceneCard(
        scene_id="s1",
        act=ActType.RISE,
        branch_id="root",
        pov_character_id="hero",
        objective="obj",
        conflict="con",
        outcome="out",
        full_text="주인공이 죽은 사람을 살려냈다.",
    )
    project.scenes["s1"] = scene

    checker = ConsistencyChecker()
    fake = FakeRuleChecker({"죽은 자는 되살릴 수 없다": True})
    issues = checker.check_world_rule_violations(project, rule_checker=fake)
    assert len(issues) == 1
    assert "세계관 규칙 위반 의심" in issues[0].message


def test_target_scene_ids_filter():
    project = _make_project()
    for i in range(3):
        scene = SceneCard(
            scene_id=f"s{i}",
            act=ActType.RISE,
            branch_id="root",
            pov_character_id="hero",
            objective="obj",
            conflict="con",
            outcome="out",
            full_text=f"RULE_BREAK::마법은 대가를 치른다" if i == 1 else "정상 장면",
        )
        project.scenes[f"s{i}"] = scene

    checker = ConsistencyChecker()
    assert checker.check_world_rule_violations(project, target_scene_ids=["s0"]) == []
    assert len(checker.check_world_rule_violations(project, target_scene_ids=["s1"])) == 1


def test_unify_engine_orphaned_hooks():
    project = _make_project()
    s1 = SceneCard(
        scene_id="s1", act=ActType.RISE, branch_id="root",
        pov_character_id="hero", objective="o", conflict="c", outcome="r",
        full_text="장면1", setup_hooks=["hook_A", "hook_B"],
    )
    s2 = SceneCard(
        scene_id="s2", act=ActType.DEVELOPMENT, branch_id="root",
        pov_character_id="hero", objective="o", conflict="c", outcome="r",
        full_text="장면2", payoff_hooks=["hook_A"],
    )
    project.scenes["s1"] = s1
    project.scenes["s2"] = s2
    project.acts[ActType.RISE].append("s1")
    project.acts[ActType.DEVELOPMENT].append("s2")

    engine = UnifyEngine(scene_generator=RuleBasedMockGenerator(), unify_helper=MockUnifyHelper())
    report = engine.analyze(project)
    assert "hook_B" in report.orphaned_hooks
    assert "hook_A" not in report.orphaned_hooks


def test_unify_engine_apply_fixes():
    project = _make_project()
    s1 = SceneCard(
        scene_id="s1", act=ActType.RISE, branch_id="root",
        pov_character_id="hero", objective="o", conflict="c", outcome="r",
        full_text="원본 텍스트",
    )
    project.scenes["s1"] = s1

    from core.models import UnifyProposal, UnifyReport
    proposal = UnifyProposal(
        proposal_id="p1",
        issue_id="test-issue",
        severity="high",
        description="테스트 이슈",
        scene_ids=["s1"],
        proposed_fix="수정된 텍스트",
        fix_type="scene_rewrite",
        auto_fixable=True,
    )
    report = UnifyReport(issues=[], proposals=[proposal])

    engine = UnifyEngine(scene_generator=RuleBasedMockGenerator())
    modified = engine.apply_fixes(project, report)
    assert "s1" in modified
    assert project.scenes["s1"].full_text == "수정된 텍스트"
    assert project.scenes["s1"].user_modified is False


def test_unify_engine_no_issues_on_empty():
    project = _make_project()
    engine = UnifyEngine(scene_generator=RuleBasedMockGenerator(), unify_helper=MockUnifyHelper())
    report = engine.analyze(project)
    assert report.issues == []
    assert report.orphaned_hooks == []
    assert report.chronology_issues == []
