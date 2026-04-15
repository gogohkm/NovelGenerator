from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, QMimeData
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QRadioButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QAbstractItemView,
)

from core.consistency import UnifyEngine
from core.generation_loop import BranchOptionGenerator, PlotManager, StoryEngine
from core.llm_adapter import (
    LLMBranchOptionGenerator,
    LLMCharacterHelper,
    LLMUnifyHelper,
    LLMWorldRuleChecker,
    LMStudioClient,
    LMStudioConfig,
    LMStudioOpenAICompatibleGenerator,
    MockUnifyHelper,
    StaticBranchOptionGenerator,
)
from core.models import (
    ActType,
    BranchNode,
    CharacterProfile,
    EndingCondition,
    SceneCard,
    StoryProject,
    UnifyProposal,
    UnifyReport,
)
from core.persistence import load_project, save_project


ACT_LABELS = {
    ActType.RISE: "기(起)",
    ActType.DEVELOPMENT: "승(承)",
    ActType.TURN: "전(轉)",
    ActType.CONCLUSION: "결(結)",
}
ACT_COLORS = {
    ActType.RISE: QColor("#4CAF50"),
    ActType.DEVELOPMENT: QColor("#2196F3"),
    ActType.TURN: QColor("#FF9800"),
    ActType.CONCLUSION: QColor("#F44336"),
}
ACT_ORDER = [ActType.RISE, ActType.DEVELOPMENT, ActType.TURN, ActType.CONCLUSION]


@dataclass
class AppState:
    project: StoryProject
    current_branch_id: str = "root"
    viewing_scene_id: Optional[str] = None


def build_default_project() -> StoryProject:
    project = StoryProject(
        project_id="novel-001",
        title="새 프로젝트",
        genre="판타지",
        tone="진지함",
        narrative_viewpoint="3인칭 제한 시점",
        style_preset="담백하고 생동감",
        world_rules=["마법은 대가를 치른다", "죽은 자는 되살릴 수 없다"],
    )
    root = BranchNode(
        branch_id="root",
        parent_branch_id=None,
        label="초기 사건",
        decision_prompt="주인공이 맞닥뜨린 사건의 방향을 선택",
        expected_consequence="갈등의 형태가 달라짐",
    )
    project.branches[root.branch_id] = root
    project.acts = {act: [] for act in ActType}
    project.endings["ending-1"] = EndingCondition(ending_id="ending-1", title="희망의 결말")
    project.characters["protagonist"] = CharacterProfile(
        character_id="protagonist",
        name="주인공",
        role="주인공",
        personality="정의롭고 결단력 있음",
        background="과거의 상처를 안고 미래를 개척하고자 함"
    )
    return project


# ─── [A] Story Flow Bar Widget ──────────────────────────────────────

class StoryFlowBar(QWidget):
    """기▪▪▪ → 승▪▪▪▪▪ → 전▪▪ → 결  형태의 전체 흐름 요약 바."""
    scene_clicked = Signal(str)  # scene_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(48)
        self.setMaximumHeight(48)
        self._project: Optional[StoryProject] = None
        self._highlight_scene_id: Optional[str] = None
        self._scene_rects: list[tuple] = []  # (x, y, w, h, scene_id)

    def set_project(self, project: StoryProject, highlight_scene_id: Optional[str] = None) -> None:
        self._project = project
        self._highlight_scene_id = highlight_scene_id
        self.update()

    def paintEvent(self, event) -> None:
        if not self._project:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        margin = 4
        bar_h = 22
        bar_y = (h - bar_h) // 2

        total_scenes = max(sum(len(self._project.acts.get(a, [])) for a in ACT_ORDER), 1)
        self._scene_rects.clear()

        x = margin
        usable_w = w - margin * 2 - 3 * 14  # 3 arrows between acts
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)

        for i, act in enumerate(ACT_ORDER):
            scene_ids = self._project.acts.get(act, [])
            count = len(scene_ids)
            act_w = max(int(usable_w * count / total_scenes), 30) if count > 0 else 30

            color = ACT_COLORS[act]
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color.lighter(160)))
            painter.drawRoundedRect(x, bar_y, act_w, bar_h, 4, 4)

            # Scene dots
            if count > 0:
                dot_spacing = max(act_w // (count + 1), 6)
                for j, sid in enumerate(scene_ids):
                    dx = x + dot_spacing * (j + 1)
                    dx = min(dx, x + act_w - 4)
                    is_highlight = (sid == self._highlight_scene_id)
                    painter.setBrush(QBrush(QColor("white") if is_highlight else color))
                    painter.setPen(QPen(color.darker(130), 2 if is_highlight else 0))
                    r = 6 if is_highlight else 4
                    painter.drawEllipse(int(dx - r), int(bar_y + bar_h // 2 - r), r * 2, r * 2)
                    self._scene_rects.append((dx - r, bar_y, r * 2, bar_h, sid))

            # Act label
            painter.setPen(QPen(color.darker(150)))
            painter.drawText(x, bar_y - 2, act_w, 14, Qt.AlignmentFlag.AlignCenter, f"{ACT_LABELS[act]} ({count})")

            x += act_w

            # Arrow
            if i < 3:
                painter.setPen(QPen(QColor("#999"), 1))
                painter.drawText(x, bar_y, 14, bar_h, Qt.AlignmentFlag.AlignCenter, "→")
                x += 14

        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        px, py = pos.x(), pos.y()
        for rx, ry, rw, rh, sid in self._scene_rects:
            if rx - 4 <= px <= rx + rw + 4 and ry <= py <= ry + rh:
                self.scene_clicked.emit(sid)
                return


# ─── [F] Collapsible Group Box ──────────────────────────────────────

class CollapsibleGroupBox(QGroupBox):
    """클릭하면 접기/펼치기 가능한 QGroupBox."""

    def __init__(self, title: str, parent=None, collapsed: bool = False):
        super().__init__(title, parent)
        self.setCheckable(True)
        self.setChecked(not collapsed)
        self.toggled.connect(self._on_toggled)
        self._content_height = 0
        if collapsed:
            self.setMaximumHeight(24)

    def _on_toggled(self, checked: bool) -> None:
        if checked:
            self.setMaximumHeight(16777215)
            for child in self.findChildren(QWidget):
                child.setVisible(True)
        else:
            for child in self.findChildren(QWidget):
                child.setVisible(False)
            self.setMaximumHeight(24)


# ─── [E] Drag-reorder List Widget ───────────────────────────────────

class ReorderableListWidget(QListWidget):
    """드래그 앤 드롭으로 항목 순서를 변경할 수 있는 QListWidget."""
    order_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.model().rowsMoved.connect(lambda: self.order_changed.emit())


# ─── Workers ────────────────────────────────────────────────────────

class GenerationWorker(QThread):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, engine: StoryEngine, project: StoryProject,
                 branch_id: str, option_index: int, target_act: ActType,
                 custom_option: Optional[str] = None, context_mode: str = "contiguous",
                 pov_character_id: str = "protagonist"):
        super().__init__()
        self.engine = engine
        self.project = project
        self.branch_id = branch_id
        self.option_index = option_index
        self.target_act = target_act
        self.custom_option = custom_option
        self.context_mode = context_mode
        self.pov_character_id = pov_character_id

    def run(self) -> None:
        try:
            scene = self.engine.run_turn(
                self.project, self.branch_id, self.option_index, target_act=self.target_act,
                custom_option=self.custom_option, context_mode=self.context_mode,
                pov_character_id=self.pov_character_id
            )
            self.finished.emit(scene)
        except Exception as e:
            self.error.emit(str(e))


class OptionRefreshWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, generator, project: StoryProject, branch_id: str):
        super().__init__()
        self.generator = generator
        self.project = project
        self.branch_id = branch_id

    def run(self) -> None:
        try:
            options = self.generator.generate_options(self.project, self.branch_id)
            self.finished.emit(options)
        except Exception as e:
            self.error.emit(str(e))


class SceneSaveWorker(QThread):
    finished = Signal(str, str)
    error = Signal(str)

    def __init__(self, scene_generator, scene_id: str, scene_text: str):
        super().__init__()
        self.scene_generator = scene_generator
        self.scene_id = scene_id
        self.scene_text = scene_text

    def run(self) -> None:
        try:
            summary = self.scene_generator.summarize_scene(self.scene_text)
            self.finished.emit(self.scene_id, summary)
        except Exception as e:
            self.error.emit(str(e))


class UnifyAnalyzeWorker(QThread):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, unify_engine: UnifyEngine, project: StoryProject):
        super().__init__()
        self.unify_engine = unify_engine
        self.project = project

    def run(self) -> None:
        try:
            report = self.unify_engine.analyze(self.project)
            report = self.unify_engine.propose_fixes(self.project, report)
            self.finished.emit(report)
        except Exception as e:
            self.error.emit(str(e))


class UnifyApplyWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, unify_engine: UnifyEngine, project: StoryProject, report: UnifyReport):
        super().__init__()
        self.unify_engine = unify_engine
        self.project = project
        self.report = report

    def run(self) -> None:
        try:
            modified = self.unify_engine.apply_fixes(self.project, self.report)
            self.finished.emit(modified)
        except Exception as e:
            self.error.emit(str(e))


class CharacterProfileGenerateWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, helper: 'LLMCharacterHelper', project: 'StoryProject', name: str, role: str):
        super().__init__()
        self.helper = helper
        self.project = project
        self.name = name
        self.role = role

    def run(self) -> None:
        try:
            profile_data = self.helper.generate_initial_profile(self.project, self.name, self.role)
            self.finished.emit(profile_data)
        except Exception as e:
            self.error.emit(str(e))


class CharacterExtractWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, helper: 'LLMCharacterHelper', project: 'StoryProject', scene_text: str):
        super().__init__()
        self.helper = helper
        self.project = project
        self.scene_text = scene_text

    def run(self) -> None:
        try:
            items = self.helper.extract_new_characters(self.project, self.scene_text)
            self.finished.emit(items)
        except Exception as e:
            self.error.emit(str(e))

# ─── Unify Dialog ───────────────────────────────────────────────────

class UnifyDialog(QDialog):
    def __init__(self, report: UnifyReport, parent=None):
        super().__init__(parent)
        self.setWindowTitle("전체 통일화 분석 결과")
        self.resize(700, 600)
        self.report = report
        self._controls: list = []

        layout = QVBoxLayout(self)

        total = len(report.proposals) + len(report.orphaned_hooks) + len(report.chronology_issues)
        if total == 0 and not report.issues:
            layout.addWidget(QLabel("모든 장면이 일관성을 만족합니다."))
            close_btn = QPushButton("닫기")
            close_btn.clicked.connect(self.reject)
            layout.addWidget(close_btn)
            return

        summary = (
            f"발견된 이슈: {len(report.issues)}건 | "
            f"수정 제안: {len(report.proposals)}건 | "
            f"고아 훅: {len(report.orphaned_hooks)}건 | "
            f"시간순 문제: {len(report.chronology_issues)}건"
        )
        layout.addWidget(QLabel(summary))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        for proposal in report.proposals:
            box = QGroupBox(f"[{proposal.severity.upper()}] {proposal.description[:80]}")
            box_layout = QVBoxLayout(box)

            if proposal.scene_ids:
                box_layout.addWidget(QLabel(f"관련 장면: {', '.join(proposal.scene_ids)}"))

            fix_preview = QTextEdit(proposal.proposed_fix[:500])
            fix_preview.setReadOnly(True)
            fix_preview.setMaximumHeight(120)
            box_layout.addWidget(fix_preview)

            if proposal.auto_fixable:
                cb = QCheckBox("자동 수정")
                cb.setChecked(True)
                box_layout.addWidget(cb)
                self._controls.append(("auto", proposal, cb))
            else:
                row = QHBoxLayout()
                accept_rb = QRadioButton("수정 적용")
                reject_rb = QRadioButton("무시")
                reject_rb.setChecked(True)
                row.addWidget(accept_rb)
                row.addWidget(reject_rb)
                box_layout.addLayout(row)
                self._controls.append(("manual", proposal, accept_rb, reject_rb))

            scroll_layout.addWidget(box)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        apply_btn = QPushButton("적용")
        cancel_btn = QPushButton("취소")
        apply_btn.clicked.connect(self._on_apply)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _on_apply(self) -> None:
        for entry in self._controls:
            if entry[0] == "auto":
                _, proposal, cb = entry
                proposal.user_choice = "accept" if cb.isChecked() else "reject"
            else:
                _, proposal, accept_rb, reject_rb = entry
                proposal.user_choice = "accept" if accept_rb.isChecked() else "reject"
        self.accept()


# ─── Main Window ────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("NovelGenerator (LM Studio 로컬 모델)")
        self.resize(1280, 860)

        self.state = AppState(project=build_default_project())
        self._worker: Optional[GenerationWorker] = None
        self._option_worker: Optional[OptionRefreshWorker] = None
        self._scene_save_worker: Optional[SceneSaveWorker] = None
        self._unify_worker: Optional[UnifyAnalyzeWorker] = None
        self._unify_apply_worker: Optional[UnifyApplyWorker] = None
        self._pending_report: Optional[UnifyReport] = None

        # --- [A] Flow bar ---
        self.flow_bar = StoryFlowBar()
        self.flow_bar.scene_clicked.connect(self._on_flow_bar_scene_clicked)

        # --- LM Studio config ---
        self.base_url = QLineEdit("http://127.0.0.1:1234/v1")
        self.model_name = QLineEdit("local-model")
        self.api_key = QLineEdit("")
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)

        # --- Project settings ---
        self.project_title = QLineEdit(self.state.project.title)
        self.genre = QLineEdit(self.state.project.genre)
        self.tone = QLineEdit(self.state.project.tone)
        self.viewpoint = QLineEdit(self.state.project.narrative_viewpoint)
        self.style = QLineEdit(self.state.project.style_preset)
        self.world_rules = QTextEdit("\n".join(self.state.project.world_rules))

        # --- Character Management ---
        self.char_list_combo = QComboBox()
        self.char_name = QLineEdit()
        self.char_role = QLineEdit()
        self.char_personality = QTextEdit()
        self.char_background = QTextEdit()
        self.char_personality.setMaximumHeight(60)
        self.char_background.setMaximumHeight(60)
        
        self.char_save_btn = QPushButton("저장 / 추가")
        self.char_auto_btn = QPushButton("LLM 자동 설정")
        self.char_extract_btn = QPushButton("현재 장면에서 새 인물 추출")
        
        # --- Scene generation POV ---
        self.scene_pov_combo = QComboBox()

        # --- Branch options ---
        self.options = QComboBox()
        self.custom_option_input = QLineEdit()
        self.custom_option_input.setPlaceholderText("직접 입력 시 위 추천 선택지를 무시하고 우선 적용됩니다.")
        
        self.context_mode_combo = QComboBox()
        self.context_mode_combo.addItems([
            "이어쓰기 (직전 장면과 대사/행동 바로 연결)",
            "새 챕터/막 시작 (시간/공간 바뀌며 줄거리만 이어감)",
            "완전 독립된 도입부/막간 (흐름 끊고 새로 시작)"
        ])

        self.generate_btn = QPushButton("선택 반영 → 장면 생성")
        self.refresh_options_btn = QPushButton("선택지 새로고침")

        # --- Scene display (editable) ---
        self.scene_text = QTextEdit()
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.save_scene_btn = QPushButton("장면 저장")
        self.save_scene_btn.setEnabled(False)

        # --- [B] Navigation buttons ---
        self.prev_scene_btn = QPushButton("◀ 이전 장면")
        self.next_scene_btn = QPushButton("다음 장면 ▶")
        self.prev_scene_btn.setEnabled(False)
        self.next_scene_btn.setEnabled(False)

        # --- [D] Delete button ---
        self.delete_scene_btn = QPushButton("장면 삭제")
        self.delete_scene_btn.setEnabled(False)
        self.delete_scene_btn.setStyleSheet("color: #d32f2f;")

        # --- Scene metadata editor ---
        self.meta_objective = QLineEdit()
        self.meta_conflict = QLineEdit()
        self.meta_outcome = QLineEdit()
        self.save_meta_btn = QPushButton("메타데이터 저장")
        self.save_meta_btn.setEnabled(False)

        # --- Progress / status ---
        self.current_branch_label = QLabel("현재 분기: root")
        self.current_scene_label = QLabel("현재 장면: (없음)")
        self.path_label = QLabel("분기 경로: root")
        self.progress_label = QLabel("진행도: 0장면 / 약 0.0페이지")
        self.act_ratio_label = QLabel("막 분포: 기 0 | 승 0 | 전 0 | 결 0")
        self.ending_status_label = QLabel("도달 가능 결말: (없음)")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 500)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%v / 500 페이지")

        # --- [E] Act tabs with reorderable lists ---
        self.act_tabs = QTabWidget()
        self.act_scene_lists: dict[ActType, ReorderableListWidget] = {}
        for act in ACT_ORDER:
            lst = ReorderableListWidget()
            lst.itemClicked.connect(self._on_act_scene_clicked)
            lst.order_changed.connect(lambda a=act: self._on_scene_order_changed(a))
            self.act_scene_lists[act] = lst
            self.act_tabs.addTab(lst, ACT_LABELS[act])

        # --- Action buttons ---
        self.new_project_btn = QPushButton("새 프로젝트")
        self.save_btn = QPushButton("저장")
        self.load_btn = QPushButton("불러오기")
        self.unify_btn = QPushButton("전체 통일화")

        self._wire()
        self._layout()
        self._refresh_options()

    def _wire(self) -> None:
        self.refresh_options_btn.clicked.connect(self._refresh_options)
        self.generate_btn.clicked.connect(self._generate_scene)
        self.new_project_btn.clicked.connect(self._new_project)
        self.save_btn.clicked.connect(self._save_project)
        self.load_btn.clicked.connect(self._load_project)
        self.unify_btn.clicked.connect(self._run_unify)
        self.save_scene_btn.clicked.connect(self._save_scene_edit)
        self.save_meta_btn.clicked.connect(self._save_meta_edit)
        self.scene_text.textChanged.connect(self._on_scene_text_changed)
        self.prev_scene_btn.clicked.connect(self._go_prev_scene)
        self.next_scene_btn.clicked.connect(self._go_next_scene)
        self.delete_scene_btn.clicked.connect(self._delete_current_scene)
        self.char_list_combo.currentIndexChanged.connect(self._on_char_selected)
        self.char_save_btn.clicked.connect(self._save_character)
        self.char_auto_btn.clicked.connect(self._auto_character_profile)
        self.char_extract_btn.clicked.connect(self._extract_characters_from_scene)

    def _layout(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)

        # [A] Flow bar at top
        root_layout.addWidget(self.flow_bar)

        # Main splitter
        main_body = QSplitter()

        # === LEFT PANEL ===
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 4, 4, 4)

        # [F] Collapsible LM Studio config
        cfg_box = CollapsibleGroupBox("LM Studio 연결", collapsed=True)
        cfg_form = QFormLayout()
        cfg_form.addRow("Base URL", self.base_url)
        cfg_form.addRow("Model", self.model_name)
        cfg_form.addRow("API Key(선택)", self.api_key)
        cfg_box.setLayout(cfg_form)
        left_layout.addWidget(cfg_box)

        # [F] Collapsible project settings
        proj_box = CollapsibleGroupBox("프로젝트 설정", collapsed=True)
        proj_form = QFormLayout()
        proj_form.addRow("제목", self.project_title)
        proj_form.addRow("장르", self.genre)
        proj_form.addRow("톤", self.tone)
        proj_form.addRow("시점", self.viewpoint)
        proj_form.addRow("문체", self.style)
        proj_form.addRow(QLabel("세계관 규칙(줄바꿈으로 여러 개)"))
        proj_form.addRow(self.world_rules)
        proj_box.setLayout(proj_form)
        left_layout.addWidget(proj_box)

        # [F] Collapsible Character settings
        char_box = CollapsibleGroupBox("등장인물 관리", collapsed=True)
        char_form = QVBoxLayout(char_box)
        
        char_dropdown_row = QHBoxLayout()
        char_dropdown_row.addWidget(QLabel("선택:"))
        char_dropdown_row.addWidget(self.char_list_combo, 1)
        char_form.addLayout(char_dropdown_row)
        
        c_form = QFormLayout()
        c_form.addRow("이름", self.char_name)
        c_form.addRow("역할", self.char_role)
        c_form.addRow("성격", self.char_personality)
        c_form.addRow("과거", self.char_background)
        char_form.addLayout(c_form)
        
        char_btn_row = QHBoxLayout()
        char_btn_row.addWidget(self.char_save_btn)
        char_btn_row.addWidget(self.char_auto_btn)
        char_form.addLayout(char_btn_row)
        
        char_form.addWidget(self.char_extract_btn)
        
        left_layout.addWidget(char_box)
        
        actions = QHBoxLayout()
        actions.addWidget(self.new_project_btn)
        actions.addWidget(self.save_btn)
        actions.addWidget(self.load_btn)
        actions.addWidget(self.unify_btn)
        left_layout.addLayout(actions)

        branch_box = QGroupBox("분기 선택 및 생성")
        branch_layout = QVBoxLayout(branch_box)
        branch_layout.addWidget(self.current_branch_label)
        
        branch_pov_row = QHBoxLayout()
        branch_pov_row.addWidget(QLabel("시점 인물(POV):"))
        branch_pov_row.addWidget(self.scene_pov_combo, 1)
        branch_layout.addLayout(branch_pov_row)
        
        branch_layout.addWidget(QLabel("LLM 추천 선택지:"))
        branch_layout.addWidget(self.options)
        branch_layout.addWidget(QLabel("직접 입력 (우선 적용):"))
        branch_layout.addWidget(self.custom_option_input)
        branch_layout.addWidget(QLabel("컨텍스트 모드:"))
        branch_layout.addWidget(self.context_mode_combo)
        branch_actions = QHBoxLayout()
        branch_actions.addWidget(self.refresh_options_btn)
        branch_actions.addWidget(self.generate_btn)
        branch_layout.addLayout(branch_actions)
        left_layout.addWidget(branch_box)

        progress_box = QGroupBox("집필 진행 현황")
        progress_layout = QVBoxLayout(progress_box)
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.act_ratio_label)
        progress_layout.addWidget(self.ending_status_label)
        progress_layout.addWidget(self.path_label)
        progress_layout.addWidget(QLabel("막 탭 선택 → 장면 클릭/추가 (드래그로 순서 변경)"))
        progress_layout.addWidget(self.act_tabs, 1)
        left_layout.addWidget(progress_box, 2)

        # === RIGHT PANEL ===
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 4, 4, 4)

        # [B] Navigation row
        nav_row = QHBoxLayout()
        nav_row.addWidget(self.prev_scene_btn)
        nav_row.addWidget(self.current_scene_label, 1)
        nav_row.addWidget(self.next_scene_btn)
        right_layout.addLayout(nav_row)

        split_text = QSplitter(Qt.Orientation.Vertical)

        scene_box = QGroupBox("장면 본문 (편집 가능)")
        scene_box_layout = QVBoxLayout(scene_box)
        scene_box_layout.addWidget(self.scene_text)
        scene_btn_row = QHBoxLayout()
        scene_btn_row.addWidget(self.save_scene_btn)
        scene_btn_row.addStretch()
        scene_btn_row.addWidget(self.delete_scene_btn)  # [D]
        scene_box_layout.addLayout(scene_btn_row)

        summary_box = QGroupBox("요약")
        summary_layout = QVBoxLayout(summary_box)
        summary_layout.addWidget(self.summary_text)

        meta_box = QGroupBox("장면 메타데이터")
        meta_form = QFormLayout(meta_box)
        meta_form.addRow("목표", self.meta_objective)
        meta_form.addRow("갈등", self.meta_conflict)
        meta_form.addRow("결과", self.meta_outcome)
        meta_form.addRow(self.save_meta_btn)

        split_text.addWidget(scene_box)
        split_text.addWidget(summary_box)
        split_text.addWidget(meta_box)
        split_text.setSizes([500, 120, 140])
        right_layout.addWidget(split_text, 1)

        main_body.addWidget(left)
        main_body.addWidget(right)
        main_body.setSizes([460, 820])

        root_layout.addWidget(main_body, 1)
        self._refresh_progress_ui()

    # ─── Helpers ───

    def _apply_project_settings_to_model(self) -> None:
        p = self.state.project
        p.title = self.project_title.text().strip() or "새 프로젝트"
        p.genre = self.genre.text().strip() or p.genre
        p.tone = self.tone.text().strip() or p.tone
        p.narrative_viewpoint = self.viewpoint.text().strip() or p.narrative_viewpoint
        p.style_preset = self.style.text().strip() or p.style_preset
        rules = [r.strip() for r in self.world_rules.toPlainText().splitlines() if r.strip()]
        p.world_rules = rules

    def _build_lm_client(self) -> LMStudioClient:
        cfg = LMStudioConfig(
            base_url=self.base_url.text().strip(),
            model=self.model_name.text().strip() or "local-model",
            api_key=self.api_key.text().strip() or None,
        )
        return LMStudioClient(cfg)

    def _build_engine(self, option_generator=None) -> StoryEngine:
        client = self._build_lm_client()
        scene_gen = LMStudioOpenAICompatibleGenerator(client)
        opt_gen = option_generator or LLMBranchOptionGenerator(client)
        return StoryEngine(PlotManager(), opt_gen, scene_gen)

    def _current_target_act(self) -> ActType:
        idx = self.act_tabs.currentIndex()
        return ACT_ORDER[idx]

    def _set_generation_ui_enabled(self, enabled: bool) -> None:
        self.generate_btn.setEnabled(enabled)
        self.refresh_options_btn.setEnabled(enabled)
        self.generate_btn.setText("생성 중..." if not enabled else "선택 반영 → 장면 생성")

    def _all_scene_ids_in_order(self) -> list[str]:
        """전체 장면을 기→승→전→결 순서로 flat list 반환."""
        result = []
        for act in ACT_ORDER:
            result.extend(self.state.project.acts.get(act, []))
        return result

    # ─── [B] Navigation ───

    def _go_prev_scene(self) -> None:
        all_ids = self._all_scene_ids_in_order()
        if not all_ids or not self.state.viewing_scene_id:
            return
        try:
            idx = all_ids.index(self.state.viewing_scene_id)
        except ValueError:
            return
        if idx > 0:
            self._navigate_to_scene(all_ids[idx - 1])

    def _go_next_scene(self) -> None:
        all_ids = self._all_scene_ids_in_order()
        if not all_ids or not self.state.viewing_scene_id:
            return
        try:
            idx = all_ids.index(self.state.viewing_scene_id)
        except ValueError:
            return
        if idx < len(all_ids) - 1:
            self._navigate_to_scene(all_ids[idx + 1])

    def _navigate_to_scene(self, scene_id: str) -> None:
        scene = self.state.project.scenes.get(scene_id)
        if not scene:
            return
        # Switch to the correct tab
        act_idx = ACT_ORDER.index(scene.act) if scene.act in ACT_ORDER else 0
        self.act_tabs.setCurrentIndex(act_idx)
        self._show_scene(scene)

    def _update_nav_buttons(self) -> None:
        all_ids = self._all_scene_ids_in_order()
        sid = self.state.viewing_scene_id
        if not sid or sid not in all_ids:
            self.prev_scene_btn.setEnabled(False)
            self.next_scene_btn.setEnabled(False)
            self.prev_scene_btn.setText("◀ 이전 장면")
            self.next_scene_btn.setText("다음 장면 ▶")
            return

        idx = all_ids.index(sid)
        total = len(all_ids)

        has_prev = idx > 0
        has_next = idx < total - 1
        self.prev_scene_btn.setEnabled(has_prev)
        self.next_scene_btn.setEnabled(has_next)
        self.prev_scene_btn.setText(f"◀ {all_ids[idx - 1]}" if has_prev else "◀ 이전 장면")
        self.next_scene_btn.setText(f"{all_ids[idx + 1]} ▶" if has_next else "다음 장면 ▶")

    # ─── [A] Flow bar click ───

    def _on_flow_bar_scene_clicked(self, scene_id: str) -> None:
        self._navigate_to_scene(scene_id)

    # ─── Option refresh ───

    def _refresh_options(self) -> None:
        try:
            self._apply_project_settings_to_model()
            client = self._build_lm_client()
            generator = LLMBranchOptionGenerator(client)
            self._option_worker = OptionRefreshWorker(
                generator, self.state.project, self.state.current_branch_id,
            )
            self._option_worker.finished.connect(self._on_options_ready)
            self._option_worker.error.connect(self._on_options_error)
            self.refresh_options_btn.setEnabled(False)
            self.refresh_options_btn.setText("선택지 생성 중...")
            self._option_worker.start()
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))

    def _on_options_ready(self, options) -> None:
        self.options.clear()
        for opt in options:
            self.options.addItem(f"{opt.label}  |  {opt.rationale}  |  리스크: {opt.risk}")
        self.refresh_options_btn.setEnabled(True)
        self.refresh_options_btn.setText("선택지 새로고침")
        self._refresh_progress_ui()

    def _on_options_error(self, msg: str) -> None:
        self.refresh_options_btn.setEnabled(True)
        self.refresh_options_btn.setText("선택지 새로고침")
        try:
            fallback = StaticBranchOptionGenerator()
            options = fallback.generate_options(self.state.project, self.state.current_branch_id)
            self.options.clear()
            for opt in options:
                self.options.addItem(f"{opt.label}  |  {opt.rationale}  |  리스크: {opt.risk}")
            self._refresh_progress_ui()
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))

    # ─── Scene generation (async) ───

    def _generate_scene(self) -> None:
        try:
            self._apply_project_settings_to_model()
            idx = self.options.currentIndex()
            custom_option_text = self.custom_option_input.text().strip()
            
            if idx < 0 and not custom_option_text:
                QMessageBox.information(self, "안내", "선택지를 고르거나 직접 입력하세요.")
                return

            context_mode_idx = self.context_mode_combo.currentIndex()
            mode_map = ["contiguous", "new_chapter", "standalone"]
            context_mode = mode_map[context_mode_idx]
            pov_id = self.scene_pov_combo.currentData() or "protagonist"

            self._set_generation_ui_enabled(False)
            target_act = self._current_target_act()
            engine = self._build_engine()
            self._worker = GenerationWorker(
                engine, self.state.project, self.state.current_branch_id, max(0, idx), target_act,
                custom_option=custom_option_text, context_mode=context_mode, pov_character_id=pov_id
            )
            self._worker.finished.connect(self._on_generation_done)
            self._worker.error.connect(self._on_generation_error)
            self._worker.start()
        except Exception as e:
            self._set_generation_ui_enabled(True)
            QMessageBox.critical(self, "생성 실패", str(e))

    def _on_generation_done(self, scene: SceneCard) -> None:
        self._set_generation_ui_enabled(True)
        self.state.current_branch_id = scene.branch_id
        self.custom_option_input.clear()
        self.context_mode_combo.setCurrentIndex(0)
        self.current_branch_label.setText(f"현재 분기: {self.state.current_branch_id}")
        self._show_scene(scene)

        if scene.reachable_endings:
            endings = self.state.project.endings
            names = [endings[eid].title for eid in scene.reachable_endings if eid in endings]
            if names:
                self.ending_status_label.setText(f"도달 가능 결말: {', '.join(names)}")
                QMessageBox.information(self, "결말 도달 가능",
                    f"다음 결말에 도달할 수 있습니다:\n{chr(10).join(names)}")
            else:
                self.ending_status_label.setText("도달 가능 결말: (없음)")
        else:
            self.ending_status_label.setText("도달 가능 결말: (없음)")

        self._refresh_options()

    def _on_generation_error(self, msg: str) -> None:
        self._set_generation_ui_enabled(True)
        QMessageBox.critical(self, "생성 실패", msg)

    # ─── Scene display/edit ───

    def _show_scene(self, scene: SceneCard) -> None:
        self.state.viewing_scene_id = scene.scene_id
        self.scene_text.blockSignals(True)
        self.scene_text.setPlainText(scene.full_text or "")
        self.scene_text.blockSignals(False)
        self.summary_text.setPlainText(scene.summary or "")
        self.meta_objective.setText(scene.objective)
        self.meta_conflict.setText(scene.conflict)
        self.meta_outcome.setText(scene.outcome)
        self.save_scene_btn.setEnabled(True)
        self.save_meta_btn.setEnabled(True)
        self.delete_scene_btn.setEnabled(True)
        modified_tag = " [수정됨]" if scene.user_modified else ""

        # [C] Scene position indicator
        all_ids = self._all_scene_ids_in_order()
        pos = all_ids.index(scene.scene_id) + 1 if scene.scene_id in all_ids else 0
        total = len(all_ids)
        self.current_scene_label.setText(
            f"[{pos}/{total}] {scene.scene_id} (막: {ACT_LABELS.get(scene.act, scene.act.value)}){modified_tag}"
        )

        self._update_nav_buttons()
        self._refresh_progress_ui()

    def _on_act_scene_clicked(self, item: QListWidgetItem) -> None:
        scene_id = item.data(Qt.ItemDataRole.UserRole)
        if not scene_id or not isinstance(scene_id, str):
            return
        scene = self.state.project.scenes.get(scene_id)
        if scene is None:
            QMessageBox.warning(self, "안내", f"장면을 찾을 수 없습니다: {scene_id}")
            return
        self._show_scene(scene)

    def _on_scene_text_changed(self) -> None:
        self.save_scene_btn.setEnabled(self.state.viewing_scene_id is not None)

    def _save_scene_edit(self) -> None:
        sid = self.state.viewing_scene_id
        if not sid:
            return
        scene = self.state.project.scenes.get(sid)
        if not scene:
            return

        new_text = self.scene_text.toPlainText()
        scene.full_text = new_text
        scene.user_modified = True

        try:
            client = self._build_lm_client()
            gen = LMStudioOpenAICompatibleGenerator(client)
            self._scene_save_worker = SceneSaveWorker(gen, sid, new_text)
            self._scene_save_worker.finished.connect(self._on_scene_save_done)
            self._scene_save_worker.error.connect(self._on_scene_save_error)
            self.save_scene_btn.setEnabled(False)
            self.save_scene_btn.setText("저장 중...")
            self._scene_save_worker.start()
        except Exception:
            self._refresh_progress_ui()
            QMessageBox.information(self, "저장 완료", "본문이 저장되었습니다 (요약은 LLM 없이 갱신되지 않음).")

    def _on_scene_save_done(self, scene_id: str, new_summary: str) -> None:
        self.save_scene_btn.setEnabled(True)
        self.save_scene_btn.setText("장면 저장")
        scene = self.state.project.scenes.get(scene_id)
        if scene:
            scene.summary = new_summary
        self.summary_text.setPlainText(new_summary)
        self._refresh_progress_ui()

    def _on_scene_save_error(self, msg: str) -> None:
        self.save_scene_btn.setEnabled(True)
        self.save_scene_btn.setText("장면 저장")
        self._refresh_progress_ui()

    def _save_meta_edit(self) -> None:
        sid = self.state.viewing_scene_id
        if not sid:
            return
        scene = self.state.project.scenes.get(sid)
        if not scene:
            return
        scene.objective = self.meta_objective.text()
        scene.conflict = self.meta_conflict.text()
        scene.outcome = self.meta_outcome.text()
        scene.user_modified = True
        self._refresh_progress_ui()

    # ─── [D] Delete scene ───

    def _delete_current_scene(self) -> None:
        sid = self.state.viewing_scene_id
        if not sid:
            return
        scene = self.state.project.scenes.get(sid)
        if not scene:
            return

        reply = QMessageBox.question(
            self, "장면 삭제",
            f"{sid} (막: {ACT_LABELS.get(scene.act, scene.act.value)}) 장면을 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        project = self.state.project

        # Remove from acts
        act_list = project.acts.get(scene.act, [])
        if sid in act_list:
            act_list.remove(sid)

        # Remove from branches
        branch = project.branches.get(scene.branch_id)
        if branch and sid in branch.scene_ids:
            branch.scene_ids.remove(sid)

        # Remove from scenes
        del project.scenes[sid]

        # Remove from memory
        project.memory.global_bible.pop(f"{sid}:outcome", None)
        if sid in project.memory.recent_scene_window:
            project.memory.recent_scene_window.remove(sid)

        # Navigate to adjacent scene or clear
        all_ids = self._all_scene_ids_in_order()
        self.state.viewing_scene_id = None
        if all_ids:
            self._navigate_to_scene(all_ids[-1])
        else:
            self.scene_text.blockSignals(True)
            self.scene_text.clear()
            self.scene_text.blockSignals(False)
            self.summary_text.clear()
            self.meta_objective.clear()
            self.meta_conflict.clear()
            self.meta_outcome.clear()
            self.save_scene_btn.setEnabled(False)
            self.save_meta_btn.setEnabled(False)
            self.delete_scene_btn.setEnabled(False)
            self.current_scene_label.setText("현재 장면: (없음)")
            self._update_nav_buttons()

        self._refresh_progress_ui()

    # ─── [E] Drag-reorder scenes ───

    def _on_scene_order_changed(self, act: ActType) -> None:
        """드래그로 순서 변경 후 project.acts를 동기화."""
        lst = self.act_scene_lists[act]
        new_order = []
        for i in range(lst.count()):
            item = lst.item(i)
            sid = item.data(Qt.ItemDataRole.UserRole)
            if sid:
                new_order.append(sid)
                scene = self.state.project.scenes.get(sid)
                if scene:
                    scene.order_index = i
        self.state.project.acts[act] = new_order
        self.flow_bar.set_project(self.state.project, self.state.viewing_scene_id)

    # ─── Unify ───

    def _run_unify(self) -> None:
        try:
            self._apply_project_settings_to_model()
            client = self._build_lm_client()
            scene_gen = LMStudioOpenAICompatibleGenerator(client)
            try:
                rule_checker = LLMWorldRuleChecker(client)
                unify_helper = LLMUnifyHelper(client)
            except Exception:
                rule_checker = None
                unify_helper = MockUnifyHelper()

            engine = UnifyEngine(
                scene_generator=scene_gen,
                rule_checker=rule_checker,
                unify_helper=unify_helper,
            )
            self.unify_btn.setEnabled(False)
            self.unify_btn.setText("분석 중...")
            self._unify_worker = UnifyAnalyzeWorker(engine, self.state.project)
            self._unify_worker.finished.connect(self._on_unify_analyzed)
            self._unify_worker.error.connect(self._on_unify_error)
            self._unify_worker.start()
        except Exception as e:
            self.unify_btn.setEnabled(True)
            self.unify_btn.setText("전체 통일화")
            QMessageBox.critical(self, "통일화 실패", str(e))

    def _on_unify_analyzed(self, report: UnifyReport) -> None:
        self.unify_btn.setEnabled(True)
        self.unify_btn.setText("전체 통일화")

        dialog = UnifyDialog(report, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._pending_report = report
            client = self._build_lm_client()
            scene_gen = LMStudioOpenAICompatibleGenerator(client)
            engine = UnifyEngine(scene_generator=scene_gen)
            self._unify_apply_worker = UnifyApplyWorker(engine, self.state.project, report)
            self._unify_apply_worker.finished.connect(self._on_unify_applied)
            self._unify_apply_worker.error.connect(self._on_unify_error)
            self.unify_btn.setEnabled(False)
            self.unify_btn.setText("적용 중...")
            self._unify_apply_worker.start()

    def _on_unify_applied(self, modified_ids: list) -> None:
        self.unify_btn.setEnabled(True)
        self.unify_btn.setText("전체 통일화")
        self._refresh_progress_ui()
        if modified_ids:
            QMessageBox.information(self, "통일화 완료",
                f"{len(modified_ids)}개 장면이 수정되었습니다:\n{', '.join(modified_ids)}")
        else:
            QMessageBox.information(self, "통일화 완료", "수정된 장면이 없습니다.")

    def _on_unify_error(self, msg: str) -> None:
        self.unify_btn.setEnabled(True)
        self.unify_btn.setText("전체 통일화")
        QMessageBox.critical(self, "통일화 오류", msg)

    # ─── Project management ───

    def _new_project(self) -> None:
        self.state = AppState(project=build_default_project())
        self._sync_ui_from_project()

    def _save_project(self) -> None:
        try:
            self._apply_project_settings_to_model()
            path, _ = QFileDialog.getSaveFileName(self, "프로젝트 저장", "", "Novel Project (*.json)")
            if not path:
                return
            save_project(self.state.project, path)
        except Exception as e:
            QMessageBox.critical(self, "저장 실패", str(e))

    def _load_project(self) -> None:
        try:
            path, _ = QFileDialog.getOpenFileName(self, "프로젝트 불러오기", "", "Novel Project (*.json)")
            if not path:
                return
            project = load_project(path)
            self.state = AppState(project=project, current_branch_id="root")
            self._sync_ui_from_project()
        except Exception as e:
            QMessageBox.critical(self, "불러오기 실패", str(e))

    def _sync_ui_from_project(self) -> None:
        p = self.state.project
        self.project_title.setText(p.title)
        self.genre.setText(p.genre)
        self.tone.setText(p.tone)
        self.viewpoint.setText(p.narrative_viewpoint)
        self.style.setText(p.style_preset)
        self.world_rules.setPlainText("\n".join(p.world_rules))
        self.scene_text.blockSignals(True)
        self.scene_text.clear()
        self.scene_text.blockSignals(False)
        self.summary_text.clear()
        self.meta_objective.clear()
        self.meta_conflict.clear()
        self.meta_outcome.clear()
        self.save_scene_btn.setEnabled(False)
        self.save_meta_btn.setEnabled(False)
        self.delete_scene_btn.setEnabled(False)
        self.state.viewing_scene_id = None
        self.current_branch_label.setText(f"현재 분기: {self.state.current_branch_id}")
        self.current_scene_label.setText("현재 장면: (없음)")
        self.ending_status_label.setText("도달 가능 결말: (없음)")
        self._refresh_char_list()
        self._update_nav_buttons()
        self._refresh_options()

    # ─── Character Management ───
    def _refresh_char_list(self) -> None:
        self.char_list_combo.blockSignals(True)
        self.scene_pov_combo.blockSignals(True)
        
        self.char_list_combo.clear()
        self.scene_pov_combo.clear()
        
        self.char_list_combo.addItem("새 인물 추가...", "")
        self.scene_pov_combo.addItem("기본(전지적/작품기본)", "protagonist")
        
        for cid, cp in self.state.project.characters.items():
            self.char_list_combo.addItem(f"{cp.name} ({cp.role})", cid)
            self.scene_pov_combo.addItem(f"{cp.name}", cid)
            
        self.char_list_combo.blockSignals(False)
        self.scene_pov_combo.blockSignals(False)

    def _on_char_selected(self) -> None:
        cid = self.char_list_combo.currentData()
        if not cid:
            self.char_name.clear()
            self.char_role.clear()
            self.char_personality.clear()
            self.char_background.clear()
            return
        
        cp = self.state.project.characters.get(cid)
        if cp:
            self.char_name.setText(cp.name)
            self.char_role.setText(cp.role)
            self.char_personality.setPlainText(cp.personality)
            self.char_background.setPlainText(cp.background)

    def _save_character(self) -> None:
        name = self.char_name.text().strip()
        role = self.char_role.text().strip()
        if not name:
            QMessageBox.warning(self, "입력 오류", "이름을 입력하세요.")
            return

        cid = self.char_list_combo.currentData()
        if not cid:
            cid = f"char_{len(self.state.project.characters) + 1}_{hash(name)%1000}"

        cp = CharacterProfile(
            character_id=cid,
            name=name,
            role=role,
            personality=self.char_personality.toPlainText().strip(),
            background=self.char_background.toPlainText().strip()
        )
        self.state.project.characters[cid] = cp
        self._refresh_char_list()
        
        idx = self.char_list_combo.findData(cid)
        if idx >= 0:
            self.char_list_combo.setCurrentIndex(idx)
            
        QMessageBox.information(self, "저장 완료", f"'{name}' 설정이 저장되었습니다.")

    def _auto_character_profile(self) -> None:
        name = self.char_name.text().strip()
        role = self.char_role.text().strip()
        if not name or not role:
            QMessageBox.warning(self, "입력 오류", "이름과 역할을 먼저 입력하세요.")
            return

        client = self._build_lm_client()
        helper = LLMCharacterHelper(client)
        self._char_gen_worker = CharacterProfileGenerateWorker(helper, self.state.project, name, role)
        self._char_gen_worker.finished.connect(self._on_auto_char_profile_done)
        self._char_gen_worker.error.connect(lambda e: QMessageBox.critical(self, "오류", str(e)))
        self.char_auto_btn.setEnabled(False)
        self.char_auto_btn.setText("생성 중...")
        self._char_gen_worker.start()

    def _on_auto_char_profile_done(self, prof: dict) -> None:
        self.char_auto_btn.setEnabled(True)
        self.char_auto_btn.setText("LLM 자동 설정")
        self.char_personality.setPlainText(prof.get("personality", ""))
        self.char_background.setPlainText(prof.get("background", ""))
        self._save_character()

    def _extract_characters_from_scene(self) -> None:
        sid = self.state.viewing_scene_id
        if not sid:
            QMessageBox.warning(self, "안내", "먼저 추출할 장면을 선택하세요.")
            return
            
        scene = self.state.project.scenes.get(sid)
        if not scene or not scene.full_text:
            QMessageBox.warning(self, "안내", "장면 본문이 비어 있습니다.")
            return

        client = self._build_lm_client()
        helper = LLMCharacterHelper(client)
        self._char_ext_worker = CharacterExtractWorker(helper, self.state.project, scene.full_text)
        self._char_ext_worker.finished.connect(self._on_char_extract_done)
        self._char_ext_worker.error.connect(self._on_char_extract_error)
        self.char_extract_btn.setEnabled(False)
        self.char_extract_btn.setText("추출 중...")
        self._char_ext_worker.start()

    def _on_char_extract_done(self, items: list) -> None:
        self.char_extract_btn.setEnabled(True)
        self.char_extract_btn.setText("현재 장면에서 새 인물 추출")
        if not items:
            QMessageBox.information(self, "추출 완료", "새롭게 등장한 비중있는 인물이 없습니다.")
            return
            
        added = []
        for item in items:
            name = item.get("name", "").strip()
            if not name: continue
            
            exists = any(p.name == name for p in self.state.project.characters.values())
            if not exists:
                cid = f"char_{len(self.state.project.characters) + 1}_{hash(name)%1000}"
                cp = CharacterProfile(
                    character_id=cid,
                    name=name,
                    role=item.get("role", "역할 미상"),
                    personality=item.get("personality", ""),
                    background=item.get("background", "")
                )
                self.state.project.characters[cid] = cp
                added.append(name)
                
        self._refresh_char_list()
        if added:
            QMessageBox.information(self, "추출 완료", f"새 등장인물이 추가되었습니다:\n{', '.join(added)}")
        else:
            QMessageBox.information(self, "추출 완료", "새 인물이 감지되었으나 이미 등록된 인물이거나 이름이 없습니다.")

    def _on_char_extract_error(self, msg: str) -> None:
        self.char_extract_btn.setEnabled(True)
        self.char_extract_btn.setText("현재 장면에서 새 인물 추출")
        QMessageBox.critical(self, "추출 오류", msg)

    # ─── Progress UI ───

    def _refresh_progress_ui(self) -> None:
        project = self.state.project
        scene_count = len(project.scenes)
        total_chars = sum(len(s.full_text or "") for s in project.scenes.values())
        estimated_pages = total_chars / 1800 if total_chars else 0.0

        gi = len(project.acts.get(ActType.RISE, []))
        seung = len(project.acts.get(ActType.DEVELOPMENT, []))
        jeon = len(project.acts.get(ActType.TURN, []))
        gyeol = len(project.acts.get(ActType.CONCLUSION, []))

        self.progress_label.setText(f"진행도: {scene_count}장면 / 약 {estimated_pages:.1f}페이지")
        self.progress_bar.setValue(min(int(estimated_pages), 500))
        self.act_ratio_label.setText(f"막 분포: 기 {gi} | 승 {seung} | 전 {jeon} | 결 {gyeol}")
        self.path_label.setText(f"분기 경로: {self._build_branch_path(self.state.current_branch_id)}")

        # [A] Update flow bar
        self.flow_bar.set_project(project, self.state.viewing_scene_id)

        # [C] + [E] Tab lists with highlight and numbering
        for i, act in enumerate(ACT_ORDER):
            act_list = self.act_scene_lists[act]
            act_list.blockSignals(True)
            act_list.clear()
            scene_ids = project.acts.get(act, [])
            for j, scene_id in enumerate(scene_ids):
                scene = project.scenes.get(scene_id)
                if not scene:
                    continue
                one_line = (scene.summary or "").replace("\n", " ")
                if len(one_line) > 55:
                    one_line = one_line[:55] + "..."
                prefix = "[수정됨] " if scene.user_modified else ""
                label = f"{j + 1}. {prefix}{scene.scene_id} | {one_line}"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, scene.scene_id)

                # [C] Highlight current scene
                if scene.scene_id == self.state.viewing_scene_id:
                    item.setBackground(QColor(ACT_COLORS[act].lighter(180)))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)

                act_list.addItem(item)

            act_list.blockSignals(False)
            count = len(scene_ids)
            self.act_tabs.setTabText(i, f"{ACT_LABELS[act]} ({count})")

    def _build_branch_path(self, branch_id: str) -> str:
        chain = []
        current = branch_id
        visited = set()
        while current and current not in visited and current in self.state.project.branches:
            visited.add(current)
            chain.append(current)
            current = self.state.project.branches[current].parent_branch_id or ""
        chain.reverse()
        return " > ".join(chain) if chain else "root"


def main() -> None:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
