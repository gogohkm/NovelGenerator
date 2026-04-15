from __future__ import annotations

from core.consistency import ConsistencyChecker, RewriteImpactAnalyzer, UnifyEngine
from core.generation_loop import EndingEvaluator, PlotManager, StaticBranchOptionGenerator, StoryEngine
from core.llm_adapter import MockUnifyHelper, RuleBasedMockGenerator
from core.models import ActType, BranchNode, EndingCondition, StoryProject


def build_sample_project() -> StoryProject:
    project = StoryProject(
        project_id="novel-001",
        title="분기 도시의 연대기",
        genre="SF 미스터리",
        tone="긴장감 있는 서정",
        narrative_viewpoint="3인칭 제한 시점",
        style_preset="리듬감 있는 문장",
        world_rules=[
            "시간 역행은 불가능하다",
            "중앙 AI는 물리적 실체를 가질 수 없다",
        ],
    )

    root_branch = BranchNode(
        branch_id="root",
        parent_branch_id=None,
        label="초기 사건",
        decision_prompt="정전 사건의 원인을 먼저 추적할지 결정",
        expected_consequence="정보 확보 vs 즉시 충돌",
    )
    project.branches[root_branch.branch_id] = root_branch
    project.acts = {act: [] for act in ActType}

    project.endings["ending-hope"] = EndingCondition(
        ending_id="ending-hope",
        title="연대의 복구",
        required_facts={"alliance_formed": "true"},
        theme_alignment_hint="협력과 책임",
    )
    return project


def run_demo() -> None:
    project = build_sample_project()
    engine = StoryEngine(
        plot_manager=PlotManager(),
        option_generator=StaticBranchOptionGenerator(),
        scene_generator=RuleBasedMockGenerator(),
    )

    # 기(起)에 장면 생성
    scene_gi = engine.run_turn(project, current_branch_id="root", selected_option_index=0, target_act=ActType.RISE)
    print(f"[기] {scene_gi.scene_id}: {scene_gi.full_text}")
    print()

    # 결(結)로 바로 점프해서 장면 생성
    scene_gyeol = engine.run_turn(project, current_branch_id=scene_gi.branch_id, selected_option_index=1, target_act=ActType.CONCLUSION)
    print(f"[결] {scene_gyeol.scene_id}: {scene_gyeol.full_text}")
    print()

    # 정합성 검사
    checker = ConsistencyChecker()
    print("사실 충돌:", checker.check_fact_conflicts(project))

    # 영향 분석
    impact = RewriteImpactAnalyzer().analyze(project, changed_branch_id=scene_gi.branch_id)
    print("영향 분석:", impact)

    # 결말 평가
    evaluator = EndingEvaluator()
    for e in evaluator.evaluate(project):
        status = "도달 가능" if e.is_reachable else "미도달"
        print(f"결말 [{e.title}]: {status} (미충족: {e.missing_facts}, 차단: {e.blocking_facts})")

    # 전체 통일화 (Mock)
    print()
    unify = UnifyEngine(scene_generator=RuleBasedMockGenerator(), unify_helper=MockUnifyHelper())
    report = unify.analyze(project)
    report = unify.propose_fixes(project, report)
    print(f"통일화 결과: 이슈 {len(report.issues)}건, 제안 {len(report.proposals)}건, "
          f"고아 훅 {len(report.orphaned_hooks)}건, 시간순 문제 {len(report.chronology_issues)}건")


if __name__ == "__main__":
    run_demo()
