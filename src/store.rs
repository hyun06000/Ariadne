//! 걷기를 디스크에 눕히고 다시 세운다.
//!
//! Agent 의 한 턴은 한 프로세스다. 저장이 없으면 `open` 다음 턴에 닫을 걷기가 없다 —
//! 그래서 저장은 편의가 아니라 **걷기가 프로세스를 넘게 하는 유일한 길**이다.
//!
//! # 이 파일은 두 번째 통로다
//!
//! Agent 는 파일을 직접 쓸 수 있다. 즉 걷기의 메서드를 거치지 않고 상태를 바꿀 수 있고,
//! v0 에는 그것을 막을 신뢰 경계가 없다. **막을 수 없으니 이름을 붙여 둔다.**
//! 대신 되살릴 때 [`Walk::restore`] 가 불변식을 처음부터 다시 재고, 걷기가 만들 수 없는
//! 꼴이면 파일을 거절한다 — 조용히 이상한 걷기가 되살아나는 것보다 낫다.
//!
//! # 형식은 버릴 수 있다
//!
//! 파일 첫 줄의 `format: 0` 이 그것을 스스로 말한다. 0 은 **약속하지 않는 번호**다 —
//! 다음 형식이 이것을 읽어 줄 의무가 없고, 모르는 번호는 읽지 않고 거절한다.
//!
//! 그래서 코어 타입([`Walk`]·`StepNode`·[`Report`](crate::Report))에는 `Serialize` 를 달지 않는다.
//! 디스크의 꼴은 여기 있는 `Stored*` 만 안다 — 코어에 달면 그 순간 형식이 공개 계약이 된다.

use std::collections::BTreeMap;
use std::ffi::OsString;
use std::fmt;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize, Serializer};

use crate::node::{NodeKind, NodeStatus};
use crate::rules::RuleSet;
use crate::walk::{NodeId, RestoreError, StepNode, Walk, WalkState};

/// 이 크레이트가 읽고 쓰는 저장 형식의 번호.
///
/// 0 은 "버릴 수 있는 형식"이라는 뜻이다. 올라가면 그때 옮기는 법을 함께 정한다.
pub const FORMAT: u32 = 0;

/// 저장소 안에서 걷기가 눕는 자리.
pub const WALK_PATH: &str = ".gil/walk.yaml";

/// 걷기를 파일에 눕힌다. 부모 디렉터리가 없으면 만든다.
///
/// 먼저 옆자리에 쓰고 제자리로 옮긴다 — 쓰다 죽어도 반쯤 쓰인 걷기가 남지 않는다.
pub fn save(walk: &Walk, path: impl AsRef<Path>) -> Result<(), StoreError> {
    let path = path.as_ref();
    let stored = StoredWalk::from(walk);
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

/// 파일에서 걷기를 다시 세운다.
///
/// 규칙은 파일에 없다 — [`RuleSet`] 은 언제나 `gil-spec.yaml` 에서 새로 읽어 넘긴다.
/// 문법이 바뀌면 저장된 걷기도 **새 문법으로** 판정받아야 하고, 파일에 넣어 두면 그러지 못한다.
pub fn load(rules: RuleSet, path: impl AsRef<Path>) -> Result<Walk, StoreError> {
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

    let stored: StoredWalk = serde_norway::from_str(&text).map_err(StoreError::Decode)?;
    if stored.format != FORMAT {
        return Err(StoreError::UnknownFormat {
            found: stored.format,
            known: FORMAT,
        });
    }

    Walk::restore(rules, stored.into_state()).map_err(StoreError::NotAWalk)
}

/// 디스크에 눕는 걷기의 꼴. **저장만 아는 모양이다.**
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct StoredWalk {
    /// 첫 줄에 온다 — 파일이 제 형식을 스스로 밝히게.
    format: u32,
    next_id: u32,
    current: Option<u32>,
    finished: bool,
    pending_revisit: Option<u32>,
    nodes: Vec<StoredNode>,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct StoredNode {
    id: u32,
    /// 읽기는 [`NodeKind`] 가 이미 아는 이름으로 하고, 쓰기만 여기서 한다 —
    /// 종류의 이름을 두 자리에 적으면 한쪽이 낡는다.
    #[serde(serialize_with = "write_kind")]
    kind: NodeKind,
    parent: Option<u32>,
    revisit_from: Option<u32>,
    status: StoredStatus,
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

impl From<&Walk> for StoredWalk {
    fn from(walk: &Walk) -> Self {
        StoredWalk {
            format: FORMAT,
            next_id: walk.next_id(),
            current: walk.current().map(NodeId::raw),
            finished: walk.is_finished(),
            pending_revisit: walk.pending_revisit().map(NodeId::raw),
            nodes: walk.nodes().iter().map(StoredNode::from).collect(),
        }
    }
}

impl StoredWalk {
    fn into_state(self) -> WalkState {
        WalkState {
            current: self.current.map(NodeId::from_raw),
            finished: self.finished,
            next_id: self.next_id,
            pending_revisit: self.pending_revisit.map(NodeId::from_raw),
            nodes: self.nodes.into_iter().map(StepNode::from).collect(),
        }
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
            report: node.report.as_ref().map(|report| {
                report
                    .field_names()
                    .map(|name| {
                        let value = report.get(name).expect("방금 이름을 받아 온 칸이다");
                        (name.to_string(), value.to_string())
                    })
                    .collect()
            }),
        }
    }
}

impl From<StoredNode> for StepNode {
    fn from(node: StoredNode) -> Self {
        StepNode {
            id: NodeId::from_raw(node.id),
            kind: node.kind,
            parent: node.parent.map(NodeId::from_raw),
            revisit_from: node.revisit_from.map(NodeId::from_raw),
            status: node.status.into(),
            report: node.report.map(|fields| fields.into_iter().collect()),
        }
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
    /// 저장된 걷기가 아직 없다. 잘못이 아니라 **아직 시작하지 않았다**는 사실이다.
    NotFound { path: String },
    Read { path: String, source: io::Error },
    Write { path: String, source: io::Error },
    Encode(serde_norway::Error),
    Decode(serde_norway::Error),
    /// 이 크레이트가 모르는 형식이다 — 지어내 읽지 않는다.
    UnknownFormat { found: u32, known: u32 },
    /// 읽히기는 했으나 걷기가 만들 수 있는 꼴이 아니다.
    NotAWalk(RestoreError),
}

impl fmt::Display for StoreError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            StoreError::NotFound { path } => {
                write!(f, "저장된 걷기가 없다: {path}")
            }
            StoreError::Read { path, source } => {
                write!(f, "저장된 걷기를 읽지 못했다: {path} — {source}")
            }
            StoreError::Write { path, source } => {
                write!(f, "걷기를 쓰지 못했다: {path} — {source}")
            }
            StoreError::Encode(source) => write!(f, "걷기를 저장할 꼴로 옮기지 못했다: {source}"),
            StoreError::Decode(source) => write!(f, "저장 파일의 형식이 맞지 않다: {source}"),
            StoreError::UnknownFormat { found, known } => write!(
                f,
                "저장 형식 {found} 은(는) 이 gil 이 모른다 (아는 것: {known}) \
                 — 모르는 형식을 짐작해 읽지 않는다"
            ),
            StoreError::NotAWalk(source) => write!(
                f,
                "저장 파일이 걷기가 만들 수 없는 꼴을 담고 있다 — {source}"
            ),
        }
    }
}

impl std::error::Error for StoreError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            StoreError::Read { source, .. } | StoreError::Write { source, .. } => Some(source),
            StoreError::Encode(source) | StoreError::Decode(source) => Some(source),
            StoreError::NotAWalk(source) => Some(source),
            StoreError::NotFound { .. } | StoreError::UnknownFormat { .. } => None,
        }
    }
}
