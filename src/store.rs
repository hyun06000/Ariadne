//! Cycle 을 디스크에 눕히고 다시 세운다.
//!
//! Agent 의 한 턴은 한 프로세스다. 저장이 없으면 `open` 다음 턴에 닫을 것이 없다 —
//! 그래서 저장은 편의가 아니라 **일이 프로세스를 넘게 하는 유일한 길**이다.
//!
//! # 이 파일은 두 번째 통로다
//!
//! Agent 는 파일을 직접 쓸 수 있다. 즉 도메인의 메서드를 거치지 않고 상태를 바꿀 수 있고,
//! v0 에는 그것을 막을 신뢰 경계가 없다. **막을 수 없으니 이름을 붙여 둔다.**
//! 대신 되살릴 때 [`Cycle::restore`] 가 두 계층의 불변식을 처음부터 다시 재고, 만들 수 없는
//! 꼴이면 파일을 거절한다 — 조용히 이상한 것이 되살아나는 것보다 낫다.
//!
//! # 형식은 버릴 수 있다
//!
//! 파일 첫 줄의 `format` 이 그것을 스스로 말한다. 모르는 번호는 읽지 않고 거절하고,
//! **앞 형식을 만나면 조용히 무시하지 않고 앞 형식이라고 말한다.**
//!
//! 그래서 코어 타입([`Cycles`]·`Cycle`·`Walk`·[`Report`](crate::Report))에는 `Serialize` 를
//! 달지 않는다.
//! 디스크의 꼴은 여기 있는 `Stored*` 만 안다 — 코어에 달면 그 순간 형식이 공개 계약이 된다.

use std::collections::BTreeMap;
use std::ffi::OsString;
use std::fmt;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize, Serializer};

use crate::cycle::{CycleKind, CycleState};
use crate::cycles::{CycleId, Cycles, CyclesState};
use crate::existence::{Existence, ExistenceState, Journey, Revision};
use crate::project::{Project, ProjectError};
use crate::refs::{
    ExistenceRef, JourneyRef, KnowledgeRef, MemoryRef, RefSyntaxError, RelationRef, StateRef,
    WillRef,
};
use crate::node::{NodeKind, NodeStatus};
use crate::report::Report;
use crate::rules::RuleSet;
use crate::walk::{NodeId, RestoreError, StepNode, WalkState};
use crate::will::Will;

/// 이 크레이트가 읽고 쓰는 저장 형식의 번호.
///
/// 0 은 걷기 하나, 1 은 Cycle 하나, 2 는 Cycle Graph, 3 은 **Project State** 다 —
/// World Graph 옆에 지속적 Existence 들과 「지금 누가 행동하는가」가 함께 눕는다.
/// 모양이 바뀔 때마다 올린다 —
/// 그래야 앞 형식을 만났을 때 파서 오류가 아니라 **앞 형식이라고** 말할 수 있다.
pub const FORMAT: u32 = 3;

/// 저장소 안에서 상태가 눕는 자리.
pub const STATE_PATH: &str = ".gil/state.yaml";

/// 앞 형식이 눕던 자리. 읽지는 않고, 만나면 **말한다**.
pub const LEGACY_WALK_PATH: &str = ".gil/walk.yaml";

/// 지금 상태를 파일에 눕힌다. 부모 디렉터리가 없으면 만든다.
///
/// 먼저 옆자리에 쓰고 제자리로 옮긴다 — 쓰다 죽어도 반쯤 쓰인 상태가 남지 않는다.
pub fn save(project: &Project, path: impl AsRef<Path>) -> Result<(), StoreError> {
    let path = path.as_ref();
    let stored = StoredState::from(project);
    let text = serde_norway::to_string(&stored).map_err(StoreError::Encode)?;

    if let Some(parent) = path.parent()
        && !parent.as_os_str().is_empty()
    {
        fs::create_dir_all(parent).map_err(|source| StoreError::Write {
            path: parent.display().to_string(),
            source,
        })?;
    }

    let mut temp = OsString::from(path.as_os_str());
    temp.push(".writing");
    let temp = PathBuf::from(temp);

    fs::write(&temp, text).map_err(|source| StoreError::Write {
        path: temp.display().to_string(),
        source,
    })?;
    fs::rename(&temp, path).map_err(|source| StoreError::Write {
        path: path.display().to_string(),
        source,
    })
}

/// 파일에서 상태를 다시 세운다.
///
/// 규칙은 파일에 없다 — [`RuleSet`] 은 언제나 `gil-spec.yaml` 에서 새로 읽어 넘긴다.
/// 문법이 바뀌면 저장된 것도 **새 문법으로** 판정받아야 하고, 파일에 넣어 두면 그러지 못한다.
pub fn load(rules: RuleSet, path: impl AsRef<Path>) -> Result<Project, StoreError> {
    let path = path.as_ref();
    let text = fs::read_to_string(path).map_err(|source| match source.kind() {
        io::ErrorKind::NotFound => StoreError::NotFound {
            path: path.display().to_string(),
        },
        _ => StoreError::Read {
            path: path.display().to_string(),
            source,
        },
    })?;

    // **형식을 먼저 읽는다.** 구조를 통째로 해석한 뒤에 보면, 모양이 바뀐 앞 형식은
    // "앞 형식이다" 가 아니라 파서 오류로 도착한다 — 사람이 무엇을 해야 할지 모른다.
    let head: StoredFormat = serde_norway::from_str(&text).map_err(StoreError::Decode)?;
    match head.format.cmp(&FORMAT) {
        std::cmp::Ordering::Less => {
            return Err(StoreError::PreviousFormat {
                found: head.format,
                current: FORMAT,
                path: path.display().to_string(),
            });
        }
        std::cmp::Ordering::Greater => {
            return Err(StoreError::UnknownFormat {
                found: head.format,
                known: FORMAT,
            });
        }
        std::cmp::Ordering::Equal => {}
    }

    let stored: StoredState = serde_norway::from_str(&text).map_err(StoreError::Decode)?;
    stored.into_project(rules)
}

/// typed reference 하나를 읽는다. 무엇의 자리였는지를 함께 말한다.
fn read_ref<T: std::str::FromStr<Err = RefSyntaxError>>(
    text: &str,
    field: &'static str,
) -> Result<T, StoreError> {
    text.parse().map_err(|source| StoreError::BadRef {
        field,
        value: text.to_string(),
        source,
    })
}

/// 있으면 읽고 없으면 그대로 없다.
fn read_opt_ref<T: std::str::FromStr<Err = RefSyntaxError>>(
    text: &Option<String>,
    field: &'static str,
) -> Result<Option<T>, StoreError> {
    match text {
        Some(text) => read_ref(text, field).map(Some),
        None => Ok(None),
    }
}

impl StoredState {
    /// 읽어 온 값으로 프로젝트를 다시 세운다.
    ///
    /// 두 축을 각자 세운 뒤 [`Project::restore`] 가 **서로 맞물리는지**를 잰다.
    fn into_project(self, rules: RuleSet) -> Result<Project, StoreError> {
        let current: ExistenceRef = read_ref(&self.current_existence_ref, "current_existence_ref")?;

        let mut existences = BTreeMap::new();
        for (name, stored) in self.existences {
            let id: ExistenceRef = read_ref(&format!("existence:{name}"), "existences.<name>")?;
            existences.insert(id.number(), stored.into_existence(id)?);
        }

        let mut states = BTreeMap::new();
        for name in self.existence_states.into_keys() {
            let id: StateRef = read_ref(&format!("state:{name}"), "existence_states.<name>")?;
            states.insert(id.number(), ExistenceState);
        }

        let cycles = Cycles::restore(rules, self.cycles.into_state()?).map_err(StoreError::NotValid)?;
        Project::restore(cycles, existences, states, current, self.next_will_id)
            .map_err(StoreError::NotWhole)
    }
}

impl StoredExistence {
    fn into_existence(self, id: ExistenceRef) -> Result<Existence, StoreError> {
        let current: JourneyRef = read_ref(&self.current_journey_ref, "current_journey_ref")?;

        let active = match self.journey.active_will {
            Some(will) => Some(will.into_will()?),
            None => None,
        };
        let mut done = Vec::with_capacity(self.journey.done_wills.len());
        for will in self.journey.done_wills {
            done.push(will.into_will()?);
        }

        let mut revisions = BTreeMap::new();
        for (name, stored) in self.journey.revisions {
            // 판의 이름은 그 Journey 안에서만 뜻이 있다 — 소유자를 붙여 읽는다.
            let named: JourneyRef = read_ref(&format!("journey:{}@{name}", id.id()), "revisions.<name>")?;
            revisions.insert(named.revision(), stored.into_revision()?);
        }
        Ok(Existence::restore(
            id,
            current,
            Journey::restore(active, done, revisions),
        ))
    }
}

impl StoredWill {
    fn into_will(self) -> Result<Will, StoreError> {
        Ok(Will::restore(
            // 객체 자신의 이름은 bare 로 실린다 — 읽을 때 종류를 붙여 준다.
            read_ref(&format!("will:{}", self.id), "will.id")?,
            read_ref(&self.existence_ref, "will.existence_ref")?,
            read_ref(&self.target_node_ref, "will.target_node_ref")?,
            self.objective,
            self.next_action,
            self.done_when,
        ))
    }
}

impl From<&Will> for StoredWill {
    fn from(will: &Will) -> Self {
        StoredWill {
            id: will.id().id(),
            existence_ref: will.existence().to_string(),
            target_node_ref: will.target().to_string(),
            objective: will.objective().to_string(),
            next_action: will.next_action().to_string(),
            done_when: will.done_when().to_string(),
        }
    }
}

impl StoredRevision {
    fn into_revision(self) -> Result<Revision, StoreError> {
        // **비울 수 없는 자리다.** Existence 가 있는데 State 가 없는 상태는 없다.
        let Some(state) = self.existence_state_ref else {
            return Err(StoreError::JourneyWithoutState);
        };
        Ok(Revision::restore(
            read_ref(&state, "existence_state_ref")?,
            read_opt_ref::<KnowledgeRef>(&self.knowledge_head_ref, "knowledge_head_ref")?,
            read_opt_ref::<MemoryRef>(&self.memory_head_ref, "memory_head_ref")?,
            read_opt_ref::<RelationRef>(&self.relations_head_ref, "relations_head_ref")?,
            read_opt_ref::<WillRef>(&self.will_head_ref, "will_head_ref")?,
        ))
    }
}

/// 형식 번호만 먼저 보는 눈.
///
/// 나머지 칸은 일부러 **모른 척한다** — 모양이 어떻게 바뀌었든 번호는 읽혀야 한다.
#[derive(Debug, Deserialize)]
struct StoredFormat {
    format: u32,
}

/// 디스크에 눕는 상태의 꼴. **저장만 아는 모양이다.**
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct StoredState {
    /// 첫 줄에 온다 — 파일이 제 형식을 스스로 밝히게.
    format: u32,
    /// **프로젝트 전체의** Will 이름 발급기. Existence 가 달라도 이름을 나눠 쓰지 않는다
    /// (Node Model §2.1). 그래서 Journey 안이 아니라 뿌리에 있다.
    next_will_id: u32,
    /// 지금 행동하는 존재. `existence:X1` 꼴의 typed reference 다.
    current_existence_ref: String,
    /// 프로젝트 안에서 지속되는 행동 주체들. 이름은 bare(`X1`) 로 적는다 —
    /// **제 이름은 bare, 남을 가리키는 자리만 종류를 지닌다**(Node Model §2.1).
    existences: BTreeMap<String, StoredExistence>,
    /// 그들의 State 객체들. 지금은 내용이 없다.
    existence_states: BTreeMap<String, StoredExistenceState>,
    cycles: StoredCycles,
}

/// 지속적 Existence 하나.
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct StoredExistence {
    current_journey_ref: String,
    journey: StoredJourney,
}

/// Journey — 판들과, 아직 짓지 않은 Will 의 자리.
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct StoredJourney {
    /// 지금 하려는 하나의 행동. **inline 객체다** — Done 이 되기 전에 별도 object store 를
    /// 만들지 않는다(Will Model §4).
    active_will: Option<StoredWill>,
    /// 끝낸 행동들, 끝낸 순서대로. **ref 목록이 아니라 객체 목록이다.**
    done_wills: Vec<StoredWill>,
    revisions: BTreeMap<String, StoredRevision>,
}

/// 행동 한 단위.
///
/// `id` 는 bare(`W1`), 남을 가리키는 칸은 종류를 지닌다(`existence:X1` · `step:C1/S1`).
/// **status 칸이 없다** — Active 인지 Done 인지는 이 객체가 어느 자리에 실렸는가가 말한다.
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct StoredWill {
    id: String,
    existence_ref: String,
    target_node_ref: String,
    objective: String,
    next_action: String,
    done_when: String,
}

/// Journey 의 한 판.
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct StoredRevision {
    /// **비울 수 없는 자리.** `Option` 인 것은 비어 있어도 읽히게 하려는 것이 아니라,
    /// 비었다고 **말해 주기** 위해서다 — serde 오류가 아니라 GIL 의 말로 거절한다.
    existence_state_ref: Option<String>,
    knowledge_head_ref: Option<String>,
    memory_head_ref: Option<String>,
    relations_head_ref: Option<String>,
    will_head_ref: Option<String>,
}

/// Existence State 하나 — 내용이 없다.
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct StoredExistenceState {}

/// Cycle Graph 하나.
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct StoredCycles {
    next_id: u32,
    current: u32,
    nodes: Vec<StoredCycle>,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct StoredCycle {
    id: u32,
    /// 이 Cycle 을 연 존재. Open 시 고정된다.
    existence_ref: String,
    /// 이 Cycle 을 닫은 Journey 판. 컨테이너 Close 는 새 판을 만들지 않고 **그때의
    /// current 판**을 provenance 로 적는다.
    journey_ref: Option<String>,
    /// 읽기는 [`CycleKind`] 가 이미 아는 이름으로 하고, 쓰기만 여기서 한다.
    #[serde(serialize_with = "write_cycle_kind")]
    kind: CycleKind,
    status: StoredStatus,
    parent: Option<u32>,
    /// Cycle 수준의 되돌아감은 아직 없다. 자리를 비워 두되 **채워진 파일은 거절한다** —
    /// 확인할 수 없는 출처를 있는 척 읽지 않는다.
    revisit_from: Option<u32>,
    report: Option<BTreeMap<String, String>>,
    steps: StoredWalk,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct StoredWalk {
    next_id: u32,
    current: Option<u32>,
    pending_revisit: Option<u32>,
    nodes: Vec<StoredNode>,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct StoredNode {
    id: u32,
    #[serde(serialize_with = "write_kind")]
    kind: NodeKind,
    parent: Option<u32>,
    revisit_from: Option<u32>,
    status: StoredStatus,
    /// 이 Step 을 연 존재. Open 시 고정된다.
    existence_ref: String,
    /// 이 Step 을 닫은 Journey 판. 열려 있는 동안은 비어 있다.
    journey_ref: Option<String>,
    report: Option<BTreeMap<String, String>>,
}

/// 상태는 디스크에서도 **적힌 것**이다 — Report 가 있는지로 되계산하지 않는다.
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum StoredStatus {
    Open,
    Closed,
}

fn write_kind<S: Serializer>(kind: &NodeKind, serializer: S) -> Result<S::Ok, S::Error> {
    serializer.serialize_str(kind.as_str())
}

fn write_cycle_kind<S: Serializer>(kind: &CycleKind, serializer: S) -> Result<S::Ok, S::Error> {
    serializer.serialize_str(kind.as_str())
}

fn write_report(report: &Report) -> BTreeMap<String, String> {
    report
        .field_names()
        .map(|name| {
            let value = report.get(name).expect("방금 이름을 받아 온 칸이다");
            (name.to_string(), value.to_string())
        })
        .collect()
}

impl From<&Project> for StoredState {
    fn from(project: &Project) -> Self {
        let (cycles, existences, states, current) = project.parts();
        StoredState {
            format: FORMAT,
            next_will_id: project.next_will_id(),
            current_existence_ref: current.to_string(),
            existences: existences
                .values()
                .map(|existence| (existence.id().id(), StoredExistence::from(existence)))
                .collect(),
            existence_states: states
                .keys()
                .map(|number| {
                    let id = StateRef::new(*number).expect("발급된 State 이름은 reference 가 된다");
                    (id.id(), StoredExistenceState {})
                })
                .collect(),
            cycles: StoredCycles {
                next_id: cycles.next_name(),
                current: cycles.current_id().raw(),
                nodes: cycles.nodes().iter().map(StoredCycle::from).collect(),
            },
        }
    }
}

impl From<&Existence> for StoredExistence {
    fn from(existence: &Existence) -> Self {
        StoredExistence {
            current_journey_ref: existence.current_journey().to_string(),
            journey: StoredJourney {
                active_will: existence.journey().active_will().map(StoredWill::from),
                done_wills: existence
                    .journey()
                    .done_wills()
                    .iter()
                    .map(StoredWill::from)
                    .collect(),
                revisions: existence
                    .journey()
                    .revisions()
                    .map(|(number, revision)| {
                        // 판의 이름은 그 Journey 안에서만 뜻이 있으므로 bare 로 적는다.
                        // 글자를 여기 옮겨 적지 않는다 — reference 타입이 이미 그것을 안다.
                        let name = format!("{}{number}", JourneyRef::LETTER);
                        let stored = StoredRevision {
                            existence_state_ref: Some(revision.existence_state().to_string()),
                            knowledge_head_ref: revision.knowledge_head().map(|h| h.to_string()),
                            memory_head_ref: revision.memory_head().map(|h| h.to_string()),
                            relations_head_ref: revision.relations_head().map(|h| h.to_string()),
                            will_head_ref: revision.will_head().map(|h| h.to_string()),
                        };
                        (name, stored)
                    })
                    .collect(),
            },
        }
    }
}

impl From<&crate::cycle::Cycle> for StoredCycle {
    fn from(cycle: &crate::cycle::Cycle) -> Self {
        let walk = cycle.steps();
        StoredCycle {
            id: cycle.id().raw(),
            existence_ref: cycle.existence().to_string(),
            journey_ref: cycle.journey().map(|journey| journey.to_string()),
            kind: cycle.kind(),
            status: cycle.status().into(),
            parent: cycle.parent().map(CycleId::raw),
            revisit_from: None,
            report: cycle.report().map(write_report),
            steps: StoredWalk {
                next_id: walk.next_id(),
                current: walk.current().map(NodeId::raw),
                pending_revisit: walk.pending_revisit().map(NodeId::raw),
                nodes: walk.nodes().iter().map(StoredNode::from).collect(),
            },
        }
    }
}

impl StoredCycles {
    fn into_state(self) -> Result<CyclesState, StoreError> {
        let mut nodes = Vec::with_capacity(self.nodes.len());
        for cycle in self.nodes {
            nodes.push(cycle.into_state()?);
        }
        Ok(CyclesState {
            next_id: self.next_id,
            current: CycleId::from_raw(self.current),
            nodes,
        })
    }
}

impl StoredCycle {
    fn into_state(self) -> Result<CycleState, StoreError> {
        // Cycle 수준의 되돌아감을 짓지 않았으니 출처를 검사할 수단이 없다.
        // 검사할 수 없는 것을 있는 척 읽는 대신 거절한다 — 없는 것과 못 찾은 것은 다르다.
        if self.revisit_from.is_some() {
            return Err(StoreError::CycleRevisitNotBuilt);
        }
        let mut steps = Vec::with_capacity(self.steps.nodes.len());
        for node in self.steps.nodes {
            steps.push(node.into_step()?);
        }
        Ok(CycleState {
            id: CycleId::from_raw(self.id),
            parent: self.parent.map(CycleId::from_raw),
            kind: self.kind,
            status: self.status.into(),
            existence: read_ref(&self.existence_ref, "cycle.existence_ref")?,
            journey: read_opt_ref(&self.journey_ref, "cycle.journey_ref")?,
            report: self.report.map(|fields| fields.into_iter().collect()),
            steps: WalkState {
                current: self.steps.current.map(NodeId::from_raw),
                next_id: self.steps.next_id,
                pending_revisit: self.steps.pending_revisit.map(NodeId::from_raw),
                nodes: steps,
            },
        })
    }
}

impl From<&StepNode> for StoredNode {
    fn from(node: &StepNode) -> Self {
        StoredNode {
            id: node.id.raw(),
            kind: node.kind,
            parent: node.parent.map(NodeId::raw),
            revisit_from: node.revisit_from.map(NodeId::raw),
            status: node.status.into(),
            existence_ref: node.existence.to_string(),
            journey_ref: node.journey.map(|journey| journey.to_string()),
            report: node.report.as_ref().map(write_report),
        }
    }
}

impl StoredNode {
    fn into_step(self) -> Result<StepNode, StoreError> {
        Ok(StepNode {
            id: NodeId::from_raw(self.id),
            kind: self.kind,
            parent: self.parent.map(NodeId::from_raw),
            revisit_from: self.revisit_from.map(NodeId::from_raw),
            status: self.status.into(),
            existence: read_ref(&self.existence_ref, "step.existence_ref")?,
            journey: read_opt_ref(&self.journey_ref, "step.journey_ref")?,
            report: self.report.map(|fields| fields.into_iter().collect()),
        })
    }
}

impl From<NodeStatus> for StoredStatus {
    fn from(status: NodeStatus) -> Self {
        match status {
            NodeStatus::Open => StoredStatus::Open,
            NodeStatus::Closed => StoredStatus::Closed,
        }
    }
}

impl From<StoredStatus> for NodeStatus {
    fn from(status: StoredStatus) -> Self {
        match status {
            StoredStatus::Open => NodeStatus::Open,
            StoredStatus::Closed => NodeStatus::Closed,
        }
    }
}

/// 저장이 실패한 이유.
#[derive(Debug)]
pub enum StoreError {
    /// 저장된 것이 아직 없다. 잘못이 아니라 **아직 시작하지 않았다**는 사실이다.
    NotFound { path: String },
    /// 앞 형식의 파일을 만났다. 읽지 않고, 있다는 사실을 말한다.
    LegacyFormat { path: String },
    Read { path: String, source: io::Error },
    Write { path: String, source: io::Error },
    Encode(serde_norway::Error),
    Decode(serde_norway::Error),
    /// 이 크레이트가 모르는 형식이다 — 지어내 읽지 않는다.
    UnknownFormat { found: u32, known: u32 },
    /// 이 gil 이 **알지만 더는 읽지 않는** 앞 형식이다.
    PreviousFormat {
        found: u32,
        current: u32,
        path: String,
    },
    /// Cycle 되돌아감의 출처가 적혀 있는데 그것을 검사할 계층이 아직 없다.
    CycleRevisitNotBuilt,
    /// Journey 판이 State 를 가리키지 않는다.
    JourneyWithoutState,
    /// typed reference 로 읽히지 않는 값이 있다.
    BadRef {
        field: &'static str,
        value: String,
        source: RefSyntaxError,
    },
    /// 두 축이 서로 맞물리지 않는다.
    NotWhole(ProjectError),
    /// 읽히기는 했으나 걸어서 만들 수 있는 꼴이 아니다.
    NotValid(RestoreError),
}

impl fmt::Display for StoreError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            StoreError::NotFound { path } => {
                write!(f, "저장된 것이 없다: {path}")
            }
            StoreError::LegacyFormat { path } => write!(
                f,
                "여기 있는 {path} 는 **앞 형식**이라 이 gil 이 읽지 않는다.\n\
                 조용히 무시하지 않으려고 알린다 — 그 안의 기록은 그대로 있다.\n\
                 새로 시작하려면 그 파일을 직접 치우고 `gil start` 를 한다."
            ),
            StoreError::Read { path, source } => {
                write!(f, "저장된 것을 읽지 못했다: {path} — {source}")
            }
            StoreError::Write { path, source } => {
                write!(f, "상태를 쓰지 못했다: {path} — {source}")
            }
            StoreError::Encode(source) => write!(f, "저장할 꼴로 옮기지 못했다: {source}"),
            StoreError::Decode(source) => write!(f, "저장 파일의 형식이 맞지 않다: {source}"),
            StoreError::UnknownFormat { found, known } => write!(
                f,
                "저장 형식 {found} 은(는) 이 gil 이 모른다 (아는 것: {known}) \
                 — 모르는 형식을 짐작해 읽지 않는다"
            ),
            StoreError::PreviousFormat {
                found,
                current,
                path,
            } => write!(
                f,
                "여기 있는 {path} 는 **저장 형식 {found}** 이고, 이 gil 은 {current} 를 읽는다.\n\
                 조용히 무시하지 않으려고 알린다 — 그 안의 기록은 그대로 있다.\n\
                 새로 시작하려면 그 파일을 직접 치우고 `gil start` 를 한다."
            ),
            StoreError::CycleRevisitNotBuilt => write!(
                f,
                "이 파일의 Cycle 이 revisit_from 을 지녔는데, Cycle 수준의 되돌아감은 \
                 아직 짓지 않았다 — 검사할 수 없는 출처를 있는 척 읽지 않는다"
            ),
            StoreError::JourneyWithoutState => write!(
                f,
                "Journey 판에 existence_state_ref 가 없다 — 모든 판은 실재하는 \
                 Existence State 를 가리켜야 한다"
            ),
            StoreError::BadRef {
                field,
                value,
                source,
            } => write!(f, "{field} 의 {value:?} 를 읽지 못했다 — {source}"),
            StoreError::NotWhole(source) => write!(
                f,
                "저장 파일의 세계와 존재가 서로 맞물리지 않는다 — {source}"
            ),
            StoreError::NotValid(source) => write!(
                f,
                "저장 파일이 걸어서 만들 수 없는 꼴을 담고 있다 — {source}"
            ),
        }
    }
}

impl std::error::Error for StoreError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            StoreError::Read { source, .. } | StoreError::Write { source, .. } => Some(source),
            StoreError::Encode(source) | StoreError::Decode(source) => Some(source),
            StoreError::NotValid(source) => Some(source),
            StoreError::NotWhole(source) => Some(source),
            StoreError::BadRef { source, .. } => Some(source),
            StoreError::NotFound { .. }
            | StoreError::LegacyFormat { .. }
            | StoreError::UnknownFormat { .. }
            | StoreError::PreviousFormat { .. }
            | StoreError::CycleRevisitNotBuilt
            | StoreError::JourneyWithoutState => None,
        }
    }
}
