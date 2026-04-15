from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.generation_loop import (
    EndingEvaluator,
    PlotManager,
    StaticBranchOptionGenerator,
    StoryEngine,
)
from core.llm_adapter import RuleBasedMockGenerator
from core.models import (
    ActType,
    BranchNode,
    EndingCondition,
    FactStability,
    SceneCard,
    StoryFact,
    StoryProject,
)


def _make_project(scene_count: int = 0, tension: float = 0.0) -> StoryProject:
    project = StoryProject(
        project_id="test",
        title="테스트",
        genre="판타지",
        tone="진지",
        narrative_viewpoint="3인칭",
        style_preset="간결",
    )
    root = BranchNode(
        branch_id="root",
        parent_branch_id=None,
        label="시작",
        decision_prompt="결정",
        expected_consequence="결과",
    )
    project.branches["root"] = root
    project.acts = {act: [] for act in ActType}
    project.memory.tension_score = tension

    for i in range(scene_count):
        sid = f"scene-{i:04d}"
        scene = SceneCard(
            scene_id=sid,
            act=ActType.RISE,
            branch_id="root",
            pov_character_id="hero",
            objective="obj",
            conflict="con",
            outcome="out",
        )
        project.scenes[sid] = scene
        project.acts[ActType.RISE].append(sid)

    return project


def test_static_option_generator():
    project = _make_project()
    gen = StaticBranchOptionGenerator()
    options = gen.generate_options(project, "root")
    assert len(options) == 3
    assert all(o.branch_id.startswith("root-") for o in options)


def test_plot_manager_basic_thresholds():
    pm = PlotManager()
    assert pm.suggest_next_act(_make_project(0)) == ActType.RISE
    assert pm.suggest_next_act(_make_project(25)) == ActType.DEVELOPMENT
    assert pm.suggest_next_act(_make_project(65)) == ActType.TURN
    assert pm.suggest_next_act(_make_project(95)) == ActType.CONCLUSION


def test_plot_manager_high_tension():
    pm = PlotManager()
    result = pm.suggest_next_act(_make_project(10, tension=0.85))
    assert result == ActType.TURN


def test_ending_evaluator_reachable():
    project = _make_project()
    project.endings["e1"] = EndingCondition(
        ending_id="e1",
        title="해피엔딩",
        required_facts={"hero_alive": "true"},
        minimum_tension_score=0.0,
    )
    project.memory.global_bible["hero_alive"] = StoryFact(
        key="hero_alive",
        value="true",
        source_scene_id="s1",
        stability=FactStability.IMMUTABLE,
    )

    evals = EndingEvaluator().evaluate(project)
    assert len(evals) == 1
    assert evals[0].is_reachable is True
    assert evals[0].missing_facts == []


def test_ending_evaluator_missing_fact():
    project = _make_project()
    project.endings["e1"] = EndingCondition(
        ending_id="e1",
        title="해피엔딩",
        required_facts={"hero_alive": "true"},
    )

    evals = EndingEvaluator().evaluate(project)
    assert evals[0].is_reachable is False
    assert "hero_alive" in evals[0].missing_facts


def test_ending_evaluator_blocking_fact():
    project = _make_project()
    project.endings["e1"] = EndingCondition(
        ending_id="e1",
        title="해피엔딩",
        prohibited_facts={"villain_won": "true"},
    )
    project.memory.global_bible["villain_won"] = StoryFact(
        key="villain_won",
        value="true",
        source_scene_id="s1",
        stability=FactStability.MUTABLE,
    )

    evals = EndingEvaluator().evaluate(project)
    assert evals[0].is_reachable is False
    assert "villain_won" in evals[0].blocking_facts


def test_ending_evaluator_tension_not_met():
    project = _make_project(tension=0.3)
    project.endings["e1"] = EndingCondition(
        ending_id="e1",
        title="클라이맥스",
        minimum_tension_score=0.8,
    )

    evals = EndingEvaluator().evaluate(project)
    assert evals[0].is_reachable is False
    assert evals[0].tension_met is False


def test_story_engine_run_turn():
    project = _make_project()
    project.endings["e1"] = EndingCondition(ending_id="e1", title="기본 결말")
    engine = StoryEngine(
        plot_manager=PlotManager(),
        option_generator=StaticBranchOptionGenerator(),
        scene_generator=RuleBasedMockGenerator(),
    )
    scene = engine.run_turn(project, "root", 0)
    assert scene.scene_id == "scene-0001"
    assert scene.full_text is not None
    assert scene.summary is not None
    assert isinstance(scene.reachable_endings, list)


def test_run_turn_with_target_act():
    """target_act를 지정하면 PlotManager 무시하고 해당 막에 장면이 생성된다."""
    project = _make_project()
    engine = StoryEngine(
        plot_manager=PlotManager(),
        option_generator=StaticBranchOptionGenerator(),
        scene_generator=RuleBasedMockGenerator(),
    )
    scene = engine.run_turn(project, "root", 1, target_act=ActType.CONCLUSION)
    assert scene.act == ActType.CONCLUSION
    assert scene.scene_id in project.acts[ActType.CONCLUSION]
    assert scene.order_index == 0


def test_run_turn_order_index_increments():
    """같은 막에 여러 장면 생성 시 order_index가 증가한다."""
    project = _make_project()
    engine = StoryEngine(
        plot_manager=PlotManager(),
        option_generator=StaticBranchOptionGenerator(),
        scene_generator=RuleBasedMockGenerator(),
    )
    s1 = engine.run_turn(project, "root", 0, target_act=ActType.RISE)
    s2 = engine.run_turn(project, s1.branch_id, 0, target_act=ActType.RISE)
    assert s1.order_index == 0
    assert s2.order_index == 1
