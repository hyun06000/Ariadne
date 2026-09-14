//! `gil restore` — **지금 위치가 요구하는 세계로 작업 폴더를 되돌린다.**
//!
//! ```text
//! 목표 유도 → preflight → prepare → apply → verify → commit → cleanup
//!                            │        │       │
//!                            └────────┴───────┴──→ 실패하면 rollback
//! ```
//!
//! 성공하거나, 실행 전 세계로 돌아가거나, 둘 중 하나다. 중간에 멈춘 세계를 정상이라고
//! 말하지 않는다.
//!
//! # 무엇을 바꾸지 않는가
//!
//! **논리 상태는 한 글자도 바뀌지 않는다.** Current Cycle·Step·Active Will·Done Will·
//! Journey 판·Graph·Report·SnapshotRegistry·`next_snapshot_id`·기존 Snapshot 객체·
//! `state.yaml` 전부 그대로다(Artifact Model §9).
//!
//! restore 는 **세계를 되돌리는 것이지 시간을 되감는 것이 아니다.** 되돌아간 사실 자체가
//! Journey 에 적히지도 않는다 — 그것은 다음 Verify 가 관측할 때 드러난다.
//!
//! # 되돌릴 자료는 역사가 아니다
//!
//! 덮어쓰거나 지울 파일의 원본은 transaction 이 사는 동안만 보관한다.
//!
//! ```text
//! 새 SnapshotRef 발급 없음
//! registry 추가 없음
//! 지금의 dirty 세계를 자동 보존한 역사로 만들지 않음
//! ```
//!
//! 확정되지 않은 세계에 이름을 주면, 사람이 확정한 적 없는 것이 시간선에 남는다.
//!
//! # 이 잠금이 막지 못하는 것
//!
//! 프로젝트 잠금은 GIL 명령끼리의 협력적 잠금이라(§10.6) **외부 편집기의 쓰기를 막지
//! 않는다.** 그래서 파일을 건드리기 직전에 「지금도 계획이 본 그대로인가」를 다시 묻고,
//! 다르면 앞으로 가지 않고 되돌린다.

pub mod plan;

use std::fmt;
use std::fs::{self, File};
use std::io;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use crate::artifact::{ContentDigest, Manifest, ObjectStore, ObserveError, digest_of, observe};
use crate::refs::SnapshotRef;

pub(crate) use plan::{Operation, Plan, PlanError, Step};

/// 루트 `.gil/` 아래 transaction 이 사는 자리.
const RESTORE: &str = "restore";
/// rollback 이 걸린 transaction — 이 이름은 **하나뿐**이다(프로젝트 잠금이 그것을 보장한다).
const ACTIVE: &str = "active";
/// 아직 rollback 이 걸리지 않은 준비 중 자료.
const PREPARING: &str = "preparing-";
/// 논리 결정이 이미 끝나 지우기만 남은 잔해.
const CLEANUP: &str = "cleanup-";
/// forward restore 가 성공으로 확정됐다는 표식.
const COMMITTED: &str = "COMMITTED";
/// 계획이 눕는 파일 이름.
const PLAN: &str = "PLAN";
/// 되돌릴 원본들이 눕는 폴더.
const BACKUP: &str = "backup";

/// 임시 이름이 겹치지 않게 세는 수.
static NEXT_TICKET: AtomicU64 = AtomicU64::new(0);

/// transaction 이 사는 곳들 — **이름을 아는 자리는 여기 하나다.**
///
/// 사용자 입력을 내부 경로에 이어 붙이는 자리가 없다. 경로는 전부 이 구조체가 조립한다.
pub(crate) struct Area {
    root: PathBuf,
}

impl Area {
    pub(crate) fn at(gil_dir: &Path) -> Area {
        Area {
            root: gil_dir.join(RESTORE),
        }
    }

    fn root(&self) -> &Path {
        &self.root
    }

    fn active(&self) -> PathBuf {
        self.root.join(ACTIVE)
    }

    /// 이번 명령만 쓰는 준비 자리.
    fn preparing(&self) -> PathBuf {
        self.root.join(format!(
            "{PREPARING}{}-{}",
            std::process::id(),
            NEXT_TICKET.fetch_add(1, Ordering::Relaxed)
        ))
    }

    fn cleanup(&self) -> PathBuf {
        self.root.join(format!(
            "{CLEANUP}{}-{}",
            std::process::id(),
            NEXT_TICKET.fetch_add(1, Ordering::Relaxed)
        ))
    }

    /// 이 이름이 GIL 이 만든 transaction 자리인가 — 그리고 어느 종류인가.
    fn classify(name: &str) -> Option<Kind> {
        if name == ACTIVE {
            return Some(Kind::Active);
        }
        for (prefix, kind) in [(PREPARING, Kind::Preparing), (CLEANUP, Kind::Cleanup)] {
            if let Some(rest) = name.strip_prefix(prefix)
                && is_ticket(rest)
            {
                return Some(kind);
            }
        }
        None
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Kind {
    Preparing,
    Active,
    Cleanup,
}

/// `<pid>-<표>` 인가. 이름 규칙을 아는 자리는 [`Area`] 하나다.
fn is_ticket(rest: &str) -> bool {
    match rest.split_once('-') {
        Some((pid, ticket)) => {
            !pid.is_empty()
                && !ticket.is_empty()
                && pid.bytes().all(|b| b.is_ascii_digit())
                && ticket.bytes().all(|b| b.is_ascii_digit())
        }
        None => false,
    }
}

// ── 복원의 결과 ────────────────────────────────────────────────────────────

/// 복원이 실제로 한 일 — receipt 가 읽는 값.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Restored {
    /// 어느 세계로 되돌렸는가.
    pub world: SnapshotRef,
    /// 바꿀 것이 없었는가. 그렇다면 아래 세 수는 전부 0 이고 아무것도 만들지 않았다.
    pub no_op: bool,
    pub replaced: usize,
    pub created: usize,
    pub deleted: usize,
}

// ── 실행 ───────────────────────────────────────────────────────────────────

/// 작업 폴더를 목표 세계로 되돌린다.
///
/// 부르는 쪽이 이미 프로젝트 잠금을 쥐고 있고, restore 영역의 복구도 끝나 있어야 한다.
pub(crate) fn run(
    root: &Path,
    gil: &Path,
    store: &ObjectStore,
    world: SnapshotRef,
    target: &Manifest,
) -> Result<Restored, RestoreFailure> {
    let area = Area::at(gil);

    // ── preflight ─────────────────────────────────────────────────────────
    //
    // **파일을 하나도 건드리기 전에** 전부 확인한다. 목표의 blob 하나라도 없거나 손상됐으면
    // 여기서 멈추고, 작업 폴더는 그대로다.
    verify_blobs(store, target, world)?;

    let before = observe(root).map_err(|source| RestoreFailure::Observe {
        stage: Stage::Preflight,
        said: source.to_string(),
    })?;

    let steps = plan::steps(root, &before, target);
    if steps.is_empty() {
        // **바꿀 것이 없다.** transaction 도, 객체도, 저장도 만들지 않는다.
        return Ok(Restored {
            world,
            no_op: true,
            replaced: 0,
            created: 0,
            deleted: 0,
        });
    }

    let counts = tally(&steps);
    let plan = Plan::new(world, steps);

    // ── prepare ───────────────────────────────────────────────────────────
    let active = prepare(&area, root, &plan)?;
    failpoint::crash_at("after-prepare");
    failpoint::meddle("after-prepare", root);

    // ── apply → verify → commit ───────────────────────────────────────────
    //
    // 여기부터는 rollback 이 걸려 있다. 어느 길로 실패하든 실행 전 세계로 돌아간다.
    let mut made: Vec<PathBuf> = Vec::new();
    match forward(root, store, &plan, target, &mut made) {
        Ok(()) => {
            commit(&area, &active)?;
            Ok(Restored {
                world,
                no_op: false,
                replaced: counts.0,
                created: counts.1,
                deleted: counts.2,
            })
        }
        Err(forward_failed) => {
            // 되돌리다 또 실패하면 **그 사실을 그대로 말한다.** 손상된 상태를 정상이라고
            // 선언하지 않는다 — 다음 명령이 복구를 다시 시도한다.
            match rollback(root, &active, &plan, &made) {
                Ok(()) => {
                    let _ = finish(&area, &active);
                    Err(RestoreFailure::RolledBack {
                        world,
                        cause: Box::new(forward_failed),
                    })
                }
                Err(rollback_failed) => Err(RestoreFailure::RecoveryRequired {
                    world,
                    cause: Box::new(forward_failed),
                    then: Box::new(rollback_failed),
                }),
            }
        }
    }
}

fn tally(steps: &[Step]) -> (usize, usize, usize) {
    let mut counts = (0, 0, 0);
    for step in steps {
        match step.operation {
            Operation::Replace { .. } => counts.0 += 1,
            Operation::Create { .. } => counts.1 += 1,
            Operation::Delete { .. } => counts.2 += 1,
        }
    }
    counts
}

/// 목표 세계의 **모든 blob 을 흘려 읽어 지문을 다시 잰다.**
///
/// 경로만 믿지 않는다. 하나라도 없거나 주소와 다르면 여기서 멈추고 **작업 폴더는 손대지
/// 않는다** — 반쯤 복원된 세계보다 아무것도 안 한 세계가 낫다.
///
/// 이 전수 검증은 `load` 가 하지 않는 일이다(§10.9). 그 바이트를 실제로 쓰는 자리가
/// 여기이므로, 여기서 한다.
fn verify_blobs(
    store: &ObjectStore,
    target: &Manifest,
    world: SnapshotRef,
) -> Result<(), RestoreFailure> {
    for entry in target.entries() {
        store
            .read_blob(&entry.content, &mut io::sink())
            .map_err(|source| RestoreFailure::Blob {
                world,
                path: entry.path.as_str().to_string(),
                said: source.to_string(),
            })?;
    }
    Ok(())
}

// ── prepare ────────────────────────────────────────────────────────────────

/// 되돌릴 자료와 계획을 눕히고, **원자적으로** `active` 로 건다.
///
/// `active` 가 생기기 전에 죽으면 남는 것은 `preparing-*` 뿐이고, 그것은 다음 명령이
/// 안전하게 치운다. `active` 가 생긴 뒤에 죽으면 반드시 rollback 하거나 commit 을 처리한다.
fn prepare(area: &Area, root: &Path, plan: &Plan) -> Result<PathBuf, RestoreFailure> {
    let staging = area.preparing();
    let backup = staging.join(BACKUP);
    make_dir(&backup, Stage::Prepare)?;

    // ① 덮어쓰거나 지울 **현재 파일만** 보관한다. 세계 전체를 복제하지 않는다.
    for step in plan.steps() {
        let Some(ordinal) = step.operation.backup() else {
            continue;
        };
        let from = root.join(step.path.as_str());
        let to = backup.join(ordinal.to_string());
        copy_out(&from, &to).map_err(|source| RestoreFailure::Io {
            stage: Stage::Prepare,
            doing: "되돌릴 원본을 보관하지",
            path: from.display().to_string(),
            said: source.to_string(),
        })?;
    }

    // ② 계획을 적고 디스크에 밀어 넣는다.
    write_durable(&staging.join(PLAN), &plan.encode(), Stage::Prepare)?;
    sync_dir(&backup, Stage::Prepare)?;
    sync_dir(&staging, Stage::Prepare)?;
    // 아직 `active` 가 없다 — 여기서 죽으면 남는 것은 `preparing-*` 뿐이고,
    // 그것은 다음 명령이 그냥 치운다.
    failpoint::crash_at("prepared-not-armed");

    // ③ **여기서부터 rollback 이 걸린다.** 이름이 바뀌는 한 순간에.
    let active = area.active();
    fs::rename(&staging, &active).map_err(|source| RestoreFailure::Io {
        stage: Stage::Prepare,
        doing: "transaction 을 확정하지",
        path: active.display().to_string(),
        said: source.to_string(),
    })?;
    sync_dir(area.root(), Stage::Prepare)?;
    Ok(active)
}

// ── apply ──────────────────────────────────────────────────────────────────

/// 파일을 목표와 정확히 같게 만들고 그 결과를 다시 관측해 확인한다.
fn forward(
    root: &Path,
    store: &ObjectStore,
    plan: &Plan,
    target: &Manifest,
    made: &mut Vec<PathBuf>,
) -> Result<(), RestoreFailure> {
    let mut applied = 0usize;
    for step in plan.steps() {
        // **계획이 본 그대로인가.** 준비하는 사이에 밖에서 누가 고쳤으면 앞으로 가지 않는다.
        still_as_planned(root, step)?;
        apply(root, store, step, made)?;
        applied += 1;
        if applied == 1 {
            failpoint::crash_at("after-first-apply");
            failpoint::fail_at("after-first-apply", Stage::Apply)?;
        }
    }
    failpoint::crash_at("after-apply");
    failpoint::fail_at("after-apply", Stage::Apply)?;
    failpoint::meddle("after-apply", root);

    // 결과가 정말 목표와 같은가 — **안정된 관측으로** 다시 본다.
    let found = observe(root).map_err(|source| RestoreFailure::Observe {
        stage: Stage::Verify,
        said: source.to_string(),
    })?;
    match &found == target {
        true => Ok(()),
        false => Err(RestoreFailure::NotTheTargetWorld),
    }
}

/// 이 자리가 계획을 세울 때 본 그대로인가.
fn still_as_planned(root: &Path, step: &Step) -> Result<(), RestoreFailure> {
    let at = root.join(step.path.as_str());
    let found = current_digest(&at).map_err(|source| RestoreFailure::Io {
        stage: Stage::Apply,
        doing: "적용 직전에 지금 상태를 확인하지",
        path: at.display().to_string(),
        said: source.to_string(),
    })?;

    let expected = step.operation.before();
    match (expected, found.as_ref()) {
        (Some(before), Some(now)) if before == now => Ok(()),
        (None, None) => Ok(()),
        _ => Err(RestoreFailure::ChangedUnderneath {
            path: step.path.as_str().to_string(),
        }),
    }
}

/// 지금 그 자리의 지문. 없으면 `None`. **일반 파일이 아니면 오류다.**
fn current_digest(at: &Path) -> io::Result<Option<ContentDigest>> {
    let kind = match fs::symlink_metadata(at) {
        Ok(data) => data.file_type(),
        Err(source) if source.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(source) => return Err(source),
    };
    if !kind.is_file() {
        return Err(io::Error::other("일반 파일이 아니다"));
    }
    Ok(Some(digest_of(File::open(at)?)?))
}

/// 한 자리를 목표대로 만든다.
///
/// # 목표 blob 과 hard link 하지 않는다
///
/// 작업 파일은 사람이 곧 고칠 파일이다. 그것이 immutable blob 과 inode 를 나눠 쓰면, 다음
/// 편집이 **창고 안의 객체를 함께 고친다** — 그 순간 그 주소의 내용이 주소와 달라지고,
/// 그 세계를 가리키는 모든 Snapshot 이 거짓이 된다. 그래서 언제나 **복사한다.**
fn apply(
    root: &Path,
    store: &ObjectStore,
    step: &Step,
    made: &mut Vec<PathBuf>,
) -> Result<(), RestoreFailure> {
    let at = root.join(step.path.as_str());
    match &step.operation {
        Operation::Delete { .. } => {
            fs::remove_file(&at).map_err(|source| RestoreFailure::Io {
                stage: Stage::Apply,
                doing: "파일을 지우지",
                path: at.display().to_string(),
                said: source.to_string(),
            })?;
            prune_empty(root, &at);
            Ok(())
        }
        Operation::Replace { target, mode, .. } => place(store, &at, target, Some(*mode), made),
        Operation::Create { target } => place(store, &at, target, None, made),
    }
}

/// 목표 blob 을 그 자리에 놓는다 — 흘려 복사하고, 지문을 다시 재고, 제자리로 옮긴다.
fn place(
    store: &ObjectStore,
    at: &Path,
    target: &ContentDigest,
    mode: Option<u32>,
    made: &mut Vec<PathBuf>,
) -> Result<(), RestoreFailure> {
    let parent = at.parent().expect("프로젝트 상대 경로에는 부모가 있다");
    made.extend(make_dir(parent, Stage::Apply)?);

    // **같은 파일 시스템의 옆자리**에 쓴다 — 다른 자리에 쓰면 rename 이 원자적이지 않다.
    let temp = temp_beside(at);
    {
        let mut file = File::create(&temp).map_err(|source| RestoreFailure::Io {
            stage: Stage::Apply,
            doing: "옆자리 파일을 만들지",
            path: temp.display().to_string(),
            said: source.to_string(),
        })?;
        // `read_blob` 이 흘려 보내면서 **지문을 다시 잰다.** 창고가 거짓말하면 여기서 걸린다.
        store
            .read_blob(target, &mut file)
            .map_err(|source| RestoreFailure::Io {
                stage: Stage::Apply,
                doing: "목표 내용을 흘려 쓰지",
                path: at.display().to_string(),
                said: source.to_string(),
            })?;
        durable(&mut file, &temp, Stage::Apply)?;
    }

    // 권한: Replace 는 **실행 전 권한을 그대로** 되살린다. Snapshot 에는 권한이 없으므로
    // 「과거의 권한을 복원했다」고 말하지 않는다 — 지금 것을 보존할 뿐이다(§3.1).
    set_mode(&temp, mode)?;

    fs::rename(&temp, at).map_err(|source| RestoreFailure::Io {
        stage: Stage::Apply,
        doing: "제자리로 옮기지",
        path: at.display().to_string(),
        said: source.to_string(),
    })?;
    sync_dir(parent, Stage::Apply)
}

// ── rollback ───────────────────────────────────────────────────────────────

/// 실행 전 세계로 되돌린다 — 계획을 거꾸로 밟는다.
/// 실행 전 세계로 되돌린다 — 계획을 거꾸로 밟는다.
///
/// `made` 는 **이번 적용이 실제로 만든 폴더**다. 그것만 지운다 — 원래 있던 빈 폴더까지
/// 지우면 되돌린 것이 아니라 더 깎아 낸 것이 된다. 다른 프로세스가 복구할 때는 무엇을
/// 만들었는지 알 수 없으므로 아무 폴더도 지우지 않는다(빈 폴더는 세계가 아니다 §3.4).
fn rollback(
    root: &Path,
    active: &Path,
    plan: &Plan,
    made: &[PathBuf],
) -> Result<(), RestoreFailure> {
    failpoint::fail_at("in-rollback", Stage::Rollback)?;
    let backup = active.join(BACKUP);

    for step in plan.steps() {
        let at = root.join(step.path.as_str());
        match &step.operation {
            // 없던 파일이었다 — 다시 없앤다.
            Operation::Create { .. } => {
                match fs::remove_file(&at) {
                    Ok(()) => {}
                    Err(source) if source.kind() == io::ErrorKind::NotFound => {}
                    Err(source) => {
                        return Err(RestoreFailure::Io {
                            stage: Stage::Rollback,
                            doing: "새로 만든 파일을 도로 지우지",
                            path: at.display().to_string(),
                            said: source.to_string(),
                        });
                    }
                }
            }
            // 있던 파일이었다 — 보관해 둔 원본과 권한을 되살린다.
            Operation::Replace { backup: id, mode, .. }
            | Operation::Delete { backup: id, mode, .. } => {
                restore_one(&backup.join(id.to_string()), &at, *mode)?;
            }
        }
    }
    // **우리가 만든 폴더만**, 그리고 비었을 때만 거둔다. 깊은 것부터 지워야 안에서
    // 바깥으로 비워진다.
    let mut ours: Vec<&PathBuf> = made.iter().collect();
    ours.sort_by_key(|path| std::cmp::Reverse(path.components().count()));
    for dir in ours {
        if dir.starts_with(root) && dir != root {
            let _ = fs::remove_dir(dir);
        }
    }
    Ok(())
}

fn restore_one(from: &Path, to: &Path, mode: u32) -> Result<(), RestoreFailure> {
    let parent = to.parent().expect("프로젝트 상대 경로에는 부모가 있다");
    make_dir(parent, Stage::Rollback)?;

    let temp = temp_beside(to);
    copy_out(from, &temp).map_err(|source| RestoreFailure::Io {
        stage: Stage::Rollback,
        doing: "보관해 둔 원본을 되살리지",
        path: to.display().to_string(),
        said: source.to_string(),
    })?;
    set_mode(&temp, Some(mode))?;
    fs::rename(&temp, to).map_err(|source| RestoreFailure::Io {
        stage: Stage::Rollback,
        doing: "원본을 제자리로 옮기지",
        path: to.display().to_string(),
        said: source.to_string(),
    })?;
    sync_dir(parent, Stage::Rollback)
}

// ── commit 과 cleanup ──────────────────────────────────────────────────────

/// forward restore 를 성공으로 확정한다.
///
/// **순서가 전부다.** 보관한 원본을 먼저 지우고 표식을 나중에 쓰면, 그 사이에 죽었을 때
/// 다음 명령이 「rollback 해야 한다」고 판단하고도 되돌릴 자료가 없다.
///
/// ```text
/// COMMITTED 를 쓰고 fsync         ← 여기가 지나면 되돌리지 않는다
/// active 를 fsync
/// active → cleanup-* 로 이름 변경
/// restore 폴더를 fsync
/// cleanup-* 제거
/// ```
fn commit(area: &Area, active: &Path) -> Result<(), RestoreFailure> {
    failpoint::crash_at("before-commit");
    failpoint::fail_at("before-commit", Stage::Commit)?;

    write_durable(&active.join(COMMITTED), &[], Stage::Commit)?;
    sync_dir(active, Stage::Commit)?;
    failpoint::crash_at("after-commit");

    finish(area, active)
}

/// 논리 결정이 끝난 transaction 을 잔해 자리로 옮기고 지운다.
fn finish(area: &Area, active: &Path) -> Result<(), RestoreFailure> {
    let leftover = area.cleanup();
    fs::rename(active, &leftover).map_err(|source| RestoreFailure::Io {
        stage: Stage::Cleanup,
        doing: "끝난 transaction 을 잔해 자리로 옮기지",
        path: leftover.display().to_string(),
        said: source.to_string(),
    })?;
    sync_dir(area.root(), Stage::Cleanup)?;
    failpoint::crash_at("before-cleanup");

    remove_canonical(&leftover, Kind::Cleanup)?;
    sync_dir(area.root(), Stage::Cleanup)
}

// ── 다음 명령의 복구 ───────────────────────────────────────────────────────

/// 프로젝트를 열기 전에 restore 영역을 정리한다 — **`state.yaml` 을 읽기보다 먼저.**
///
/// 미완의 transaction 이 남긴 파일 위에서 상태를 읽으면, 그 상태는 **아무도 확정한 적 없는
/// 세계**를 설명하게 된다.
///
/// ```text
/// preparing-*            rollback 이 아직 안 걸렸다 — 그냥 치운다
/// active/ (COMMITTED 없음) 되돌린 뒤 치운다
/// active/COMMITTED       되돌리지 않는다 — 잔해만 치운다
/// cleanup-*              이미 결정이 끝났다 — 치운다
/// 그 밖의 이름            거절한다. 모르는 것을 지우지 않는다
/// ```
///
/// 복구가 실패하면 **원래 명령을 실행하지 않는다.**
/// restore 영역에 남아 있는 것들 — **이름만 모은다. 아무것도 건드리지 않는다.**
///
/// `recover` 와 [`left_behind`] 가 이 한 자리를 함께 쓴다. 「무엇이 남았는가」를 두 군데서
/// 세면 한쪽이 낡아, 복구하는 쪽과 복구가 필요하다고 말하는 쪽의 판단이 갈린다.
fn area_entries(area: &Area) -> Result<Vec<(String, PathBuf)>, RestoreFailure> {
    let entries = match fs::read_dir(area.root()) {
        Ok(entries) => entries,
        // 아직 아무도 복원한 적이 없다. 정상이다.
        Err(source) if source.kind() == io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(source) => {
            return Err(RestoreFailure::Io {
                stage: Stage::Recovery,
                doing: "restore 영역을 들여다보지",
                path: area.root().display().to_string(),
                said: source.to_string(),
            });
        }
    };
    // 이름을 먼저 전부 모은다 — 지우면서 읽으면 무엇을 보았는지 흔들린다.
    let mut found: Vec<(String, PathBuf)> = Vec::new();
    for entry in entries {
        let entry = entry.map_err(|source| RestoreFailure::Io {
            stage: Stage::Recovery,
            doing: "restore 영역을 들여다보지",
            path: area.root().display().to_string(),
            said: source.to_string(),
        })?;
        found.push((entry.file_name().to_string_lossy().into_owned(), entry.path()));
    }
    Ok(found)
}

/// 미완의 복원이 남아 있는가 — **보기만 한다.**
///
/// 읽기만 하는 열기가 쓰는 문이다. 여기서 `Some` 이 나오면 그 Project 는 **아무도 확정한 적
/// 없는 세계** 위에 서 있으므로, 읽는 쪽은 복구하지 않고 그 사실을 그대로 거절해야 한다
/// (Host UI Model §9.1.1). 무엇이 남았는지 사람이 읽을 수 있게 이름으로 돌려준다.
pub(crate) fn left_behind(gil: &Path) -> Result<Option<String>, RestoreFailure> {
    let area = Area::at(gil);
    let found = area_entries(&area)?;
    if found.is_empty() {
        return Ok(None);
    }
    let mut names: Vec<String> = found.into_iter().map(|(name, _)| name).collect();
    names.sort();
    Ok(Some(names.join(", ")))
}

pub(crate) fn recover(root: &Path, gil: &Path) -> Result<(), RestoreFailure> {
    let area = Area::at(gil);
    let mut found = area_entries(&area)?;
    if found.is_empty() {
        return Ok(());
    }

    // **active 를 먼저 처리한다.** 잔해를 치우다 실패해 rollback 을 못 하는 일이 없게.
    found.sort_by_key(|(name, _)| Area::classify(name) != Some(Kind::Active));

    for (name, path) in found {
        let Some(kind) = Area::classify(&name) else {
            return Err(RestoreFailure::StrangeArea {
                path: path.display().to_string(),
            });
        };
        match kind {
            Kind::Preparing | Kind::Cleanup => remove_canonical(&path, kind)?,
            Kind::Active => recover_active(root, &area, &path)?,
        }
    }
    sync_dir(area.root(), Stage::Recovery)
}

fn recover_active(root: &Path, area: &Area, active: &Path) -> Result<(), RestoreFailure> {
    // 표식이 있으면 **되돌리지 않는다.** forward 는 이미 확정됐다.
    if active.join(COMMITTED).exists() {
        return finish(area, active);
    }

    let bytes = fs::read(active.join(PLAN)).map_err(|source| RestoreFailure::Io {
        stage: Stage::Recovery,
        doing: "남은 transaction 의 계획을 읽지",
        path: active.join(PLAN).display().to_string(),
        said: source.to_string(),
    })?;
    let plan = Plan::decode(&bytes).map_err(RestoreFailure::Plan)?;

    // 보관해 둔 원본이 계획이 말한 만큼 전부 있는가 — 되돌리기 **전에** 본다.
    let backup = active.join(BACKUP);
    for step in plan.steps() {
        if let Some(id) = step.operation.backup()
            && !backup.join(id.to_string()).is_file()
        {
            return Err(RestoreFailure::BackupMissing {
                path: step.path.as_str().to_string(),
            });
        }
    }

    let world = plan.world();
    rollback(root, active, &plan, &[]).map_err(|source| RestoreFailure::RecoveryRequired {
        world,
        cause: Box::new(RestoreFailure::Injected {
            stage: Stage::Recovery,
        }),
        then: Box::new(source),
    })?;

    // 되돌린 결과가 실행 전 세계와 같은가.
    let found = observe(root).map_err(|source| RestoreFailure::Observe {
        stage: Stage::Recovery,
        said: source.to_string(),
    })?;
    if found != plan.before_world() {
        return Err(RestoreFailure::RollbackDidNotLand);
    }
    finish(area, active)
}

// ── 파일 연장 ──────────────────────────────────────────────────────────────

/// GIL 이 만든 구조만 지운다. **모르는 것이 있으면 지우지 않고 거절한다.**
fn remove_canonical(at: &Path, kind: Kind) -> Result<(), RestoreFailure> {
    let strange = |path: &Path| RestoreFailure::StrangeArea {
        path: path.display().to_string(),
    };

    let entries = match fs::read_dir(at) {
        Ok(entries) => entries,
        Err(source) if source.kind() == io::ErrorKind::NotFound => return Ok(()),
        Err(source) => {
            return Err(RestoreFailure::Io {
                stage: Stage::Cleanup,
                doing: "transaction 자리를 들여다보지",
                path: at.display().to_string(),
                said: source.to_string(),
            });
        }
    };

    for entry in entries {
        let entry = entry.map_err(|source| RestoreFailure::Io {
            stage: Stage::Cleanup,
            doing: "transaction 자리를 들여다보지",
            path: at.display().to_string(),
            said: source.to_string(),
        })?;
        let name = entry.file_name().to_string_lossy().into_owned();
        let path = entry.path();
        // 심볼릭 링크는 따라가지 않는다 — 따라가면 밖의 것을 지운다.
        let kind_of = fs::symlink_metadata(&path)
            .map_err(|source| RestoreFailure::Io {
                stage: Stage::Cleanup,
                doing: "transaction 자리의 항목을 보지",
                path: path.display().to_string(),
                said: source.to_string(),
            })?
            .file_type();

        match name.as_str() {
            PLAN | COMMITTED if kind_of.is_file() => remove_file(&path)?,
            BACKUP if kind_of.is_dir() => {
                remove_backups(&path)?;
                remove_dir(&path)?;
            }
            _ => return Err(strange(&path)),
        }
    }
    let _ = kind;
    remove_dir(at)
}

/// 보관 자리에는 **불투명한 서수 이름의 일반 파일**만 있다.
fn remove_backups(at: &Path) -> Result<(), RestoreFailure> {
    let entries = fs::read_dir(at).map_err(|source| RestoreFailure::Io {
        stage: Stage::Cleanup,
        doing: "보관 자리를 들여다보지",
        path: at.display().to_string(),
        said: source.to_string(),
    })?;
    for entry in entries {
        let entry = entry.map_err(|source| RestoreFailure::Io {
            stage: Stage::Cleanup,
            doing: "보관 자리를 들여다보지",
            path: at.display().to_string(),
            said: source.to_string(),
        })?;
        let name = entry.file_name().to_string_lossy().into_owned();
        let path = entry.path();
        let is_file = fs::symlink_metadata(&path)
            .map(|data| data.file_type().is_file())
            .unwrap_or(false);
        if !is_file || name.is_empty() || !name.bytes().all(|b| b.is_ascii_digit()) {
            return Err(RestoreFailure::StrangeArea {
                path: path.display().to_string(),
            });
        }
        remove_file(&path)?;
    }
    Ok(())
}

fn remove_file(at: &Path) -> Result<(), RestoreFailure> {
    fs::remove_file(at).map_err(|source| RestoreFailure::Io {
        stage: Stage::Cleanup,
        doing: "잔해를 지우지",
        path: at.display().to_string(),
        said: source.to_string(),
    })
}

fn remove_dir(at: &Path) -> Result<(), RestoreFailure> {
    fs::remove_dir(at).map_err(|source| RestoreFailure::Io {
        stage: Stage::Cleanup,
        doing: "잔해 폴더를 지우지",
        path: at.display().to_string(),
        said: source.to_string(),
    })
}

/// 파일이 사라져 비게 된 폴더를 루트까지 거슬러 치운다.
///
/// **빈 디렉터리는 Artifact 세계가 아니다**(§3.4). 그래서 남겨 두어도 세계는 같지만,
/// 복원한 자리에 빈 껍데기가 쌓이는 것은 사람이 보기에 되돌아간 것이 아니다.
fn prune_empty(root: &Path, from: &Path) {
    let mut cursor = from.parent();
    while let Some(dir) = cursor {
        if dir == root || !dir.starts_with(root) {
            return;
        }
        if fs::remove_dir(dir).is_err() {
            return;
        }
        cursor = dir.parent();
    }
}

/// 옆자리 임시 이름 — **같은 폴더 안**이라 rename 이 파일 시스템을 넘지 않는다.
fn temp_beside(at: &Path) -> PathBuf {
    let mut name = std::ffi::OsString::from(at.file_name().unwrap_or_default());
    name.push(format!(
        ".gil-restore-{}-{}",
        std::process::id(),
        NEXT_TICKET.fetch_add(1, Ordering::Relaxed)
    ));
    at.with_file_name(name)
}

fn copy_out(from: &Path, to: &Path) -> io::Result<()> {
    let mut source = File::open(from)?;
    let mut sink = File::create(to)?;
    io::copy(&mut source, &mut sink)?;
    sink.flush_and_sync()
}

/// `flush` + `sync_all` 을 한 이름으로 — 두 줄을 빠뜨리지 않게.
trait Durable {
    fn flush_and_sync(&mut self) -> io::Result<()>;
}

impl Durable for File {
    fn flush_and_sync(&mut self) -> io::Result<()> {
        use io::Write as _;
        self.flush()?;
        self.sync_all()
    }
}

fn durable(file: &mut File, at: &Path, stage: Stage) -> Result<(), RestoreFailure> {
    file.flush_and_sync().map_err(|source| RestoreFailure::Io {
        stage,
        doing: "디스크에 밀어 넣지",
        path: at.display().to_string(),
        said: source.to_string(),
    })
}

fn write_durable(at: &Path, bytes: &[u8], stage: Stage) -> Result<(), RestoreFailure> {
    use io::Write as _;
    let mut file = File::create(at).map_err(|source| RestoreFailure::Io {
        stage,
        doing: "파일을 만들지",
        path: at.display().to_string(),
        said: source.to_string(),
    })?;
    file.write_all(bytes).map_err(|source| RestoreFailure::Io {
        stage,
        doing: "파일에 쓰지",
        path: at.display().to_string(),
        said: source.to_string(),
    })?;
    durable(&mut file, at, stage)
}

/// 폴더를 만들고 **이번에 새로 생긴 것들**을 돌려준다.
///
/// 되돌릴 때 지울 것과 원래 있던 것을 가르려면, 만든 쪽이 그 사실을 알아야 한다.
fn make_dir(at: &Path, stage: Stage) -> Result<Vec<PathBuf>, RestoreFailure> {
    let mut fresh: Vec<PathBuf> = Vec::new();
    let mut cursor = Some(at);
    while let Some(dir) = cursor {
        if dir.exists() {
            break;
        }
        fresh.push(dir.to_path_buf());
        cursor = dir.parent();
    }
    fs::create_dir_all(at).map_err(|source| RestoreFailure::Io {
        stage,
        doing: "폴더를 만들지",
        path: at.display().to_string(),
        said: source.to_string(),
    })?;
    Ok(fresh)
}

/// 이름이 디렉터리에 실제로 새겨지도록 부모를 디스크에 밀어 넣는다.
///
/// Unix 에서만 한다. macOS 의 `fsync` 는 드라이브 쓰기 캐시까지 비우지 않으므로
/// (`F_FULLFSYNC` 가 그 일을 한다), 여기서 얻는 것은 **파일 시스템 계층까지의 내구성**이다.
#[cfg(unix)]
fn sync_dir(at: &Path, stage: Stage) -> Result<(), RestoreFailure> {
    File::open(at)
        .and_then(|dir| dir.sync_all())
        .map_err(|source| RestoreFailure::Io {
            stage,
            doing: "폴더를 디스크에 밀어 넣지",
            path: at.display().to_string(),
            said: source.to_string(),
        })
}

#[cfg(not(unix))]
fn sync_dir(_at: &Path, _stage: Stage) -> Result<(), RestoreFailure> {
    Ok(())
}

#[cfg(unix)]
fn set_mode(at: &Path, mode: Option<u32>) -> Result<(), RestoreFailure> {
    use std::os::unix::fs::PermissionsExt;
    let Some(mode) = mode else {
        // 새로 만드는 파일은 시스템 기본 권한을 쓴다 — Snapshot 에 권한이 없으므로
        // 「원래 권한」이라 부를 것이 없다.
        return Ok(());
    };
    fs::set_permissions(at, fs::Permissions::from_mode(mode)).map_err(|source| RestoreFailure::Io {
        stage: Stage::Apply,
        doing: "권한을 되살리지",
        path: at.display().to_string(),
        said: source.to_string(),
    })
}

#[cfg(not(unix))]
fn set_mode(_at: &Path, _mode: Option<u32>) -> Result<(), RestoreFailure> {
    Ok(())
}

/// 이 자리의 현재 권한. Unix 가 아니면 0.
#[cfg(unix)]
pub(crate) fn mode_of(at: &Path) -> u32 {
    use std::os::unix::fs::PermissionsExt;
    fs::symlink_metadata(at)
        .map(|data| data.permissions().mode())
        .unwrap_or(0o644)
}

#[cfg(not(unix))]
pub(crate) fn mode_of(_at: &Path) -> u32 {
    0
}

// ── 시험용 실패 지점 ───────────────────────────────────────────────────────

/// **정해진 지점에서 죽거나 실패하게 만드는 손** — 시험에만 있다.
///
/// crash recovery 는 「그 순간에 죽으면」을 재는 것이라, 밖에서 만들 수 없는 순간이 필요하다.
/// 그래서 그 순간들에만 이름을 붙여 연다. 이름은 여기 적힌 것뿐이고, 무장하지 않으면
/// 아무 일도 하지 않는다.
///
/// `debug_assertions` 가 켜진 빌드에서만 컴파일된다 — 배포 빌드에는 이 코드가 없다.
#[cfg(debug_assertions)]
pub(crate) mod failpoint {
    use super::{RestoreFailure, Stage};

    /// 이 지점에서 **프로세스를 즉시 죽인다** — 전원이 끊긴 것과 같다.
    const CRASH: &str = "GIL_RESTORE_CRASH";
    /// 이 지점에서 **오류를 돌려준다** — I/O 가 실패한 것과 같다.
    const FAIL: &str = "GIL_RESTORE_FAIL";

    fn armed(key: &str, point: &str) -> bool {
        std::env::var(key).is_ok_and(|value| value == point)
    }

    /// 정해진 지점에서 프로젝트 파일 하나를 **밖에서** 고친다 — `<지점>:<경로>`.
    ///
    /// 「잠금은 편집기를 막지 않는다」(§9)를 재려면 GIL 이 일하는 중간을 비집어야 하는데,
    /// 그 순간은 밖에서 만들 수 없다. 두 자리를 연다.
    ///
    /// ```text
    /// after-prepare:<경로>   적용 직전 검사가 잡아야 한다
    /// after-apply:<경로>     최종 결과 확인이 잡아야 한다
    /// ```
    const MEDDLE: &str = "GIL_RESTORE_MEDDLE";

    pub(super) fn meddle(point: &str, root: &std::path::Path) {
        let Ok(value) = std::env::var(MEDDLE) else {
            return;
        };
        let Some(relative) = value.strip_prefix(point).and_then(|rest| rest.strip_prefix(':'))
        else {
            return;
        };
        let at = root.join(relative);
        if let Ok(mut text) = std::fs::read(&at) {
            text.extend_from_slice(b"!");
            let _ = std::fs::write(&at, text);
        }
    }

    pub(super) fn crash_at(point: &str) {
        if armed(CRASH, point) {
            // `abort` 다 — unwind 하지 않으므로 Drop 도 돌지 않는다. 진짜 죽음에 가깝다.
            std::process::abort();
        }
    }

    pub(super) fn fail_at(point: &str, stage: Stage) -> Result<(), RestoreFailure> {
        match armed(FAIL, point) {
            true => Err(RestoreFailure::Injected { stage }),
            false => Ok(()),
        }
    }
}

#[cfg(not(debug_assertions))]
mod failpoint {
    use super::{RestoreFailure, Stage};

    pub(super) fn meddle(_point: &str, _root: &std::path::Path) {}

    pub(super) fn crash_at(_point: &str) {}

    pub(super) fn fail_at(_point: &str, _stage: Stage) -> Result<(), RestoreFailure> {
        Ok(())
    }
}

// ── 오류 ───────────────────────────────────────────────────────────────────

/// 어느 단계에서 멈췄는가 — **사람이 할 일이 단계마다 다르다.**
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Stage {
    Preflight,
    Prepare,
    Apply,
    Verify,
    Commit,
    Rollback,
    Cleanup,
    Recovery,
}

impl Stage {
    /// 이 단계에서 멈췄다면 프로젝트 파일은 어떤 상태인가.
    fn files(self) -> &'static str {
        match self {
            Stage::Preflight | Stage::Prepare => "프로젝트 파일은 하나도 바뀌지 않았다.",
            Stage::Apply | Stage::Verify | Stage::Commit | Stage::Cleanup => {
                "복원을 되돌려 실행 전 세계로 돌아갔다."
            }
            Stage::Rollback | Stage::Recovery => {
                "되돌리다 멈췄다 — **복구가 필요하다.** 다음 GIL 명령이 이어서 시도한다."
            }
        }
    }
}

impl fmt::Display for Stage {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Stage::Preflight => "사전 검사",
            Stage::Prepare => "준비",
            Stage::Apply => "적용",
            Stage::Verify => "결과 확인",
            Stage::Commit => "확정",
            Stage::Rollback => "되돌리기",
            Stage::Cleanup => "잔해 정리",
            Stage::Recovery => "복구",
        })
    }
}

/// 복원이 멈춘 이유.
///
/// [`walk::RestoreError`](crate::RestoreError) 와 다른 것이다 — 그쪽은 **저장 파일이 걸어서
/// 만들 수 없는 꼴**이라는 뜻이고, 이쪽은 **작업 폴더를 되돌리다 멈췄다**는 뜻이다.
#[derive(Debug)]
pub enum RestoreFailure {
    /// 목표 세계의 blob 하나가 없거나 손상됐다.
    Blob {
        world: SnapshotRef,
        path: String,
        said: String,
    },
    /// 프로젝트를 관측하지 못했다.
    Observe { stage: Stage, said: String },
    /// 남은 계획을 읽지 못했다.
    Plan(PlanError),
    /// 적용 직전에 그 자리가 계획이 본 것과 달라져 있었다.
    ChangedUnderneath { path: String },
    /// 되돌릴 원본이 없다.
    BackupMissing { path: String },
    /// 적용을 마쳤는데 결과가 목표 세계가 아니다.
    NotTheTargetWorld,
    /// 되돌렸는데 실행 전 세계가 아니다.
    RollbackDidNotLand,
    /// restore 영역에 GIL 이 모르는 것이 있다.
    StrangeArea { path: String },
    /// 앞으로 가지 못해 **되돌렸다.** 프로젝트 파일은 실행 전 그대로다.
    RolledBack {
        world: SnapshotRef,
        cause: Box<RestoreFailure>,
    },
    /// 되돌리는 것마저 실패했다 — **복구가 필요하다.**
    RecoveryRequired {
        world: SnapshotRef,
        cause: Box<RestoreFailure>,
        then: Box<RestoreFailure>,
    },
    /// 시험이 심어 둔 실패.
    Injected { stage: Stage },
    Io {
        stage: Stage,
        doing: &'static str,
        path: String,
        said: String,
    },
}

impl RestoreFailure {
    /// 어느 단계에서 멈췄는가.
    pub fn stage(&self) -> Stage {
        match self {
            RestoreFailure::Blob { .. } => Stage::Preflight,
            RestoreFailure::Plan(_) | RestoreFailure::BackupMissing { .. } => Stage::Recovery,
            RestoreFailure::ChangedUnderneath { .. } => Stage::Apply,
            RestoreFailure::NotTheTargetWorld => Stage::Verify,
            RestoreFailure::RollbackDidNotLand => Stage::Rollback,
            RestoreFailure::StrangeArea { .. } => Stage::Recovery,
            RestoreFailure::RolledBack { cause, .. } => cause.stage(),
            RestoreFailure::RecoveryRequired { .. } => Stage::Rollback,
            RestoreFailure::Observe { stage, .. }
            | RestoreFailure::Injected { stage }
            | RestoreFailure::Io { stage, .. } => *stage,
        }
    }

    /// 프로젝트 파일이 지금 어떤 상태인가 — 한 줄로.
    pub fn files(&self) -> &'static str {
        match self {
            RestoreFailure::RolledBack { .. } => "복원을 되돌려 실행 전 세계로 돌아갔다.",
            RestoreFailure::RecoveryRequired { .. } => {
                "되돌리다 멈췄다 — **복구가 필요하다.** 다음 GIL 명령이 이어서 시도한다."
            }
            other => other.stage().files(),
        }
    }

    fn why(&self) -> String {
        match self {
            RestoreFailure::Blob { world, path, said } => format!(
                "{world} 를 이루는 파일 {path:?} 의 내용이 창고에 없거나 손상됐다 — {said}"
            ),
            RestoreFailure::Observe { said, .. } => said.clone(),
            RestoreFailure::Plan(source) => format!("남은 transaction 의 계획이 온전하지 않다 — {source}"),
            RestoreFailure::ChangedUnderneath { path } => format!(
                "{path:?} 가 준비하는 사이에 밖에서 바뀌었다 — GIL 잠금은 편집기의 쓰기를 막지 않는다"
            ),
            RestoreFailure::BackupMissing { path } => {
                format!("{path:?} 를 되돌릴 원본이 보관 자리에 없다")
            }
            RestoreFailure::NotTheTargetWorld => {
                "적용을 마쳤는데 결과가 목표 세계와 다르다".to_string()
            }
            RestoreFailure::RollbackDidNotLand => {
                "되돌렸는데 실행 전 세계와 다르다".to_string()
            }
            RestoreFailure::StrangeArea { path } => {
                format!("{path} 는 GIL 이 만든 transaction 자료가 아니다 — 모르는 것을 지우지 않는다")
            }
            RestoreFailure::RolledBack { cause, .. } => cause.why(),
            RestoreFailure::RecoveryRequired { cause, then, .. } => {
                format!("{}\n그리고 되돌리다 다시 멈췄다 — {}", cause.why(), then.why())
            }
            RestoreFailure::Injected { .. } => "시험이 심어 둔 실패".to_string(),
            RestoreFailure::Io {
                doing, path, said, ..
            } => format!("{path} 를 {doing} 못했다 — {said}"),
        }
    }

    /// 이 실패의 목표 세계. 목표를 정하기 전에 멈췄으면 없다.
    fn world(&self) -> Option<SnapshotRef> {
        match self {
            RestoreFailure::Blob { world, .. }
            | RestoreFailure::RolledBack { world, .. }
            | RestoreFailure::RecoveryRequired { world, .. } => Some(*world),
            _ => None,
        }
    }
}

impl fmt::Display for RestoreFailure {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        writeln!(f, "거절: Artifact 세계를 복원하지 못했다.\n")?;
        if let Some(world) = self.world() {
            writeln!(f, "목표\n  {world}\n")?;
        }
        writeln!(f, "멈춘 단계\n  {}\n", self.stage())?;
        writeln!(f, "이유\n  {}\n", self.why().replace('\n', "\n  "))?;
        writeln!(f, "프로젝트 파일\n  {}\n", self.files())?;
        writeln!(
            f,
            "논리 상태\n  Step·Will·Journey·Graph 는 바뀌지 않았다.\n"
        )?;
        write!(f, "실행\n  {}", self.next_move())
    }
}

impl RestoreFailure {
    fn next_move(&self) -> &'static str {
        match self {
            RestoreFailure::ChangedUnderneath { .. } => {
                "다른 프로그램이 이 폴더를 쓰고 있지 않은지 확인한 뒤 `gil restore`"
            }
            RestoreFailure::StrangeArea { .. } => "그 자리를 직접 확인한 뒤 다시 시도한다",
            RestoreFailure::RecoveryRequired { .. } => {
                "다음 GIL 명령이 복구를 이어서 시도한다 — `gil status`"
            }
            RestoreFailure::Blob { .. } => "창고가 손상됐다 — 이 세계는 되살릴 수 없다",
            _ => "gil status",
        }
    }
}

impl From<ObserveError> for RestoreFailure {
    fn from(source: ObserveError) -> RestoreFailure {
        RestoreFailure::Observe {
            stage: Stage::Preflight,
            said: source.to_string(),
        }
    }
}

impl std::error::Error for RestoreFailure {}

