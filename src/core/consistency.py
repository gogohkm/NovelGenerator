from __future__ import annotations

from typing import Dict, List, Optional, Set

from .generation_loop import SceneGenerator, WorldRuleChecker
from .models import (
    ActType,
    ConsistencyIssue,
    FactStability,
    RewriteImpact,
    SceneCard,
    StoryFact,
    StoryProject,
    UnifyProposal,
    UnifyReport,
)


ACT_ORDER = [ActType.RISE, ActType.DEVELOPMENT, ActType.TURN, ActType.CONCLUSION]


class ConsistencyChecker:
    def check_fact_conflicts(self, project: StoryProject) -> List[ConsistencyIssue]:
        issues: List[ConsistencyIssue] = []
        facts_by_key: Dict[str, List[str]] = {}

        for key, fact in project.memory.global_bible.items():
            facts_by_key.setdefault(key, []).append(fact.value)

        for key, values in facts_by_key.items():
            unique_values = set(values)
            if len(unique_values) > 1:
                issues.append(
                    ConsistencyIssue(
                        issue_id=f"fact-conflict-{key}",
                        severity="high",
                        fact_key=key,
                        message=f"같은 사실 키에 서로 다른 값이 존재합니다: {sorted(unique_values)}",
                    )
                )

        return issues

    def check_world_rule_violations(
        self,
        project: StoryProject,
        rule_checker: Optional[WorldRuleChecker] = None,
        target_scene_ids: Optional[List[str]] = None,
    ) -> List[ConsistencyIssue]:
        issues: List[ConsistencyIssue] = []

        if target_scene_ids is not None:
            scenes_to_check = {
                sid: project.scenes[sid]
                for sid in target_scene_ids
                if sid in project.scenes
            }
        else:
            scenes_to_check = dict(project.scenes)

        text_by_scene = {
            scene_id: (scene.full_text or "") + " " + (scene.summary or "")
            for scene_id, scene in scenes_to_check.items()
        }

        marker_flagged: Set[str] = set()

        for rule in project.world_rules:
            if not rule.strip():
                continue
            for scene_id, text in text_by_scene.items():
                if f"RULE_BREAK::{rule}" in text:
                    marker_flagged.add(scene_id)
                    issues.append(
                        ConsistencyIssue(
                            issue_id=f"rule-break-{scene_id}",
                            severity="high",
                            fact_key="world_rule",
                            message=f"세계관 규칙 위반 감지: {rule}",
                            related_scene_ids=[scene_id],
                        )
                    )

        if rule_checker is not None:
            for rule in project.world_rules:
                if not rule.strip():
                    continue
                for scene_id, text in text_by_scene.items():
                    if scene_id in marker_flagged:
                        continue
                    if not text.strip():
                        continue

                    result = rule_checker.check_rule_violation(rule, text)
                    if result.violated and result.confidence >= 0.6:
                        issues.append(
                            ConsistencyIssue(
                                issue_id=f"llm-rule-violation-{scene_id}-{hash(rule) % 10000}",
                                severity="medium" if result.confidence < 0.8 else "high",
                                fact_key="world_rule",
                                message=f"세계관 규칙 위반 의심 (신뢰도 {result.confidence:.0%}): {rule} — {result.explanation}",
                                related_scene_ids=[scene_id],
                            )
                        )

        return issues


class RewriteImpactAnalyzer:
    def analyze(self, project: StoryProject, changed_branch_id: str) -> RewriteImpact:
        direct = list(project.branches[changed_branch_id].scene_ids)
        transitive: Set[str] = set()

        descendant_branches = self._find_descendant_branches(project, changed_branch_id)
        for branch_id in descendant_branches:
            for scene_id in project.branches[branch_id].scene_ids:
                if scene_id not in direct:
                    transitive.add(scene_id)

        priorities = self._build_priority_map(project, direct, list(transitive))
        return RewriteImpact(
            changed_branch_id=changed_branch_id,
            directly_impacted_scene_ids=direct,
            transitively_impacted_scene_ids=sorted(list(transitive)),
            rewrite_priority=priorities,
        )

    def _find_descendant_branches(self, project: StoryProject, parent_branch_id: str) -> List[str]:
        descendants: List[str] = []
        queue = [parent_branch_id]
        while queue:
            current = queue.pop(0)
            for branch_id, branch in project.branches.items():
                if branch.parent_branch_id == current:
                    descendants.append(branch_id)
                    queue.append(branch_id)
        return descendants

    def _build_priority_map(self, project: StoryProject, direct: List[str], transitive: List[str]) -> Dict[str, int]:
        priority: Dict[str, int] = {}
        for scene_id in direct:
            priority[scene_id] = 1

        for scene_id in transitive:
            scene = project.scenes.get(scene_id)
            if scene is None:
                continue
            priority[scene_id] = 2 if scene.act.value in {"gi", "seung"} else 3

        return priority


def update_fact(project: StoryProject, key: str, value: str, scene: SceneCard, stability: FactStability) -> None:
    existing = project.memory.global_bible.get(key)
    if existing and existing.stability == FactStability.IMMUTABLE and existing.value != value:
        raise ValueError(f"Immutable fact conflict: {key}")

    project.memory.global_bible[key] = StoryFact(
        key=key,
        value=value,
        source_scene_id=scene.scene_id,
        stability=stability,
    )


class UnifyEngine:
    """전체 통일화 엔진: 분석 → 수정 제안 → 적용."""

    def __init__(
        self,
        scene_generator: Optional[SceneGenerator] = None,
        rule_checker: Optional[WorldRuleChecker] = None,
        unify_helper=None,
    ):
        self.checker = ConsistencyChecker()
        self.scene_generator = scene_generator
        self.rule_checker = rule_checker
        self.unify_helper = unify_helper

    def analyze(self, project: StoryProject) -> UnifyReport:
        issues: List[ConsistencyIssue] = []

        # 1. 사실 충돌
        issues.extend(self.checker.check_fact_conflicts(project))

        # 2. 세계관 규칙 위반
        issues.extend(self.checker.check_world_rule_violations(project, rule_checker=self.rule_checker))

        # 3. 고아 훅
        orphaned = self._check_orphaned_hooks(project)

        # 4. 시간순 검사
        chronology = self._check_chronology(project)

        return UnifyReport(
            issues=issues,
            proposals=[],
            orphaned_hooks=orphaned,
            chronology_issues=chronology,
        )

    def propose_fixes(self, project: StoryProject, report: UnifyReport) -> UnifyReport:
        proposals: List[UnifyProposal] = []
        counter = 0

        for issue in report.issues:
            counter += 1
            proposal = self._propose_for_issue(project, issue, counter)
            if proposal:
                proposals.append(proposal)

        for hook in report.orphaned_hooks:
            counter += 1
            proposals.append(UnifyProposal(
                proposal_id=f"proposal-{counter:04d}",
                issue_id=f"orphan-hook-{hash(hook) % 10000}",
                severity="medium",
                description=f"setup_hook '{hook}'에 대응하는 payoff_hook이 없습니다",
                scene_ids=[],
                proposed_fix=f"payoff 장면에 '{hook}' 훅 추가 필요",
                fix_type="hook_resolution",
                auto_fixable=False,
            ))

        for chrono_desc in report.chronology_issues:
            counter += 1
            proposals.append(UnifyProposal(
                proposal_id=f"proposal-{counter:04d}",
                issue_id=f"chrono-{counter}",
                severity="medium",
                description=chrono_desc,
                scene_ids=[],
                proposed_fix="시간순 참조를 수정해야 합니다",
                fix_type="chronology_fix",
                auto_fixable=False,
            ))

        report.proposals = proposals
        return report

    def apply_fixes(self, project: StoryProject, report: UnifyReport) -> List[str]:
        modified_scene_ids: List[str] = []

        for proposal in report.proposals:
            if proposal.user_choice == "reject":
                continue
            accepted = proposal.user_choice == "accept" or (proposal.auto_fixable and proposal.user_choice is None)
            if not accepted:
                continue

            if proposal.fix_type == "scene_rewrite":
                for sid in proposal.scene_ids:
                    scene = project.scenes.get(sid)
                    if not scene:
                        continue
                    scene.full_text = proposal.proposed_fix
                    if self.scene_generator:
                        scene.summary = self.scene_generator.summarize_scene(scene.full_text)
                    scene.user_modified = False
                    modified_scene_ids.append(sid)

            elif proposal.fix_type == "fact_correction":
                for sid in proposal.scene_ids:
                    scene = project.scenes.get(sid)
                    if not scene:
                        continue
                    fact_key = proposal.issue_id.replace("fact-conflict-", "")
                    fact = project.memory.global_bible.get(fact_key)
                    if fact and fact.stability != FactStability.IMMUTABLE:
                        project.memory.global_bible[fact_key] = StoryFact(
                            key=fact_key,
                            value=proposal.proposed_fix,
                            source_scene_id=sid,
                            stability=fact.stability,
                        )
                    modified_scene_ids.append(sid)

        return modified_scene_ids

    def _propose_for_issue(self, project: StoryProject, issue: ConsistencyIssue, counter: int) -> Optional[UnifyProposal]:
        if issue.fact_key != "world_rule" and issue.issue_id.startswith("fact-conflict-"):
            # 사실 충돌: 최신 장면의 값을 우선
            return UnifyProposal(
                proposal_id=f"proposal-{counter:04d}",
                issue_id=issue.issue_id,
                severity=issue.severity,
                description=issue.message,
                scene_ids=issue.related_scene_ids,
                proposed_fix=self._latest_fact_value(project, issue.fact_key),
                fix_type="fact_correction",
                auto_fixable=True,
            )

        if issue.related_scene_ids and self.unify_helper:
            # 세계관 위반 등: LLM 기반 장면 재작성 제안
            sid = issue.related_scene_ids[0]
            scene = project.scenes.get(sid)
            if scene:
                rewritten = self.unify_helper.propose_scene_rewrite(project, scene, issue.message)
                return UnifyProposal(
                    proposal_id=f"proposal-{counter:04d}",
                    issue_id=issue.issue_id,
                    severity=issue.severity,
                    description=issue.message,
                    scene_ids=issue.related_scene_ids,
                    proposed_fix=rewritten,
                    fix_type="scene_rewrite",
                    auto_fixable=False,
                )

        return None

    def _latest_fact_value(self, project: StoryProject, fact_key: str) -> str:
        fact = project.memory.global_bible.get(fact_key)
        return fact.value if fact else ""

    def _check_orphaned_hooks(self, project: StoryProject) -> List[str]:
        all_setups: Set[str] = set()
        all_payoffs: Set[str] = set()
        for scene in project.scenes.values():
            all_setups.update(scene.setup_hooks)
            all_payoffs.update(scene.payoff_hooks)
        return sorted(all_setups - all_payoffs)

    def _check_chronology(self, project: StoryProject) -> List[str]:
        issues: List[str] = []

        scenes_by_act: Dict[ActType, List[SceneCard]] = {act: [] for act in ACT_ORDER}
        for scene in project.scenes.values():
            if scene.act in scenes_by_act:
                scenes_by_act[scene.act].append(scene)

        for i, act in enumerate(ACT_ORDER):
            later_acts = ACT_ORDER[i + 1:]
            if not later_acts:
                continue

            later_summaries: List[str] = []
            for later_act in later_acts:
                for s in scenes_by_act[later_act]:
                    if s.summary:
                        later_summaries.append(s.summary)

            if not later_summaries:
                continue

            later_text = "\n".join(later_summaries)

            if self.unify_helper:
                for scene in scenes_by_act[act]:
                    if not scene.full_text:
                        continue
                    result = self.unify_helper.check_chronology(scene.full_text, later_text)
                    if result.violated and result.confidence >= 0.6:
                        issues.append(
                            f"장면 {scene.scene_id} (막: {act.value})이 이후 막의 사건을 참조: {result.explanation}"
                        )

        return issues
