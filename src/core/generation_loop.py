from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Protocol

from .models import (
    ActType,
    BranchNode,
    EndingCondition,
    FactStability,
    SceneCard,
    StoryFact,
    StoryProject,
)


@dataclass
class BranchOption:
    branch_id: str
    label: str
    rationale: str
    risk: str
    expected_ending_direction: str


@dataclass
class RuleCheckResult:
    violated: bool
    confidence: float
    explanation: str


@dataclass
class EndingEvaluation:
    ending_id: str
    title: str
    is_reachable: bool
    missing_facts: List[str] = field(default_factory=list)
    blocking_facts: List[str] = field(default_factory=list)
    tension_met: bool = True


class SceneGenerator(Protocol):
    def generate_scene_text(self, project: StoryProject, scene: SceneCard) -> str:
        ...

    def summarize_scene(self, scene_text: str) -> str:
        ...


class BranchOptionGeneratorProtocol(Protocol):
    def generate_options(self, project: StoryProject, current_branch_id: str) -> List[BranchOption]:
        ...


class WorldRuleChecker(Protocol):
    def check_rule_violation(self, rule: str, scene_text: str) -> RuleCheckResult:
        ...


class EndingEvaluator:
    def evaluate(self, project: StoryProject) -> List[EndingEvaluation]:
        results: List[EndingEvaluation] = []
        bible = project.memory.global_bible
        tension = project.memory.tension_score

        for ending in project.endings.values():
            missing: List[str] = []
            for key, expected in ending.required_facts.items():
                fact = bible.get(key)
                if fact is None or fact.value != expected:
                    missing.append(key)

            blocking: List[str] = []
            for key, prohibited in ending.prohibited_facts.items():
                fact = bible.get(key)
                if fact is not None and fact.value == prohibited:
                    blocking.append(key)

            tension_met = tension >= ending.minimum_tension_score
            is_reachable = len(missing) == 0 and len(blocking) == 0 and tension_met

            results.append(EndingEvaluation(
                ending_id=ending.ending_id,
                title=ending.title,
                is_reachable=is_reachable,
                missing_facts=missing,
                blocking_facts=blocking,
                tension_met=tension_met,
            ))

        return results


class PlotManager:
    def suggest_next_act(self, project: StoryProject) -> ActType:
        scene_count = len(project.scenes)
        tension = project.memory.tension_score

        gi = len(project.acts.get(ActType.RISE, []))
        seung = len(project.acts.get(ActType.DEVELOPMENT, []))
        jeon = len(project.acts.get(ActType.TURN, []))
        gyeol = len(project.acts.get(ActType.CONCLUSION, []))

        reachable = EndingEvaluator().evaluate(project)
        any_reachable = any(e.is_reachable for e in reachable)

        if any_reachable and scene_count >= 10:
            return ActType.CONCLUSION

        if tension >= 0.8 and scene_count >= 5:
            return ActType.TURN

        total = gi + seung + jeon + gyeol or 1
        gi_ratio = gi / total
        seung_ratio = seung / total

        if gi_ratio < 0.2 and scene_count < 30:
            return ActType.RISE
        if seung_ratio < 0.35 and scene_count < 60:
            return ActType.DEVELOPMENT
        if tension >= 0.5:
            return ActType.TURN

        if scene_count < 20:
            return ActType.RISE
        if scene_count < 60:
            return ActType.DEVELOPMENT
        if scene_count < 90:
            return ActType.TURN
        return ActType.CONCLUSION


class StaticBranchOptionGenerator:
    def generate_options(self, project: StoryProject, current_branch_id: str) -> List[BranchOption]:
        base = project.branches[current_branch_id]
        return [
            BranchOption(
                branch_id=f"{current_branch_id}-A",
                label=f"{base.label}: 정면 돌파",
                rationale="즉시 갈등을 확대해 몰입감을 올림",
                risk="주요 인물의 손실 가능성 증가",
                expected_ending_direction="비극/성장형 결말",
            ),
            BranchOption(
                branch_id=f"{current_branch_id}-B",
                label=f"{base.label}: 우회 전략",
                rationale="정보를 확보하며 긴장감을 유지",
                risk="중반 템포 저하 가능성",
                expected_ending_direction="추리/반전형 결말",
            ),
            BranchOption(
                branch_id=f"{current_branch_id}-C",
                label=f"{base.label}: 동맹 요청",
                rationale="관계도 변화를 이용해 장기 갈등 설계",
                risk="새 인물 증가로 관리 복잡도 상승",
                expected_ending_direction="연대/회복형 결말",
            ),
        ]


# backward-compatible alias
BranchOptionGenerator = StaticBranchOptionGenerator


class StoryEngine:
    def __init__(
        self,
        plot_manager: PlotManager,
        option_generator: BranchOptionGeneratorProtocol,
        scene_generator: SceneGenerator,
    ):
        self.plot_manager = plot_manager
        self.option_generator = option_generator
        self.scene_generator = scene_generator
        self._ending_evaluator = EndingEvaluator()

    def run_turn(
        self,
        project: StoryProject,
        current_branch_id: str,
        selected_option_index: int,
        target_act: Optional[ActType] = None,
    ) -> SceneCard:
        options = self.option_generator.generate_options(project, current_branch_id)
        selected = options[selected_option_index]

        if selected.branch_id not in project.branches:
            project.branches[selected.branch_id] = BranchNode(
                branch_id=selected.branch_id,
                parent_branch_id=current_branch_id,
                label=selected.label,
                decision_prompt=selected.rationale,
                expected_consequence=selected.risk,
            )

        act = target_act if target_act is not None else self.plot_manager.suggest_next_act(project)
        scene_id = f"scene-{len(project.scenes) + 1:04d}"
        order_index = len(project.acts.get(act, []))
        scene_card = SceneCard(
            scene_id=scene_id,
            act=act,
            branch_id=selected.branch_id,
            pov_character_id="protagonist",
            objective=selected.rationale,
            conflict=selected.risk,
            outcome=f"결말 방향 힌트: {selected.expected_ending_direction}",
            order_index=order_index,
        )

        scene_text = self.scene_generator.generate_scene_text(project, scene_card)
        scene_card.full_text = scene_text
        scene_card.summary = self.scene_generator.summarize_scene(scene_text)

        project.scenes[scene_id] = scene_card
        project.branches[selected.branch_id].scene_ids.append(scene_id)
        project.acts.setdefault(act, []).append(scene_id)
        project.memory.add_scene_to_window(scene_id)
        project.memory.act_summaries[act] = scene_card.summary
        project.memory.global_bible[f"{scene_id}:outcome"] = StoryFact(
            key=f"{scene_id}:outcome",
            value=scene_card.outcome,
            source_scene_id=scene_id,
            stability=FactStability.SEMI_MUTABLE,
        )

        evaluations = self._ending_evaluator.evaluate(project)
        scene_card.reachable_endings = [e.ending_id for e in evaluations if e.is_reachable]

        return scene_card
