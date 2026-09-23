//! Cycle — 하나의 실험을 담는 그릇.
//!
//! 상위 Cycle Graph([`Cycles`](crate::Cycles))에서는 Node 하나로 보이고, 안에는
//! Step Graph([`Walk`])가 산다.
//!
//! 부모는 **태어날 때 기록된다** — Step 과 같은 규칙이다. 되돌아감의 출처(`revisit_from`)도
//! 같다: 되돌아온 뒤 난 첫 Cycle 에만 한 번 적히고 바뀌지 않으며, **계보의 변이 아니다.**
//!
//! # 내부 Outcome 이 닫혀도 Cycle 은 아직 열려 있다
//!
//! ```text
//! 내부 Outcome 닫힘  →  Cycle Report 작성  →  Cycle Closed  →  Cycle Exit
//! ```
//!
//! Cycle Report 는 닫힘의 **필수 조건**이다. 그래서 `cycle_exit` 은 여는 것이 아니다 —
//! 경계는 Step 이 아니라 Cycle 을 닫는 행위가 지나가는 자리다.
//!
//! # 여기가 문지기다
//!
//! [`Walk`] 는 자기가 어느 Cycle 안에 있는지 모르고, 닫혔는지도 모른다. 닫힌 Cycle 안에서
//! Step 이 움직이지 못하게 막는 것은 이 자리의 몫이다 — **닫힘의 진실원은 [`Cycle::status`]
//! 하나뿐**이고, 걷기 쪽에 같은 사실을 복제해 두지 않는다.

use std::fmt;

use crate::node::{NodeKind, NodeStatus};
use crate::report::Report;
use crate::rules::RuleSet;
use crate::contract::CloseContract;
use crate::validate::GrammarError;
use crate::cycles::CycleId;
use crate::refs::{CycleRef, ExistenceRef, JourneyRef, RefSyntaxError, SnapshotRef, StepRef};
use crate::walk::{NodeId, RestoreError, Walk, WalkError, WalkState};

use serde::Deserialize;

/// Cycle 의 종류.
///
/// 둘은 같은 수명과 같은 Cycle Report 어휘를 쓰지만 **안의 Step 문법이 다르다** —
/// 그 차이는 `gil-spec.yaml` 의 `cycle_kinds` 안에 산다.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CycleKind {
    /// 사용자의 의도를 문장으로 만들고 인간의 승인을 받는다. 프로젝트의 첫 Cycle 이다.
    Interview,
    Experiment,
}

impl CycleKind {
    /// 모든 종류. 시험이 전수로 훑을 때 쓴다.
    pub const ALL: [CycleKind; 2] = [CycleKind::Interview, CycleKind::Experiment];

    /// `gil-spec.yaml` 에 적히는 이름.
    pub fn as_str(self) -> &'static str {
        match self {
            CycleKind::Interview => "interview",
            CycleKind::Experiment => "experiment",
        }
    }

    /// 사람이 적어 준 이름을 종류로 읽는다. 모르는 이름이면 `None`.
    ///
    /// 이름의 목록을 여기 다시 적지 않는다 — [`CycleKind::ALL`] 이 이미 그것을 안다.
    pub fn parse(name: &str) -> Option<CycleKind> {
        CycleKind::ALL.into_iter().find(|kind| kind.as_str() == name)
    }
}

impl fmt::Display for CycleKind {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// Cycle Report 가 판정한 자리를 가리키는 칸.
const OUTCOME_REF: &str = "outcome_ref";
/// Cycle Report 가 다음에 무엇을 할지 적는 칸.
const NEXT_ACTION: &str = "next_direction.action";
/// Step Outcome 과 Cycle Report 가 함께 쓰는 판정의 칸 이름.
const VERDICT: &str = "verdict";
/// Outcome 이 그 판정에서 남은 것을 적는 칸.
const LESSON: &str = "lesson";
/// Interview Outcome 이 근거로 삼은 Synthesis 를 가리키는 칸.
const SYNTHESIS_REF: &str = "synthesis_ref";
/// Synthesis 가 인간의 승인을 적는 칸.
const APPROVED: &str = "approved";
/// Synthesis 가 근거로 삼은 Interview Node 들을 가리키는 칸.
const BASIS_REFS: &str = "basis_refs";
/// 승인을 뜻하는 유일한 값.
const YES: &str = "yes";

/// Cycle Report 가 가리키는 판정의 주소.
///
/// **typed StepRef 다** — `step:C1/S4`. Step 이름은 소속 Cycle 안에서만 유일하므로 bare `4` 나
/// 화면 축약 `#4` 로는 어느 Cycle 의 판정인지 정해지지 않는다(Node Model §2.1).
///
/// 칸이 있다는 것은 문법이 이미 보증한다. 여기서 답하는 것은 **적힌 글자가 주소로 읽히는가**
/// 하나뿐이다. 그 주소가 이 Cycle 의 마지막 판정인지는 [`Cycle::check_outcome_ref`] 가 본다.
fn outcome_ref_of(report: &Report, expected: StepRef) -> Result<StepRef, OutcomeRefError> {
    let raw = report
        .get(OUTCOME_REF)
        .expect("close_requires 가 outcome_ref 를 요구한다");
    raw.parse().map_err(|source| OutcomeRefError::Unreadable {
        value: raw.to_string(),
        source,
        expected,
    })
}

/// 한 실험 — 안에 Step Graph 를 담는다.
#[derive(Debug, Clone)]
pub struct Cycle {
    id: CycleId,
    /// 같은 Cycle Graph 안에서 어느 Cycle 의 세계를 이어받아 났는가.
    ///
    /// `None` 은 고아가 아니라 **이 Graph 의 뿌리**라는 뜻이다. 한 번 적히면 바뀌지 않고,
    /// 실행 순서로 되계산하지 않는다 — Step 의 `parent` 와 같은 규칙이다.
    parent: Option<CycleId>,
    /// **어느 실패가 이 갈래를 낳았는가.** 되돌아온 뒤 난 첫 Cycle 에만 있다.
    ///
    /// `parent` 와 **다른 것**이다. `parent` 는 누구의 사고와 세계를 이어받았는가이고,
    /// 이 값은 어느 결정에서 갈라져 나왔는가다. **계보는 이것을 따라가지 않는다** —
    /// 따라가면 되돌아오며 버린 갈래가 조상으로 섞인다(Spec §17 · Time Model §6).
    ///
    /// 평범한 `open_child` 로 난 Cycle 에는 없다. 한 번 적히면 바뀌지 않고, 자손에게
    /// 전파되지도 않는다.
    revisit_from: Option<CycleId>,
    kind: CycleKind,
    status: NodeStatus,
    /// **누가 이 Cycle 을 열었는가.** 열 때 한 번 정해지고 lifetime 동안 바뀌지 않는다.
    ///
    /// 연 Existence 와 닫는 Existence 는 같아야 한다(Node Model §13-6). 그래서 이 값은
    /// 소유의 증거이자 provenance 다.
    existence: ExistenceRef,
    /// **어떤 Journey 판에서 닫았는가.** Close 때 확정된다.
    ///
    /// 아직 `None` 뿐이다 — Node Close 의 통합 transaction 은 다음 걸음의 몫이고,
    /// 없는 것을 채워 두지 않는다. 채워진 파일은 복원이 거절한다.
    journey: Option<JourneyRef>,
    /// 닫히면서 받는다. 열려 있는 동안은 `None`.
    report: Option<Report>,
    /// **이 Cycle 을 연 전이가 출발한 세계.** 생성과 동시에 실재한다(Artifact Model §7.1).
    ///
    /// ```text
    /// 뿌리          gil start 의 최초 Snapshot
    /// open_child    부모의 exit_snapshot_ref
    /// ```
    ///
    /// `Option` 이 아니다 — 「나중에 채울 null」을 두면 그 null 을 읽는 규칙이 생기고,
    /// 그 규칙은 채워진 뒤에도 남는다.
    entry: SnapshotRef,
    /// **닫히면서 확정한 세계.** 열려 있는 동안은 `None`.
    ///
    /// 새 세계를 만들지 않는다 — 안에서 이미 확정된 것 중 **마지막 Outcome 의 계보에서
    /// 가장 가까운 Verify** 를 고르고, 없으면 Entry 를 물려받는다(§7.5).
    exit: Option<SnapshotRef>,
    steps: Walk,
}

impl Cycle {
    /// 실험 하나를 연다. 안의 Step Graph 는 시작 경계에 선다.
    ///
    /// 이름과 부모는 **여기서 한 번 정해지고 바뀌지 않는다.** 여는 것은 [`Cycles`] 뿐이다
    /// — 이름을 발급하는 자리가 하나여야 두 Cycle 이 같은 이름을 받지 않는다.
    ///
    /// [`Cycles`]: crate::Cycles
    pub(crate) fn start(
        rules: RuleSet,
        id: CycleId,
        kind: CycleKind,
        existence: ExistenceRef,
        parent: Option<CycleId>,
        entry: SnapshotRef,
    ) -> Cycle {
        Cycle {
            id,
            parent,
            revisit_from: None,
            kind,
            status: NodeStatus::Open,
            existence,
            journey: None,
            report: None,
            entry,
            exit: None,
            steps: Walk::start(rules, id.to_ref(), kind, existence),
        }
    }

    /// 이 Cycle 의 이름.
    pub fn id(&self) -> CycleId {
        self.id
    }

    /// 이 Cycle 이 어느 Cycle 의 세계를 이어받아 났는가. 뿌리면 `None`.
    pub fn parent(&self) -> Option<CycleId> {
        self.parent
    }

    /// **어느 실패가 이 갈래를 낳았는가.** 되돌아온 뒤 난 첫 Cycle 에만 있다.
    ///
    /// 계보를 물을 때 이것을 따라가지 않는다 — 그것이 이 값과 [`Cycle::parent`] 의 차이다.
    pub fn revisit_from(&self) -> Option<CycleId> {
        self.revisit_from
    }

    /// 되돌아온 뒤 난 첫 Cycle 에 제 출처를 새긴다 — **이름을 발급한 자리만 부른다.**
    pub(crate) fn born_from_revisit(&mut self, from: CycleId) {
        self.revisit_from = Some(from);
    }

    pub fn kind(&self) -> CycleKind {
        self.kind
    }

    /// 이 Cycle 을 연 Existence. 열 때 정해지고 바뀌지 않는다.
    pub fn existence(&self) -> ExistenceRef {
        self.existence
    }

    /// 이 Cycle 을 닫은 Journey 판. 열려 있는 동안은 `None`.
    ///
    /// 컨테이너인 Cycle 의 Close 는 **새 판을 만들지 않는다**(Existence Model §4) —
    /// 그때의 `current_journey_ref` 를 provenance 로 적을 뿐이다.
    pub fn journey(&self) -> Option<JourneyRef> {
        self.journey
    }

    pub fn status(&self) -> NodeStatus {
        self.status
    }

    pub fn is_closed(&self) -> bool {
        self.status == NodeStatus::Closed
    }

    /// 이 Cycle 을 연 전이가 출발한 세계. **언제나 있다.**
    pub fn entry_snapshot(&self) -> SnapshotRef {
        self.entry
    }

    /// 이 Cycle 이 닫히며 확정한 세계. 열려 있는 동안은 `None`.
    pub fn exit_snapshot(&self) -> Option<SnapshotRef> {
        self.exit
    }

    /// 이 Cycle 안에서 **지금 유효한 세계** — 캐시가 아니라 구조에서 유도한다.
    ///
    /// ```text
    /// 닫힌 Cycle                    exit_snapshot_ref
    /// 서 있는 자리의 계보에 Verify   가장 가까운 Verify.snapshot_ref
    /// 없으면                        entry_snapshot_ref
    /// ```
    ///
    /// 이름의 크기도 저장 배열의 순서도 보지 않는다 — **버려진 가지에도 더 큰 이름이
    /// 있다.** 오직 `parent` 사슬만 거슬러 오른다(Artifact Model §7.6·§9).
    pub fn world_snapshot(&self) -> SnapshotRef {
        if let Some(exit) = self.exit {
            return exit;
        }
        self.verify_in_lineage().unwrap_or(self.entry)
    }

    /// 서 있는 자리의 계보에서 **가장 가까운 닫힌 Verify** 가 확정한 세계.
    ///
    /// 계보를 뿌리부터 받아 **뒤에서부터** 훑는다 — 가장 가까운 것이 먼저 잡힌다.
    /// 서 있는 자리 자신도 포함한다(닫힌 Verify 위에 서 있을 수 있다).
    fn verify_in_lineage(&self) -> Option<SnapshotRef> {
        let here = self.steps.current()?;
        let lineage = self.steps.lineage(here).ok()?;
        lineage
            .iter()
            .rev()
            .filter(|node| node.kind == NodeKind::Verify && node.is_closed())
            .find_map(|node| node.snapshot)
    }

    /// 닫히면서 받은 Cycle Report. 열려 있는 동안은 `None`.
    pub fn report(&self) -> Option<&Report> {
        self.report.as_ref()
    }

    /// 안의 Step Graph. 읽기만 한다.
    pub fn steps(&self) -> &Walk {
        &self.steps
    }

    /// 이 Cycle 이 따르는 Grammar.
    pub fn rules(&self) -> &RuleSet {
        self.steps.rules()
    }

    /// 그 종류의 Step 을 닫는 계약 — **자리 주소까지 붙여서.**
    ///
    /// 계약을 읽는 자리가 하나여야 Receipt·help·거절이 같은 말을 한다([`CloseContract`]).
    pub fn step_contract(&self, step: NodeId, kind: NodeKind) -> Option<CloseContract> {
        CloseContract::of_step(
            self.rules(),
            self.kind,
            kind,
            format!("{} · {kind}", self.step_ref(step)),
        )
    }

    /// 아직 열지 않은 종류의 Step 을 닫는 계약 — 자리 대신 종류만 밝힌다.
    pub fn contract_of_kind(&self, kind: NodeKind) -> Option<CloseContract> {
        CloseContract::of_step(self.rules(), self.kind, kind, kind.to_string())
    }

    /// 이 Cycle 자신을 닫는 계약.
    pub fn close_contract(&self) -> Option<CloseContract> {
        CloseContract::of_cycle(
            self.rules(),
            self.kind,
            format!("{} · {}", self.id.to_ref(), self.kind),
        )
    }

    /// 안에서 다음 Step 을 연다.
    pub fn open_step(&mut self, kind: NodeKind) -> Result<(), CycleError> {
        self.must_be_open()?;
        self.check_interview_branch(kind)?;
        self.steps.open(kind).map_err(CycleError::Step)
    }

    /// Synthesis 뒤에 무엇이 열리는가는 **인간의 답이 가른다.**
    ///
    /// ```text
    /// Synthesis(no)  → Question        왜 아닌지 다시 묻는다
    /// Synthesis(yes) → Outcome(success) 인간 승인을 근거로 성공한다
    /// ```
    ///
    /// 문법은 `synthesis → question | outcome` 까지만 안다. 어느 쪽인지는 Report 의 값이라
    /// 문법이 볼 수 없다(Cycle Model §13 「전이 의미」). 여기서 가르지 않으면 두 가지 일이
    /// 생긴다 — `no` 를 받은 제안 위에서 Cycle 이 성공으로 닫히고, `yes` 를 받고도 갈 곳이
    /// 둘로 보여 사람이 고르지 않아도 될 것을 고르게 된다.
    fn check_interview_branch(&self, kind: NodeKind) -> Result<(), CycleError> {
        if self.kind != CycleKind::Interview {
            return Ok(());
        }
        let here = self.steps.current().and_then(|id| self.steps.node(id));
        let Some(approved) = here
            .filter(|node| node.kind == NodeKind::Synthesis && node.is_closed())
            .and_then(|node| node.report.as_ref())
            .and_then(|report| report.get(APPROVED))
        else {
            // Synthesis 위가 아니면 가를 것이 없다 — 문법이 알아서 판정한다.
            return Ok(());
        };

        let wanted = match approved {
            YES => NodeKind::Outcome,
            _ => NodeKind::Question,
        };
        match kind == wanted {
            true => Ok(()),
            false => Err(SynthesisRefError::WrongBranch {
                approved: approved.to_string(),
                asked: kind,
                wanted,
            }
            .into()),
        }
    }

    /// 안에서 열려 있는 Step 을 닫고 **어느 판에서 닫았는지**까지 새긴다.
    ///
    /// [`Project`](crate::Project) 의 통합 transaction 만 부른다 — 판은 Journey 쪽의 것이라
    /// Cycle 이 스스로 알 수 없다.
    pub(crate) fn close_step_into(
        &mut self,
        report: Report,
        journey: JourneyRef,
        world: Option<SnapshotRef>,
    ) -> Result<NodeId, CycleError> {
        let at = self.step_now_open().ok_or(CycleError::Step(WalkError::NothingToClose))?;
        self.close_step_with(report, world)?;
        self.steps.record_journey(at, journey);
        Ok(at)
    }

    /// 이 Cycle 을 닫고 그때 서 있던 판을 provenance 로 새긴다.
    pub(crate) fn close_into(
        &mut self,
        report: Report,
        journey: JourneyRef,
    ) -> Result<(), CycleError> {
        self.close(report)?;
        self.journey = Some(journey);
        Ok(())
    }

    /// 닫히면서 확정될 Exit 세계 — **아직 닫지 않은 채로 미리 묻는다.**
    ///
    /// 마지막 Outcome 의 계보에서 가장 가까운 닫힌 Verify, 없으면 Entry(§7.5). 새 세계를
    /// 만들지 않으므로 이 값은 언제나 이미 registry 에 있는 이름이다.
    pub fn exit_would_be(&self) -> SnapshotRef {
        self.verify_in_lineage().unwrap_or(self.entry)
    }

    /// 안에서 열려 있는 Step 을 닫는다. **Verify 는 이 문으로 닫히지 않는다.**
    pub fn close_step(&mut self, report: Report) -> Result<(), CycleError> {
        self.close_step_with(report, None)
    }

    /// 관측한 세계와 함께 Verify 를 닫는다.
    pub fn close_verify_step(
        &mut self,
        report: Report,
        world: SnapshotRef,
    ) -> Result<(), CycleError> {
        self.close_step_with(report, Some(world))
    }

    fn close_step_with(
        &mut self,
        report: Report,
        world: Option<SnapshotRef>,
    ) -> Result<(), CycleError> {
        self.must_be_open()?;
        if let Some(at) = self.step_now_open() {
            self.check_synthesis_ref(at, &report)?;
            self.check_basis_refs(at, &report)?;
        }
        match world {
            Some(world) => self.steps.close_verify(report, world),
            None => self.steps.close(report),
        }
        .map_err(CycleError::Step)
    }

    /// 지금 **열려 있는** Step. 끝 경계에 서 있으면 없다.
    ///
    /// 컨테이너인 Cycle 은 안에 열린 자리가 있는 동안 닫히지 않고, 열린 실행형 Step 하나가
    /// 곧 Current Will 의 target 이다(Will Model §5). 그래서 이 자리를 밖에서도 묻는다.
    pub fn step_now_open(&self) -> Option<NodeId> {
        self.steps
            .current()
            .filter(|id| self.steps.node(*id).is_some_and(|node| !node.is_closed()))
    }

    /// `target` 이 `here` 의 **구조적 Lineage** 에 속하는가 — `parent` 사슬만 따라 잰다.
    ///
    /// Time Model 이 말하는 Lineage 다. `revisit_from` 은 **출처**일 뿐 lineage 간선이
    /// 아니므로 이 길로 들어오지 않는다. `here` 자신은 제 조상이 아니다.
    ///
    /// 이름의 크기·저장 배열의 순서·닫힌 시각은 **보지 않는다**. 버려진 가지에도 더 작은
    /// 이름이 있고, 그런 자리를 근거로 삼는 것을 막는 것이 이 검사의 전부다.
    fn in_lineage_of(&self, here: NodeId, target: NodeId) -> Result<bool, CycleError> {
        let lineage = self.steps.lineage(here).map_err(CycleError::Step)?;
        Ok(lineage
            .iter()
            .any(|node| node.id == target && node.id != here))
    }

    /// Synthesis 가 **무엇을 근거로 그 문장을 지었는가.**
    ///
    /// 명세 §16: *"Synthesis 는 근거 없는 새로운 목표나 제약을 추가할 수 없다."* 그 근거는
    /// 이 Interview 안에서 **이미 닫힌 Question 또는 Interpretation** 이며, 이 제안이
    /// **딛고 온 길 위에 있어야** 한다 — 현재 Synthesis 의 구조적 Lineage 다.
    ///
    /// Lineage 는 [`Cycle::in_lineage_of`] 가 `parent` 사슬로만 잰다. 버려진 가지의 더 작은
    /// 이름도, 되돌아감으로만 닿는 자리도, 이 제안 뒤에 난 자리도 그 길 위에 없다 —
    /// 셋 다 같은 이유로 거절된다.
    ///
    /// 문법은 block scalar 안에 **한 줄에 하나**다(§16). 쉼표로 이어 붙인 목록을 위해 범용
    /// list 문법을 만들지 않는다 — 한 줄에 하나면 각 줄이 그대로 하나의 주소다.
    ///
    /// Report 원문은 그대로 보존한다. 여기서 하는 것은 **읽어서 재는 것**뿐이다.
    fn check_basis_refs(&self, at: NodeId, report: &Report) -> Result<(), CycleError> {
        let Some(node) = self
            .steps
            .node(at)
            .filter(|node| node.kind == NodeKind::Synthesis)
        else {
            return Ok(());
        };
        // 칸이 아예 없는 것과 비워 둔 것은 **같은 실패**다 — 근거가 하나도 없다.
        // 파서는 그 둘을 구분할 수 있지만 도메인이 말할 것은 하나뿐이다.
        let raw = report.get(BASIS_REFS).unwrap_or_default();

        let mut seen: Vec<StepRef> = Vec::new();
        for line in raw.lines() {
            let line = line.trim();
            if line.is_empty() {
                continue;
            }
            let target: StepRef = line.parse().map_err(|source| BasisRefError::Unreadable {
                value: line.to_string(),
                source,
                cycle: self.id.to_ref(),
            })?;
            if target.cycle() != self.id.to_ref() {
                return Err(BasisRefError::OtherCycle {
                    target,
                    cycle: self.id.to_ref(),
                }
                .into());
            }
            if seen.contains(&target) {
                return Err(BasisRefError::Duplicated { target }.into());
            }

            let step = NodeId::from_raw(target.step());
            let basis = self
                .steps
                .node(step)
                .ok_or(BasisRefError::NotFound { target })?;
            if !matches!(basis.kind, NodeKind::Question | NodeKind::Interpretation) {
                return Err(BasisRefError::WrongKind {
                    target,
                    kind: basis.kind,
                }
                .into());
            }
            if !basis.is_closed() {
                return Err(BasisRefError::StillOpen {
                    target,
                    here: self.step_ref(node.id),
                }
                .into());
            }
            // 딛고 온 길 위에 있는가. 이름의 크기도 닫힌 시각도 보지 않는다.
            if !self.in_lineage_of(node.id, step)? {
                return Err(BasisRefError::NotInLineage {
                    target,
                    here: self.step_ref(node.id),
                }
                .into());
            }
            seen.push(target);
        }

        match seen.is_empty() {
            true => Err(BasisRefError::Empty {
                cycle: self.id.to_ref(),
            }
            .into()),
            false => Ok(()),
        }
    }

    /// Interview Outcome 이 가리킨 자리가 **이 Cycle 의 승인된 Synthesis** 인가.
    ///
    /// `synthesis_ref` 는 `step:C1/S5` 꼴의 StepRef 다(명세 §17). Step 이름은 소속 Cycle
    /// 안에서만 유일하므로, 종류 없는 이름으로는 어느 Cycle 의 것인지 정해지지 않는다.
    ///
    /// 칸이 있는지는 문법이 본다. 여기서 보는 것은 이 걷기만 알 수 있는 넷이다 — 이 Cycle 의
    /// 주소인가 · 그런 Closed Synthesis 가 있는가 · **이 Outcome 의 Lineage 위에 있는가** ·
    /// 그것이 `yes` 를 받았는가. `basis_refs` 와 같은 출처 원칙을 그대로 적용한다.
    ///
    /// 지금의 전이 문법(§13)이 우연히 부모 Synthesis 만 닿게 하더라도 여기서 **직접** 잰다.
    /// 손으로 고친 저장 파일이 전이 규칙을 우회하는 길이 되면 안 된다.
    fn check_synthesis_ref(&self, at: NodeId, report: &Report) -> Result<(), CycleError> {
        if self.kind != CycleKind::Interview {
            return Ok(());
        }
        let Some(here) = self
            .steps
            .node(at)
            .filter(|node| node.kind == NodeKind::Outcome)
        else {
            return Ok(());
        };
        // 없으면 문법이 거절한다 — 여기서 같은 것을 두 번 묻지 않는다.
        let Some(raw) = report.get(SYNTHESIS_REF) else {
            return Ok(());
        };

        let target: StepRef = raw
            .parse()
            .map_err(|source| SynthesisRefError::Unreadable {
                value: raw.to_string(),
                source,
            })?;
        if target.cycle() != self.id.to_ref() {
            return Err(SynthesisRefError::OtherCycle {
                target,
                here: self.id,
            }
            .into());
        }

        let step = NodeId::from_raw(target.step());
        let node = self
            .steps
            .node(step)
            .filter(|node| node.kind == NodeKind::Synthesis && node.is_closed())
            .ok_or(SynthesisRefError::NotASynthesis { target })?;
        if !self.in_lineage_of(here.id, step)? {
            return Err(SynthesisRefError::NotInLineage {
                target,
                here: self.step_ref(here.id),
            }
            .into());
        }
        match node.report.as_ref().and_then(|report| report.get(APPROVED)) {
            Some(YES) => Ok(()),
            other => Err(SynthesisRefError::NotApproved {
                approved: other.unwrap_or("").to_string(),
            }
            .into()),
        }
    }

    /// 안에 적혀 있는 되돌아감을 밟는다.
    pub fn revisit_step(&mut self) -> Result<(), CycleError> {
        self.must_be_open()?;
        self.steps.revisit().map_err(CycleError::Step)
    }

    /// 지금 실제로 열 수 있는 Step 의 종류들. 닫힌 Cycle 에서는 아무것도 못 연다.
    ///
    /// **여기서 규칙을 다시 쓰지 않는다** — Cycle 을 복제해 실제로 열어 보고 답한다.
    /// 안내와 실행이 갈리면 안내를 믿은 Agent 가 한 번 실패하고서야 옳은 수를 알게 된다
    /// (실사용 보고 #123). Interview 의 승인 문지기도 이 길로 함께 반영된다.
    pub fn openable_here(&self) -> Vec<NodeKind> {
        NodeKind::ALL
            .into_iter()
            .filter(|kind| self.clone().open_step(*kind).is_ok())
            .collect()
    }

    /// 지금 이 Cycle 을 닫을 수 있는가 — 안의 Step Graph 가 끝 경계에 닿았는가.
    ///
    /// 판정은 [`Walk::at_exit`] 에게 넘긴다. 규칙은 문법이 갖는다.
    pub fn can_close(&self) -> bool {
        !self.is_closed() && self.steps.at_exit()
    }

    /// 이 Cycle 을 Cycle Report 로 닫는다.
    ///
    /// 세 가지를 본다 — 안이 끝났는가 · Report 가 문법에 맞는가 · 가리킨 Outcome 이 실재하고
    /// 같은 판정을 말하는가. 앞의 둘은 [`RuleSet`] 이 판정하고, 마지막은 이 걷기만 알 수 있다
    /// (`outcome_ref` 는 이 Cycle 안에서만 뜻이 있는 이름이다).
    pub fn close(&mut self, report: Report) -> Result<(), CycleError> {
        self.must_be_open()?;
        if !self.steps.at_exit() {
            return Err(CycleError::StepsNotDone);
        }

        self.rules()
            .validate_cycle_close(self.kind, &report)
            .map_err(CycleError::Grammar)?;
        self.check_outcome_ref(&report)?;

        // **Exit 은 고르는 것이 아니라 유도되는 것이다.** 그래서 인자로 받지 않는다 —
        // 받으면 부르는 쪽이 버려진 가지의 세계를 넣을 길이 생긴다.
        self.exit = Some(self.exit_would_be());
        self.status = NodeStatus::Closed;
        self.report = Some(report);
        Ok(())
    }

    /// 가리킨 자리가 **이 Cycle 의 마지막 판정**이고 같은 판정을 말하는가.
    ///
    /// 명세 §11: *"outcome_ref 는 내부 Step Graph 의 마지막 Outcome Report 를 가리킨다."*
    /// 아무 닫힌 Outcome 이나 받으면, 마지막이 `success` 인데 옛 `failure` 를 가리켜 Cycle 을
    /// `failure` 로 닫을 수 있다 — 그러면 Cycle Report 가 제 안의 기록과 다른 말을 한다.
    ///
    /// **여기서 묻는 것은 하나뿐이다: 서 있는 자리인가.** 그 자리가 닫힌 Outcome 이라는 것은
    /// [`Walk::at_exit`] 가 이미 보증했고(그것만이 `cycle_exit` 을 지날 수 있는 자리다),
    /// 같은 것을 두 자리에서 물으면 언젠가 한쪽이 낡는다.
    ///
    /// 두 verdict 는 서로 다른 계층의 판정이라 각자 소유한다. 다만 값은 같아야 한다.
    fn check_outcome_ref(&self, report: &Report) -> Result<(), CycleError> {
        let last = self
            .steps
            .current()
            .expect("끝 경계에 닿았다면 서 있는 자리가 있다");
        let expected = self.step_ref(last);

        // 거절할 때마다 **기대하는 그 주소**를 함께 말한다 — 무엇이 틀렸는지 알아도
        // 무엇을 적어야 하는지 모르면 사람은 한 번 더 틀린다.
        let target = outcome_ref_of(report, expected)?;
        if target.cycle() != self.id.to_ref() {
            return Err(OutcomeRefError::OtherCycle { target, expected }.into());
        }
        let node = self
            .steps
            .node(NodeId::from_raw(target.step()))
            .ok_or(OutcomeRefError::NotFound { target, expected })?;
        if node.kind != NodeKind::Outcome {
            return Err(OutcomeRefError::NotAnOutcome {
                target,
                kind: node.kind,
                expected,
            }
            .into());
        }
        if target != expected {
            return Err(OutcomeRefError::NotTheLastOutcome { target, expected }.into());
        }

        let theirs = node
            .report
            .as_ref()
            .expect("끝 경계에 닿은 자리는 닫힌 Outcome 이다")
            .get(VERDICT)
            .expect("닫힌 Outcome 은 verdict 를 지닌다");
        let ours = report.get(VERDICT).expect("close_requires 가 요구한다");
        if ours != theirs {
            return Err(OutcomeRefError::VerdictDisagrees {
                target: expected,
                cycle: ours.to_string(),
                outcome: theirs.to_string(),
            }
            .into());
        }
        Ok(())
    }

    /// 이 Cycle 안의 Step 을 가리키는 **typed reference** — `step:C1/S4`.
    ///
    /// Step 이름은 소속 Cycle 안에서만 유일하다. 그래서 주소를 만드는 자리는 Cycle 이다 —
    /// 제 이름을 아는 것이 여기뿐이기 때문이다.
    pub fn step_ref(&self, step: NodeId) -> StepRef {
        self.steps.step_ref(step)
    }

    /// 이 Cycle 의 **유일한 Define** 의 Report. 아직 적지 않았으면 `None`.
    ///
    /// 하나의 Experiment Cycle 에는 Define 이 정확히 하나뿐이고, 닫히면 problem 과
    /// success_condition 은 바뀌지 않는다(Cycle Model §7). 그래서 "그 실험이 무엇이었나" 의
    /// 원본은 언제나 이 자리 하나다 — **Cycle Report 에 복제하지 않고 여기서 읽는다.**
    ///
    /// 읽는 쪽이 둘이다(`gil story` 의 Cycle 절과 `gil context` 의 이전 Cycle 절). 그래서
    /// 원본을 찾아가는 길은 여기 하나로 둔다 — 두 자리에 적으면 한쪽이 낡는다.
    pub fn define(&self) -> Option<&Report> {
        self.steps
            .nodes()
            .iter()
            .find(|node| node.kind == NodeKind::Define)?
            .report
            .as_ref()
    }

    /// 이 Interview 가 **처음 던진 질문**. Experiment 의 `define()` 에 대응한다.
    ///
    /// 되묻기로 Question 이 여럿이어도 **첫 번째**가 이 Cycle 의 출발 질문이다 — 나중 질문은
    /// 그 출발에서 갈라져 나온 것이고, Cycle 이 무엇을 묻고 있었는지는 첫 질문이 말한다.
    /// 지금 어디에 서 있는지는 별개의 사실이라 섞지 않는다.
    ///
    /// 열려 있으면 Report 가 아직 없다 — 그때는 `None` 이 아니라 **그 Node** 를 돌려주어,
    /// 읽는 쪽이 「아직 묻는 중」과 「아직 묻지 않았다」를 가릴 수 있게 한다.
    pub fn opening_question(&self) -> Option<&crate::walk::StepNode> {
        self.steps
            .nodes()
            .iter()
            .find(|node| node.kind == NodeKind::Question)
    }

    /// 이 Cycle 의 판정이 **근거로 삼은 그 Outcome** 의 lesson. 열려 있으면 없다.
    ///
    /// 서 있는 자리에서 꺼내지 않고 Cycle Report 에 **적힌 참조**를 따라간다 — 무엇을 근거로
    /// 판정했는지는 Cycle Report 가 이미 적어 두었고, 읽는 쪽은 그것을 따를 뿐이다.
    /// 되돌아가 버린 갈래의 판정은 이 참조가 가리키지 않으므로 함께 오지 않는다.
    pub fn judged_lesson(&self) -> Option<&str> {
        let raw = self.report.as_ref()?.get(OUTCOME_REF)?;
        let target: StepRef = raw.parse().ok()?;
        let step = NodeId::from_raw(target.step());
        self.steps.node(step)?.report.as_ref()?.get(LESSON)
    }

    /// 이 Cycle 이 **닫히면서 적어 둔** 다음 방향. 열려 있으면 아직 없다.
    ///
    /// 무엇을 할지는 여기 이미 적혀 있다. 위 계층은 그것을 **밟을** 뿐, 다시 고르지 않는다 —
    /// Step 의 되돌아감과 같은 모양이다(근거와 이동이 떨어지지 않는다).
    pub fn declared_action(&self) -> Option<&str> {
        self.report.as_ref()?.get(NEXT_ACTION)
    }

    fn must_be_open(&self) -> Result<(), CycleError> {
        match self.is_closed() {
            true => Err(CycleError::AlreadyClosed),
            false => Ok(()),
        }
    }

    /// 저장이 읽어 온 값으로 Cycle 을 다시 세운다.
    ///
    /// 안의 걷기는 [`Walk::restore`] 가 재고, 여기서는 **Cycle 층의 불변식**만 다시 잰다.
    pub(crate) fn restore(rules: RuleSet, state: CycleState) -> Result<Cycle, RestoreError> {
        let cycle = Cycle {
            id: state.id,
            parent: state.parent,
            revisit_from: state.revisit_from,
            kind: state.kind,
            status: state.status,
            existence: state.existence,
            journey: state.journey,
            report: state.report,
            entry: state.entry,
            exit: state.exit,
            steps: Walk::restore(rules, state.id.to_ref(), state.kind, state.existence, state.steps)?,
        };

        cycle.check_restored_refs()?;

        match (cycle.status, &cycle.report) {
            (NodeStatus::Open, Some(_)) => return Err(RestoreError::ReportOnOpenCycle),
            (NodeStatus::Closed, None) => return Err(RestoreError::CycleClosedWithoutReport),
            (NodeStatus::Open, None) => {}
            (NodeStatus::Closed, Some(report)) => {
                // 닫힌 Cycle 은 **닫을 수 있었던 자리**에서 닫혔어야 한다.
                if !cycle.steps.at_exit() {
                    return Err(RestoreError::CycleClosedTooEarly);
                }
                // 닫을 때 통과했어야 하는 검사를 그대로 다시 잰다 — 파일은 두 번째 통로다.
                cycle
                    .rules()
                    .validate_cycle_close(cycle.kind, report)
                    .map_err(|source| RestoreError::CycleReport {
                        source: Box::new(CycleError::Grammar(source)),
                    })?;
                cycle
                    .check_outcome_ref(report)
                    .map_err(|source| RestoreError::CycleReport {
                        source: Box::new(source),
                    })?;
            }
        }

        Ok(cycle)
    }

    /// 실려 온 Step Report 들의 **참조 출처**를 다시 잰다.
    ///
    /// 닫을 때 통과했어야 하는 검사를 파일에서도 그대로 잰다 — 저장 파일은 두 번째 통로이지
    /// **전이 규칙을 우회하는 뒷문이 아니다.** `parent` 를 손으로 고쳐 다른 가지의 Synthesis 를
    /// 근거로 세운 파일은 여기서 멈춘다.
    fn check_restored_refs(&self) -> Result<(), RestoreError> {
        for node in self.steps.nodes() {
            let Some(report) = node.report.as_ref() else {
                continue;
            };
            let checked = self
                .check_basis_refs(node.id, report)
                .and_then(|()| self.check_synthesis_ref(node.id, report));
            checked.map_err(|source| RestoreError::StepReport {
                step: self.step_ref(node.id),
                source: Box::new(source),
            })?;
        }
        Ok(())
    }
}

/// 저장에서 되살려 온 Cycle 의 값들 — [`Cycle::restore`] 의 입구.
///
/// **저장 형식이 아니라 Cycle 의 상태다.** 디스크에 어떤 꼴로 눕는지는 `store` 만 안다.
pub(crate) struct CycleState {
    pub id: CycleId,
    pub parent: Option<CycleId>,
    pub revisit_from: Option<CycleId>,
    pub kind: CycleKind,
    pub status: NodeStatus,
    pub existence: ExistenceRef,
    pub journey: Option<JourneyRef>,
    pub report: Option<Report>,
    pub entry: SnapshotRef,
    pub exit: Option<SnapshotRef>,
    pub steps: WalkState,
}

/// Cycle 이 거절한 이유.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CycleError {
    /// 안의 걷기가 거절했다.
    Step(WalkError),
    /// 이 Cycle 은 이미 닫혔다.
    AlreadyClosed,
    /// 안의 Step Graph 가 아직 끝 경계에 닿지 않았다.
    StepsNotDone,
    /// Cycle Report 가 문법에 맞지 않는다.
    Grammar(GrammarError),
    /// 가리킨 Outcome 이 이 Cycle 안에서 성립하지 않는다.
    OutcomeRef(OutcomeRefError),
    /// 가리킨 Synthesis 가 이 Interview 안에서 성립하지 않는다.
    SynthesisRef(SynthesisRefError),
    /// 적어 둔 근거가 이 Interview 안에서 성립하지 않는다.
    BasisRefs(BasisRefError),
}

/// `basis_refs` 가 이 Interview 안에서 성립하지 않는 이유.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BasisRefError {
    /// 한 줄이 Step 주소로 읽히지 않는다 — bare `1` · `#1` · 쉼표로 이은 목록이 여기로 온다.
    Unreadable {
        value: String,
        source: RefSyntaxError,
        cycle: CycleRef,
    },
    /// 다른 Cycle 의 Step 을 가리킨다.
    OtherCycle { target: StepRef, cycle: CycleRef },
    /// 같은 자리를 두 번 적었다.
    Duplicated { target: StepRef },
    /// 이 Cycle 에 그런 Step 이 없다.
    NotFound { target: StepRef },
    /// 근거가 될 수 없는 Kind 다.
    WrongKind { target: StepRef, kind: NodeKind },
    /// 아직 열려 있는 자리다 — 닫히지 않은 것은 근거가 아니다.
    StillOpen { target: StepRef, here: StepRef },
    /// 이 Synthesis 가 딛고 온 길(구조적 Lineage) 위에 없다 — 버려진 가지 · 되돌아감으로만
    /// 닿는 자리 · 이 제안 뒤에 난 자리가 모두 여기로 온다.
    NotInLineage { target: StepRef, here: StepRef },
    /// 근거를 하나도 적지 않았다 — 칸이 없든 비었든 같은 실패다.
    Empty { cycle: CycleRef },
}

impl From<BasisRefError> for CycleError {
    fn from(err: BasisRefError) -> Self {
        CycleError::BasisRefs(err)
    }
}

impl fmt::Display for BasisRefError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            BasisRefError::Unreadable {
                value,
                source,
                cycle,
            } => write!(
                f,
                "{BASIS_REFS} 의 {value:?} 는 Step 주소로 읽히지 않는다 — {source}.\n\
                 한 줄에 하나씩 적는다: {BASIS_REFS}: |\n    step:{}/S1\n    step:{}/S2",
                cycle.id(),
                cycle.id()
            ),
            BasisRefError::OtherCycle { target, cycle } => write!(
                f,
                "{BASIS_REFS} 가 {target} 을(를) 가리키는데 그것은 다른 Cycle 의 자리다 — \
                 근거는 이 Interview({}) 안에 있어야 한다",
                cycle
            ),
            BasisRefError::Duplicated { target } => {
                write!(f, "{BASIS_REFS} 에 {target} 이(가) 두 번 적혔다")
            }
            BasisRefError::NotFound { target } => {
                write!(f, "{BASIS_REFS} 가 가리키는 {target} 이(가) 이 Cycle 에 없다")
            }
            BasisRefError::WrongKind { target, kind } => write!(
                f,
                "{target} 은(는) {kind} 라 근거가 될 수 없다 — {BASIS_REFS} 는 이미 닫힌 \
                 question 또는 interpretation 을 가리킨다"
            ),
            BasisRefError::StillOpen { target, here } => write!(
                f,
                "{target} 은(는) 아직 열려 있다 — {here} 는 이미 닫힌 question 또는 \
                 interpretation 만 근거로 삼는다"
            ),
            BasisRefError::NotInLineage { target, here } => write!(
                f,
                "{target} 은(는) {here} 가 딛고 온 길 위에 없다 — 근거는 이 제안의 \
                 Lineage(부모 사슬) 안에 있어야 한다. 버려진 가지나 되돌아감으로만 닿는 \
                 자리는 이름이 더 작아도 근거가 아니다"
            ),
            BasisRefError::Empty { cycle } => write!(
                f,
                "{BASIS_REFS} 에 근거가 하나도 없다 — Synthesis 는 근거 없는 목표나 제약을 \
                 더하지 않는다.\n\
                 한 줄에 하나씩 적는다: {BASIS_REFS}: |\n    step:{}/S1",
                cycle.id()
            ),
        }
    }
}

impl std::error::Error for BasisRefError {}

/// `synthesis_ref` 가 이 Interview 안에서 성립하지 않는 이유.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SynthesisRefError {
    /// StepRef 로 읽히지 않는다.
    Unreadable {
        value: String,
        source: RefSyntaxError,
    },
    /// 다른 Cycle 의 Step 을 가리킨다.
    OtherCycle { target: StepRef, here: CycleId },
    /// 그 자리에 닫힌 Synthesis 가 없다.
    NotASynthesis { target: StepRef },
    /// 이 Outcome 이 딛고 온 길(구조적 Lineage) 위에 없는 Synthesis 다.
    NotInLineage { target: StepRef, here: StepRef },
    /// 그 Synthesis 는 인간의 승인을 받지 못했다.
    NotApproved { approved: String },
    /// 인간의 답이 가리키는 갈래가 아니다.
    WrongBranch {
        approved: String,
        asked: NodeKind,
        wanted: NodeKind,
    },
}

impl From<SynthesisRefError> for CycleError {
    fn from(err: SynthesisRefError) -> Self {
        CycleError::SynthesisRef(err)
    }
}

impl fmt::Display for SynthesisRefError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            SynthesisRefError::Unreadable { value, source } => write!(
                f,
                "{SYNTHESIS_REF} 의 {value:?} 는 Step 주소로 읽히지 않는다 — {source}"
            ),
            SynthesisRefError::OtherCycle { target, here } => write!(
                f,
                "{SYNTHESIS_REF} 가 {target} 을(를) 가리키는데 여기는 {here} 다 — \
                 근거는 이 Interview 안에 있어야 한다"
            ),
            SynthesisRefError::NotASynthesis { target } => write!(
                f,
                "{target} 에는 닫힌 Synthesis 가 없다 — {SYNTHESIS_REF} 는 승인을 받은 제안을 \
                 가리켜야 한다"
            ),
            SynthesisRefError::NotInLineage { target, here } => write!(
                f,
                "{target} 은(는) {here} 가 딛고 온 길 위에 없다 — success 는 이 Outcome 의 \
                 Lineage(부모 사슬) 안에 있는 승인된 Synthesis 로만 닫는다"
            ),
            SynthesisRefError::NotApproved { approved } => write!(
                f,
                "그 Synthesis 의 {APPROVED} 는 {approved:?} 다 — 인간이 {YES} 로 승인한 제안만 \
                 Interview 의 근거가 된다"
            ),
            SynthesisRefError::WrongBranch {
                approved,
                asked,
                wanted,
            } => write!(
                f,
                "그 Synthesis 의 {APPROVED} 가 {approved:?} 라 다음은 {wanted} 다 — \
                 {asked} 는 이 갈래가 아니다.\n\
                 승인 여부가 다음 자리를 가른다: yes 면 판정으로, 아니면 다시 묻는 질문으로."
            ),
        }
    }
}

impl std::error::Error for SynthesisRefError {}

/// `outcome_ref` 가 이 Cycle 안에서 성립하지 않는 이유.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum OutcomeRefError {
    /// Step 주소로 읽히지 않는다 — bare `4` 와 화면 축약 `#4` 가 여기로 온다.
    Unreadable {
        value: String,
        source: RefSyntaxError,
        expected: StepRef,
    },
    /// 다른 Cycle 의 Step 을 가리킨다.
    OtherCycle { target: StepRef, expected: StepRef },
    /// 이 Cycle 에 그런 Step 이 없다.
    NotFound { target: StepRef, expected: StepRef },
    /// 그 자리는 판정이 아니다.
    NotAnOutcome {
        target: StepRef,
        kind: NodeKind,
        expected: StepRef,
    },
    /// 이 Cycle 의 **마지막 판정**이 아니다 — 지나간 판정을 근거로 삼을 수 없다.
    NotTheLastOutcome { target: StepRef, expected: StepRef },
    /// 두 계층의 판정이 어긋난다.
    VerdictDisagrees {
        target: StepRef,
        cycle: String,
        outcome: String,
    },
}

impl From<OutcomeRefError> for CycleError {
    fn from(err: OutcomeRefError) -> Self {
        CycleError::OutcomeRef(err)
    }
}

impl fmt::Display for CycleError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            CycleError::Step(err) => write!(f, "{err}"),
            CycleError::AlreadyClosed => write!(
                f,
                "이 Cycle 은 이미 닫혔다 — 닫힌 Cycle 안에서는 아무것도 움직이지 않는다"
            ),
            CycleError::StepsNotDone => write!(
                f,
                "아직 이 Cycle 을 닫을 수 없다 — 안의 Outcome 이 닫혀 있어야 한다"
            ),
            CycleError::Grammar(err) => write!(f, "{err}"),
            CycleError::OutcomeRef(err) => write!(f, "{err}"),
            CycleError::SynthesisRef(err) => write!(f, "{err}"),
            CycleError::BasisRefs(err) => write!(f, "{err}"),
        }
    }
}

impl fmt::Display for OutcomeRefError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            OutcomeRefError::Unreadable {
                value,
                source,
                expected,
            } => write!(
                f,
                "{OUTCOME_REF} 의 {value:?} 는 Step 주소로 읽히지 않는다 — {source}.\n\
                 여기 적을 것: {OUTCOME_REF}: {expected}"
            ),
            OutcomeRefError::OtherCycle { target, expected } => write!(
                f,
                "{OUTCOME_REF} 가 {target} 을(를) 가리키는데 그것은 다른 Cycle 의 자리다.\n\
                 여기 적을 것: {OUTCOME_REF}: {expected}"
            ),
            OutcomeRefError::NotFound { target, expected } => write!(
                f,
                "{OUTCOME_REF} 가 가리키는 {target} 이(가) 이 Cycle 에 없다.\n\
                 여기 적을 것: {OUTCOME_REF}: {expected}"
            ),
            OutcomeRefError::NotAnOutcome {
                target,
                kind,
                expected,
            } => write!(
                f,
                "{target} 은(는) {kind} 라 판정이 아니다 — {OUTCOME_REF} 는 판정을 가리킨다.\n\
                 여기 적을 것: {OUTCOME_REF}: {expected}"
            ),
            OutcomeRefError::NotTheLastOutcome { target, expected } => write!(
                f,
                "{OUTCOME_REF} 는 이 Cycle 의 **마지막 판정**을 가리켜야 한다 \
                 — {target} 이(가) 아니라 {expected} 다.\n\
                 지나간 판정을 근거로 삼으면 Cycle Report 가 제 안의 기록과 다른 말을 하게 된다."
            ),
            OutcomeRefError::VerdictDisagrees {
                target,
                cycle,
                outcome,
            } => write!(
                f,
                "Cycle 은 {cycle:?} 라 하고 {target} 은(는) {outcome:?} 라 한다 — \
                 두 판정은 계층이 다르지만 값은 같아야 한다"
            ),
        }
    }
}

impl std::error::Error for CycleError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            CycleError::Step(err) => Some(err),
            CycleError::Grammar(err) => Some(err),
            CycleError::OutcomeRef(err) => Some(err),
            CycleError::SynthesisRef(err) => Some(err),
            CycleError::BasisRefs(err) => Some(err),
            CycleError::AlreadyClosed | CycleError::StepsNotDone => None,
        }
    }
}

impl std::error::Error for OutcomeRefError {}
