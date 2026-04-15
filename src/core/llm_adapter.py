from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import List, Optional

import urllib.request

from .generation_loop import (
    BranchOption,
    RuleCheckResult,
    SceneGenerator,
    StaticBranchOptionGenerator,
)
from .models import ActType, ConsistencyIssue, SceneCard, StoryProject


class RuleBasedMockGenerator(SceneGenerator):
    """
    LLM 연동 전까지 사용 가능한 기본 생성기.
    실제 AI 모델 어댑터는 동일 인터페이스를 구현하면 된다.
    """

    def generate_scene_text(self, project: StoryProject, scene: SceneCard) -> str:
        return (
            f"[{project.title}] {scene.scene_id}\n"
            f"목표: {scene.objective}\n"
            f"갈등: {scene.conflict}\n"
            f"결과: {scene.outcome}\n"
            "주인공은 선택의 결과를 받아들이며 다음 분기를 맞이한다."
        )

    def summarize_scene(self, scene_text: str) -> str:
        lines = [line.strip() for line in scene_text.splitlines() if line.strip()]
        return " / ".join(lines[:3])


class MockWorldRuleChecker:
    """오프라인/테스트용 — 항상 위반 없음."""

    def check_rule_violation(self, rule: str, scene_text: str) -> RuleCheckResult:
        return RuleCheckResult(violated=False, confidence=1.0, explanation="mock: no violation")


@dataclass
class LMStudioConfig:
    base_url: str = "http://127.0.0.1:1234/v1"
    model: str = "local-model"
    api_key: Optional[str] = None
    timeout_s: float = 120.0


class LMStudioClient:
    """LM Studio OpenAI-compatible API 호출을 위한 공유 클라이언트."""

    def __init__(self, config: LMStudioConfig):
        self.config = config

    def chat_completion(self, system: str, user: str, temperature: float = 0.8) -> str:
        url = f"{self.config.base_url}/chat/completions"
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.config.api_key:
            req.add_header("Authorization", f"Bearer {self.config.api_key}")

        with urllib.request.urlopen(req, timeout=self.config.timeout_s) as resp:
            raw = resp.read().decode("utf-8")
        parsed = json.loads(raw)
        return parsed["choices"][0]["message"]["content"]


class LMStudioOpenAICompatibleGenerator(SceneGenerator):
    def __init__(self, config_or_client: LMStudioConfig | LMStudioClient):
        if isinstance(config_or_client, LMStudioClient):
            self.client = config_or_client
        else:
            self.client = LMStudioClient(config_or_client)

    @property
    def config(self) -> LMStudioConfig:
        return self.client.config

    def generate_scene_text(self, project: StoryProject, scene: SceneCard) -> str:
        system = (
            "당신은 장편 소설을 분기형으로 집필하는 작가 AI다. "
            "주어진 프로젝트 설정(장르/톤/시점/세계관)을 위반하지 말고, "
            "장면 카드의 목표/갈등/결과를 충실히 반영해 한국어로 장면을 작성하라. "
            "반드시 이전 장면의 내용과 자연스럽게 이어지도록 하고, "
            "확정된 사실(스토리 바이블)과 모순되지 않게 작성하라."
        )
        user = self._build_scene_prompt(project, scene)
        return self.client.chat_completion(system=system, user=user)

    def _build_scene_prompt(self, project: StoryProject, scene: SceneCard) -> str:
        mem = project.memory
        parts: list[str] = []

        # 1) 프로젝트 기본 설정
        parts.append(
            f"프로젝트 제목: {project.title}\n"
            f"장르: {project.genre}\n"
            f"톤: {project.tone}\n"
            f"시점: {project.narrative_viewpoint}\n"
            f"문체 프리셋: {project.style_preset}\n"
            f"세계관 규칙:\n- " + "\n- ".join(project.world_rules)
        )

        # 2) 확정된 사실 (스토리 바이블) — 최대 20개
        if mem.global_bible:
            bible_lines = []
            for key, fact in list(mem.global_bible.items())[-20:]:
                bible_lines.append(f"  - {fact.key}: {fact.value} [{fact.stability.value}]")
            parts.append("\n[확정된 사실(스토리 바이블)]\n" + "\n".join(bible_lines))

        # 3) 캐릭터 상태
        if mem.character_states:
            char_lines = []
            for cid, cs in mem.character_states.items():
                char_lines.append(
                    f"  - {cid}: 신체={cs.physical_status}, 심리={cs.mental_status}, "
                    f"목표={', '.join(cs.goals) or '없음'}"
                )
            parts.append("\n[등장인물 현재 상태]\n" + "\n".join(char_lines))

        # 4) 막별 요약 — 전체 흐름 파악용
        act_labels = {
            ActType.RISE: "기(起)", ActType.DEVELOPMENT: "승(承)",
            ActType.TURN: "전(轉)", ActType.CONCLUSION: "결(結)",
        }
        if mem.act_summaries:
            summary_lines = []
            for act_type in [ActType.RISE, ActType.DEVELOPMENT, ActType.TURN, ActType.CONCLUSION]:
                s = mem.act_summaries.get(act_type)
                if s:
                    summary_lines.append(f"  - {act_labels[act_type]}: {s}")
            if summary_lines:
                parts.append("\n[막별 누적 요약]\n" + "\n".join(summary_lines))

        # 5) 같은 막의 기존 장면 요약 — 막 내 흐름 연속성
        same_act_ids = project.acts.get(scene.act, [])
        if same_act_ids:
            same_act_lines = []
            for sid in same_act_ids[-5:]:  # 최근 5개
                s = project.scenes.get(sid)
                if s and s.summary:
                    same_act_lines.append(f"  - {sid}: {s.summary}")
            if same_act_lines:
                parts.append(
                    f"\n[현재 막({act_labels.get(scene.act, scene.act.value)}) 기존 장면 요약]\n"
                    + "\n".join(same_act_lines)
                )

        # 6) 최근 장면 본문/요약 — 직전 장면과의 직접 연결
        recent_ids = mem.recent_scene_window[-3:]
        if recent_ids:
            recent_parts = []
            for sid in recent_ids:
                s = project.scenes.get(sid)
                if not s:
                    continue
                # 가장 마지막 장면은 본문 일부 포함, 나머지는 요약만
                if sid == recent_ids[-1] and s.full_text:
                    text_snippet = s.full_text[-800:]  # 마지막 800자
                    recent_parts.append(
                        f"  [{sid} (막: {act_labels.get(s.act, s.act.value)}) — 직전 장면 본문 끝부분]\n"
                        f"  ...{text_snippet}"
                    )
                elif s.summary:
                    recent_parts.append(f"  - {sid} ({act_labels.get(s.act, s.act.value)}): {s.summary}")
            if recent_parts:
                parts.append("\n[최근 장면 흐름 (시간순)]\n" + "\n".join(recent_parts))

        # 7) 이후 막에 이미 작성된 장면이 있으면 힌트 제공 (비선형 집필 대응)
        act_order = [ActType.RISE, ActType.DEVELOPMENT, ActType.TURN, ActType.CONCLUSION]
        current_act_idx = act_order.index(scene.act) if scene.act in act_order else -1
        if current_act_idx >= 0:
            later_hints = []
            for later_act in act_order[current_act_idx + 1:]:
                for sid in project.acts.get(later_act, [])[:3]:
                    s = project.scenes.get(sid)
                    if s and s.summary:
                        later_hints.append(f"  - {sid} ({act_labels[later_act]}): {s.summary}")
            if later_hints:
                parts.append(
                    "\n[이후 막에 이미 작성된 장면 (복선/연결 고려)]\n"
                    + "\n".join(later_hints)
                )

        # 8) 현재 장면 카드
        parts.append(
            f"\n[작성할 장면]\n"
            f"장면ID: {scene.scene_id}\n"
            f"막: {act_labels.get(scene.act, scene.act.value)}\n"
            f"분기: {scene.branch_id}\n"
            f"POV: {scene.pov_character_id}\n"
            f"목표: {scene.objective}\n"
            f"갈등: {scene.conflict}\n"
            f"결과(유도): {scene.outcome}"
        )

        # 9) 요구사항
        parts.append(
            "\n[요구사항]\n"
            "- 900~1400자 내외\n"
            "- 이전 장면의 결말과 자연스럽게 연결될 것\n"
            "- 이후 장면(이미 작성된 경우)으로 이어질 복선을 포함할 것\n"
            "- 확정된 사실(스토리 바이블)과 모순되지 않을 것\n"
            "- 다음 장면으로 이어질 떡밥 1개 포함\n"
            "- 세계관 규칙을 위반하지 않을 것"
        )

        return "\n".join(parts)

    def summarize_scene(self, scene_text: str) -> str:
        system = "당신은 편집자다. 장면을 2~3문장으로 요약하라."
        user = f"장면 원문:\n{scene_text}\n\n요약:"
        return self.client.chat_completion(system=system, user=user).strip()


class LLMBranchOptionGenerator:
    """LLM을 활용해 스토리 컨텍스트에 맞는 분기 선택지를 동적 생성한다."""

    def __init__(self, client: LMStudioClient, fallback: Optional[StaticBranchOptionGenerator] = None):
        self.client = client
        self._fallback = fallback or StaticBranchOptionGenerator()

    def generate_options(self, project: StoryProject, current_branch_id: str) -> List[BranchOption]:
        try:
            return self._generate_via_llm(project, current_branch_id)
        except Exception:
            return self._fallback.generate_options(project, current_branch_id)

    def _generate_via_llm(self, project: StoryProject, current_branch_id: str) -> List[BranchOption]:
        base = project.branches[current_branch_id]

        recent_summaries = ""
        for sid in project.memory.recent_scene_window[-3:]:
            scene = project.scenes.get(sid)
            if scene and scene.summary:
                recent_summaries += f"- {sid}: {scene.summary}\n"

        system = (
            "당신은 분기형 소설의 플롯 설계자다. "
            "현재 스토리 상태를 분석해 3개의 분기 선택지를 제안하라. "
            "반드시 아래 JSON 배열 형식으로만 응답하라 (설명 텍스트 없이 JSON만):\n"
            '[{"label":"...", "rationale":"...", "risk":"...", "expected_ending_direction":"..."}]'
        )
        user = (
            f"프로젝트: {project.title} ({project.genre}, {project.tone})\n"
            f"세계관 규칙: {', '.join(project.world_rules)}\n"
            f"현재 분기: {base.label}\n"
            f"분기 결정 상황: {base.decision_prompt}\n"
            f"긴장도: {project.memory.tension_score}\n"
            f"최근 장면 요약:\n{recent_summaries or '(없음)'}\n"
            f"장면 수: {len(project.scenes)}\n\n"
            "위 맥락을 반영해 3개의 선택지를 JSON으로 제시하라."
        )

        raw = self.client.chat_completion(system=system, user=user, temperature=0.9)

        json_match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not json_match:
            raise ValueError("LLM 응답에서 JSON 배열을 찾을 수 없음")

        items = json.loads(json_match.group())
        if not isinstance(items, list) or len(items) < 1:
            raise ValueError("유효한 선택지 배열이 아님")

        options: List[BranchOption] = []
        for i, item in enumerate(items[:3]):
            suffix = chr(ord("A") + i)
            options.append(BranchOption(
                branch_id=f"{current_branch_id}-{suffix}",
                label=item.get("label", f"선택지 {suffix}"),
                rationale=item.get("rationale", ""),
                risk=item.get("risk", ""),
                expected_ending_direction=item.get("expected_ending_direction", ""),
            ))
        return options


class LLMWorldRuleChecker:
    """LLM을 활용해 세계관 규칙 위반을 시맨틱하게 검사한다."""

    def __init__(self, client: LMStudioClient):
        self.client = client

    def check_rule_violation(self, rule: str, scene_text: str) -> RuleCheckResult:
        try:
            return self._check_via_llm(rule, scene_text)
        except Exception:
            return RuleCheckResult(violated=False, confidence=0.0, explanation="LLM 검사 실패")

    def _check_via_llm(self, rule: str, scene_text: str) -> RuleCheckResult:
        system = (
            "당신은 소설 편집자다. 세계관 규칙 위반 여부를 판정하라. "
            '반드시 아래 JSON 형식으로만 응답하라:\n'
            '{"violated": true/false, "confidence": 0.0~1.0, "explanation": "..."}'
        )
        user = (
            f"세계관 규칙: {rule}\n\n"
            f"장면 텍스트:\n{scene_text[:2000]}\n\n"
            "이 장면이 위 규칙을 위반하는가?"
        )

        raw = self.client.chat_completion(system=system, user=user, temperature=0.2)

        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not json_match:
            raise ValueError("JSON을 찾을 수 없음")

        data = json.loads(json_match.group())
        return RuleCheckResult(
            violated=bool(data.get("violated", False)),
            confidence=float(data.get("confidence", 0.0)),
            explanation=str(data.get("explanation", "")),
        )


class MockUnifyHelper:
    """오프라인/테스트용 — 원본 텍스트 그대로 반환."""

    def propose_scene_rewrite(self, project: StoryProject, scene: SceneCard, issue_description: str) -> str:
        return scene.full_text or ""

    def check_chronology(self, scene_text: str, later_events: str) -> RuleCheckResult:
        return RuleCheckResult(violated=False, confidence=1.0, explanation="mock: no chronology issue")


class LLMUnifyHelper:
    """LLM을 활용해 통일화 수정 제안을 생성한다."""

    def __init__(self, client: LMStudioClient):
        self.client = client

    def propose_scene_rewrite(self, project: StoryProject, scene: SceneCard, issue_description: str) -> str:
        system = (
            "당신은 소설 편집자다. 아래 이슈를 해결하기 위해 장면을 최소한으로 수정하라. "
            "프로젝트의 장르/톤/시점/세계관을 유지하면서 문제 부분만 고쳐라. "
            "수정된 전체 장면 텍스트만 반환하라 (설명 없이 본문만)."
        )
        user = (
            f"프로젝트: {project.title} ({project.genre}, {project.tone})\n"
            f"세계관 규칙: {', '.join(project.world_rules)}\n\n"
            f"문제점: {issue_description}\n\n"
            f"원본 장면 ({scene.scene_id}, 막: {scene.act.value}):\n"
            f"{(scene.full_text or '')[:3000]}\n\n"
            "위 문제를 해결한 수정 본문:"
        )
        try:
            return self.client.chat_completion(system=system, user=user, temperature=0.3)
        except Exception:
            return scene.full_text or ""

    def check_chronology(self, scene_text: str, later_events: str) -> RuleCheckResult:
        system = (
            "당신은 소설 편집자다. 이 장면이 아직 일어나지 않은 미래 사건을 참조하는지 판정하라. "
            '반드시 아래 JSON 형식으로만 응답하라:\n'
            '{"violated": true/false, "confidence": 0.0~1.0, "explanation": "..."}'
        )
        user = (
            f"장면 텍스트:\n{scene_text[:2000]}\n\n"
            f"이 장면보다 나중에 일어나는 사건들:\n{later_events[:2000]}\n\n"
            "이 장면이 위 미래 사건을 미리 참조하고 있는가?"
        )
        try:
            raw = self.client.chat_completion(system=system, user=user, temperature=0.2)
            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not json_match:
                return RuleCheckResult(violated=False, confidence=0.0, explanation="JSON 파싱 실패")
            data = json.loads(json_match.group())
            return RuleCheckResult(
                violated=bool(data.get("violated", False)),
                confidence=float(data.get("confidence", 0.0)),
                explanation=str(data.get("explanation", "")),
            )
        except Exception:
            return RuleCheckResult(violated=False, confidence=0.0, explanation="LLM 시간순 검사 실패")
