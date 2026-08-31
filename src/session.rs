//! 프로젝트 트랜잭션 — **한 GIL 명령이 프로젝트를 쥐고 있는 동안.**
//!
//! ```text
//! 프로젝트 루트와 .gil 자리를 정한다
//! → 잠금을 잡는다                    ← 여기서 실패하면 아무것도 읽지 않았다
//! → state.yaml 을 읽고 복원·검증한다
//! → 명령을 수행한다
//! → state.yaml 을 저장한다
//! → 값이 떨어지며 잠금이 풀린다
//! ```
//!
//! **읽은 뒤에 잠그지 않는다.** 읽고 나서 잠그면 그 사이에 다른 명령이 끝나 버려, 이미
//! 낡은 상태를 손에 쥔 채 잠금을 얻는다. 그것은 잠금이 없는 것과 같다.
//!
//! # 왜 이 타입이 공개인가
//!
//! 잠금 guard 자체([`ProjectLock`])는 내보내지 않는다. 밖으로 나가는 것은 **잠금을 이미
//! 쥔 트랜잭션** 하나다 — 그래야 「잠그는 것을 잊는다」는 상태가 타입에 존재하지 않는다.
//! 이 값을 손에 넣었다는 것이 곧 잠갔다는 뜻이고, 이 값이 떨어졌다는 것이 곧 풀렸다는
//! 뜻이다.
//!
//! # 이 보장이 미치지 않는 곳
//!
//! [`load`](crate::load)·[`save`](crate::save) 는 여전히 잠금 없이 부를 수 있는 저층
//! 함수다. 라이브러리를 직접 쓰는 코드가 그 길로 가면 이 직렬화는 적용되지 않는다.
//! CLI 는 전부 이 트랜잭션을 지나므로 **GIL 명령끼리는** 보장된다(Artifact Model §10.6).

use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};

use crate::artifact::{self, Manifest, ObjectStore};
use crate::cycle::CycleKind;
use crate::cycles::{CycleId, CycleRevisit, CycleRevisitError, CyclesError, OpenAfterRevisitError};
use crate::lock::{LOCK_FILE, LockError, ProjectLock};
use crate::node::NodeKind;
use crate::project::{ActionError, Closed, ClosedCycle, Opened, Project};
use crate::refs::SnapshotRef;
use crate::report::Report;
use crate::restore::{self, RestoreFailure, Restored};
use crate::rules::RuleSet;
use crate::store::{self, LEGACY_WALK_PATH, StoreError};
use crate::will::ActionContract;

/// `.gil/` 안에서 **초기화를 막지 않는** 이름들.
///
/// 이전에 중단된 `gil start` 나 미참조 객체가 남긴 내부 흔적이다. 이것들만 있는 `.gil` 은
/// 「아직 아무 논리 상태도 없는 자리」이므로 다시 시도할 수 있다.
const INTERNAL_ONLY: &[&str] = &[LOCK_FILE, "artifacts", "restore"];

/// 한 GIL 명령이 이 프로젝트를 쥐고 있는 동안 사는 값.
pub struct ProjectSession {
    project: Project,
    state_path: PathBuf,
    /// **맨 뒤에 선언한다.** Rust 는 필드를 선언 차례로 떨어뜨리므로, 잠금이 마지막에
    /// 풀린다. 위의 것들이 떨어질 때까지 프로젝트는 여전히 잠겨 있다.
    _lock: ProjectLock,
}

impl ProjectSession {
    /// 이미 있는 프로젝트를 연다 — **잠근 다음에 읽는다.**
    ///
    /// `state_path` 는 `<루트>/.gil/state.yaml` 이다. 그 자리를 찾는 일은 부르는 쪽의
    /// 몫이다 — 어디서부터 거슬러 올라 찾을지는 표면마다 다르다.
    pub fn open(rules: RuleSet, state_path: impl AsRef<Path>) -> Result<Self, SessionError> {
        let state_path = state_path.as_ref().to_path_buf();
        let gil = gil_dir(&state_path)?;

        let lock = ProjectLock::acquire(&gil).map_err(SessionError::from)?;

        // **잠금 → 복구 → 잔해 회수 → state 읽기.** 순서가 전부다.
        //
        // 미완의 복원이 남긴 파일 위에서 상태를 읽으면, 그 상태는 **아무도 확정한 적 없는
        // 세계**를 설명하게 된다. 그래서 파일을 먼저 제자리로 돌린 뒤에 읽는다.
        // 복구가 실패하면 원래 명령을 실행하지 않는다.
        restore::recover(&project_root(&gil)?, &gil).map_err(SessionError::Restore)?;
        reap_tmp(&ObjectStore::at(&gil))?;

        let project = store::load_within(&lock, rules, &state_path).map_err(SessionError::Store)?;

        Ok(ProjectSession {
            project,
            state_path,
            _lock: lock,
        })
    }

    /// 새 프로젝트를 세운다 — **잠근 다음에 무엇이 이미 있는지 본다.**
    ///
    /// 잠그기 전에 보면 두 `gil start` 가 나란히 「비어 있다」를 읽고 각자 다른 최초 상태를
    /// 세운다. 그래서 순서가 뒤집히면 안 된다.
    ///
    /// 아직 저장하지는 않는다. [`commit`](Self::commit) 이 그것을 한다 — 둘 다 같은 잠금
    /// 안에 있다.
    pub fn start(rules: RuleSet, state_path: impl AsRef<Path>) -> Result<Self, SessionError> {
        let state_path = state_path.as_ref().to_path_buf();
        let gil = gil_dir(&state_path)?;

        // `.gil/` 을 만들며 잠근다. 초기화가 실패해 잠금 파일 하나가 남는 것은 손상이
        // 아니다 — 파일의 존재는 초기화 완료도 잠금 보유도 뜻하지 않는다.
        let lock = ProjectLock::bootstrap(&gil).map_err(SessionError::from)?;
        let store = ObjectStore::at(&gil);
        restore::recover(&project_root(&gil)?, &gil).map_err(SessionError::Restore)?;
        reap_tmp(&store)?;
        initializable(&gil, &state_path)?;
        check_object_store(&store)?;

        // **최초 세계는 지금 여기 있는 파일들이다.** 빈 세계로 만들지 않는다 — 그러면
        // 첫 Verify 가 「전부 새로 생겼다」로 보이고, 그것은 일어난 일이 아니다(§4).
        let root = project_root(&gil)?;
        let world = capture(&root, &store)?;

        Ok(ProjectSession {
            project: Project::start(rules, world),
            state_path,
            _lock: lock,
        })
    }

    pub fn project(&self) -> &Project {
        &self.project
    }

    pub fn project_mut(&mut self) -> &mut Project {
        &mut self.project
    }

    /// 읽어 온 **그 파일**. 읽은 자리와 쓰는 자리가 갈리면 적은 것이 다른 데로 간다.
    pub fn state_path(&self) -> &Path {
        &self.state_path
    }

    /// 지금 상태를 눕힌다 — **아직 잠금을 쥔 채로.**
    ///
    /// 여기 닿았을 때는 이미 필요한 blob·manifest 가 전부 확정되고 재검증까지 끝나 있다.
    /// 순서가 뒤집히면 `state.yaml` 이 아직 없는 객체를 가리키는 순간이 생긴다(§10).
    pub fn commit(&self) -> Result<(), SessionError> {
        store::save_within(&self._lock, &self.project, &self.state_path).map_err(SessionError::Store)
    }

    /// 이 프로젝트의 루트 — Artifact 세계가 사는 자리.
    pub fn root(&self) -> Result<PathBuf, SessionError> {
        project_root(&gil_dir(&self.state_path)?)
    }

    fn store(&self) -> Result<ObjectStore, SessionError> {
        Ok(ObjectStore::at(&gil_dir(&self.state_path)?))
    }
}

/// **한 GIL 명령 = 한 transaction.** 세계를 만지는 문은 전부 여기 있다.
///
/// 도메인([`Project`])은 순수해서 파일을 볼 수 없다. 그래서 「지금 폴더가 기준 세계와
/// 같은가」를 묻는 일은 여기서만 할 수 있고, 그 물음을 지나지 않는 Close 는 CLI 에 없다.
impl ProjectSession {
    pub fn open_action_step(
        &mut self,
        kind: NodeKind,
        contract: ActionContract,
    ) -> Result<Opened, SessionError> {
        self.project
            .open_action_step(kind, contract)
            .map_err(SessionError::Action)
    }

    pub fn open_child_cycle(&mut self, kind: CycleKind) -> Result<CycleId, SessionError> {
        self.project.open_child_cycle(kind).map_err(SessionError::Cycles)
    }

    /// **되돌아온 자리에서 새 갈래를 연다.**
    ///
    /// Cycle container 를 여는 것이라 Artifact 를 관측하지 않고 Snapshot 도 확정하지 않는다.
    /// 새 Cycle 의 Entry 는 **저장된 대상의 Exit** 을 읽는다 — 지금 폴더를 다시 재지 않는다.
    pub fn open_branch_cycle(&mut self, kind: CycleKind) -> Result<CycleId, SessionError> {
        self.project.open_branch_cycle(kind).map_err(SessionError::Branch)
    }

    /// **Cycle 계층의 되돌아감을 밟는다 — 논리 상태를 먼저 확정하고 세계를 뒤따르게 한다.**
    ///
    /// 이 문은 아직 **어느 명령에도 걸려 있지 않다.** pending 을 소비해 새 Cycle 을 여는
    /// 동작이 서기 전에 공개하면 사용자가 빠져나올 수 없는 자리가 생긴다(M4-D 가 잇는다).
    /// 지금 공개된 까닭은 하나뿐이다 — 이 순서를 바깥에서 재현해 검증하기 위해서다.
    ///
    /// # 순서가 전부다
    ///
    /// ```text
    /// 1. 사전 검사   clean 인가 · 밟을 것이 적혀 있는가 · 그 세계가 창고에 있는가
    /// 2. ② state    옮긴 논리 상태를 원자적으로 교체한다
    /// 3. ③ 작업 폴더 기존 restore transaction 으로 대상의 Exit 세계를 투영한다
    /// ```
    ///
    /// **②보다 먼저 폴더를 만지지 않는다.** 작업 폴더는 논리 상태에서 유도되는 투영이므로,
    /// 먼저 옮겨 두면 「폴더는 대상의 세계인데 상태는 아직 실패 Cycle」이라는, 스스로의
    /// clean 전제에 자기가 걸리는 자리가 생긴다.
    ///
    /// **③이 실패해도 ②를 되돌리지 않는다.** 논리 이동은 이미 확정됐고, 그 사실을 숨기면
    /// 다음 명령이 무엇을 해야 하는지 알 수 없게 된다. 남는 상태는 하나뿐이다 —
    /// 「상태는 대상, 폴더는 아직」 — 그리고 그 처방은 이미 지어진 멱등 `gil restore` 다.
    /// 그것이 유도하는 목표가 바로 이 대상의 Exit 세계이므로 한 번에 수렴한다.
    pub fn revisit_cycle(&mut self) -> Result<CycleRevisited, SessionError> {
        // ── 사전 검사 ─────────────────────────────────────────────────────
        //
        // 여기서 거절하면 state·작업 폴더·창고·Journey·Will 어느 것도 바뀌지 않는다.
        let before = self.world_state()?;
        if let WorldState::Dirty { world, changes } = before {
            return Err(SessionError::RevisitNeedsCleanWorld { world, changes });
        }
        if let WorldState::Unknown { said, .. } = before {
            return Err(SessionError::Observe { said });
        }

        // 논리 이동은 **복사본 위에서** 계산한다. 저장이 서기 전까지 이 세션이 쥔 상태는
        // 한 글자도 바뀌지 않는다.
        let mut next = self.project.clone();
        let moved = next.revisit_cycle().map_err(SessionError::Revisit)?;

        // 되돌아갈 세계가 창고에 실제로 있는지 **저장 전에** 묻는다. 뒤에 물으면 논리만
        // 옮겨 놓고 돌아갈 곳이 없다는 사실을 그때 알게 된다.
        let address = next
            .world_manifest(moved.target_world)
            .ok_or(SessionError::UnknownWorld {
                world: moved.target_world,
            })?
            .clone();
        let store = self.store()?;
        let target = store
            .read_manifest(&address)
            .map_err(|source| SessionError::Manifest {
                world: moved.target_world,
                said: source.to_string(),
            })?;
        let root = self.root()?;
        let gil = gil_dir(&self.state_path)?;

        // ── ② 논리 상태 ───────────────────────────────────────────────────
        //
        // 저장이 실패하면 ③ 을 **시작하지 않는다.** 그리고 이 세션이 쥔 상태도 옮기지
        // 않는다 — 확정되지 않은 이동을 확정된 척 들고 있지 않는다.
        failpoint::fail_at("before-state-save")?;
        store::save_within(&self._lock, &next, &self.state_path).map_err(SessionError::Store)?;
        self.project = next;
        failpoint::crash_at("after-state-save");
        failpoint::fail_at("after-state-save")?;

        // ── ③ 작업 폴더 ───────────────────────────────────────────────────
        let world = restore::run(&root, &gil, &store, moved.target_world, &target).map_err(
            |source| SessionError::RevisitWorldIncomplete {
                moved,
                source: Box::new(source),
            },
        )?;
        Ok(CycleRevisited { moved, world })
    }

    pub fn revisit_step(&mut self) -> Result<(), SessionError> {
        self.project
            .cycles_mut()
            .current_mut()
            .revisit_step()
            .map_err(|source| SessionError::Action(source.into()))
    }

    /// 열려 있는 자리를 닫는다 — **Verify 인지 아닌지는 여기서 가른다.**
    ///
    /// ```text
    /// verify      관측 → 객체 확정 → 이름 발급 → 닫는다
    /// 그 밖       세계가 기준과 같은지 먼저 묻고, 같을 때만 닫는다
    /// ```
    pub fn close_step(&mut self, report: Report) -> Result<Closed, SessionError> {
        // **pending 을 먼저 묻는다.** 되돌아온 자리에는 열린 Step 이 없으므로 그냥 두면
        // 「닫을 자리가 없다」로 거절되는데, 그 말은 사실이지만 무엇을 해야 하는지
        // 알려 주지 않는다. 판정은 `Project` 의 그 함수 하나가 한다.
        self.project.no_pending_revisit().map_err(SessionError::Action)?;
        let cycle = self.project.cycles().current();
        let opened = cycle
            .step_now_open()
            .ok_or(SessionError::Action(ActionError::NothingOpen))?;
        let kind = cycle
            .steps()
            .node(opened)
            .expect("방금 자리를 받아 왔다")
            .kind;

        match self.can_confirm_artifact() {
            true => self.close_verify(report),
            false => {
                self.require_clean(Gate::Step(cycle.step_ref(opened), kind))?;
                self.project
                    .close_action_step(report)
                    .map_err(SessionError::Action)
            }
        }
    }

    /// Verify 를 닫으며 지금 세계를 확정한다.
    ///
    /// 객체를 먼저 눕히고 그 다음에 도메인을 움직인다. 객체 확정 뒤에 도메인이나 저장이
    /// 실패하면 **객체는 미참조로 남을 수 있지만** 논리 상태의 부분 변경은 남지 않는다
    /// (Artifact Model §3.5·§10).
    fn close_verify(&mut self, report: Report) -> Result<Closed, SessionError> {
        let world = capture(&self.root()?, &self.store()?)?;
        self.project
            .close_verify_step(report, world)
            .map_err(SessionError::Action)
    }

    /// Cycle 을 닫는다 — **새 세계를 만들지 않는다.**
    ///
    /// Exit 은 안에서 이미 확정된 것 중에서 유도된다([`Cycle::exit_would_be`]). 그래서
    /// 여기서 하는 일은 「지금 폴더가 그 세계와 같은가」를 묻는 것뿐이다.
    pub fn close_cycle(&mut self, report: Report) -> Result<ClosedCycle, SessionError> {
        let cycle = self.project.cycles().current();
        self.require_clean(Gate::Cycle(cycle.id().to_ref()))?;
        self.project
            .close_cycle(report)
            .map_err(SessionError::Action)
    }

    /// **지금 자리에서 Artifact 변경을 확정할 수 있는가 — 판정은 여기 한 자리다.**
    ///
    /// 세계를 확정할 권한은 열린 Verify 에만 있다(Artifact Model §5). `gil close` 의 갈림,
    /// `gil status` 의 안내, `gil help` 의 Topic 선택이 **같은 이 함수**를 부른다 — 셋이
    /// 각자 재면 언젠가 갈리고, 그러면 화면과 실행이 서로 다른 말을 한다.
    pub fn can_confirm_artifact(&self) -> bool {
        self.open_step_kind() == Some(NodeKind::Verify)
    }

    /// 지금 **열려 있는** 자리의 Kind. 닫혀 있거나 Cycle 경계면 `None`.
    fn open_step_kind(&self) -> Option<NodeKind> {
        let cycle = self.project.cycles().current();
        cycle
            .step_now_open()
            .and_then(|at| cycle.steps().node(at))
            .map(|node| node.kind)
    }

    /// **작업 폴더를 지금 위치가 요구하는 세계로 되돌린다.**
    ///
    /// 목표는 고르는 것이 아니라 [`Project::world_snapshot`](crate::Project::world_snapshot)
    /// 이 유도한다 — dirty 판정·Cycle Exit·복원이 **같은 함수 하나**를 쓴다. 두 자리에
    /// 적으면 한쪽이 낡고, 그러면 「닫을 수 있다」와 「되돌아갈 곳」이 서로 다른 세계를
    /// 가리킨다.
    ///
    /// 논리 상태는 하나도 바뀌지 않는다. `state.yaml` 도 저장하지 않는다.
    pub fn restore(&self) -> Result<Restored, SessionError> {
        let world = self.project.world_snapshot();
        let address = self
            .project
            .world_manifest(world)
            .ok_or(SessionError::UnknownWorld { world })?
            .clone();
        let store = self.store()?;
        let target = store
            .read_manifest(&address)
            .map_err(|source| SessionError::Manifest {
                world,
                said: source.to_string(),
            })?;

        restore::run(
            &self.root()?,
            &gil_dir(&self.state_path)?,
            &store,
            world,
            &target,
        )
        .map_err(SessionError::Restore)
    }

    /// 지금 폴더가 **구조적으로 유도한 기준 세계**와 같은가.
    ///
    /// 세계를 확정할 권한은 Verify 에만 있다(§5). 그래서 그 밖의 Close 는 세계를 바꾸지
    /// 않았을 때만 지날 수 있다 — 바뀐 채로 닫으면 그 변경은 **어느 Snapshot 에도 속하지
    /// 않는 사실**이 되고, 나중에 되돌아갈 곳을 잃는다.
    fn require_clean(&self, gate: Gate) -> Result<(), SessionError> {
        match self.world_state()? {
            WorldState::Clean { .. } => Ok(()),
            WorldState::Dirty { world, changes } => Err(SessionError::Dirty {
                gate,
                world,
                changes,
            }),
            // 판정하지 못한 것은 dirty 가 **아니다.** 모르는 것을 안다고 말하지 않는다.
            WorldState::Unknown { said, .. } => Err(SessionError::Observe { said }),
        }
    }

    /// **지금 폴더가 기준 세계와 어떤 관계인가 — 하나뿐인 읽기 경로.**
    ///
    /// dirty gate([`close_step`](Self::close_step)·[`close_cycle`](Self::close_cycle))도,
    /// [`restore`](Self::restore)도, `gil status` 도 전부 이 함수를 지난다. 세 자리가 각자
    /// 재면 언젠가 갈리고, 그러면 「닫을 수 있다」와 「되돌아갈 곳」과 「지금 상태」가
    /// 서로 다른 세계를 말하게 된다.
    ///
    /// 기준 세계 자체도 새로 계산하지 않는다 —
    /// [`Project::world_snapshot`](crate::Project::world_snapshot) 이 유도한 것을 그대로 쓴다.
    ///
    /// **아무것도 쓰지 않는다.** 저장하지 않고 관측하므로 창고도 커지지 않는다.
    pub fn world_state(&self) -> Result<WorldState, SessionError> {
        let world = self.project.world_snapshot();
        let address = self
            .project
            .world_manifest(world)
            .ok_or(SessionError::UnknownWorld { world })?
            .clone();
        let store = self.store()?;
        let expected = store
            .read_manifest(&address)
            .map_err(|source| SessionError::Manifest {
                world,
                said: source.to_string(),
            })?;

        // 관측이 실패하면 **모른다고 말한다.** 심볼릭 링크나 중첩 GIL 을 만나 못 본 것을
        // 「바뀌었다」로 옮기면, 사람은 바꾼 적 없는 것을 되돌리려 한다.
        let found = match artifact::observe(&self.root()?) {
            Ok(found) => found,
            Err(source) => {
                return Ok(WorldState::Unknown {
                    world,
                    said: source.to_string(),
                });
            }
        };

        Ok(match found == expected {
            true => WorldState::Clean { world },
            false => WorldState::Dirty {
                world,
                changes: differences(&expected, &found),
            },
        })
    }
}

/// **되돌아감이 끝난 뒤 손에 남는 것** — 논리 이동과 세계 투영, 둘 다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CycleRevisited {
    /// 어디서 갈라져 어디에 섰고, 어느 세계를 목표로 삼았는가.
    pub moved: CycleRevisit,
    /// 그 세계를 실제로 투영한 결과. 이미 같은 세계였다면 `no_op` 이다.
    pub world: Restored,
}

/// 되돌아감의 두 경계를 바깥에서 끊어 보기 위한 자리.
///
/// ②와 ③ 사이는 프로세스가 죽는 그 순간에만 존재한다 — 밖에서는 만들 수 없다.
/// `restore` 쪽 failpoint 와 같은 규율을 쓰고, **release 빌드에는 없다.**
#[cfg(debug_assertions)]
mod failpoint {
    use super::SessionError;

    const CRASH: &str = "GIL_REVISIT_CRASH";
    const FAIL: &str = "GIL_REVISIT_FAIL";

    fn armed(key: &str, point: &str) -> bool {
        std::env::var(key).is_ok_and(|value| value == point)
    }

    pub(super) fn crash_at(point: &str) {
        if armed(CRASH, point) {
            // `abort` 다 — Drop 이 돌지 않으므로 잠금도 운영체제가 거둔다.
            std::process::abort();
        }
    }

    pub(super) fn fail_at(point: &str) -> Result<(), SessionError> {
        match armed(FAIL, point) {
            true => Err(SessionError::Injected { point: point.to_string() }),
            false => Ok(()),
        }
    }
}

#[cfg(not(debug_assertions))]
mod failpoint {
    use super::SessionError;

    pub(super) fn crash_at(_point: &str) {}

    pub(super) fn fail_at(_point: &str) -> Result<(), SessionError> {
        Ok(())
    }
}

/// 작업 폴더와 기준 세계의 관계. **읽기만 해서 얻는 값이다.**
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum WorldState {
    /// 폴더가 기준 세계와 같다.
    Clean { world: SnapshotRef },
    /// 다르다. `changes` 는 사람이 읽을 만큼만 잘린 요약이다 — 전체 목록이 아니다.
    Dirty {
        world: SnapshotRef,
        changes: Vec<String>,
    },
    /// **판정하지 못했다.** dirty 가 아니라 모른다는 뜻이다.
    Unknown { world: SnapshotRef, said: String },
}

impl WorldState {
    /// 어느 세계를 기준으로 삼았는가. 셋 다 이것은 안다.
    pub fn world(&self) -> SnapshotRef {
        match self {
            WorldState::Clean { world }
            | WorldState::Dirty { world, .. }
            | WorldState::Unknown { world, .. } => *world,
        }
    }
}

/// dirty 판정이 걸린 자리 — 사람이 할 일이 다르므로 구분해 말한다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Gate {
    Step(crate::refs::StepRef, NodeKind),
    Cycle(crate::refs::CycleRef),
}

/// 두 세계가 어떻게 다른가 — **사람이 읽을 만큼만.**
const SHOWN: usize = 12;

fn differences(expected: &Manifest, found: &Manifest) -> Vec<String> {
    let mut out = Vec::new();
    for entry in found.entries() {
        match expected.get(&entry.path) {
            None => out.push(format!("새로 생김  {}", entry.path.as_str())),
            Some(before) if before != &entry.content => {
                out.push(format!("바뀜      {}", entry.path.as_str()))
            }
            Some(_) => {}
        }
    }
    for entry in expected.entries() {
        if found.get(&entry.path).is_none() {
            out.push(format!("사라짐    {}", entry.path.as_str()));
        }
    }
    // 잘라 낼 때는 **잘랐다고 말한다.** 조용히 줄이면 목록이 전부인 줄 안다.
    if out.len() > SHOWN {
        let hidden = out.len() - SHOWN;
        out.truncate(SHOWN);
        out.push(format!("… 그리고 {hidden} 개 더"));
    }
    out
}

/// `.gil/` 이 사는 프로젝트 루트.
fn project_root(gil: &Path) -> Result<PathBuf, SessionError> {
    gil.parent()
        .filter(|parent| !parent.as_os_str().is_empty())
        .map(Path::to_path_buf)
        .ok_or_else(|| SessionError::NoProjectDir {
            path: gil.display().to_string(),
        })
}

/// 지금 폴더를 관측해 blob 과 manifest 를 확정하고 **그 세계의 주소**를 돌려준다.
///
/// 여기서 돌아온 시점에 객체는 전부 눕고 재검증까지 끝나 있다. `state.yaml` 이 그 주소를
/// 가리키는 것은 그 다음이다.
fn capture(root: &Path, store: &ObjectStore) -> Result<crate::ManifestAddress, SessionError> {
    let manifest = artifact::capture(root, store)
        .map_err(|source| SessionError::Observe { said: source.to_string() })?;
    store
        .put_manifest(&manifest)
        .map_err(|source| SessionError::Object {
            said: source.to_string(),
        })
}

/// `.gil/artifacts/tmp/` 의 잔해를 거둔다 — **GIL 이 만든 이름만.**
///
/// ```text
/// <pid>-<표> 인 일반 파일   지운다
/// 그 밖의 이름              거절한다
/// 디렉터리·심볼릭 링크      거절한다
/// tmp 가 없음               정상
/// ```
///
/// 모르는 것을 지우지 않는다. 그리고 **살아 있는 다른 GIL 프로세스의 임시 파일을 지울 수
/// 없다** — 이 함수는 프로젝트 잠금을 쥔 채로만 불리고, 잠금을 쥔 명령은 한 번에 하나다.
fn reap_tmp(store: &ObjectStore) -> Result<(), SessionError> {
    let tmp = store.tmp();
    let entries = match fs::read_dir(&tmp) {
        Ok(entries) => entries,
        // 아직 아무도 확정한 적이 없다. 정상이다.
        Err(source) if source.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(source) => {
            return Err(SessionError::Unreadable {
                path: tmp.display().to_string(),
                source: source.to_string(),
            });
        }
    };

    for entry in entries {
        let entry = entry.map_err(|source| SessionError::Unreadable {
            path: tmp.display().to_string(),
            source: source.to_string(),
        })?;
        let name = entry.file_name();
        let name = name.to_string_lossy().into_owned();
        let path = entry.path();

        // `symlink_metadata` 다 — 따라가면 링크가 가리키는 것을 보고 「일반 파일」이라
        // 답하고, 그러면 링크를 지우면서 남의 파일을 지웠다고 믿게 된다.
        let kind = fs::symlink_metadata(&path)
            .map_err(|source| SessionError::Unreadable {
                path: path.display().to_string(),
                source: source.to_string(),
            })?
            .file_type();

        if !kind.is_file() || !ObjectStore::is_temp_name(&name) {
            return Err(SessionError::StrangeTemp {
                path: path.display().to_string(),
            });
        }
        fs::remove_file(&path).map_err(|source| SessionError::Unreadable {
            path: path.display().to_string(),
            source: source.to_string(),
        })?;
    }
    Ok(())
}

/// 창고 최상위에 GIL 이 모르는 것이 있는가 — `gil start` 를 다시 시도하기 전에.
///
/// 조용히 무시하지도, 지우지도 않는다. 무엇인지 모르는 것 위에 새 프로젝트를 세우는 것은
/// 되돌릴 수 없다.
fn check_object_store(store: &ObjectStore) -> Result<(), SessionError> {
    let entries = match fs::read_dir(store.root()) {
        Ok(entries) => entries,
        Err(source) if source.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(source) => {
            return Err(SessionError::Unreadable {
                path: store.root().display().to_string(),
                source: source.to_string(),
            });
        }
    };
    for entry in entries {
        let entry = entry.map_err(|source| SessionError::Unreadable {
            path: store.root().display().to_string(),
            source: source.to_string(),
        })?;
        let name = entry.file_name();
        let name = name.to_string_lossy();
        if !ObjectStore::TOP_LEVEL.contains(&name.as_ref()) {
            return Err(SessionError::StrangeObjectStore {
                path: store.root().display().to_string(),
                found: name.into_owned(),
            });
        }
    }
    Ok(())
}

impl fmt::Debug for ProjectSession {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("ProjectSession")
            .field("state_path", &self.state_path)
            .finish_non_exhaustive()
    }
}

/// `state.yaml` 이 눕는 `.gil/` 자리.
fn gil_dir(state_path: &Path) -> Result<PathBuf, SessionError> {
    state_path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
        .map(Path::to_path_buf)
        .ok_or_else(|| SessionError::NoProjectDir {
            path: state_path.display().to_string(),
        })
}

/// 이 `.gil/` 에서 처음부터 시작해도 되는가 — **잠금을 쥔 채로 다시 본다.**
///
/// 안에 있는 것이 GIL 의 내부 흔적뿐이면 이전에 중단된 초기화로 보고 다시 시도한다.
/// 논리 상태나 모르는 파일이 있으면 **건드리지 않고 거절한다** — 무엇인지 모르는 것을
/// 새 프로젝트로 덮어쓰는 것은 되돌릴 수 없다.
fn initializable(gil: &Path, state_path: &Path) -> Result<(), SessionError> {
    if state_path.exists() {
        return Err(SessionError::AlreadyStarted {
            path: state_path.display().to_string(),
        });
    }
    let legacy = gil.join(
        Path::new(LEGACY_WALK_PATH)
            .file_name()
            .expect("앞 형식 경로에는 파일 이름이 있다"),
    );
    if legacy.exists() {
        return Err(SessionError::LegacyFormat {
            path: legacy.display().to_string(),
        });
    }

    let entries = fs::read_dir(gil).map_err(|source| SessionError::Unreadable {
        path: gil.display().to_string(),
        source: source.to_string(),
    })?;
    for entry in entries {
        let entry = entry.map_err(|source| SessionError::Unreadable {
            path: gil.display().to_string(),
            source: source.to_string(),
        })?;
        let name = entry.file_name();
        let name = name.to_string_lossy();
        if !INTERNAL_ONLY.contains(&name.as_ref()) {
            return Err(SessionError::NotEmpty {
                path: gil.display().to_string(),
                found: name.into_owned(),
            });
        }
    }
    Ok(())
}

/// 트랜잭션을 열지 못한 이유.
///
/// [`Busy`](SessionError::Busy)·[`LockUnavailable`](SessionError::LockUnavailable) 은
/// **상태를 읽기도 전에** 돌아온다. 어떤 파일도 만들거나 바꾸지 않았다.
#[derive(Debug)]
pub enum SessionError {
    /// 다른 GIL 명령이 이 프로젝트를 쥐고 있다.
    Busy { path: String },
    /// 잠금 자체를 걸 수 없었다 — 경쟁이 아니다.
    LockUnavailable { path: String, source: String },
    /// 여기에 이미 프로젝트가 있다.
    AlreadyStarted { path: String },
    /// 앞 형식의 기록이 있다.
    LegacyFormat { path: String },
    /// `.gil` 안에 GIL 이 모르는 것이 있다 — 덮어쓰지 않는다.
    NotEmpty { path: String, found: String },
    /// `state.yaml` 의 자리에 부모가 없다.
    NoProjectDir { path: String },
    /// 내부 저장소를 들여다보지 못했다.
    Unreadable { path: String, source: String },
    /// 상태를 읽거나 쓰지 못했다.
    Store(StoreError),

    // ── 세계 ──────────────────────────────────────────────────────────────
    /// 도메인이 거절했다 — 소유·행동·문법·Report.
    Action(ActionError),
    /// Cycle Graph 가 거절했다.
    Cycles(CyclesError),
    /// 프로젝트를 관측하지 못했다.
    ///
    /// 관측기의 오류 타입은 안에 남는다 — 밖으로 내보내면 창고의 내부 구조가 공개 계약이
    /// 된다. 여기 오는 것은 **이미 사람의 말로 적힌 이유**다.
    Observe { said: String },
    /// 객체를 확정하거나 읽지 못했다.
    Object { said: String },
    /// 기준 세계의 manifest 를 읽지 못했다.
    Manifest { world: SnapshotRef, said: String },
    /// 구조가 가리키는 세계가 registry 에 없다.
    UnknownWorld { world: SnapshotRef },
    /// 지금 폴더가 기준 세계와 다르다 — 이 자리는 세계를 확정할 권한이 없다.
    Dirty {
        gate: Gate,
        world: SnapshotRef,
        changes: Vec<String>,
    },
    /// `.gil/artifacts/tmp/` 에 GIL 이 만들지 않은 것이 있다.
    StrangeTemp { path: String },
    /// 창고 최상위에 GIL 이 모르는 것이 있다.
    StrangeObjectStore { path: String, found: String },
    /// 복원이나 복구가 멈췄다.
    Restore(RestoreFailure),

    // ── Cycle 계층의 되돌아감 ─────────────────────────────────────────────
    /// Cycle Graph 가 되돌아감을 거절했다.
    Revisit(CycleRevisitError),
    /// 되돌아온 자리에서 새 갈래를 열지 못했다.
    Branch(OpenAfterRevisitError),
    /// 되돌아가려는데 폴더가 기준 세계와 다르다.
    ///
    /// `Dirty` 와 가르는 까닭은 사람이 할 일이 다르기 때문이다 — 여기서는 닫을 자리가 없고,
    /// 되돌린 뒤 **같은 명령을 다시** 부르면 된다.
    RevisitNeedsCleanWorld {
        world: SnapshotRef,
        changes: Vec<String>,
    },
    /// **논리 이동은 확정됐고 작업 폴더 복원이 끝나지 않았다.**
    ///
    /// 「아무것도 바뀌지 않았다」고 말하면 안 되는 유일한 자리다. 상태는 이미 대상 조상에
    /// 서 있고, 남은 것은 폴더를 그 세계로 맞추는 일뿐이다.
    RevisitWorldIncomplete {
        moved: CycleRevisit,
        source: Box<RestoreFailure>,
    },
    /// 시험이 심어 둔 실패 — debug 빌드에만 있다.
    #[cfg(debug_assertions)]
    Injected { point: String },
}

impl SessionError {
    /// 다른 GIL 명령이 쥐고 있어 물러선 것인가.
    pub fn is_busy(&self) -> bool {
        matches!(self, SessionError::Busy { .. })
    }

    /// 이 오류가 **이미 완결된 receipt** 인가 — 무엇이·왜·다음에 무엇을 까지 스스로 말하는가.
    ///
    /// 그렇다면 부르는 쪽은 이것을 다시 감싸지 않는다. 감싸면 이유 안에 또 이유가 들어가고,
    /// 사람은 같은 말을 두 번 읽으며 어느 쪽이 제 할 일인지 헷갈린다.
    pub fn is_receipt(&self) -> bool {
        matches!(
            self,
            SessionError::Busy { .. }
                | SessionError::LockUnavailable { .. }
                | SessionError::Dirty { .. }
                | SessionError::StrangeTemp { .. }
                | SessionError::StrangeObjectStore { .. }
                | SessionError::NotEmpty { .. }
                | SessionError::Observe { .. }
                | SessionError::Manifest { .. }
                | SessionError::UnknownWorld { .. }
                | SessionError::Restore(_)
                | SessionError::Revisit(_)
                | SessionError::RevisitNeedsCleanWorld { .. }
                | SessionError::RevisitWorldIncomplete { .. }
        )
    }
}

impl From<LockError> for SessionError {
    fn from(error: LockError) -> SessionError {
        match error {
            LockError::Busy { path } => SessionError::Busy {
                path: path.display().to_string(),
            },
            LockError::Unavailable {
                path,
                doing,
                source,
            } => SessionError::LockUnavailable {
                path: path.display().to_string(),
                source: format!("{doing} 못했다 — {source}"),
            },
        }
    }
}

impl fmt::Display for SessionError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            SessionError::Busy { .. } => write!(
                f,
                "다른 GIL 명령이 이 프로젝트를 사용하고 있다.\n\n\
                 현재 상태를 읽거나 변경하지 않았다.\n\
                 앞선 명령이 끝난 뒤 다시 시도한다."
            ),
            SessionError::LockUnavailable { path, source } => write!(
                f,
                "이 프로젝트를 잠그지 못했다 ({path}) — {source}.\n\n\
                 현재 상태를 읽거나 변경하지 않았다.\n\
                 `.gil` 이 잠금을 지원하는 파일 시스템에 있는지 확인한다 \
                 (네트워크 파일 시스템에서는 지원되지 않을 수 있다)."
            ),
            SessionError::AlreadyStarted { path } => {
                write!(f, "이미 걷고 있다 ({path}).")
            }
            SessionError::LegacyFormat { path } => write!(
                f,
                "{}",
                StoreError::LegacyFormat {
                    path: path.clone()
                }
            ),
            SessionError::NotEmpty { path, found } => write!(
                f,
                "{path} 안에 GIL 이 모르는 것이 있다 ({found}).\n\n\
                 새 프로젝트를 세우면 그것을 덮어쓸 수 있어 시작하지 않는다.\n\
                 그 자리를 직접 정리한 뒤 다시 시도한다 — GIL 은 남의 파일을 치우지 않는다."
            ),
            SessionError::NoProjectDir { path } => {
                write!(f, "{path} 는 프로젝트 안의 자리가 아니다.")
            }
            SessionError::Unreadable { path, source } => {
                write!(f, "{path} 를 들여다보지 못했다 — {source}.")
            }
            SessionError::Store(source) => write!(f, "{source}"),

            SessionError::Action(source) => write!(f, "{source}"),
            SessionError::Cycles(source) => write!(f, "{source}"),
            SessionError::Observe { said } => write!(
                f,
                "{said}\n\n어떤 Snapshot 도 확정하지 않았다. \
                 Node·Will·Journey 는 닫히지도 움직이지도 않았다."
            ),
            SessionError::Object { said } => write!(f, "{said}"),
            SessionError::Manifest { world, said } => write!(
                f,
                "기준 세계 {world} 의 manifest 를 읽지 못했다 — {said}\n\
                 Node·Will·Journey 는 닫히지도 움직이지도 않았다."
            ),
            SessionError::UnknownWorld { world } => write!(
                f,
                "{world} 가 이 프로젝트의 registry 에 없다 — \
                 이름 순서나 지금 위치로 추측해 고치지 않는다."
            ),
            SessionError::Dirty {
                gate,
                world,
                changes,
            } => {
                let (what, todo) = match gate {
                    // **지금 여기서 할 수 있는 일만 말한다.** 「verify 로 가라」는 안내는
                    // Interview 안에서는 밟을 수 없는 길이다 — Interview 에 verify 가 없고,
                    // 이 Cycle 을 닫는 것도 같은 gate 에 막힌다. 그러니 먼저 되돌린다.
                    Gate::Step(step, kind) => (
                        format!("{step} · {kind} 에서는 Artifact 변경을 확정할 수 없다."),
                        format!(
                            "`gil restore` 로 현재 변경을 되돌린 뒤 이 Step 을 닫는다.\n\
                             Artifact 를 변경해야 하는 작업은 Verify Step 에서 수행한다."
                        ),
                    ),
                    Gate::Cycle(cycle) => (
                        format!("{cycle} 을(를) 닫을 수 없다."),
                        format!(
                            "Cycle 을 닫는 것은 새 세계를 만들지 않는다.\n\
                             `gil restore` 로 현재 변경을 되돌린 뒤 닫는다."
                        ),
                    ),
                };
                write!(
                    f,
                    "거절: {what}\n\n이유\n  기준 세계 {world} 이후 프로젝트 파일이 바뀌었다.\n{}\n\n\
                     지금 해야 할 일\n{}\n\n\
                     현재 Step 과 Active Will 은 그대로 열려 있다 — \
                     Node 도 Will 도 Journey 도 움직이지 않았다.",
                    changes
                        .iter()
                        .map(|line| format!("    {line}"))
                        .collect::<Vec<_>>()
                        .join("\n"),
                    todo.lines()
                        .map(|line| format!("  {line}"))
                        .collect::<Vec<_>>()
                        .join("\n")
                )
            }
            SessionError::StrangeTemp { path } => write!(
                f,
                "{path} 는 GIL 이 만든 임시 파일이 아니다.\n\n\
                 모르는 것을 지우지 않는다. 그 자리를 직접 확인한 뒤 다시 시도한다.\n\
                 현재 상태를 읽거나 변경하지 않았다."
            ),
            SessionError::Restore(source) => write!(f, "{source}"),
            SessionError::StrangeObjectStore { path, found } => write!(
                f,
                "{path} 안에 GIL 이 모르는 것이 있다 ({found}).\n\n\
                 객체 창고에는 blobs·manifests·tmp 만 있다. \
                 모르는 것을 지우거나 무시하지 않는다."
            ),

            SessionError::Branch(source) => write!(f, "{source}"),
            SessionError::Revisit(source) => write!(
                f,
                "거절: 되돌아갈 수 없다.\n\n이유\n{}\n\n\
                 Cycle 도 Report 도 Journey 도 Will 도 움직이지 않았다.",
                indented(&source.to_string())
            ),
            SessionError::RevisitNeedsCleanWorld { world, changes } => write!(
                f,
                "거절: 되돌아갈 수 없다.\n\n\
                 이유\n  기준 세계 {world} 이후 프로젝트 파일이 바뀌었다.\n{}\n\n\
                 지금 해야 할 일\n  `gil restore` 로 현재 변경을 되돌린 뒤 다시 시도한다.\n\n\
                 Graph 도 Journey 도 작업 폴더도 움직이지 않았다.",
                changes
                    .iter()
                    .map(|line| format!("    {line}"))
                    .collect::<Vec<_>>()
                    .join("\n")
            ),
            // **여기서만은 「아무것도 바뀌지 않았다」고 말하지 않는다.** 논리 이동은 이미
            // 확정됐고, 그것을 숨기면 다음에 무엇을 해야 하는지 알 수 없게 된다.
            SessionError::RevisitWorldIncomplete { moved, source } => write!(
                f,
                "되돌아감이 절반에서 멈췄다.\n\n\
                 확정된 것\n  {} 에서 {} 로 옮겨 섰다 — 이 이동은 저장됐다.\n\n\
                 끝나지 않은 것\n  작업 폴더를 {} 로 되돌리지 못했다.\n{}\n\n\
                 위 「논리 상태」는 복원 자체가 한 말이다 — 되돌아감의 이동은 그와 별개로 \
                 이미 저장됐다.\n\n\
                 지금 해야 할 일\n  `gil restore` — 지금 자리가 가리키는 세계가 곧 {} 이므로 \
                 한 번에 수렴한다.",
                moved.from,
                moved.target,
                moved.target_world,
                indented(&source.to_string()),
                moved.target_world
            ),
            #[cfg(debug_assertions)]
            SessionError::Injected { point } => {
                write!(f, "시험이 {point:?} 에서 실패를 심었다")
            }
        }
    }
}

/// 여러 줄 이유를 한 칸 들여쓴다 — 이유 블록의 모양을 한 자리에서 정한다.
fn indented(said: &str) -> String {
    said.lines()
        .map(|line| format!("  {line}"))
        .collect::<Vec<_>>()
        .join("\n")
}

impl std::error::Error for SessionError {}

// ── 시험 ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn rules() -> RuleSet {
        RuleSet::builtin().expect("함께 실린 명세를 읽는다")
    }

    fn scratch(label: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!("gil-session-{label}"));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).expect("시험이 쓸 자리를 만든다");
        root
    }

    fn state_in(root: &Path) -> PathBuf {
        root.join(crate::STATE_PATH)
    }

    #[test]
    fn starting_makes_the_place_and_holds_it() {
        let root = scratch("start");
        let session = ProjectSession::start(rules(), state_in(&root)).expect("시작한다");
        session.commit().expect("눕힌다");

        assert!(state_in(&root).exists());
        assert!(root.join(".gil").join(LOCK_FILE).exists());
    }

    #[test]
    fn a_second_command_is_refused_while_one_holds_the_project() {
        let root = scratch("held");
        let held = ProjectSession::start(rules(), state_in(&root)).expect("시작한다");
        held.commit().unwrap();

        let err = ProjectSession::open(rules(), state_in(&root)).expect_err("둘이 들어왔다");
        assert!(err.is_busy(), "{err}");

        drop(held);
        ProjectSession::open(rules(), state_in(&root)).expect("풀린 뒤에는 열린다");
    }

    #[test]
    fn starting_twice_is_refused_by_the_state_that_is_already_there() {
        let root = scratch("twice");
        ProjectSession::start(rules(), state_in(&root))
            .expect("처음")
            .commit()
            .unwrap();

        let err = ProjectSession::start(rules(), state_in(&root)).expect_err("두 번 세웠다");
        assert!(matches!(err, SessionError::AlreadyStarted { .. }), "{err}");
    }

    #[test]
    fn a_leftover_lock_file_alone_does_not_stop_a_start() {
        // 중단된 초기화의 흔적이다. 사람이 손으로 지워야 하는 상태를 만들지 않는다.
        let root = scratch("leftover");
        fs::create_dir_all(root.join(".gil")).unwrap();
        fs::write(root.join(".gil").join(LOCK_FILE), b"").unwrap();

        ProjectSession::start(rules(), state_in(&root)).expect("잔해가 시작을 막았다");
    }

    #[test]
    fn unreferenced_objects_alone_do_not_stop_a_start() {
        let root = scratch("objects");
        fs::create_dir_all(root.join(".gil/artifacts/tmp")).unwrap();
        fs::create_dir_all(root.join(".gil/artifacts/blobs/sha256/ab")).unwrap();
        fs::write(root.join(".gil/artifacts/blobs/sha256/ab/cd"), b"x").unwrap();

        ProjectSession::start(rules(), state_in(&root)).expect("미참조 객체가 시작을 막았다");
    }

    #[test]
    fn something_gil_does_not_know_stops_a_start() {
        let root = scratch("stranger");
        fs::create_dir_all(root.join(".gil")).unwrap();
        fs::write(root.join(".gil/누군가의노트.md"), "소중한 것".as_bytes()).unwrap();

        let err = ProjectSession::start(rules(), state_in(&root)).expect_err("남의 것을 덮었다");
        assert!(matches!(err, SessionError::NotEmpty { .. }), "{err}");
        // **건드리지 않았다.**
        assert_eq!(fs::read(root.join(".gil/누군가의노트.md")).unwrap(), "소중한 것".as_bytes());
        assert!(!state_in(&root).exists());
    }

    #[test]
    fn a_legacy_record_stops_a_start() {
        let root = scratch("legacy");
        fs::create_dir_all(root.join(".gil")).unwrap();
        fs::write(root.join(crate::LEGACY_WALK_PATH), b"format: 0\n").unwrap();

        let err = ProjectSession::start(rules(), state_in(&root)).expect_err("앞 형식을 덮었다");
        assert!(matches!(err, SessionError::LegacyFormat { .. }), "{err}");
    }

    #[test]
    fn a_failed_open_leaves_the_project_unlocked() {
        // 오류로 나가는 길에서도 guard 가 떨어져야 다음 명령이 들어올 수 있다.
        let root = scratch("failed-open");
        fs::create_dir_all(root.join(".gil")).unwrap();

        let err = ProjectSession::open(rules(), state_in(&root)).expect_err("없는 것을 열었다");
        assert!(matches!(err, SessionError::Store(_)), "{err}");
        ProjectSession::open(rules(), state_in(&root)).expect_err("두 번째도 같은 이유로 실패");

        // 잠금은 남지 않았다 — 이제 start 가 들어갈 수 있다.
        ProjectSession::start(rules(), state_in(&root)).expect("잠금이 남았다");
    }

    #[test]
    fn the_session_writes_back_to_the_file_it_read() {
        let root = scratch("roundtrip");
        ProjectSession::start(rules(), state_in(&root))
            .expect("시작")
            .commit()
            .unwrap();

        let session = ProjectSession::open(rules(), state_in(&root)).expect("연다");
        assert_eq!(session.state_path(), state_in(&root));
        session.commit().expect("같은 자리에 눕힌다");
    }
}
