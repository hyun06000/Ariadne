//! 복원 계획 — **되돌릴 수 있는 형태로 적어 둔 변경 목록.**
//!
//! # 왜 이진 형식인가
//!
//! `state.yaml` 은 사람이 읽으라고 YAML 이다. 이 계획은 반대다.
//!
//! ```text
//! 사람이 고칠 것이 아니다      고치면 rollback 이 엉뚱한 파일을 되살린다
//! 죽은 프로세스가 남긴 자료다  반쯤 쓰인 것을 반쯤 읽으면 안 된다
//! 길이가 스스로를 말해야 한다  trailing byte 하나도 통과시키지 않는다
//! ```
//!
//! manifest codec 과 같은 규율을 쓴다 — magic·version·big-endian 고정 폭. YAML 로 적으면
//! 들여쓰기 하나가 다른 계획이 되고, 그 계획이 남의 파일을 지운다.
//!
//! # 보관 이름은 불투명하다
//!
//! 되돌릴 원본은 `backup/<서수>` 에 눕는다. 사용자 경로를 내부 파일 이름으로 쓰지 않는다 —
//! 쓰면 그 순간 경로 문자열이 파일 시스템 조작 수단이 되고, `..` 하나로 밖이 열린다.

use std::fmt;

use crate::artifact::{ContentDigest, EntryPath, Manifest};
use crate::refs::SnapshotRef;

const MAGIC: [u8; 8] = *b"GILPLAN\0";
const FORMAT_VERSION: u32 = 1;
const TAG_SHA256: u8 = 1;

const OP_REPLACE: u8 = 1;
const OP_DELETE: u8 = 2;
const OP_CREATE: u8 = 3;

const DIGEST_BYTES: usize = 32;
const MAX_PATH_BYTES: u32 = 4096;
/// magic + version + algorithm + world + entry_count
const HEADER: usize = 8 + 4 + 1 + 4 + 8;
/// 가장 짧은 항목 — op + path_len + 한 글자 + target digest
const MIN_ENTRY: u64 = 1 + 4 + 1 + DIGEST_BYTES as u64;

/// 한 자리를 어떻게 바꾸는가.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum Operation {
    /// 있던 파일을 목표 내용으로 갈아 끼운다.
    Replace {
        /// 지금 그 자리의 내용 — 적용 직전에 「그대로인가」를 묻는 값이다.
        before: ContentDigest,
        /// `backup/<서수>` — **불투명한 이름**이다.
        backup: u64,
        /// 되돌릴 때 함께 되살릴 권한.
        mode: u32,
        target: ContentDigest,
    },
    /// 있던 파일을 없앤다.
    Delete {
        before: ContentDigest,
        backup: u64,
        mode: u32,
    },
    /// 없던 파일을 만든다.
    Create { target: ContentDigest },
}

impl Operation {
    /// 되돌릴 원본이 보관된 서수. 새로 만드는 자리는 보관할 것이 없다.
    pub(crate) fn backup(&self) -> Option<u64> {
        match self {
            Operation::Replace { backup, .. } | Operation::Delete { backup, .. } => Some(*backup),
            Operation::Create { .. } => None,
        }
    }

    /// 적용 직전에 그 자리에 있어야 하는 내용. `None` 은 **없어야 한다**는 뜻이다.
    pub(crate) fn before(&self) -> Option<&ContentDigest> {
        match self {
            Operation::Replace { before, .. } | Operation::Delete { before, .. } => Some(before),
            Operation::Create { .. } => None,
        }
    }

    fn tag(&self) -> u8 {
        match self {
            Operation::Replace { .. } => OP_REPLACE,
            Operation::Delete { .. } => OP_DELETE,
            Operation::Create { .. } => OP_CREATE,
        }
    }
}

/// 계획의 한 줄.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Step {
    pub(crate) path: EntryPath,
    pub(crate) operation: Operation,
}

/// 이번 복원이 할 일 전부.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Plan {
    world: SnapshotRef,
    steps: Vec<Step>,
}

impl Plan {
    pub(crate) fn new(world: SnapshotRef, steps: Vec<Step>) -> Plan {
        Plan { world, steps }
    }

    pub(crate) fn steps(&self) -> &[Step] {
        &self.steps
    }

    pub(crate) fn world(&self) -> SnapshotRef {
        self.world
    }

    /// 이 계획이 실행되기 **전의** 세계 — 되돌린 결과가 맞는지 재는 값.
    ///
    /// 계획은 「무엇을 바꾸는가」만 담는다. 바뀌지 않는 자리는 담지 않으므로 실행 전 세계
    /// 전체를 여기서 되세울 수는 없다 — 그래서 복구는 **관측한 세계에서 계획이 건드린
    /// 자리만 골라** 견준다.
    pub(crate) fn before_world(&self) -> BeforeWorld<'_> {
        BeforeWorld { plan: self }
    }

    // ── 이진 꼴 ───────────────────────────────────────────────────────────

    pub(crate) fn encode(&self) -> Vec<u8> {
        let mut out = Vec::with_capacity(HEADER + self.steps.len() * 96);
        out.extend_from_slice(&MAGIC);
        out.extend_from_slice(&FORMAT_VERSION.to_be_bytes());
        out.push(TAG_SHA256);
        out.extend_from_slice(&self.world.number().to_be_bytes());
        out.extend_from_slice(&(self.steps.len() as u64).to_be_bytes());

        for step in &self.steps {
            out.push(step.operation.tag());
            let path = step.path.as_str().as_bytes();
            out.extend_from_slice(&(path.len() as u32).to_be_bytes());
            out.extend_from_slice(path);
            match &step.operation {
                Operation::Replace {
                    before,
                    backup,
                    mode,
                    target,
                } => {
                    out.extend_from_slice(raw(before));
                    out.extend_from_slice(&backup.to_be_bytes());
                    out.extend_from_slice(&mode.to_be_bytes());
                    out.extend_from_slice(raw(target));
                }
                Operation::Delete {
                    before,
                    backup,
                    mode,
                } => {
                    out.extend_from_slice(raw(before));
                    out.extend_from_slice(&backup.to_be_bytes());
                    out.extend_from_slice(&mode.to_be_bytes());
                }
                Operation::Create { target } => out.extend_from_slice(raw(target)),
            }
        }
        out
    }

    pub(crate) fn decode(bytes: &[u8]) -> Result<Plan, PlanError> {
        let mut cursor = Cursor::new(bytes);

        if cursor.take(8)? != MAGIC {
            return Err(PlanError::BadMagic);
        }
        let version = u32::from_be_bytes(cursor.array()?);
        if version != FORMAT_VERSION {
            return Err(PlanError::UnknownFormatVersion { found: version });
        }
        if cursor.byte()? != TAG_SHA256 {
            return Err(PlanError::UnknownDigestAlgorithm);
        }
        let world = SnapshotRef::new(u32::from_be_bytes(cursor.array()?))
            .ok_or(PlanError::ZeroWorld)?;
        let count = u64::from_be_bytes(cursor.array()?);

        // **길이 필드를 믿고 통째로 잡지 않는다.** 남은 바이트로 가능한 수인지 먼저 본다.
        let needed = count
            .checked_mul(MIN_ENTRY)
            .ok_or(PlanError::StepCountTooLarge { count })?;
        if needed > cursor.left() as u64 {
            return Err(PlanError::StepCountTooLarge { count });
        }

        let mut steps: Vec<Step> = Vec::with_capacity(count as usize);
        for _ in 0..count {
            let tag = cursor.byte()?;
            let length = u32::from_be_bytes(cursor.array()?);
            if length == 0 || length > MAX_PATH_BYTES {
                return Err(PlanError::PathLengthOutOfRange { found: length });
            }
            let text = std::str::from_utf8(cursor.take(length as usize)?)
                .map_err(|_| PlanError::PathNotUtf8)?;
            let path = EntryPath::parse(text).ok_or(PlanError::PathNotCanonical)?;

            let operation = match tag {
                OP_REPLACE => Operation::Replace {
                    before: cursor.digest()?,
                    backup: u64::from_be_bytes(cursor.array()?),
                    mode: u32::from_be_bytes(cursor.array()?),
                    target: cursor.digest()?,
                },
                OP_DELETE => Operation::Delete {
                    before: cursor.digest()?,
                    backup: u64::from_be_bytes(cursor.array()?),
                    mode: u32::from_be_bytes(cursor.array()?),
                },
                OP_CREATE => Operation::Create {
                    target: cursor.digest()?,
                },
                found => return Err(PlanError::UnknownOperation { found }),
            };

            // **엄격한 오름차순.** 정렬해서 받아들이지 않는다 — 정렬해 주면 두 계획이
            // 같은 뜻이 되고, 그러면 바이트가 계획을 정하지 않는다.
            if let Some(last) = steps.last() {
                match path.cmp(&last.path) {
                    std::cmp::Ordering::Greater => {}
                    std::cmp::Ordering::Equal => {
                        return Err(PlanError::DuplicatePath {
                            path: text.to_string(),
                        });
                    }
                    std::cmp::Ordering::Less => {
                        return Err(PlanError::OutOfOrder {
                            path: text.to_string(),
                        });
                    }
                }
            }
            steps.push(Step { path, operation });
        }

        match cursor.left() {
            0 => Ok(Plan { world, steps }),
            extra => Err(PlanError::TrailingBytes { extra }),
        }
    }
}

/// 실행 전 세계와 지금 관측한 세계를 **계획이 건드린 자리에서만** 견준다.
pub(crate) struct BeforeWorld<'a> {
    plan: &'a Plan,
}

impl PartialEq<BeforeWorld<'_>> for Manifest {
    fn eq(&self, other: &BeforeWorld<'_>) -> bool {
        other.plan.steps.iter().all(|step| {
            let found = self.get(&step.path);
            match &step.operation {
                Operation::Create { .. } => found.is_none(),
                Operation::Replace { before, .. } | Operation::Delete { before, .. } => {
                    found == Some(before)
                }
            }
        })
    }
}

impl PartialEq<Manifest> for BeforeWorld<'_> {
    fn eq(&self, other: &Manifest) -> bool {
        other == self
    }
}

// ── 계획 세우기 ────────────────────────────────────────────────────────────

/// 지금 세계에서 목표 세계로 가려면 무엇을 해야 하는가.
///
/// **경로 오름차순**으로 낸다 — codec 이 그 차례를 요구하고, 같은 두 세계에서 언제나 같은
/// 계획이 나와야 한다.
pub(crate) fn steps(root: &std::path::Path, before: &Manifest, target: &Manifest) -> Vec<Step> {
    let mut out: Vec<Step> = Vec::new();
    let mut ordinal = 0u64;
    let mut next = || {
        let id = ordinal;
        ordinal += 1;
        id
    };

    for entry in target.entries() {
        match before.get(&entry.path) {
            None => out.push(Step {
                path: entry.path.clone(),
                operation: Operation::Create {
                    target: entry.content.clone(),
                },
            }),
            Some(now) if now != &entry.content => out.push(Step {
                path: entry.path.clone(),
                operation: Operation::Replace {
                    before: now.clone(),
                    backup: next(),
                    // **지금 권한을 그대로 들고 간다.** Snapshot 에는 권한이 없으므로
                    // 되돌릴 때 되살릴 것은 「과거의 권한」이 아니라 **실행 전 권한**이다.
                    mode: crate::restore::mode_of(&root.join(entry.path.as_str())),
                    target: entry.content.clone(),
                },
            }),
            // 같으면 건드리지 않는다.
            Some(_) => {}
        }
    }
    for entry in before.entries() {
        if target.get(&entry.path).is_none() {
            out.push(Step {
                path: entry.path.clone(),
                operation: Operation::Delete {
                    before: entry.content.clone(),
                    backup: next(),
                    mode: crate::restore::mode_of(&root.join(entry.path.as_str())),
                },
            });
        }
    }

    out.sort_by(|a, b| a.path.cmp(&b.path));
    out
}

// ── 읽기 도우미 ────────────────────────────────────────────────────────────

fn raw(digest: &ContentDigest) -> &[u8; DIGEST_BYTES] {
    crate::artifact::digest_bytes(digest)
}

/// 남은 바이트를 세며 읽는 자리 — **없는 것을 읽으려 하면 그 자리에서 멈춘다.**
struct Cursor<'a> {
    bytes: &'a [u8],
    at: usize,
}

impl<'a> Cursor<'a> {
    fn new(bytes: &'a [u8]) -> Cursor<'a> {
        Cursor { bytes, at: 0 }
    }

    fn left(&self) -> usize {
        self.bytes.len() - self.at
    }

    fn take(&mut self, want: usize) -> Result<&'a [u8], PlanError> {
        if self.left() < want {
            return Err(PlanError::Truncated {
                wanted: want,
                left: self.left(),
                at: self.at,
            });
        }
        let slice = &self.bytes[self.at..self.at + want];
        self.at += want;
        Ok(slice)
    }

    fn byte(&mut self) -> Result<u8, PlanError> {
        Ok(self.take(1)?[0])
    }

    fn array<const N: usize>(&mut self) -> Result<[u8; N], PlanError> {
        Ok(self.take(N)?.try_into().expect("방금 그 길이를 받아 왔다"))
    }

    fn digest(&mut self) -> Result<ContentDigest, PlanError> {
        Ok(crate::artifact::digest_from_raw(self.array::<DIGEST_BYTES>()?))
    }
}

/// 계획이 온전하지 않은 이유. 어느 것이든 **되돌릴 수 없다는 뜻이다.**
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PlanError {
    BadMagic,
    UnknownFormatVersion { found: u32 },
    UnknownDigestAlgorithm,
    ZeroWorld,
    StepCountTooLarge { count: u64 },
    Truncated { wanted: usize, left: usize, at: usize },
    UnknownOperation { found: u8 },
    PathLengthOutOfRange { found: u32 },
    PathNotUtf8,
    PathNotCanonical,
    DuplicatePath { path: String },
    OutOfOrder { path: String },
    TrailingBytes { extra: usize },
}

impl fmt::Display for PlanError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            PlanError::BadMagic => write!(f, "GIL 이 적은 복원 계획이 아니다"),
            PlanError::UnknownFormatVersion { found } => {
                write!(f, "이 gil 이 모르는 계획 형식이다 (version {found})")
            }
            PlanError::UnknownDigestAlgorithm => {
                write!(f, "이 gil 이 모르는 digest 알고리즘이다")
            }
            PlanError::ZeroWorld => write!(f, "snapshot:A0 은 세계의 이름이 아니다"),
            PlanError::StepCountTooLarge { count } => write!(
                f,
                "계획이 {count} 개를 담았다는데 남은 바이트가 그만큼이 아니다"
            ),
            PlanError::Truncated { wanted, left, at } => write!(
                f,
                "{at} 바이트째에서 {wanted} 바이트가 더 필요한데 {left} 만 남았다 — 계획이 잘렸다"
            ),
            PlanError::UnknownOperation { found } => {
                write!(f, "이 gil 이 모르는 동작이다 ({found})")
            }
            PlanError::PathLengthOutOfRange { found } => {
                write!(f, "경로 길이 {found} 는 1..=4096 밖이다")
            }
            PlanError::PathNotUtf8 => write!(f, "경로가 UTF-8 이 아니다"),
            PlanError::PathNotCanonical => write!(f, "경로가 정규화된 꼴이 아니다"),
            PlanError::DuplicatePath { path } => write!(f, "{path:?} 가 두 번 실렸다"),
            PlanError::OutOfOrder { path } => {
                write!(f, "{path:?} 가 오름차순 자리에 있지 않다 — 정렬해 받아들이지 않는다")
            }
            PlanError::TrailingBytes { extra } => {
                write!(f, "계획 뒤에 {extra} 바이트가 더 있다")
            }
        }
    }
}

impl std::error::Error for PlanError {}

// ── 시험 ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn world(n: u32) -> SnapshotRef {
        SnapshotRef::new(n).expect("이름은 1 부터다")
    }

    fn digest(seed: u8) -> ContentDigest {
        crate::artifact::digest_from_raw([seed; DIGEST_BYTES])
    }

    fn path(text: &str) -> EntryPath {
        EntryPath::parse(text).expect("정규화된 경로다")
    }

    /// 세 가지 동작이 다 든 계획 하나 — 경로 오름차순.
    fn a_plan() -> Plan {
        Plan::new(
            world(2),
            vec![
                Step {
                    path: path("a/deep.txt"),
                    operation: Operation::Create { target: digest(1) },
                },
                Step {
                    path: path("b.txt"),
                    operation: Operation::Replace {
                        before: digest(2),
                        backup: 0,
                        mode: 0o640,
                        target: digest(3),
                    },
                },
                Step {
                    path: path("c.txt"),
                    operation: Operation::Delete {
                        before: digest(4),
                        backup: 1,
                        mode: 0o755,
                    },
                },
            ],
        )
    }

    #[test]
    fn a_plan_reads_back_exactly_as_it_was_written() {
        let before = a_plan();
        let after = Plan::decode(&before.encode()).expect("제가 적은 것을 읽는다");
        assert_eq!(after, before);
        assert_eq!(after.world(), world(2));
    }

    #[test]
    fn an_empty_plan_is_legal_bytes() {
        // 계획이 비는 일은 없지만(비면 no-op 이라 transaction 을 만들지 않는다), **형식은**
        // 그것을 특별 취급하지 않는다 — 특별 취급이 곧 두 번째 규칙이다.
        let empty = Plan::new(world(1), Vec::new());
        assert_eq!(Plan::decode(&empty.encode()).unwrap(), empty);
    }

    #[test]
    fn something_that_is_not_a_gil_plan_is_refused() {
        assert_eq!(Plan::decode(b"").unwrap_err(), PlanError::Truncated {
            wanted: 8,
            left: 0,
            at: 0,
        });
        assert_eq!(
            Plan::decode(&[0u8; 64]).unwrap_err(),
            PlanError::BadMagic
        );
    }

    #[test]
    fn a_format_this_gil_does_not_know_is_refused() {
        let mut bytes = a_plan().encode();
        bytes[8..12].copy_from_slice(&99u32.to_be_bytes());
        assert_eq!(
            Plan::decode(&bytes).unwrap_err(),
            PlanError::UnknownFormatVersion { found: 99 }
        );

        let mut bytes = a_plan().encode();
        bytes[12] = 7;
        assert_eq!(
            Plan::decode(&bytes).unwrap_err(),
            PlanError::UnknownDigestAlgorithm
        );
    }

    #[test]
    fn a_plan_that_points_at_no_world_is_refused() {
        let mut bytes = a_plan().encode();
        bytes[13..17].copy_from_slice(&0u32.to_be_bytes());
        assert_eq!(Plan::decode(&bytes).unwrap_err(), PlanError::ZeroWorld);
    }

    #[test]
    fn a_length_field_does_not_get_to_allocate_whatever_it_likes() {
        // 길이를 믿고 통째로 잡으면 손상된 파일 하나가 메모리를 삼킨다.
        let mut bytes = a_plan().encode();
        bytes[17..25].copy_from_slice(&u64::MAX.to_be_bytes());
        assert!(matches!(
            Plan::decode(&bytes).unwrap_err(),
            PlanError::StepCountTooLarge { .. }
        ));
    }

    #[test]
    fn a_truncated_plan_says_where_it_ran_out() {
        let bytes = a_plan().encode();
        for cut in [HEADER, HEADER + 10, bytes.len() - 1] {
            assert!(
                matches!(
                    Plan::decode(&bytes[..cut]).unwrap_err(),
                    PlanError::Truncated { .. } | PlanError::StepCountTooLarge { .. }
                ),
                "{cut} 바이트에서 잘린 계획이 통과했다"
            );
        }
    }

    #[test]
    fn bytes_after_the_plan_are_refused() {
        let mut bytes = a_plan().encode();
        bytes.push(0);
        assert_eq!(
            Plan::decode(&bytes).unwrap_err(),
            PlanError::TrailingBytes { extra: 1 }
        );
    }

    #[test]
    fn an_operation_this_gil_does_not_know_is_refused() {
        let mut bytes = a_plan().encode();
        bytes[HEADER] = 9;
        assert_eq!(
            Plan::decode(&bytes).unwrap_err(),
            PlanError::UnknownOperation { found: 9 }
        );
    }

    #[test]
    fn paths_out_of_order_are_refused_not_sorted() {
        // **정렬해서 받아들이지 않는다.** 정렬해 주면 두 바이트열이 같은 계획이 되고,
        // 그러면 바이트가 계획을 정하지 않는다.
        let jumbled = Plan::new(
            world(1),
            vec![
                Step {
                    path: path("z.txt"),
                    operation: Operation::Create { target: digest(1) },
                },
                Step {
                    path: path("a.txt"),
                    operation: Operation::Create { target: digest(2) },
                },
            ],
        );
        assert_eq!(
            Plan::decode(&jumbled.encode()).unwrap_err(),
            PlanError::OutOfOrder {
                path: "a.txt".to_string()
            }
        );
    }

    #[test]
    fn the_same_path_twice_is_refused() {
        let twice = Plan::new(
            world(1),
            vec![
                Step {
                    path: path("a.txt"),
                    operation: Operation::Create { target: digest(1) },
                },
                Step {
                    path: path("a.txt"),
                    operation: Operation::Create { target: digest(2) },
                },
            ],
        );
        assert_eq!(
            Plan::decode(&twice.encode()).unwrap_err(),
            PlanError::DuplicatePath {
                path: "a.txt".to_string()
            }
        );
    }

    #[test]
    fn a_path_that_could_escape_the_project_is_refused() {
        // 계획의 경로는 **파일 시스템 조작 수단이 아니다.** `..` 하나로 밖이 열리면
        // 손상된 계획 파일이 프로젝트 밖을 지운다.
        for escape in ["../밖.txt", "/절대/경로", "a/../../밖", "."] {
            let mut bytes: Vec<u8> = Vec::new();
            bytes.extend_from_slice(&MAGIC);
            bytes.extend_from_slice(&FORMAT_VERSION.to_be_bytes());
            bytes.push(TAG_SHA256);
            bytes.extend_from_slice(&1u32.to_be_bytes());
            bytes.extend_from_slice(&1u64.to_be_bytes());
            bytes.push(OP_CREATE);
            bytes.extend_from_slice(&(escape.len() as u32).to_be_bytes());
            bytes.extend_from_slice(escape.as_bytes());
            bytes.extend_from_slice(&[0u8; DIGEST_BYTES]);

            assert_eq!(
                Plan::decode(&bytes).unwrap_err(),
                PlanError::PathNotCanonical,
                "{escape:?} 가 통과했다"
            );
        }
    }

    #[test]
    fn a_path_length_outside_the_range_is_refused() {
        let mut bytes = a_plan().encode();
        bytes[HEADER + 1..HEADER + 5].copy_from_slice(&0u32.to_be_bytes());
        assert_eq!(
            Plan::decode(&bytes).unwrap_err(),
            PlanError::PathLengthOutOfRange { found: 0 }
        );
    }

    #[test]
    fn a_path_that_is_not_utf8_is_refused() {
        let mut bytes = a_plan().encode();
        // 첫 항목의 경로 첫 바이트를 UTF-8 이 아닌 것으로 바꾼다.
        bytes[HEADER + 5] = 0xFF;
        assert_eq!(Plan::decode(&bytes).unwrap_err(), PlanError::PathNotUtf8);
    }

    // ── 계획 세우기 ───────────────────────────────────────────────────────

    fn manifest(entries: &[(&str, u8)]) -> Manifest {
        Manifest::new(
            entries
                .iter()
                .map(|(text, seed)| crate::artifact::ManifestEntry {
                    path: path(text),
                    content: digest(*seed),
                })
                .collect(),
        )
    }

    #[test]
    fn a_plan_covers_exactly_what_differs() {
        let root = std::path::Path::new("/이런/자리는/없다");
        let before = manifest(&[("keep.txt", 1), ("edit.txt", 2), ("gone.txt", 3)]);
        let target = manifest(&[("keep.txt", 1), ("edit.txt", 9), ("new.txt", 4)]);

        let steps = steps(root, &before, &target);
        let names: Vec<&str> = steps.iter().map(|step| step.path.as_str()).collect();
        // 경로 오름차순이고, 같은 자리는 아예 들어오지 않는다.
        assert_eq!(names, vec!["edit.txt", "gone.txt", "new.txt"]);
        assert!(matches!(steps[0].operation, Operation::Replace { .. }));
        assert!(matches!(steps[1].operation, Operation::Delete { .. }));
        assert!(matches!(steps[2].operation, Operation::Create { .. }));

        // 보관 서수는 **되돌릴 것에만** 붙고 서로 다르다.
        let ordinals: Vec<Option<u64>> = steps.iter().map(|s| s.operation.backup()).collect();
        assert_eq!(ordinals, vec![Some(0), Some(1), None]);
    }

    #[test]
    fn two_identical_worlds_need_no_plan() {
        let root = std::path::Path::new("/이런/자리는/없다");
        let same = manifest(&[("a.txt", 1), ("b/c.txt", 2)]);
        assert!(steps(root, &same, &same).is_empty());
    }

    #[test]
    fn the_before_world_is_measured_only_where_the_plan_touched() {
        // 계획은 **바뀌는 자리만** 담는다. 그러니 되돌린 결과를 견줄 때도 그 자리만 본다.
        let root = std::path::Path::new("/이런/자리는/없다");
        let before = manifest(&[("keep.txt", 1), ("edit.txt", 2)]);
        let target = manifest(&[("keep.txt", 1), ("edit.txt", 9)]);
        let plan = Plan::new(world(1), steps(root, &before, &target));

        assert!(before == plan.before_world(), "실행 전 세계를 못 알아본다");
        assert!(target != plan.before_world(), "목표 세계를 실행 전이라 한다");

        // 계획이 건드리지 않은 자리가 달라도 **그 자리는 묻지 않는다.**
        let elsewhere = manifest(&[("keep.txt", 7), ("edit.txt", 2)]);
        assert!(elsewhere == plan.before_world());
    }
}
