from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict

from .models import (
    ActType,
    BranchNode,
    CharacterState,
    CharacterProfile,
    EndingCondition,
    FactStability,
    SceneCard,
    StoryFact,
    StoryProject,
    StoryStateMemory,
)


def save_project(project: StoryProject, path: str) -> None:
    payload = _project_to_dict(project)
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_project(path: str) -> StoryProject:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return _project_from_dict(data)


def _project_to_dict(project: StoryProject) -> Dict[str, Any]:
    return {
        "project": asdict(project),
        "enums": {
            "ActType": {k: v.value for k, v in ActType.__members__.items()},
            "FactStability": {k: v.value for k, v in FactStability.__members__.items()},
        },
    }


def _project_from_dict(data: Dict[str, Any]) -> StoryProject:
    raw = data["project"]

    memory_raw = raw.get("memory", {})
    global_bible_raw = memory_raw.get("global_bible", {})
    act_summaries_raw = memory_raw.get("act_summaries", {})
    character_states_raw = memory_raw.get("character_states", {})

    memory = StoryStateMemory(
        global_bible={
            k: StoryFact(
                key=v["key"],
                value=v["value"],
                source_scene_id=v["source_scene_id"],
                stability=FactStability(v["stability"]),
            )
            for k, v in global_bible_raw.items()
        },
        act_summaries={ActType(k) if k in [a.value for a in ActType] else ActType.RISE: v for k, v in act_summaries_raw.items()},
        recent_scene_window=list(memory_raw.get("recent_scene_window", [])),
        character_states={
            k: CharacterState(
                character_id=v["character_id"],
                physical_status=v["physical_status"],
                mental_status=v["mental_status"],
                goals=list(v.get("goals", [])),
                constraints=list(v.get("constraints", [])),
            )
            for k, v in character_states_raw.items()
        },
        tension_score=float(memory_raw.get("tension_score", 0.0)),
    )

    project = StoryProject(
        project_id=raw["project_id"],
        title=raw["title"],
        genre=raw["genre"],
        tone=raw["tone"],
        narrative_viewpoint=raw["narrative_viewpoint"],
        style_preset=raw["style_preset"],
        world_rules=list(raw.get("world_rules", [])),
        hard_constraints=list(raw.get("hard_constraints", [])),
        characters={},
        acts={},
        branches={},
        scenes={},
        endings={},
        memory=memory,
    )

    project.characters = {
        k: CharacterProfile(
            character_id=v["character_id"],
            name=v.get("name", ""),
            role=v.get("role", ""),
            personality=v.get("personality", ""),
            background=v.get("background", ""),
        )
        for k, v in raw.get("characters", {}).items()
    }
    project.acts = {ActType(k) if k in [a.value for a in ActType] else ActType.RISE: list(v) for k, v in raw.get("acts", {}).items()}
    project.branches = {
        k: BranchNode(
            branch_id=v["branch_id"],
            parent_branch_id=v.get("parent_branch_id"),
            label=v["label"],
            decision_prompt=v["decision_prompt"],
            expected_consequence=v["expected_consequence"],
            merge_target_id=v.get("merge_target_id"),
            scene_ids=list(v.get("scene_ids", [])),
        )
        for k, v in raw.get("branches", {}).items()
    }
    project.scenes = {
        k: SceneCard(
            scene_id=v["scene_id"],
            act=ActType(v["act"]),
            branch_id=v["branch_id"],
            pov_character_id=v["pov_character_id"],
            objective=v["objective"],
            conflict=v["conflict"],
            outcome=v["outcome"],
            setup_hooks=list(v.get("setup_hooks", [])),
            payoff_hooks=list(v.get("payoff_hooks", [])),
            summary=v.get("summary"),
            full_text=v.get("full_text"),
            reachable_endings=list(v.get("reachable_endings", [])),
            user_modified=v.get("user_modified", False),
            context_mode=v.get("context_mode", "contiguous"),
            order_index=v.get("order_index", 0),
        )
        for k, v in raw.get("scenes", {}).items()
    }
    project.endings = {
        k: EndingCondition(
            ending_id=v["ending_id"],
            title=v["title"],
            required_facts=dict(v.get("required_facts", {})),
            prohibited_facts=dict(v.get("prohibited_facts", {})),
            minimum_tension_score=float(v.get("minimum_tension_score", 0.0)),
            theme_alignment_hint=v.get("theme_alignment_hint", ""),
        )
        for k, v in raw.get("endings", {}).items()
    }
    return project

