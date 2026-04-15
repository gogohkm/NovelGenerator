from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class ActType(str, Enum):
    RISE = "gi"
    DEVELOPMENT = "seung"
    TURN = "jeon"
    CONCLUSION = "gyeol"


class FactStability(str, Enum):
    IMMUTABLE = "immutable"
    SEMI_MUTABLE = "semi_mutable"
    MUTABLE = "mutable"


@dataclass
class CharacterState:
    character_id: str
    physical_status: str
    mental_status: str
    goals: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)


@dataclass
class CharacterProfile:
    character_id: str
    name: str # display name
    role: str # 주인공, 조력자, 빌런 등
    personality: str
    background: str


@dataclass
class StoryFact:
    key: str
    value: str
    source_scene_id: str
    stability: FactStability


@dataclass
class SceneCard:
    scene_id: str
    act: ActType
    branch_id: str
    pov_character_id: str
    objective: str
    conflict: str
    outcome: str
    setup_hooks: List[str] = field(default_factory=list)
    payoff_hooks: List[str] = field(default_factory=list)
    summary: Optional[str] = None
    full_text: Optional[str] = None
    reachable_endings: List[str] = field(default_factory=list)
    user_modified: bool = False
    context_mode: str = "contiguous"
    order_index: int = 0


@dataclass
class BranchNode:
    branch_id: str
    parent_branch_id: Optional[str]
    label: str
    decision_prompt: str
    expected_consequence: str
    merge_target_id: Optional[str] = None
    scene_ids: List[str] = field(default_factory=list)


@dataclass
class EndingCondition:
    ending_id: str
    title: str
    required_facts: Dict[str, str] = field(default_factory=dict)
    prohibited_facts: Dict[str, str] = field(default_factory=dict)
    minimum_tension_score: float = 0.0
    theme_alignment_hint: str = ""


@dataclass
class StoryStateMemory:
    global_bible: Dict[str, StoryFact] = field(default_factory=dict)
    act_summaries: Dict[ActType, str] = field(default_factory=dict)
    recent_scene_window: List[str] = field(default_factory=list)
    character_states: Dict[str, CharacterState] = field(default_factory=dict)
    tension_score: float = 0.0

    def add_scene_to_window(self, scene_id: str, max_window_size: int = 8) -> None:
        self.recent_scene_window.append(scene_id)
        if len(self.recent_scene_window) > max_window_size:
            self.recent_scene_window = self.recent_scene_window[-max_window_size:]


@dataclass
class StoryProject:
    project_id: str
    title: str
    genre: str
    tone: str
    narrative_viewpoint: str
    style_preset: str
    world_rules: List[str] = field(default_factory=list)
    hard_constraints: List[str] = field(default_factory=list)
    characters: Dict[str, CharacterProfile] = field(default_factory=dict)
    acts: Dict[ActType, List[str]] = field(default_factory=dict)
    branches: Dict[str, BranchNode] = field(default_factory=dict)
    scenes: Dict[str, SceneCard] = field(default_factory=dict)
    endings: Dict[str, EndingCondition] = field(default_factory=dict)
    memory: StoryStateMemory = field(default_factory=StoryStateMemory)


# --- 정합성/통일화 관련 데이터 구조 ---


@dataclass
class ConsistencyIssue:
    issue_id: str
    severity: str
    fact_key: str
    message: str
    related_scene_ids: List[str] = field(default_factory=list)


@dataclass
class RewriteImpact:
    changed_branch_id: str
    directly_impacted_scene_ids: List[str]
    transitively_impacted_scene_ids: List[str]
    rewrite_priority: Dict[str, int]


@dataclass
class UnifyProposal:
    proposal_id: str
    issue_id: str
    severity: str
    description: str
    scene_ids: List[str]
    proposed_fix: str
    fix_type: str  # "scene_rewrite", "fact_correction", "hook_resolution", "chronology_fix"
    auto_fixable: bool
    user_choice: Optional[str] = None  # "accept", "reject", or custom text


@dataclass
class UnifyReport:
    issues: List[ConsistencyIssue] = field(default_factory=list)
    proposals: List[UnifyProposal] = field(default_factory=list)
    orphaned_hooks: List[str] = field(default_factory=list)
    chronology_issues: List[str] = field(default_factory=list)
