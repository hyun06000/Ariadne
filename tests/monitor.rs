//! Monitor Snapshot — **원본에서 한 번 읽은 사실 한 벌.**
//!
//! 여기서 재는 것은 다섯이다.
//!
//! 1. **같은 원본을 가리키는가** — CLI 가 보이는 자리와 Monitor 의 자리가 어긋나지 않는다.
//! 2. **구조와 판정을 섞지 않는가** — 계보는 `parent` 만, 실패는 verdict 만, 형제는 parent 만.
//! 3. **없는 것을 지어내지 않는가** — Will 도, Chain 도, 승인 mode 도, 아직 열리지 않은 Cycle 도.
//! 4. **못 본 것을 안다고 하지 않는가** — 관측 실패는 dirty 가 아니라 unknown 이다.
//! 5. **아무것도 쓰지 않는가** — 조회 전후 Graph·Journey·Will·창고·작업 파일이 같다.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};

use gil::{
    ActionKind, CycleKind, CycleRelation, MonitorSnapshot, NodeKind, NodeStatus, ProjectSession,
    TimelineRelation, WorldMark, render_monitor_html, render_monitor_text,
};

mod common;
use common::{
    ACTION, CYCLE_TARGET, REASON, bootstrap_from, contract, cycle_report, full_report, opened,
    spec,
};

const GIL: &str = env!("CARGO_BIN_EXE_gil");

// ── 연장 ───────────────────────────────────────────────────────────────────

fn state_in(dir: &Path) -> PathBuf {
    dir.join(gil::STATE_PATH)
}

fn bare(label: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("gil-monitor-{label}"));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).expect("시험이 쓸 자리를 만든다");
    dir
}

fn write(root: &Path, path: &str, bytes: &str) {
    fs::write(root.join(path), bytes).unwrap();
}

/// 프로젝트 폴더의 **세계** — `.gil` 은 세계가 아니므로 뺀다.
fn world_of(root: &Path) -> BTreeMap<String, Vec<u8>> {
    let mut out = BTreeMap::new();
    for entry in fs::read_dir(root).expect("들여다본다") {
        let entry = entry.expect("한 자리");
        if entry.file_name() == ".gil" {
            continue;
        }
        if entry.file_type().expect("종류").is_file() {
            out.insert(
                entry.file_name().to_string_lossy().into_owned(),
                fs::read(entry.path()).expect("읽는다"),
            );
        }
    }
    out
}

fn objects_of(root: &Path) -> BTreeMap<String, Vec<u8>> {
    let mut out = BTreeMap::new();
    collect(&root.join(".gil/artifacts"), &root.join(".gil"), &mut out);
    out
}

fn collect(at: &Path, base: &Path, out: &mut BTreeMap<String, Vec<u8>>) {
    let Ok(entries) = fs::read_dir(at) else {
        return;
    };
    for entry in entries {
        let entry = entry.expect("한 자리");
        let path = entry.path();
        match entry.file_type().expect("종류").is_dir() {
            true => collect(&path, base, out),
            false => {
                let key = path.strip_prefix(base).expect("안이다").to_string_lossy().into_owned();
                out.insert(key, fs::read(&path).expect("읽는다"));
            }
        }
    }
}

fn run(dir: &Path, args: &[&str]) -> Output {
    Command::new(GIL)
        .args(args)
        .current_dir(dir)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .expect("gil 을 부를 수 있어야 한다")
}

/// 실행형 자리를 연다 — **행동 계약은 stdin 으로 간다.**
fn open_action(dir: &Path, kind: &str) {
    use std::io::Write as _;
    let out = Command::new(GIL)
        .args(["open", kind])
        .current_dir(dir)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .and_then(|mut child| {
            child
                .stdin
                .as_mut()
                .expect("stdin")
                .write_all("objective: 그 목적\nnext_action: 그 행동\ndone_when: 그 조건\n".as_bytes())?;
            child.wait_with_output()
        })
        .expect("자리를 연다");
    assert!(
        out.status.success(),
        "gil open {kind} 가 실패했다:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
}

fn ok(dir: &Path, args: &[&str]) -> String {
    let out = run(dir, args);
    assert!(
        out.status.success(),
        "gil {args:?} 가 실패했다:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    String::from_utf8_lossy(&out.stdout).into_owned()
}

// ── 시험이 서는 세계 ───────────────────────────────────────────────────────

/// Experiment 하나를 세션을 통해 끝 경계까지 걷는다.
fn walk_exit(session: &mut ProjectSession, verdict: &str) {
    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
    ] {
        opened(session.project_mut(), kind);
        let cycle = session.project().cycles().current();
        let report = full_report(cycle.rules(), CycleKind::Experiment, kind);
        session
            .close_step(report)
            .unwrap_or_else(|err| panic!("{kind} 를 닫지 못했다: {err}"));
    }
    opened(session.project_mut(), NodeKind::Outcome);
    let cycle = session.project().cycles().current();
    let report = full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Outcome)
        .with("verdict", verdict)
        .with("lesson", "이 갈래가 남긴 것")
        .with(ACTION, "close_cycle")
        .with(REASON, "판정을 Cycle 경계로 넘긴다");
    session.close_step(report).expect("판정을 닫는다");
}

fn close_cycle_toward(session: &mut ProjectSession, verdict: &str, target: Option<&str>) {
    let cycle = session.project().cycles().current();
    let last = cycle.steps().current().expect("판정에 서 있다");
    let mut report = cycle_report(cycle, verdict, last);
    if let Some(target) = target {
        report.insert(CYCLE_TARGET, target);
    }
    session.close_cycle(report).expect("Cycle 을 닫는다");
    session.commit().expect("눕힌다");
}

/// Bootstrap Interview 를 지나 Experiment 하나를 연 프로젝트.
fn started(label: &str) -> (ProjectSession, PathBuf) {
    let dir = bare(label);
    write(&dir, "work.txt", "처음");
    let mut session = ProjectSession::start(spec(), state_in(&dir)).expect("시작한다");
    *session.project_mut() = bootstrap_from(session.project().clone());
    session.commit().expect("눕힌다");
    (session, dir)
}

/// `C1 → C2(success) → C3(failure → cycle:C1)` 까지 걷고 되돌아간 프로젝트.
///
/// 조부모를 대상으로 삼는다 — 그러면 계보 `[C1, C4]` 와 버린 가지 `[C2, C3]` 의 이름이
/// **서로 엇갈리게** 놓여 ID 크기로는 어느 쪽도 가릴 수 없다.
fn branched(label: &str) -> PathBuf {
    let (mut session, dir) = started(label);
    walk_exit(&mut session, "success");
    close_cycle_toward(&mut session, "success", None);
    session.open_child_cycle(CycleKind::Experiment).expect("자식을 연다");
    walk_exit(&mut session, "failure");
    close_cycle_toward(&mut session, "failure", Some("cycle:C1"));
    drop(session);

    ok(&dir, &["revisit"]);
    ok(&dir, &["open", "experiment"]);
    dir
}

fn monitor(dir: &Path) -> MonitorSnapshot {
    ProjectSession::open(spec(), state_in(dir))
        .expect("되살린다")
        .monitor()
        .expect("Snapshot 을 만든다")
}

/// 계보의 주소만 — 순서 그대로.
fn refs(list: &[gil::CycleFacts]) -> Vec<String> {
    list.iter().map(|cycle| cycle.cycle_ref.to_string()).collect()
}

// ── ① 같은 원본을 가리키는가 ─────────────────────────────────────────────

#[test]
fn the_status_and_the_monitor_point_at_the_same_facts() {
    // 두 화면은 문자열을 주고받지 않는다. 그래도 **같은 자리와 같은 세계**를 말해야 한다.
    let dir = branched("same-facts");
    let said = ok(&dir, &["status"]);
    let seen = monitor(&dir);

    assert_eq!(seen.current_cycle.facts.cycle_ref.to_string(), "cycle:C4");
    // status 는 사람이 읽는 축약(`Cycle 4`)으로, Monitor 는 typed reference 로 같은 자리를
    // 가리킨다. **두 화면이 같은 수를 말하는지**를 잰다.
    assert!(
        said.contains(&format!("Cycle {}", seen.current_cycle.facts.cycle_ref.number())),
        "status 가 다른 Cycle 을 말한다:\n{said}"
    );
    assert!(
        said.contains(&seen.world.baseline_snapshot_ref.to_string()),
        "status 가 다른 기준 세계를 말한다:\n{said}"
    );
    assert_eq!(seen.world.state, WorldMark::Clean);
    assert!(said.contains("clean"), "{said}");

    // 아직 아무 Step 도 열지 않은 새 Cycle — 두 쪽 다 그렇게 말한다.
    assert!(seen.current_step.is_none(), "{:?}", seen.current_step);
    assert!(said.contains("아직 아무것도 열지 않았다"), "{said}");

    // Step 을 하나 열면 두 쪽이 함께 움직인다.
    open_action(&dir, "define");
    let said = ok(&dir, &["status"]);
    let seen = monitor(&dir);
    let step = seen.current_step.expect("연 자리가 있다");
    assert_eq!(step.kind, NodeKind::Define);
    assert_eq!(step.state, NodeStatus::Open);
    assert!(said.contains("define"), "{said}");
    assert!(
        said.contains(&format!("#{}", step.step_ref.step())),
        "status 가 다른 자리를 말한다:\n{said}"
    );
}

// ── ② 구조와 판정을 섞지 않는가 ──────────────────────────────────────────

#[test]
fn the_active_lineage_and_the_revisit_source_are_told_apart() {
    let dir = branched("lineage");
    let seen = monitor(&dir);

    // 계보는 `parent` 만 따라간다 — 버린 갈래는 여기 없다.
    assert_eq!(refs(&seen.active_lineage), vec!["cycle:C1", "cycle:C4"]);
    assert_eq!(
        seen.current_cycle.facts.revisit_from_cycle_ref.map(|id| id.to_string()),
        Some("cycle:C3".to_string()),
        "갈래의 출처를 잃었다"
    );
    assert_eq!(
        seen.current_cycle.facts.parent_cycle_ref.map(|id| id.to_string()),
        Some("cycle:C1".to_string()),
        "부모와 출처를 섞었다"
    );

    // 그리고 그 출처는 **계보가 아니라** 관계로 표시된다.
    let source: Vec<_> = seen
        .inactive_cycles
        .iter()
        .filter(|cycle| cycle.relation_to_current == CycleRelation::RevisitSource)
        .map(|cycle| cycle.cycle_ref.to_string())
        .collect();
    assert_eq!(source, vec!["cycle:C3"]);
}

#[test]
fn failure_is_read_from_the_verdict_and_sibling_from_the_parent() {
    // **버린 가지를 모두 실패라고 부르지 않는다.** C2 는 성공했고 C3 은 실패했는데 둘 다
    // 계보 밖이다 — 관계는 구조가, 판정은 Report 가 말한다.
    let dir = branched("verdict");
    let seen = monitor(&dir);

    let by_ref = |name: &str| {
        seen.inactive_cycles
            .iter()
            .find(|cycle| cycle.cycle_ref.to_string() == name)
            .unwrap_or_else(|| panic!("{name} 이 계보 밖 목록에 없다"))
            .clone()
    };
    let c2 = by_ref("cycle:C2");
    let c3 = by_ref("cycle:C3");

    assert_eq!(c2.report.as_ref().map(|r| r.verdict.as_str()), Some("success"));
    assert_eq!(c3.report.as_ref().map(|r| r.verdict.as_str()), Some("failure"));
    assert_eq!(c2.relation_to_current, CycleRelation::Abandoned, "성공도 계보 밖일 수 있다");
    assert_eq!(c3.relation_to_current, CycleRelation::RevisitSource);

    // 형제 여부는 **parent 가 같을 때만** 유도된다. C3 의 부모는 C2 이고 지금 자리의
    // 부모는 C1 이므로, 둘은 형제가 아니다 — 모델이 그렇게 부르지도 않는다.
    assert_eq!(c3.parent_cycle_ref.map(|id| id.to_string()), Some("cycle:C2".into()));
    assert_ne!(c3.parent_cycle_ref, seen.current_cycle.facts.parent_cycle_ref);
}

#[test]
fn active_and_inactive_are_not_decided_by_id_size() {
    // 계보는 `[C1, C4]` 이고 버린 가지는 `[C2, C3]` 다. **이름의 크기로는 어느 쪽도
    // 가릴 수 없다** — 가장 작은 것과 가장 큰 것이 함께 계보 위에 있다.
    let dir = branched("id-size");
    let seen = monitor(&dir);

    let active: Vec<u32> = seen.active_lineage.iter().map(|cycle| cycle.cycle_ref.number()).collect();
    let inactive: Vec<u32> = seen
        .inactive_cycles
        .iter()
        .map(|cycle| cycle.cycle_ref.number())
        .collect();
    assert_eq!(active, vec![1, 4]);
    assert_eq!(inactive, vec![2, 3]);
    assert!(
        active.iter().min() < inactive.iter().min() && active.iter().max() > inactive.iter().max(),
        "이름의 크기가 두 무리를 가를 수 있게 배치됐다 — 이 시험이 아무것도 못 잡는다"
    );
}

// ── ③ 없는 것을 지어내지 않는가 ─────────────────────────────────────────

#[test]
fn a_pending_revisit_is_not_shown_as_an_opened_cycle() {
    let (mut session, dir) = started("pending");
    walk_exit(&mut session, "failure");
    close_cycle_toward(&mut session, "failure", Some("cycle:C1"));
    drop(session);
    ok(&dir, &["revisit"]);

    let seen = monitor(&dir);
    let pending = seen.pending_revisit.clone().expect("되돌아온 상태다");
    assert_eq!(pending.from_cycle_ref.to_string(), "cycle:C2");
    assert_eq!(pending.target_cycle_ref.to_string(), "cycle:C1");

    // **새 Cycle 은 아직 없다.** 지금 자리는 여전히 되돌아간 대상이다.
    assert_eq!(seen.current_cycle.facts.cycle_ref.to_string(), "cycle:C1");
    assert_eq!(seen.current_cycle.facts.state, NodeStatus::Closed);
    assert!(seen.current_cycle.facts.revisit_from_cycle_ref.is_none(), "없는 갈래를 지어냈다");
    assert_eq!(refs(&seen.active_lineage), vec!["cycle:C1"]);
    assert!(
        !seen.inactive_cycles.iter().any(|c| c.cycle_ref.number() > 2),
        "열리지 않은 Cycle 이 목록에 있다"
    );
    assert_eq!(seen.current_cycle.steps.len(), 4, "대상의 Step 이 새 Cycle 의 것처럼 보인다");

    // 그리고 지금 밟을 수 있는 수는 갈래를 여는 것뿐이다.
    let kinds: Vec<ActionKind> = seen.next_actions.iter().map(|a| a.kind).collect();
    assert_eq!(
        kinds,
        vec![
            ActionKind::OpenBranch(CycleKind::Interview),
            ActionKind::OpenBranch(CycleKind::Experiment)
        ]
    );
}

#[test]
fn no_will_is_invented_from_an_open_step() {
    let (session, dir) = started("no-will");
    drop(session);

    // 이제 막 열린 Experiment — 아직 아무 자리도 열지 않았고 걸린 행동도 없다.
    let seen = monitor(&dir);
    assert!(seen.current_will.is_none());
    assert!(seen.current_step.is_none());

    // 자리를 열면 Will 이 함께 난다. 그때는 **원본에서 읽은 그 값**이다.
    open_action(&dir, "define");

    let seen = monitor(&dir);
    let will = seen.current_will.clone().expect("걸린 행동이 있다");
    assert_eq!(will.objective, "그 목적");
    assert_eq!(will.next_action, "그 행동");
    assert_eq!(will.done_when, "그 조건");
    assert_eq!(will.target_step_ref, seen.current_step.expect("자리").step_ref);
    assert_eq!(will.existence_ref, seen.current_existence.existence_ref);
}

#[test]
fn nothing_that_does_not_exist_yet_appears_in_the_model() {
    // Chain 도 승인 mode 도 시각 자료도 아직 없다. `chain: null` 같은 빈 자리조차 두지 않는다.
    let dir = branched("absent");
    let seen = monitor(&dir);
    let shown = format!("{seen:?}");

    for absent in [
        "chain", "Chain", "approval", "Approval", "checkpoint", "Checkpoint", "milestone",
        "stepwise", "autonomous", "media", "attachment",
    ] {
        assert!(
            !shown.contains(absent),
            "{absent:?} 가 모델에 나타났다 — 아직 없는 사실이다:\n{shown}"
        );
    }
    // 내부 주소와 `.gil` 경로도 공개 사실이 아니다.
    for hidden in ["sha256", ".gil", "manifest", "blobs"] {
        assert!(!shown.contains(hidden), "{hidden:?} 가 공개 모델에 실렸다:\n{shown}");
    }
}

// ── ④ 못 본 것을 안다고 하지 않는가 ─────────────────────────────────────

#[test]
#[cfg(unix)]
fn an_observation_failure_stays_unknown() {
    let (session, dir) = started("unknown");
    drop(session);
    std::os::unix::fs::symlink(dir.join("work.txt"), dir.join("link")).unwrap();

    let seen = monitor(&dir);
    assert_eq!(seen.world.state, WorldMark::Unknown, "못 본 것을 dirty 라 했다");
    assert_ne!(seen.world.state, WorldMark::Dirty);
    let reason = seen.world.reason.clone().expect("왜 못 봤는지 남겨야 한다");
    assert!(reason.contains("심볼릭 링크"), "{reason}");
    // 기준 세계는 여전히 안다 — 못 본 것은 **지금 폴더**다.
    assert_eq!(seen.world.baseline_snapshot_ref.to_string(), "snapshot:A1");
}

#[test]
fn a_clean_and_a_dirty_world_carry_no_reason() {
    let (session, dir) = started("clean-dirty");
    drop(session);
    let seen = monitor(&dir);
    assert_eq!(seen.world.state, WorldMark::Clean);
    assert!(seen.world.reason.is_none(), "clean 에 이유가 붙었다");

    write(&dir, "work.txt", "바꿔 놓았다");
    let seen = monitor(&dir);
    assert_eq!(seen.world.state, WorldMark::Dirty);
    assert!(seen.world.reason.is_none(), "dirty 에 이유가 붙었다");
    // 파일 목록도 내부 주소도 없다.
    assert!(!format!("{:?}", seen.world).contains("work.txt"));
}

// ── ⑤ 아무것도 쓰지 않는가 ──────────────────────────────────────────────

#[test]
fn a_lookup_changes_nothing() {
    let dir = branched("read-only");
    open_action(&dir, "define");

    let before = (
        fs::read(state_in(&dir)).expect("상태를 읽는다"),
        world_of(&dir),
        objects_of(&dir),
    );

    // 여러 번 조회해도 같다.
    for _ in 0..3 {
        let seen = monitor(&dir);
        assert_eq!(seen.current_cycle.facts.cycle_ref.to_string(), "cycle:C4");
    }

    assert_eq!(fs::read(state_in(&dir)).unwrap(), before.0, "state.yaml 이 바뀌었다");
    assert_eq!(world_of(&dir), before.1, "작업 파일이 바뀌었다");
    assert_eq!(objects_of(&dir), before.2, "Snapshot 창고가 바뀌었다");

    // 그리고 Graph·Journey·Will 도 같은 값으로 되살아난다.
    let after = monitor(&dir);
    assert_eq!(after.current_cycle, monitor(&dir).current_cycle);
    assert_eq!(after.current_existence, monitor(&dir).current_existence);
    assert_eq!(after.current_will, monitor(&dir).current_will);
    assert_eq!(after.inactive_cycles, monitor(&dir).inactive_cycles);
}

// ── 다음 행동 ─────────────────────────────────────────────────────────────

#[test]
fn a_dirty_world_hides_every_command_the_gate_would_refuse() {
    // **구조적으로 가능한 전이와 지금 실행 가능한 명령은 다르다.** `next_actions` 는 후자다.
    //
    // 자리마다 dirty 로 만들어 두고, 목록에 무엇이 남는지 잰다.
    let (session, dir) = started("dirty-gates");

    // ① 열린 비-Verify — `gil close` 는 dirty gate 에 막힌다.
    drop(session);
    open_action(&dir, "define");
    write(&dir, "work.txt", "손으로 바꿔 놓았다");
    let kinds = action_kinds(&dir);
    assert!(
        !kinds.iter().any(|k| matches!(k, ActionKind::CloseStep(_))),
        "dirty 비-Verify 에서 CloseStep 을 약속했다: {kinds:?}"
    );
    assert_eq!(kinds, vec![ActionKind::Restore]);

    // ② 같은 자리, clean — 이제 닫을 수 있다.
    write(&dir, "work.txt", "처음");
    assert_eq!(
        action_kinds(&dir),
        vec![ActionKind::CloseStep(NodeKind::Define)]
    );

    // ③ 열린 Verify — **세계를 확정하는 자리라 dirty 여도 닫는다.**
    close_with_report(&dir, NodeKind::Define);
    open_action(&dir, "hypothesis");
    close_with_report(&dir, NodeKind::Hypothesis);
    open_action(&dir, "verify");
    write(&dir, "work.txt", "Verify 가 바꾼 세계");
    let kinds = action_kinds(&dir);
    assert!(
        kinds.contains(&ActionKind::CloseStep(NodeKind::Verify)),
        "dirty Verify 에서 확정하는 길을 지웠다: {kinds:?}"
    );
    assert!(kinds.contains(&ActionKind::Restore), "{kinds:?}");
}

#[test]
fn a_dirty_cycle_boundary_offers_only_the_restore() {
    let (mut session, dir) = started("dirty-boundary");
    walk_exit(&mut session, "failure");
    session.commit().expect("눕힌다");
    drop(session);

    // 끝 경계 · clean — Cycle 을 닫을 수 있다.
    assert_eq!(
        action_kinds(&dir),
        vec![ActionKind::CloseCycle(CycleKind::Experiment)]
    );

    // 같은 자리 · dirty — `gil close` 는 require_clean 에 막힌다.
    write(&dir, "work.txt", "손으로 바꿔 놓았다");
    let kinds = action_kinds(&dir);
    assert!(
        !kinds.iter().any(|k| matches!(k, ActionKind::CloseCycle(_))),
        "dirty Cycle 경계에서 CloseCycle 을 약속했다: {kinds:?}"
    );
    assert_eq!(kinds, vec![ActionKind::Restore]);
}

#[test]
fn a_dirty_revisit_boundary_offers_only_the_restore() {
    let (mut session, dir) = started("dirty-revisit");
    walk_exit(&mut session, "failure");
    close_cycle_toward(&mut session, "failure", Some("cycle:C1"));
    drop(session);

    // clean — 되돌아갈 수 있다.
    assert_eq!(action_kinds(&dir), vec![ActionKind::Revisit]);

    // dirty — `gil revisit` 은 clean 을 요구한다.
    write(&dir, "work.txt", "손으로 바꿔 놓았다");
    let kinds = action_kinds(&dir);
    assert!(
        !kinds.contains(&ActionKind::Revisit),
        "dirty 되돌아감 경계에서 Revisit 을 약속했다: {kinds:?}"
    );
    assert_eq!(kinds, vec![ActionKind::Restore]);
}

#[test]
#[cfg(unix)]
fn an_unknown_world_promises_only_what_does_not_need_it() {
    // 관측 오류를 해결하지 않고는 세계를 지나는 어떤 명령도 성공하지 않는다.
    // **되돌리는 것조차** 못 한다 — restore 의 preflight 가 같은 관측을 한다.
    let (session, dir) = started("unknown-actions");
    drop(session);
    open_action(&dir, "define");
    std::os::unix::fs::symlink(dir.join("work.txt"), dir.join("link")).unwrap();

    let seen = monitor(&dir);
    assert_eq!(seen.world.state, WorldMark::Unknown);
    let kinds: Vec<ActionKind> = seen.next_actions.iter().map(|a| a.kind).collect();
    for forbidden in [
        ActionKind::CloseStep(NodeKind::Define),
        ActionKind::CloseStep(NodeKind::Verify),
        ActionKind::Restore,
        ActionKind::Revisit,
    ] {
        assert!(
            !kinds.contains(&forbidden),
            "못 본 세계에서 {forbidden:?} 를 약속했다: {kinds:?}"
        );
    }
}

/// **표 기반 검사** — 목록에 실린 명령을 자리마다 실제로 실행해 성공을 확인한다.
///
/// 「가능하다」를 문자열로 약속하고 끝내지 않는다. 각 자리에서 Snapshot 을 찍고, 그 목록의
/// 명령 하나하나를 **깨끗한 사본** 위에서 돌려 본다 — 사본이라 서로의 상태를 흔들지 않는다.
#[test]
fn every_listed_command_actually_succeeds_here() {
    let cases: Vec<(&str, fn(&Path))> = vec![
        // 아직 아무것도 열지 않은 Experiment · clean
        ("fresh", |_| {}),
        // 열린 실행형 자리 · clean
        ("open-step", |dir| open_action(dir, "define")),
        // 열린 실행형 자리 · dirty
        ("open-step-dirty", |dir| {
            open_action(dir, "define");
            write(dir, "work.txt", "바꿔 놓았다");
        }),
        // 열린 Verify · dirty — 확정이 정상 경로다
        ("verify-dirty", |dir| {
            open_action(dir, "define");
            close_with_report(dir, NodeKind::Define);
            open_action(dir, "hypothesis");
            close_with_report(dir, NodeKind::Hypothesis);
            open_action(dir, "verify");
            write(dir, "work.txt", "Verify 가 바꾼 세계");
        }),
        // 걸을 수 있는 다음 Step 이 여럿 · clean
        ("after-define", |dir| {
            open_action(dir, "define");
            close_with_report(dir, NodeKind::Define);
        }),
    ];

    for (label, arrange) in cases {
        let (session, dir) = started(&format!("table-{label}"));
        drop(session);
        arrange(&dir);

        let listed = monitor(&dir).next_actions;
        assert!(!listed.is_empty(), "{label}: 밟을 수 있는 수가 하나도 없다");

        for next in &listed {
            let command = next.command.clone().expect("v0 의 모든 수에는 명령이 있다");
            let copy = clone_project(&dir, &format!("table-{label}-{}", slug(&command)));
            run_command(&copy, &command, next.kind);
        }
    }
}

/// 되돌아감과 갈래 열기도 같은 표로 잰다 — 자리 마련이 길어 따로 둔다.
#[test]
fn the_revisit_places_also_run_what_they_list() {
    // ① 되돌아갈 수 있는 닫힌 Cycle
    let (mut session, dir) = started("table-revisit");
    walk_exit(&mut session, "failure");
    close_cycle_toward(&mut session, "failure", Some("cycle:C1"));
    drop(session);
    for next in monitor(&dir).next_actions {
        let command = next.command.expect("명령이 있다");
        let copy = clone_project(&dir, &format!("table-revisit-{}", slug(&command)));
        run_command(&copy, &command, next.kind);
    }

    // ② 되돌아온 자리 — 갈래를 여는 두 수
    ok(&dir, &["revisit"]);
    let listed = monitor(&dir).next_actions;
    assert_eq!(listed.len(), 2, "갈래를 여는 수는 둘이다");
    for next in listed {
        let command = next.command.expect("명령이 있다");
        let copy = clone_project(&dir, &format!("table-branch-{}", slug(&command)));
        run_command(&copy, &command, next.kind);
    }

    // ③ 성공으로 닫은 Cycle — 자식을 여는 두 수
    let (mut session, dir) = started("table-child");
    walk_exit(&mut session, "success");
    close_cycle_toward(&mut session, "success", None);
    drop(session);
    let listed = monitor(&dir).next_actions;
    assert_eq!(listed.len(), 2, "자식을 여는 수는 둘이다");
    for next in listed {
        let command = next.command.expect("명령이 있다");
        let copy = clone_project(&dir, &format!("table-child-{}", slug(&command)));
        run_command(&copy, &command, next.kind);
    }
}

/// 목록의 명령 하나를 실제로 돌린다 — Report 나 계약이 필요한 것은 stdin 으로 채운다.
fn run_command(dir: &Path, command: &str, kind: ActionKind) {
    let args: Vec<&str> = command.split_whitespace().skip(1).collect();
    match kind {
        // 실행형 자리를 여는 것은 계약이 필요하다.
        ActionKind::OpenStep(_) => open_action(dir, args[1]),
        // 닫는 것은 그 자리의 Report 가 필요하다.
        ActionKind::CloseStep(step) => close_with_report(dir, step),
        ActionKind::CloseCycle(_) => {
            let session = ProjectSession::open(spec(), state_in(dir)).expect("되살린다");
            let cycle = session.project().cycles().current();
            let last = cycle.steps().current().expect("판정에 서 있다");
            let report = cycle_report(cycle, "failure", last).with(CYCLE_TARGET, "cycle:C1");
            drop(session);
            stdin_ok(dir, &["close"], &written(&report));
        }
        // 나머지는 stdin 이 필요 없다.
        _ => {
            ok(dir, &args);
        }
    }
}

fn close_with_report(dir: &Path, kind: NodeKind) {
    let session = ProjectSession::open(spec(), state_in(dir)).expect("되살린다");
    let cycle = session.project().cycles().current();
    let report = full_report(cycle.rules(), CycleKind::Experiment, kind);
    drop(session);
    stdin_ok(dir, &["close"], &written(&report));
}

/// Report 를 GIL 이 읽는 꼴로 — 한 줄에 한 칸, 여러 줄은 block scalar 로.
fn written(report: &gil::Report) -> String {
    let mut out = String::new();
    for name in report.field_names() {
        let value = report.get(name).expect("방금 이름을 받아 왔다");
        match value.contains('\n') {
            false => out.push_str(&format!("{name}: {value}\n")),
            true => {
                out.push_str(&format!("{name}: |\n"));
                for line in value.lines() {
                    out.push_str(&format!("  {line}\n"));
                }
            }
        }
    }
    out
}

fn stdin_ok(dir: &Path, args: &[&str], stdin: &str) {
    use std::io::Write as _;
    let out = Command::new(GIL)
        .args(args)
        .current_dir(dir)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .and_then(|mut child| {
            child.stdin.as_mut().expect("stdin").write_all(stdin.as_bytes())?;
            child.wait_with_output()
        })
        .expect("gil 을 부른다");
    assert!(
        out.status.success(),
        "목록에 실린 `gil {}` 가 실패했다:\n{}",
        args.join(" "),
        String::from_utf8_lossy(&out.stderr)
    );
}

/// 프로젝트를 통째로 복사한다 — 한 자리의 여러 수를 서로 흔들지 않고 재기 위해.
fn clone_project(from: &Path, label: &str) -> PathBuf {
    let to = bare(label);
    copy_tree(from, &to);
    to
}

fn copy_tree(from: &Path, to: &Path) {
    fs::create_dir_all(to).unwrap();
    for entry in fs::read_dir(from).expect("들여다본다") {
        let entry = entry.expect("한 자리");
        let target = to.join(entry.file_name());
        match entry.file_type().expect("종류").is_dir() {
            true => copy_tree(&entry.path(), &target),
            false => {
                fs::copy(entry.path(), &target).unwrap();
            }
        }
    }
}

fn slug(command: &str) -> String {
    command.replace(' ', "-")
}

/// 지금 자리에서 밟을 수 있다고 말하는 수들.
fn action_kinds(dir: &Path) -> Vec<ActionKind> {
    monitor(dir).next_actions.iter().map(|a| a.kind).collect()
}

#[test]
fn the_next_actions_are_the_ones_the_cli_actually_accepts() {
    // 화면이 약속한 수를 CLI 가 거절하면 그 안내는 없느니만 못하다.
    let (mut session, dir) = started("actions");
    walk_exit(&mut session, "failure");
    close_cycle_toward(&mut session, "failure", Some("cycle:C1"));
    drop(session);

    let seen = monitor(&dir);
    let kinds: Vec<ActionKind> = seen.next_actions.iter().map(|a| a.kind).collect();
    assert_eq!(kinds, vec![ActionKind::Revisit], "실패 Cycle 에서 밟을 수 있는 것은 하나다");

    let revisit = &seen.next_actions[0];
    assert_eq!(revisit.command.as_deref(), Some("gil revisit"));
    assert_eq!(
        revisit.help_ref.as_ref().map(|id| id.as_str()),
        Some("cycle/revisit")
    );
    // 그리고 그 명령이 실제로 통한다.
    ok(&dir, &["revisit"]);
}

#[test]
fn every_action_topic_is_actually_bundled() {
    // 실리지 않은 주소를 가리키면 사람은 없는 문서를 찾아 헤맨다.
    let dir = branched("topics");
    open_action(&dir, "define");
    let seen = monitor(&dir);
    for action in &seen.next_actions {
        let Some(topic) = &action.help_ref else {
            continue;
        };
        ok(&dir, &["help", topic.as_str()]);
    }
}


// ── 손상은 Monitor 이전에 거절된다 ────────────────────────────────────────

/// 저장 파일을 손으로 고치고, 되살리기가 거절하는 말을 돌려준다.
fn tampered(dir: &Path, edit: impl FnOnce(&mut serde_norway::Value)) -> String {
    let text = fs::read_to_string(state_in(dir)).expect("상태를 읽는다");
    let mut file: serde_norway::Value = serde_norway::from_str(&text).expect("저장 파일은 YAML 이다");
    edit(&mut file);
    fs::write(state_in(dir), serde_norway::to_string(&file).unwrap()).unwrap();
    match ProjectSession::open(spec(), state_in(dir)) {
        Err(err) => err.to_string(),
        Ok(_) => panic!("걸어서 만들 수 없는 파일이 되살아났다 — Monitor 가 그것을 보게 된다"),
    }
}

#[test]
fn a_closed_cycle_missing_a_required_report_field_never_reaches_the_monitor() {
    // Monitor 는 닫힌 Cycle 의 `verdict` 와 `handoff_summary` 가 **있다고 단언한다.**
    // 그 단언이 서는 까닭은 여기 있다 — 그 칸이 없는 판은 Project 복원이 먼저 거절한다.
    //
    // 이 시험이 빨개지면 Monitor 의 `expect` 는 근거를 잃는다.
    for field in ["verdict", "handoff_summary"] {
        let (mut session, dir) = started(&format!("corrupt-{field}"));
        walk_exit(&mut session, "failure");
        close_cycle_toward(&mut session, "failure", Some("cycle:C1"));
        drop(session);

        // 성한 판에서는 Monitor 가 그 값을 읽는다.
        let seen = monitor(&dir);
        let report = seen.current_cycle.facts.report.clone().expect("닫힌 Cycle 은 Report 를 지닌다");
        assert!(!report.verdict.is_empty() && !report.handoff_summary.is_empty());

        // 그 칸을 지우면 **Monitor 에 닿기 전에** 거절된다.
        let said = tampered(&dir, |file| {
            let map = file["cycles"]["nodes"][1]["report"]
                .as_mapping_mut()
                .expect("Report 는 mapping 이다");
            map.remove(serde_norway::Value::from(field))
                .unwrap_or_else(|| panic!("{field} 가 없다"));
        });
        assert!(
            said.contains(field),
            "{field} 가 빠진 판이 다른 이유로 거절됐다:\n{said}"
        );
    }
}

#[test]
fn a_required_report_field_is_never_projected_as_an_empty_string() {
    // 성한 판에서 두 칸은 언제나 실린 값 그대로다. 빈 글은 「적지 않았다」와 「빈칸을
    // 적었다」를 구별할 수 없게 만든다.
    let dir = branched("no-empty-fields");
    let seen = monitor(&dir);
    for cycle in &seen.inactive_cycles {
        let Some(report) = &cycle.report else {
            continue;
        };
        assert!(!report.verdict.is_empty(), "{} 의 verdict 가 비었다", cycle.cycle_ref);
        assert!(
            !report.handoff_summary.is_empty(),
            "{} 의 handoff 가 비었다",
            cycle.cycle_ref
        );
        // 선택 칸만 Option 이다.
        let _: &Option<String> = &report.outcome_lesson;
    }
}

// ══════════════════════════════════════════════════════════════════════════
//  plain text renderer — 다른 renderer 가 따를 의미 기준
// ══════════════════════════════════════════════════════════════════════════
//
// 여기서 재는 것은 넷이다.
//
// 1. **필요한 절과 사실이 나오는가** — 시나리오마다 다르다.
// 2. **없는 절과 사실이 나오지 않는가** — Define 도 Will 도 Chain 도.
// 3. **구조가 꾸밈 없이 읽히는가** — 색도, 폭도, 도형 문자도 없이.
// 4. **아무것도 바꾸지 않는가.**

/// Snapshot 을 짓고 **세션을 놓은 뒤** 글을 만든다 — CLI 가 하는 그 순서.
///
/// 이 함수가 컴파일된다는 것 자체가 하나의 증거다: renderer 가 살아 있는 Session 이나
/// Project 를 필요로 했다면 `drop` 뒤의 이 호출은 컴파일되지 않는다.
fn rendered(dir: &Path) -> String {
    let seen = {
        let session = ProjectSession::open(spec(), state_in(dir)).expect("되살린다");
        session.monitor().expect("Snapshot 을 만든다")
    }; // ← 여기서 세션이 떨어지고 잠금이 풀린다.
    render_monitor_text(&seen)
}

/// 그 절의 본문 — 다음 절 제목 전까지.
fn section<'a>(text: &'a str, title: &str) -> &'a str {
    let head = format!("[{title}]\n");
    let from = text
        .find(&head)
        .unwrap_or_else(|| panic!("[{title}] 절이 없다:\n{text}"))
        + head.len();
    let rest = &text[from..];
    match rest.find("\n[") {
        Some(to) => &rest[..to],
        None => rest,
    }
}

/// 활성 경로 절이 그린 Cycle 들 — **적힌 순서 그대로.**
fn lineage_order(path: &str) -> Vec<String> {
    path.lines()
        .filter(|line| line.trim_start().starts_with("cycle:"))
        .map(|line| {
            line.trim()
                .split(' ')
                .next()
                .expect("첫 낱말이 주소다")
                .to_string()
        })
        .collect()
}

fn has_section(text: &str, title: &str) -> bool {
    text.contains(&format!("[{title}]\n"))
}

// ── ① 시나리오마다 무엇이 나오는가 ───────────────────────────────────────

#[test]
fn the_first_interview_is_not_called_an_experiment() {
    let dir = bare("text-first-interview");
    write(&dir, "work.txt", "처음");
    let session = ProjectSession::start(spec(), state_in(&dir)).expect("시작한다");
    session.commit().expect("눕힌다");
    drop(session);

    let text = rendered(&dir);
    assert!(has_section(&text, "현재 인터뷰"), "{text}");
    assert!(!has_section(&text, "현재 실험"), "Interview 를 실험이라 불렀다:\n{text}");

    let here = section(&text, "현재 인터뷰");
    assert!(here.contains("cycle:C1 · interview · 열림"), "{here}");
    assert!(here.contains("아직 아무것도 열지 않았다"), "{here}");
    // Define 이 없으니 질문도 성공 기준도 지어내지 않는다.
    assert!(!here.contains("질문:"), "없는 Define 을 지어냈다:\n{here}");
    assert!(!here.contains("성공 기준:"), "{here}");

    // 걸린 행동도, 지나온 갈래도 아직 없다 — 절 자체가 없다.
    assert!(!has_section(&text, "현재 행동"), "{text}");
    assert!(!has_section(&text, "지나온 갈래"), "{text}");
    // 세계와 다음 행동은 언제나 있다.
    assert!(has_section(&text, "현재 세계") && has_section(&text, "다음 행동"), "{text}");
}

#[test]
fn an_open_experiment_shows_its_question_and_success_condition() {
    let (session, dir) = started("text-open-experiment");
    drop(session);
    open_action(&dir, "define");
    stdin_ok(
        &dir,
        &["close"],
        "problem: 테스트 하네스가 왜 느린가\nsuccess_condition: 지배적인 구간을 수치로 지목한다\n",
    );
    open_action(&dir, "hypothesis");

    let text = rendered(&dir);
    let here = section(&text, "현재 실험");
    assert!(here.contains("cycle:C2 · experiment · 열림 · 부모 cycle:C1"), "{here}");
    assert!(here.contains("step:C2/S2 · hypothesis · 열림"), "{here}");
    assert!(here.contains("질문: 테스트 하네스가 왜 느린가"), "{here}");
    assert!(here.contains("성공 기준: 지배적인 구간을 수치로 지목한다"), "{here}");
    // 갈래의 출처가 없으니 그 낱말도 없다.
    assert!(!here.contains("갈라짐"), "없는 출처를 그렸다:\n{here}");
}

#[test]
fn an_open_verify_shows_the_will_and_the_confirming_place() {
    let (session, dir) = started("text-verify-will");
    drop(session);
    open_action(&dir, "define");
    close_with_report(&dir, NodeKind::Define);
    open_action(&dir, "hypothesis");
    close_with_report(&dir, NodeKind::Hypothesis);
    open_action(&dir, "verify");

    let text = rendered(&dir);
    let doing = section(&text, "현재 행동");
    assert!(doing.contains("step:C2/S3 에 걸려 있다"), "{doing}");
    assert!(doing.contains("목표: 그 목적"), "{doing}");
    assert!(doing.contains("지금 할 일: 그 행동"), "{doing}");
    assert!(doing.contains("완료 조건: 그 조건"), "{doing}");
    assert!(
        section(&text, "현재 세계").contains("Verify — 바뀐 세계를 확정할 수 있다"),
        "{text}"
    );
}

#[test]
fn a_branch_after_a_failure_separates_the_parent_from_the_source() {
    let dir = branched("text-branch");
    let text = rendered(&dir);

    // 부모와 갈래의 출처를 **같은 연결선으로 그리지 않는다.**
    let here = section(&text, "현재 실험");
    assert!(here.contains("부모 cycle:C1"), "{here}");
    assert!(here.contains("cycle:C3 에서 갈라짐"), "{here}");

    // 활성 경로는 뿌리부터 순서대로 — 버린 갈래는 여기 없다.
    let path = section(&text, "활성 경로");
    assert_eq!(lineage_order(path), vec!["cycle:C1", "cycle:C4"], "{path}");
    // C3 은 **경로의 항목이 아니다.** 지금 Cycle 줄에 「갈래 출처」로 적히는 것은
    // 그것과 다른 사실이고, 그래서 항목 목록으로 잰다.
    assert!(
        !lineage_order(path).contains(&"cycle:C3".to_string()),
        "버린 갈래가 활성 경로의 항목이 됐다:\n{path}"
    );

    let left = section(&text, "지나온 갈래");
    assert!(left.contains("cycle:C3"), "{left}");
    assert!(left.contains("갈래 출처: cycle:C2 (계보의 변이 아니다)") || left.contains("cycle:C2"), "{left}");
}

#[test]
fn a_pending_revisit_is_not_drawn_as_an_opened_cycle() {
    let (mut session, dir) = started("text-pending");
    walk_exit(&mut session, "failure");
    close_cycle_toward(&mut session, "failure", Some("cycle:C1"));
    drop(session);
    ok(&dir, &["revisit"]);

    let text = rendered(&dir);
    let here = section(&text, "현재 인터뷰");
    assert!(here.contains("cycle:C1 · interview · 닫힘"), "{here}");
    assert!(
        here.contains("cycle:C2 에서 갈라져 cycle:C1 에 섰다 — 새 Cycle 은 아직 없다"),
        "되돌아온 상태를 말하지 않는다:\n{here}"
    );
    // 아직 열리지 않은 Cycle 이 어디에도 없다.
    assert!(!text.contains("cycle:C3"), "열리지 않은 Cycle 을 그렸다:\n{text}");
    // 그리고 다음 행동은 갈래를 여는 둘뿐이다.
    let next = section(&text, "다음 행동");
    assert!(next.contains("새 interview 갈래를 연다"), "{next}");
    assert!(next.contains("새 experiment 갈래를 연다"), "{next}");
}

#[test]
fn success_and_failure_can_sit_side_by_side_among_the_left_behind() {
    // **계보 밖을 모두 실패라 부르지 않는다.** C2 는 성공했고 C3 은 실패했다.
    let dir = branched("text-both");
    let text = rendered(&dir);
    let left = section(&text, "지나온 갈래");

    let c2 = left.split("cycle:C2").nth(1).expect("C2 절이 있다");
    let c3 = left.split("cycle:C3").nth(1).expect("C3 절이 있다");
    assert!(c2.contains("판정: success"), "{left}");
    assert!(c3.contains("판정: failure"), "{left}");
    // 관계는 셋을 서로 다른 말로.
    assert!(c2.contains("같은 자리에서 갈라져 두고 온 가지다"), "{left}");
    assert!(c3.contains("지금 걷는 갈래가 여기서 갈라져 나왔다"), "{left}");
    // enum 이름을 그대로 내보이지 않는다.
    for variant in ["RevisitSource", "Abandoned", "Other"] {
        assert!(!left.contains(variant), "{variant} 를 그대로 보였다:\n{left}");
    }
}

#[test]
fn a_dirty_non_verify_place_shows_only_the_restore() {
    let (session, dir) = started("text-dirty-step");
    drop(session);
    open_action(&dir, "define");
    write(&dir, "work.txt", "손으로 바꿔 놓았다");

    let text = rendered(&dir);
    let world = section(&text, "현재 세계");
    assert!(world.contains("상태: dirty"), "{world}");
    assert!(!world.contains("Verify — 바뀐 세계를 확정할 수 있다"), "{world}");

    let next = section(&text, "다음 행동");
    assert!(next.contains("gil restore"), "{next}");
    assert!(!next.contains("gil close"), "닫을 수 없는 자리에서 닫으라 했다:\n{next}");
}

#[test]
fn a_dirty_verify_keeps_the_confirming_move() {
    let (session, dir) = started("text-dirty-verify");
    drop(session);
    open_action(&dir, "define");
    close_with_report(&dir, NodeKind::Define);
    open_action(&dir, "hypothesis");
    close_with_report(&dir, NodeKind::Hypothesis);
    open_action(&dir, "verify");
    write(&dir, "work.txt", "Verify 가 바꾼 세계");

    let text = rendered(&dir);
    let next = section(&text, "다음 행동");
    assert!(next.contains("열린 verify 자리를 Report 로 닫는다"), "{next}");
    assert!(next.contains("gil close"), "{next}");
    assert!(next.contains("gil restore"), "{next}");
}

#[test]
#[cfg(unix)]
fn an_unknown_world_is_not_drawn_as_dirty() {
    let (session, dir) = started("text-unknown");
    drop(session);
    open_action(&dir, "define");
    std::os::unix::fs::symlink(dir.join("work.txt"), dir.join("link")).unwrap();

    let text = rendered(&dir);
    let world = section(&text, "현재 세계");
    assert!(world.contains("상태: unknown"), "{world}");
    assert!(!world.contains("dirty"), "못 본 것을 dirty 라 했다:\n{world}");
    assert!(world.contains("보지 못한 까닭"), "이유를 잃었다:\n{world}");
    assert!(world.contains("심볼릭 링크"), "{world}");

    // 세계를 지나는 명령은 하나도 약속하지 않는다.
    let next = section(&text, "다음 행동");
    for command in ["gil close", "gil restore", "gil revisit"] {
        assert!(!next.contains(command), "못 본 세계에서 {command} 를 약속했다:\n{next}");
    }
}

#[test]
fn a_multi_line_value_keeps_its_indentation_on_every_line() {
    let (session, dir) = started("text-multiline");
    drop(session);
    open_action(&dir, "define");
    stdin_ok(
        &dir,
        &["close"],
        "problem: |\n  첫 줄이다.\n  둘째 줄이다.\n  셋째 줄이다.\nsuccess_condition: 한 줄\n",
    );

    let text = rendered(&dir);
    let here = section(&text, "현재 실험");
    assert!(here.contains("질문: 첫 줄이다."), "{here}");
    // 뒷줄은 **모두 같은 깊이**로 들어간다.
    assert!(here.contains("\n    둘째 줄이다.\n"), "뒷줄의 들여쓰기가 없다:\n{here:?}");
    assert!(here.contains("\n    셋째 줄이다.\n"), "{here:?}");
}

// ── ② 꾸미지 않는다 ──────────────────────────────────────────────────────

#[test]
fn nothing_is_wrapped_coloured_or_drawn_with_box_characters() {
    let (session, dir) = started("text-plain");
    drop(session);
    // 아주 긴 한 줄 — 폭에 맞춰 접는 구현이라면 여기서 갈린다.
    let long = "가".repeat(400);
    open_action(&dir, "define");
    stdin_ok(
        &dir,
        &["close"],
        &format!("problem: {long}\nsuccess_condition: 짧다\n"),
    );

    let text = rendered(&dir);
    assert!(
        text.lines().any(|line| line.contains(&long)),
        "긴 값을 강제로 접었다"
    );
    assert!(!text.contains('\u{1b}'), "ANSI escape 가 있다");
    for shape in ['│', '├', '└', '─', '┌', '┐', '┘', '┬', '┴', '┤', '═', '║', '╔', '╚'] {
        assert!(!text.contains(shape), "{shape:?} 도형 문자를 썼다");
    }
}

#[test]
fn no_internal_address_or_gil_path_reaches_the_screen() {
    let dir = branched("text-no-internals");
    let text = rendered(&dir);
    for hidden in ["sha256", ".gil", "manifest", "blobs", "state.yaml", "/tmp"] {
        assert!(!text.contains(hidden), "{hidden:?} 가 화면에 나왔다:\n{text}");
    }
    // 아직 없는 것도 나오지 않는다.
    for absent in ["Chain", "chain", "승인", "checkpoint", "milestone", "autonomous"] {
        assert!(!text.contains(absent), "{absent:?} 가 화면에 나왔다:\n{text}");
    }
}

// ── ③ 같은 사실은 같은 글 ────────────────────────────────────────────────

#[test]
fn the_same_snapshot_always_renders_the_same_bytes() {
    // 관측 시각을 싣지 않는 까닭이 여기 있다 — 시각이 들어가면 같은 사실이 매번 다른 글이
    // 되고, 두 화면이 같은지 물을 수 없다.
    let dir = branched("text-stable");
    let session = ProjectSession::open(spec(), state_in(&dir)).expect("되살린다");
    let seen = session.monitor().expect("Snapshot");
    drop(session);

    let once = render_monitor_text(&seen);
    for _ in 0..3 {
        assert_eq!(render_monitor_text(&seen), once, "같은 Snapshot 이 다른 글이 됐다");
    }
    // 상태가 바뀌지 않았다면 새 Snapshot 도 같은 글을 만든다.
    assert_eq!(rendered(&dir), once);
}

// ── ④ 명령의 계약 ────────────────────────────────────────────────────────

#[test]
fn the_monitor_command_prints_the_same_text() {
    let dir = branched("cmd-same-text");
    assert_eq!(ok(&dir, &["monitor"]), rendered(&dir));
}

#[test]
fn the_monitor_command_takes_no_argument() {
    let dir = branched("cmd-args");
    for extra in ["--format", "html", "--watch", "cycle:C1", "-v"] {
        let out = run(&dir, &["monitor", extra]);
        assert!(!out.status.success(), "{extra} 를 받아들였다");
        let said = String::from_utf8_lossy(&out.stderr);
        assert!(said.contains("받지 않는다"), "{extra}: {said}");
    }
}

#[test]
fn the_monitor_command_changes_nothing() {
    let dir = branched("cmd-read-only");
    open_action(&dir, "define");
    let before = (
        fs::read(state_in(&dir)).expect("상태를 읽는다"),
        world_of(&dir),
        objects_of(&dir),
    );

    for _ in 0..3 {
        ok(&dir, &["monitor"]);
    }

    assert_eq!(fs::read(state_in(&dir)).unwrap(), before.0, "state.yaml 이 바뀌었다");
    assert_eq!(world_of(&dir), before.1, "작업 파일이 바뀌었다");
    assert_eq!(objects_of(&dir), before.2, "Snapshot 창고가 바뀌었다");

    // Graph·Journey·Will 도 그대로다.
    let seen = monitor(&dir);
    assert_eq!(seen.current_cycle, monitor(&dir).current_cycle);
    assert_eq!(seen.current_will, monitor(&dir).current_will);
    assert_eq!(seen.current_existence, monitor(&dir).current_existence);
}

#[test]
fn the_general_help_lists_the_monitor_command() {
    let dir = branched("cmd-help");
    let said = ok(&dir, &["--help"]);
    assert!(said.contains("gil monitor"), "{said}");
    // 아직 없는 선택지를 약속하지 않는다.
    assert!(!said.contains("--watch") && !said.contains("--format"), "{said}");
}

// ── ⑤ 활성 경로의 해상도 ─────────────────────────────────────────────────
//
// 참조만 늘어놓으면 화면은 「지금 어디인가」에는 답해도 **「왜 여기 있는가」에는 답하지
// 못한다.** 직렬로 성공한 조상이 무엇을 실험했고 무엇을 넘겼는지가 읽혀야 한다.
//
// 그러나 조상의 **Step 은 펼치지 않는다.** 그것은 다른 독자(`gil history`)의 몫이다.

/// `C1(interview·성공) → C2(experiment·성공) → C3(열림·Define 까지)` 를 걷는다.
///
/// 직렬로 닫힌 Cycle **둘** 뒤에 열린 현재 Cycle 이 온다.
fn serial(label: &str) -> PathBuf {
    let (mut session, dir) = started(label);
    walk_exit(&mut session, "success");
    close_cycle_toward(&mut session, "success", None);
    session.open_child_cycle(CycleKind::Experiment).expect("자식을 연다");
    session.commit().expect("눕힌다");
    drop(session);

    open_action(&dir, "define");
    stdin_ok(
        &dir,
        &["close"],
        "problem: 잘못된 문자열 설정도 기본값으로 복구되는가\n\
         success_condition: 알 수 없는 문자열이 기본값으로 떨어진다\n",
    );
    dir
}

#[test]
fn every_active_ancestor_shows_its_kind_and_state() {
    let dir = serial("lineage-kind-state");
    let text = rendered(&dir);
    let path = section(&text, "활성 경로");

    assert_eq!(lineage_order(path), vec!["cycle:C1", "cycle:C2", "cycle:C3"], "{path}");
    assert!(path.contains("cycle:C1 · interview · 닫힘"), "{path}");
    assert!(path.contains("cycle:C2 · experiment · 닫힘 · 부모 cycle:C1"), "{path}");
    assert!(path.contains("cycle:C3 · experiment · 열림 · 부모 cycle:C2"), "{path}");
}

#[test]
fn a_closed_active_ancestor_hands_over_what_it_learned() {
    // **이 절이 답해야 하는 물음은 「왜 지금 여기 있는가」다.**
    let dir = serial("lineage-handoff");
    let text = rendered(&dir);
    let path = section(&text, "활성 경로");

    // 이전 활성 Experiment 의 질문·판정·인수인계가 읽힌다.
    assert!(path.contains("질문: <problem>"), "조상의 질문이 없다:\n{path}");
    assert!(path.contains("판정: success"), "조상의 판정이 없다:\n{path}");
    assert!(
        path.contains("넘긴 것: 다음 Cycle 이 알아야 할 것"),
        "조상이 넘긴 것이 없다:\n{path}"
    );
    assert!(path.contains("다음 방향: open_child"), "{path}");
}

#[test]
fn an_active_ancestor_never_unfolds_its_steps() {
    // 조상의 Step 을 늘어놓으면 이 절이 곧 전체 history 가 된다.
    let dir = serial("lineage-no-steps");
    let text = rendered(&dir);
    let path = section(&text, "활성 경로");

    assert!(!path.contains("step:"), "조상의 Step 을 펼쳤다:\n{path}");
    // Step Report 의 칸 이름도 새어 나오지 않는다.
    for field in ["execution", "result", "hypothesis_fit", "rationale", "guardrail"] {
        assert!(!path.contains(field), "{field} 가 활성 경로에 나왔다:\n{path}");
    }

    // 그리고 **타입이 그것을 막는다** — 계보의 항목에는 Step 을 담을 자리가 없다.
    let seen = monitor(&dir);
    assert_eq!(seen.current_cycle.steps.len(), 1, "지금 자리는 제 Step 을 안다");
    // `seen.active_lineage[0].steps` 는 **컴파일되지 않는다.**
}

#[test]
fn the_current_cycle_is_the_last_item_with_the_same_identity() {
    let dir = serial("lineage-last-item");
    let seen = monitor(&dir);
    let last = seen.active_lineage.last().expect("계보는 비지 않는다");

    // 같은 함수가 지었으므로 **같은 값**이다 — 주소만이 아니라 사실 전체가.
    assert_eq!(*last, seen.current_cycle.facts, "마지막 항목과 지금 자리가 갈렸다");
    assert_eq!(last.cycle_ref, seen.current_cycle.facts.cycle_ref);
    assert_eq!(last.cycle_ref.to_string(), "cycle:C3");
}

#[test]
fn the_lineage_never_grows_along_the_revisit_source() {
    // 되돌아와 난 갈래에서도 계보는 `parent` 만 따라간다.
    let dir = branched("lineage-not-revisit");
    let seen = monitor(&dir);
    let refs = refs(&seen.active_lineage);
    assert_eq!(refs, vec!["cycle:C1", "cycle:C4"]);

    let source = seen
        .current_cycle
        .facts
        .revisit_from_cycle_ref
        .expect("갈래의 출처가 있다");
    assert_eq!(source.to_string(), "cycle:C3");
    assert!(
        !refs.contains(&source.to_string()),
        "갈래의 출처가 계보에 섞였다: {refs:?}"
    );
    // 그리고 화면의 항목 목록도 같다.
    let text = rendered(&dir);
    assert_eq!(lineage_order(section(&text, "활성 경로")), refs);
}

#[test]
fn the_active_and_the_left_behind_read_their_verdict_the_same_way() {
    // 같은 `verdict` 가 절에 따라 다른 뜻으로 읽히면 안 된다 — 두 절이 같은 문을 쓴다.
    let dir = branched("lineage-same-report");
    let text = rendered(&dir);
    let path = section(&text, "활성 경로");
    let left = section(&text, "지나온 갈래");

    // 활성 조상 C1 과 버린 갈래 C2·C3 이 **같은 이름표**로 판정을 말한다.
    assert!(path.contains("판정: success"), "{path}");
    assert!(left.contains("판정: success") && left.contains("판정: failure"), "{left}");
    assert!(path.contains("넘긴 것: ") && left.contains("넘긴 것: "), "이름표가 갈렸다");
    // 옛 이름표가 남아 있지 않다.
    assert!(!text.contains("다음 Cycle 에 넘길 것"), "두 이름표가 공존한다:\n{text}");
}

/// **`Other` 가 실제로 나타나는 자리를 짓는다.**
///
/// `C1 → C2 → C3 → C4(실패)` 를 직렬로 걷고 뿌리 `C1` 로 되돌아가 `C5` 를 연다.
/// 그러면 계보는 `[C1, C5]` 이고 버린 것들의 관계가 셋으로 갈린다.
///
/// ```text
/// C2  부모가 C1(계보 위)  → 두고 온 가지
/// C3  부모가 C2(계보 밖)  → 활성 경로와 직접 맞닿지 않는다   ← Other
/// C4  C5 의 갈래 출처                                    → RevisitSource
/// ```
fn three_relations(label: &str) -> PathBuf {
    let (mut session, dir) = started(label);
    for _ in 0..2 {
        walk_exit(&mut session, "success");
        close_cycle_toward(&mut session, "success", None);
        session.open_child_cycle(CycleKind::Experiment).expect("자식을 연다");
    }
    walk_exit(&mut session, "failure");
    close_cycle_toward(&mut session, "failure", Some("cycle:C1"));
    session.commit().expect("눕힌다");
    drop(session);

    ok(&dir, &["revisit"]);
    ok(&dir, &["open", "experiment"]);
    dir
}

#[test]
fn a_cycle_off_the_path_is_not_called_disconnected() {
    // `Other` 는 Graph 가 끊겼다는 뜻이 아니다 — 같은 Graph 안의 두고 온 가지의 자손이다.
    let dir = three_relations("lineage-other-wording");
    let seen = monitor(&dir);

    // 세 관계가 실제로 함께 나타나는 자리인지 먼저 확인한다 — 아니면 이 시험은
    // 아무것도 잡지 못한다.
    let relation = |name: &str| {
        seen.inactive_cycles
            .iter()
            .find(|cycle| cycle.cycle_ref.to_string() == name)
            .unwrap_or_else(|| panic!("{name} 이 계보 밖 목록에 없다"))
            .relation_to_current
    };
    assert_eq!(relation("cycle:C2"), CycleRelation::Abandoned);
    assert_eq!(relation("cycle:C3"), CycleRelation::Other);
    assert_eq!(relation("cycle:C4"), CycleRelation::RevisitSource);

    let text = rendered(&dir);
    let left = section(&text, "지나온 갈래");
    assert!(
        left.contains("현재 활성 경로 밖에 있고, 그 경로와 직접 맞닿지 않는다"),
        "Other 를 구조적으로 정확히 말하지 않는다:\n{left}"
    );
    assert!(
        !text.contains("지금 길과 이어져 있지 않다"),
        "Graph 단절을 암시하는 문장이 남아 있다:\n{text}"
    );
    // 세 관계가 서로 다른 문장으로 갈린다.
    assert!(left.contains("같은 자리에서 갈라져 두고 온 가지다"), "{left}");
    assert!(left.contains("지금 걷는 갈래가 여기서 갈라져 나왔다"), "{left}");
}

#[test]
fn the_lineage_is_more_than_a_list_of_references() {
    // **돌연변이 방지선.** 참조만 늘어놓는 구현으로 되돌리면 여기서 걸린다.
    let dir = serial("lineage-not-just-refs");
    let path = section(&rendered(&dir), "활성 경로").to_string();

    // 주소만 있는 줄로 이루어져 있지 않다 — 조상마다 사실이 딸려 있다.
    let bare: Vec<&str> = path
        .lines()
        .filter(|line| {
            let trimmed = line.trim();
            trimmed.starts_with("cycle:") && !trimmed.contains('·')
        })
        .collect();
    assert!(bare.is_empty(), "주소만 적힌 줄이 있다: {bare:?}");
    // 그리고 닫힌 조상의 판정과 인수인계가 실제로 있다.
    assert!(path.contains("판정: "), "{path}");
    assert!(path.contains("넘긴 것: "), "{path}");
}

// ══════════════════════════════════════════════════════════════════════════
//  안전한 standalone HTML renderer
// ══════════════════════════════════════════════════════════════════════════
//
// 이 renderer 가 다루는 것은 **사람이 적은 글**이다. 그것이 markup 이 되면 화면은 문서가
// 아니라 실행기가 된다. 그래서 여기서 재는 것은 셋이다.
//
// 1. **완전하고 닫힌 문서인가** — 밖에서 아무것도 불러오지 않고, 스스로 자물쇠를 건다.
// 2. **사용자 글이 글자로만 남는가** — 태그도, 속성도, 주소도, CSS 도 되지 못한다.
// 3. **두 화면이 같은 사실을 말하는가** — 서로의 출력을 파싱하지 않고, 각자 Snapshot 을 읽는다.

/// Snapshot 을 짓고 **세션을 놓은 뒤** HTML 을 만든다 — CLI 가 하는 그 순서.
fn html_of(dir: &Path) -> String {
    let seen = {
        let session = ProjectSession::open(spec(), state_in(dir)).expect("되살린다");
        session.monitor().expect("Snapshot 을 만든다")
    }; // ← 여기서 세션이 떨어지고 잠금이 풀린다.
    render_monitor_html(&seen)
}

// ── ① 완전하고 닫힌 문서 ─────────────────────────────────────────────────

#[test]
fn the_document_is_complete_and_declares_itself() {
    let html = html_of(&serial("html-document"));

    assert!(html.starts_with("<!doctype html>\n"), "{}", &html[..60]);
    assert!(html.contains("<html lang=\"ko\">"), "lang 이 없다");
    assert!(html.contains("<meta charset=\"utf-8\">"), "charset 이 없다");
    assert!(
        html.contains("<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"),
        "viewport 가 없다"
    );
    assert!(html.contains("<title>GIL Monitor</title>"), "title 이 없다");
    assert!(html.trim_end().ends_with("</html>"), "문서가 닫히지 않았다");
    // semantic 골격.
    for element in ["<main>", "<header>", "<h1>", "<section>", "<h2>", "<dl>", "<dt>", "<dd>"] {
        assert!(html.contains(element), "{element} 가 없다");
    }
}

#[test]
fn the_document_locks_itself_with_a_strict_policy() {
    let html = html_of(&serial("html-csp"));
    let csp = html
        .lines()
        .find(|line| line.contains("Content-Security-Policy"))
        .expect("CSP 가 없다");

    for directive in [
        "default-src 'none'",
        "script-src 'none'",
        "img-src 'none'",
        "font-src 'none'",
        "connect-src 'none'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'none'",
        "style-src 'unsafe-inline'",
    ] {
        assert!(csp.contains(directive), "{directive} 가 없다:\n{csp}");
    }
}

#[test]
fn nothing_is_fetched_and_nothing_runs() {
    let html = html_of(&branched("html-closed"));
    for forbidden in [
        "<script", "</script", "javascript:", "<iframe", "<object", "<embed", "<base",
        "<form", "<input", "<button", "<img", "<link", "@import", "url(", "srcset",
    ] {
        assert!(!html.contains(forbidden), "{forbidden:?} 가 문서에 있다");
    }
    // event handler attribute 는 하나도 없다.
    for handler in ["onerror", "onload", "onclick", "onmouseover", "onfocus", "onanimationstart"] {
        assert!(!html.contains(handler), "{handler} 가 문서에 있다");
    }
    // 바깥으로 나가는 주소가 없다 — 애초에 href·src 를 만들지 않는다.
    assert!(!html.contains("href="), "href 를 만들었다");
    assert!(!html.contains("src="), "src 를 만들었다");
    assert!(!html.contains("http://") && !html.contains("https://"), "외부 주소가 있다");
    // style 은 renderer 가 소유한 하나뿐이고, inline style 속성은 없다.
    assert_eq!(html.matches("<style>").count(), 1, "고정 stylesheet 는 하나다");
    assert!(!html.contains("style=\""), "inline style 속성을 만들었다");
}

// ── ② 사용자 글은 글자로만 남는다 ────────────────────────────────────────

/// 사람이 적을 수 있는 **가장 나쁜 글들.**
const NASTY: &[&str] = &[
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "<a href=\"javascript:alert(1)\">x</a>",
    "<style>body{display:none}</style>",
    "\" onmouseover=\"alert(1)",
    "'><script>alert(1)</script>",
    "a & b < c > d",
];

/// 그 글들을 Report·Define·Will·world 이유에 **실제로 심은** 프로젝트.
fn nasty_project(label: &str) -> PathBuf {
    let (session, dir) = started(label);
    drop(session);
    // Define 의 두 칸.
    open_action(&dir, "define");
    stdin_ok(
        &dir,
        &["close"],
        &format!(
            "problem: |\n  {}\n  {}\n  {}\nsuccess_condition: {}\n",
            NASTY[0], NASTY[1], NASTY[6], NASTY[2]
        ),
    );
    // Will 의 세 칸.
    stdin_ok_open(&dir, "hypothesis", NASTY[3], NASTY[4], NASTY[5]);
    dir
}

/// 행동 계약 세 칸에 임의의 글을 심어 자리를 연다.
fn stdin_ok_open(dir: &Path, kind: &str, objective: &str, next_action: &str, done_when: &str) {
    use std::io::Write as _;
    let contract =
        format!("objective: {objective}\nnext_action: {next_action}\ndone_when: {done_when}\n");
    let out = Command::new(GIL)
        .args(["open", kind])
        .current_dir(dir)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .and_then(|mut child| {
            child.stdin.as_mut().expect("stdin").write_all(contract.as_bytes())?;
            child.wait_with_output()
        })
        .expect("자리를 연다");
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
}

#[test]
fn every_dangerous_string_stays_text() {
    let dir = nasty_project("html-escape");
    let html = html_of(&dir);

    // 위험한 모양이 **요소가 되지 않는다.**
    for forbidden in ["<script", "<img", "<style>body", "<a href"] {
        assert!(!html.contains(forbidden), "{forbidden:?} 가 요소가 됐다");
    }
    // 그러나 **글자로는 남아 있다** — 내용이 사라지면 사람이 무엇을 적었는지 모른다.
    for nasty in NASTY {
        let escaped = nasty
            .replace('&', "&amp;")
            .replace('<', "&lt;")
            .replace('>', "&gt;")
            .replace('"', "&quot;")
            .replace('\'', "&#39;");
        assert!(
            html.contains(&escaped),
            "{nasty:?} 가 글자로 보존되지 않았다:\n{escaped}"
        );
    }
    // `&` 를 두 번 바꾸지 않았다.
    assert!(!html.contains("&amp;lt;"), "escape 를 두 번 걸었다");
    // 그리고 plain text 에는 **그대로** 남는다 — 두 화면이 같은 글을 말한다.
    let text = rendered(&dir);
    for nasty in NASTY {
        assert!(text.contains(nasty), "plain text 가 {nasty:?} 를 잃었다");
    }
}

#[test]
fn no_user_string_becomes_a_tag_an_attribute_or_css() {
    let dir = nasty_project("html-no-injection");
    let html = html_of(&dir);

    // 이 문서가 쓰는 태그는 **renderer 가 정한 목록**뿐이다.
    let mut tags: Vec<String> = Vec::new();
    let mut rest = html.as_str();
    while let Some(at) = rest.find('<') {
        rest = &rest[at + 1..];
        let name: String = rest
            .chars()
            .take_while(|ch| ch.is_ascii_alphanumeric() || *ch == '!' || *ch == '/')
            .collect();
        let name = name.trim_start_matches('/').to_string();
        if !name.is_empty() && !tags.contains(&name) {
            tags.push(name);
        }
    }
    let allowed = [
        "!doctype", "html", "head", "meta", "title", "style", "body", "main", "header",
        "h1", "h2", "h3", "p", "section", "dl", "dt", "dd", "ol", "ul", "li", "code",
        "details", "summary", "div",
        // 그림이 쓰는 것 — 전부 renderer 가 적는다. `script`·`foreignObject`·`image`·
        // `a`·`use` 는 **여기 없다**, 그러므로 생기면 이 시험이 먼저 깨진다.
        "svg", "desc", "g", "rect", "circle", "path", "text",
    ];
    for tag in &tags {
        assert!(allowed.contains(&tag.as_str()), "renderer 가 모르는 태그 {tag:?} 가 생겼다");
    }

    // 속성도 고정된 것뿐이다 — 값이 사용자 글에서 오지 않는다.
    for attribute in ["class=\"note\"", "class=\"path\""] {
        assert!(html.contains(attribute), "{attribute} 가 없다");
    }
    // 그리고 문서 전체에서 class 값은 renderer 가 정한 셋뿐이다.
    for chunk in html.split("class=\"").skip(1) {
        let value = chunk.split('"').next().expect("닫는 따옴표가 있다");
        assert!(
            [
                "note", "path", "branch", "focus", "picture", "record", "legend", "graph",
                // Cycle 그룹
                "g-cycle g-now", "g-cycle g-on", "g-cycle g-off", "g-rail", "g-group",
                "g-group-mark", "g-origin",
                // Step 행
                "g-step g-now", "g-step g-on", "g-step g-off", "g-dot", "g-ring", "g-sign",
                "g-kind", "g-said", "g-mark", "g-ref", "g-here",
                // 줄과 선
                "g-lane", "g-stop", "g-turn", "g-head", "g-folded", "g-link",
                // 그림과 목록을 가르는 자리
                "for-readers",
            ]
            .contains(&value),
            "renderer 가 모르는 class {value:?} 가 생겼다"
        );
    }
    // `<style>` 안에는 사용자 글이 한 조각도 없다.
    let style = html
        .split("<style>")
        .nth(1)
        .and_then(|rest| rest.split("</style>").next())
        .expect("stylesheet 가 있다");
    for nasty in NASTY {
        assert!(!style.contains(nasty), "사용자 글이 CSS 에 들어갔다");
    }
    assert!(!style.contains("alert"), "CSS 에 사용자 글이 섞였다");
}

#[test]
fn commands_and_topics_are_code_not_links() {
    let dir = serial("html-code-not-links");
    let html = html_of(&dir);
    assert!(html.contains("<code>gil "), "명령이 code 로 있지 않다");
    assert!(!html.contains("href="), "명령을 링크로 만들었다");
    assert!(!html.contains("<button"), "명령을 버튼으로 만들었다");
}

// ── ③ 두 화면이 같은 사실을 말하는가 ─────────────────────────────────────

/// Snapshot 하나가 **반드시 담고 있어야 하는 사실들.**
///
/// 어느 renderer 의 출력도 읽지 않는다 — Snapshot 에서 곧바로 뽑는다. 두 화면은 각자
/// 이 목록을 통과해야 하고, 그래서 한쪽이 다른 쪽을 파싱하는 일이 없다.
///
/// 새 저장 schema 도 공개 wire format 도 아니다. 시험이 두 표현을 견주는 자리일 뿐이다.
fn inventory(seen: &MonitorSnapshot) -> Vec<String> {
    let mut want: Vec<String> = Vec::new();

    fn cycle_facts(cycle: &gil::CycleFacts, want: &mut Vec<String>) {
        want.push(cycle.cycle_ref.to_string());
        want.push(cycle.kind.to_string());
        want.push(state_word(cycle.state).to_string());
        if let Some(parent) = cycle.parent_cycle_ref {
            want.push(parent.to_string());
        }
        if let Some(from) = cycle.revisit_from_cycle_ref {
            want.push(from.to_string());
        }
        if let Some(define) = &cycle.experiment_definition {
            want.push(define.problem.clone());
            want.push(define.success_condition.clone());
        }
        if let Some(report) = &cycle.report {
            want.push(report.verdict.clone());
            want.push(report.handoff_summary.clone());
            if let Some(lesson) = &report.outcome_lesson {
                want.push(lesson.clone());
            }
            if let Some(direction) = &report.next_direction {
                want.push(direction.action.clone());
                if let Some(reason) = &direction.reason {
                    want.push(reason.clone());
                }
                if let Some(target) = direction.target_cycle_ref {
                    want.push(target.to_string());
                }
            }
        }
    }

    cycle_facts(&seen.current_cycle.facts, &mut want);
    for cycle in &seen.active_lineage {
        cycle_facts(cycle, &mut want);
    }
    for cycle in &seen.inactive_cycles {
        want.push(cycle.cycle_ref.to_string());
        want.push(state_word(cycle.state).to_string());
        want.push(relation_word(cycle.relation_to_current).to_string());
        if let Some(parent) = cycle.parent_cycle_ref {
            want.push(parent.to_string());
        }
        if let Some(from) = cycle.revisit_from_cycle_ref {
            want.push(from.to_string());
        }
        if let Some(report) = &cycle.report {
            want.push(report.verdict.clone());
            want.push(report.handoff_summary.clone());
        }
    }

    if let Some(step) = &seen.current_step {
        want.push(step.step_ref.to_string());
        want.push(step.kind.to_string());
        want.push(state_word(step.state).to_string());
    }
    if let Some(pending) = &seen.pending_revisit {
        want.push(pending.from_cycle_ref.to_string());
        want.push(pending.target_cycle_ref.to_string());
    }
    if let Some(will) = &seen.current_will {
        want.push(will.will_ref.to_string());
        want.push(will.target_step_ref.to_string());
        want.push(will.objective.clone());
        want.push(will.next_action.clone());
        want.push(will.done_when.clone());
    }
    want.push(seen.world.baseline_snapshot_ref.to_string());
    want.push(world_word(seen.world.state).to_string());
    if let Some(reason) = &seen.world.reason {
        want.push(reason.clone());
    }
    for action in &seen.next_actions {
        want.push(action.reason.clone());
        if let Some(command) = &action.command {
            want.push(command.clone());
        }
        if let Some(topic) = &action.help_ref {
            want.push(topic.as_str().to_string());
        }
    }

    want.sort();
    want.dedup();
    want
}

/// 두 화면이 상태를 부르는 **그 낱말** — 시험도 같은 것을 쓴다.
fn state_word(state: NodeStatus) -> &'static str {
    match state {
        NodeStatus::Open => "열림",
        NodeStatus::Closed => "닫힘",
    }
}

fn world_word(state: WorldMark) -> &'static str {
    match state {
        WorldMark::Clean => "clean",
        WorldMark::Dirty => "dirty",
        WorldMark::Unknown => "unknown",
    }
}

fn relation_word(relation: CycleRelation) -> &'static str {
    match relation {
        CycleRelation::RevisitSource => "지금 걷는 갈래가 여기서 갈라져 나왔다",
        CycleRelation::Abandoned => "같은 자리에서 갈라져 두고 온 가지다",
        CycleRelation::Other => "현재 활성 경로 밖에 있고, 그 경로와 직접 맞닿지 않는다",
    }
}

fn escaped(raw: &str) -> String {
    raw.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}

/// 한 프로젝트에서 두 화면이 같은 사실을 담는지 잰다.
fn assert_parity(dir: &Path, label: &str) {
    let seen = monitor(dir);
    let text = render_monitor_text(&seen);
    let html = render_monitor_html(&seen);

    for fact in inventory(&seen) {
        // plain text 는 여러 줄 값의 뒷줄을 들여쓴다. 그래서 한 덩어리로 견주지 않고
        // **줄마다** 남아 있는지 본다 — 내용이 사라지지 않았는지가 물음이다.
        for line in fact.lines() {
            assert!(
                text.contains(line),
                "{label}: plain text 가 {line:?} 를 잃었다"
            );
        }
        // HTML 은 `pre-wrap` 이라 줄바꿈이 그대로 남는다 — 통째로 견딘다.
        assert!(
            html.contains(&escaped(&fact)),
            "{label}: HTML 이 {fact:?} 를 잃었다"
        );
    }
}

#[test]
fn both_renderers_preserve_the_same_facts() {
    // 시나리오마다 담기는 사실이 다르다 — 한 자리만 재면 빈 절을 지나친다.
    assert_parity(&serial("parity-serial"), "직렬 계보");
    assert_parity(&branched("parity-branch"), "되돌아와 난 갈래");
    assert_parity(&three_relations("parity-relations"), "세 관계");
    assert_parity(&nasty_project("parity-nasty"), "위험한 글");
}

#[test]
fn both_renderers_agree_on_the_pending_revisit() {
    let (mut session, dir) = started("parity-pending");
    walk_exit(&mut session, "failure");
    close_cycle_toward(&mut session, "failure", Some("cycle:C1"));
    drop(session);
    ok(&dir, &["revisit"]);

    assert_parity(&dir, "pending");
    // 그리고 **어느 쪽도** 열리지 않은 Cycle 을 그리지 않는다.
    assert!(!rendered(&dir).contains("cycle:C3"));
    assert!(!html_of(&dir).contains("cycle:C3"));
}

#[test]
#[cfg(unix)]
fn both_renderers_agree_on_an_unknown_world() {
    let (session, dir) = started("parity-unknown");
    drop(session);
    open_action(&dir, "define");
    std::os::unix::fs::symlink(dir.join("work.txt"), dir.join("link")).unwrap();

    assert_parity(&dir, "unknown");
    let html = html_of(&dir);
    assert!(html.contains("unknown — 지금 폴더를 보지 못했다"), "{html}");
    assert!(!html.contains("dirty —"), "못 본 것을 dirty 라 했다");
    assert!(html.contains("보지 못한 까닭"), "이유를 잃었다");
}

// ── ④ 시나리오 ───────────────────────────────────────────────────────────

#[test]
fn the_first_interview_invents_no_experiment_in_html() {
    let dir = bare("html-first-interview");
    write(&dir, "work.txt", "처음");
    let session = ProjectSession::start(spec(), state_in(&dir)).expect("시작한다");
    session.commit().expect("눕힌다");
    drop(session);

    let html = html_of(&dir);
    assert!(html.contains("<h2>현재 인터뷰</h2>"), "{html}");
    assert!(!html.contains("<h2>현재 실험</h2>"), "Interview 를 실험이라 불렀다");
    assert!(!html.contains("<dt>질문</dt>"), "없는 Define 을 지어냈다");
    assert!(!html.contains("<h2>지나온 갈래</h2>"), "없는 절을 그렸다");
    assert!(!html.contains("<h2>현재 행동</h2>"), "없는 Will 을 그렸다");
    assert!(html.contains("아직 아무것도 열지 않았다"), "{html}");
}

#[test]
fn a_serial_ancestor_hands_over_in_html_too() {
    let html = html_of(&serial("html-ancestor"));
    let path = html
        .split("<h2>활성 경로</h2>")
        .nth(1)
        .and_then(|rest| rest.split("<h2>").next())
        .expect("활성 경로 절이 있다");

    assert!(path.contains("cycle:C1 · interview · 닫힘"), "{path}");
    assert!(path.contains("cycle:C2 · experiment · 닫힘 · 부모 cycle:C1"), "{path}");
    assert!(path.contains("<dt>판정</dt>"), "{path}");
    assert!(path.contains("<dt>넘긴 것</dt>"), "{path}");
    // 조상의 Step 은 펼치지 않는다.
    assert!(!path.contains("step:"), "조상의 Step 을 펼쳤다:\n{path}");
    // 깊이는 중첩 목록으로 — 색이 아니다.
    assert!(path.matches("<ol class=\"path\">").count() >= 3, "{path}");
}

#[test]
fn success_failure_and_the_revisit_source_are_told_apart_in_html() {
    let html = html_of(&three_relations("html-relations"));
    let left = html
        .split("<h2>지나온 갈래</h2>")
        .nth(1)
        .and_then(|rest| rest.split("<h2>").next())
        .expect("지나온 갈래 절이 있다");

    assert!(left.contains("<dd>success</dd>"), "{left}");
    assert!(left.contains("<dd>failure</dd>"), "{left}");
    for relation in [
        "지금 걷는 갈래가 여기서 갈라져 나왔다",
        "같은 자리에서 갈라져 두고 온 가지다",
        "현재 활성 경로 밖에 있고, 그 경로와 직접 맞닿지 않는다",
    ] {
        assert!(left.contains(relation), "{relation} 이 없다:\n{left}");
    }
    // 활성 경로와 **모양으로도** 갈린다.
    assert!(left.contains("class=\"branch\""), "{left}");
    // enum 이름은 나오지 않는다.
    for variant in ["RevisitSource", "Abandoned", "Other"] {
        assert!(!left.contains(variant), "{variant} 를 그대로 보였다");
    }
}

#[test]
fn the_will_shows_its_three_values_in_html() {
    let (session, dir) = started("html-will");
    drop(session);
    open_action(&dir, "define");
    let html = html_of(&dir);
    assert!(html.contains("<h2>현재 행동</h2>"), "{html}");
    for value in ["<dd>그 목적</dd>", "<dd>그 행동</dd>", "<dd>그 조건</dd>"] {
        assert!(html.contains(value), "{value} 가 없다");
    }
    for label in ["<dt>목표</dt>", "<dt>지금 할 일</dt>", "<dt>완료 조건</dt>"] {
        assert!(html.contains(label), "{label} 이 없다");
    }
}

#[test]
fn a_dirty_verify_shows_both_moves_in_html() {
    let (session, dir) = started("html-dirty-verify");
    drop(session);
    open_action(&dir, "define");
    close_with_report(&dir, NodeKind::Define);
    open_action(&dir, "hypothesis");
    close_with_report(&dir, NodeKind::Hypothesis);
    open_action(&dir, "verify");
    write(&dir, "work.txt", "Verify 가 바꾼 세계");

    let html = html_of(&dir);
    assert!(html.contains("dirty — 기준 세계 이후 파일이 바뀌었다"), "{html}");
    assert!(html.contains("<code>gil close</code>"), "{html}");
    assert!(html.contains("<code>gil restore</code>"), "{html}");
    assert!(html.contains("Verify — 바뀐 세계를 확정할 수 있다"), "{html}");
}

// ── ⑤ 안정성과 명령 ──────────────────────────────────────────────────────

#[test]
fn the_same_snapshot_always_renders_the_same_html() {
    let dir = branched("html-stable");
    let session = ProjectSession::open(spec(), state_in(&dir)).expect("되살린다");
    let seen = session.monitor().expect("Snapshot");
    drop(session);

    let once = render_monitor_html(&seen);
    for _ in 0..3 {
        assert_eq!(render_monitor_html(&seen), once, "같은 Snapshot 이 다른 문서가 됐다");
    }
    assert_eq!(html_of(&dir), once);
}

#[test]
fn the_html_flag_prints_the_function_result() {
    let dir = branched("cmd-html");
    assert_eq!(ok(&dir, &["monitor", "--html"]), html_of(&dir));
    // 기본 출력은 **바뀌지 않는다.**
    assert_eq!(ok(&dir, &["monitor"]), rendered(&dir));
    assert_ne!(ok(&dir, &["monitor"]), ok(&dir, &["monitor", "--html"]));
}

#[test]
fn the_monitor_command_still_refuses_anything_else() {
    let dir = branched("cmd-html-args");
    for extra in ["--html=1", "html", "--watch", "--format", "-h", "cycle:C1"] {
        let out = run(&dir, &["monitor", extra]);
        assert!(!out.status.success(), "{extra} 를 받아들였다");
        let said = String::from_utf8_lossy(&out.stderr);
        assert!(said.contains("받지 않는다"), "{extra}: {said}");
    }
}

#[test]
fn the_html_command_changes_nothing() {
    let dir = branched("cmd-html-read-only");
    open_action(&dir, "define");
    let before = (
        fs::read(state_in(&dir)).expect("상태를 읽는다"),
        world_of(&dir),
        objects_of(&dir),
    );

    for _ in 0..3 {
        ok(&dir, &["monitor", "--html"]);
    }

    assert_eq!(fs::read(state_in(&dir)).unwrap(), before.0, "state.yaml 이 바뀌었다");
    assert_eq!(world_of(&dir), before.1, "작업 파일이 바뀌었다");
    assert_eq!(objects_of(&dir), before.2, "Snapshot 창고가 바뀌었다");
}

#[test]
fn no_internal_address_reaches_the_html_either() {
    let html = html_of(&branched("html-no-internals"));
    for hidden in ["sha256", ".gil", "manifest", "blobs", "state.yaml", "/tmp"] {
        assert!(!html.contains(hidden), "{hidden:?} 가 문서에 있다");
    }
    for absent in ["Chain", "chain", "승인", "checkpoint", "milestone", "autonomous"] {
        assert!(!html.contains(absent), "{absent:?} 가 문서에 있다");
    }
}

// ── gil monitor --serve — 공개 표면 ────────────────────────────────────────
//
// 여기서 재는 것은 **사람이 실제로 밟는 길**이다. 창의 안쪽은 lib 시험이 재고, 여기서는
// 명령 하나가 무엇을 적고 무엇을 적지 않는지, 그리고 끝난 뒤에 무엇이 남는지를 본다.

/// 진짜 프로젝트 하나를 세운다 — `gil start` 가 만드는 것과 같은 자리로.
fn fresh(label: &str) -> PathBuf {
    let dir = bare(label);
    fs::write(dir.join("a.txt"), "가").expect("세계를 하나 둔다");
    let session =
        gil::ProjectSession::start(spec(), state_in(&dir)).expect("시작한다");
    session.commit().expect("눕힌다");
    dir
}

/// `gil monitor --serve` 를 띄우고 적어 낸 주소를 받는다.
///
/// 끝낼 책임은 부르는 쪽에 있다 — [`stop`] 을 쓴다.
fn start_serving(dir: &Path) -> (std::process::Child, String) {
    let mut child = Command::new(GIL)
        .args(["monitor", "--serve"])
        .current_dir(dir)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("gil 을 부를 수 있어야 한다");

    // 주소 한 줄이 나올 때까지만 읽는다. 끝까지 읽으면 이 명령은 끝나지 않으므로 멈춘다.
    let mut out = std::io::BufReader::new(child.stdout.take().expect("stdout"));
    let mut said = String::new();
    for _ in 0..8 {
        let mut line = String::new();
        if std::io::BufRead::read_line(&mut out, &mut line).unwrap_or(0) == 0 {
            break;
        }
        said.push_str(&line);
        if said.contains("Ctrl-C") {
            break;
        }
    }
    child.stdout = Some(out.into_inner());
    (child, said)
}

/// 신호 하나로 끝내고, 끝났는지 확인한다.
fn stop(child: &mut std::process::Child) -> bool {
    let pid = child.id().to_string();
    let _ = Command::new("kill").args(["-INT", &pid]).status();
    for _ in 0..50 {
        match child.try_wait() {
            Ok(Some(_)) => return true,
            _ => std::thread::sleep(std::time::Duration::from_millis(100)),
        }
    }
    let _ = child.kill();
    false
}

/// 날 것 그대로 한 통 보내고 받는다.
fn fetch(url: &str) -> Option<String> {
    let rest = url.strip_prefix("http://")?;
    let (host, path) = rest.split_once('/')?;
    let mut stream = std::net::TcpStream::connect(host).ok()?;
    stream
        .set_read_timeout(Some(std::time::Duration::from_secs(5)))
        .ok()?;
    std::io::Write::write_all(
        &mut stream,
        format!("GET /{path} HTTP/1.1\r\nHost: {host}\r\n\r\n").as_bytes(),
    )
    .ok()?;
    let mut got = Vec::new();
    let _ = std::io::Read::read_to_end(&mut stream, &mut got);
    Some(String::from_utf8_lossy(&got).into_owned())
}

#[test]
fn serving_says_the_address_once_and_nothing_more() {
    let dir = fresh("serve-says-address");
    let (mut child, said) = start_serving(&dir);

    // 요구된 네 가지를 모두 말한다.
    assert!(said.contains("GIL Monitor가 이 주소에서 현재 프로젝트를 보여 준다."), "{said}");
    assert!(said.contains("이 주소는 이 실행 동안만 유효하다."), "{said}");
    assert!(said.contains("종료하려면 Ctrl-C."), "{said}");
    let url = said
        .lines()
        .find(|line| line.starts_with("http://127.0.0.1:"))
        .expect("주소 한 줄이 없다")
        .to_string();

    // token 은 주소 안에 **한 번만** 나온다.
    let token = url.rsplit('/').next().expect("token").to_string();
    assert_eq!(token.len(), 64, "token 이 짧다: {token}");
    assert_eq!(said.matches(&token).count(), 1, "token 을 따로 되풀이했다: {said}");

    // 프로젝트 안쪽은 한 글자도 적지 않는다.
    for secret in [".gil", "state.yaml", "artifacts", "blobs", "sha256", "project.lock"] {
        assert!(!said.contains(secret), "{secret} 을 적었다: {said}");
    }
    assert!(
        !said.contains(&dir.display().to_string()),
        "프로젝트 경로를 적었다: {said}"
    );
    // Snapshot 전체도, 감시 사건도 적지 않는다.
    assert!(!said.contains("<html"), "화면을 통째로 적었다");
    assert!(!said.contains("활성 경로"), "Snapshot 을 적었다");

    // 그리고 그 주소는 실제로 화면을 준다.
    let answer = fetch(&url).expect("붙는다");
    assert!(answer.starts_with("HTTP/1.1 200 OK"), "{answer}");
    assert!(answer.contains("활성 경로"), "화면이 아니다");

    assert!(stop(&mut child), "Ctrl-C 로 끝나지 않았다");
}

#[test]
fn serving_does_not_open_a_browser() {
    let dir = fresh("serve-no-browser");
    let (mut child, said) = start_serving(&dir);
    // 사람이 직접 열어야 한다는 것이 계약이다. 열어 주는 명령을 부르지 않았다는 증거는
    // 자식 프로세스가 없다는 것이다.
    //
    // **한 번만 보면 놓친다.** browser 를 여는 명령은 짧게 살다 사라지므로, 주소를 적은
    // 직후부터 되풀이해 살핀다.
    let pid = child.id().to_string();
    for _ in 0..150 {
        let children = Command::new("pgrep")
            .args(["-P", &pid])
            .output()
            .expect("pgrep");
        assert!(
            children.stdout.is_empty(),
            "무언가를 열었다: {}",
            String::from_utf8_lossy(&children.stdout)
        );
        std::thread::sleep(std::time::Duration::from_millis(10));
    }
    assert!(!said.to_lowercase().contains("open"), "{said}");
    assert!(stop(&mut child), "Ctrl-C 로 끝나지 않았다");
}

#[test]
fn after_ctrl_c_nothing_is_left_behind() {
    let dir = fresh("serve-leaves-nothing");
    let before_world = fs::read(dir.join("a.txt")).expect("세계를 읽는다");
    let before_state = fs::read(dir.join(gil::STATE_PATH)).expect("상태를 읽는다");

    let (mut child, said) = start_serving(&dir);
    let url = said
        .lines()
        .find(|line| line.starts_with("http://"))
        .expect("주소")
        .to_string();
    let token = url.rsplit('/').next().expect("token").to_string();
    assert!(fetch(&url).is_some(), "살아 있어야 한다");

    assert!(stop(&mut child), "Ctrl-C 로 끝나지 않았다");

    // 주소는 더 이상 답하지 않는다.
    assert!(fetch(&url).is_none_or(|got| got.is_empty()), "닫혔는데 답한다");
    // 저장 파일도 작업 파일도 그대로다.
    assert_eq!(before_world, fs::read(dir.join("a.txt")).expect("다시 읽는다"));
    assert_eq!(
        before_state,
        fs::read(dir.join(gil::STATE_PATH)).expect("다시 읽는다")
    );
    // token 도 cache 도 port 도 디스크에 남지 않았다.
    for path in every_file(&dir) {
        let Ok(bytes) = fs::read(&path) else { continue };
        assert!(
            !String::from_utf8_lossy(&bytes).contains(&token),
            "token 이 {path:?} 에 남았다"
        );
        assert!(
            !path.to_string_lossy().contains(&token),
            "token 이 파일 이름에 남았다"
        );
    }
    // 그리고 다음 명령이 곧바로 실행된다.
    let after = Command::new(GIL)
        .arg("status")
        .current_dir(&dir)
        .output()
        .expect("부른다");
    assert!(after.status.success(), "잠금이 남았다: {after:?}");
}

fn every_file(root: &Path) -> Vec<PathBuf> {
    let mut found = Vec::new();
    let Ok(entries) = fs::read_dir(root) else {
        return found;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        match path.is_dir() {
            true => found.extend(every_file(&path)),
            false => found.push(path),
        }
    }
    found
}

#[test]
fn the_two_older_shapes_are_untouched() {
    let dir = fresh("serve-older-shapes");
    let plain = Command::new(GIL)
        .arg("monitor")
        .current_dir(&dir)
        .output()
        .expect("부른다");
    let page = Command::new(GIL)
        .args(["monitor", "--html"])
        .current_dir(&dir)
        .output()
        .expect("부른다");
    assert!(plain.status.success() && page.status.success());
    let page = String::from_utf8_lossy(&page.stdout);
    // 저장해 여는 문서에는 스스로를 다시 받아오는 표지가 없다.
    assert!(!page.contains("http-equiv=\"refresh\""), "standalone 에 표지가 들어갔다");
    assert!(!page.contains("127.0.0.1"), "standalone 에 주소가 들어갔다");
}

#[test]
fn an_unknown_flag_is_refused_kindly() {
    let dir = fresh("serve-unknown-flag");
    let refused = Command::new(GIL)
        .args(["monitor", "--watch"])
        .current_dir(&dir)
        .output()
        .expect("부른다");
    assert!(!refused.status.success());
    let said = String::from_utf8_lossy(&refused.stderr);
    assert!(said.contains("거절"), "{said}");
    assert!(said.contains("--serve"), "무엇이 있는지 알려 주지 않는다: {said}");
}

// ── ⑤ 판독 실험 1 회귀 ────────────────────────────────────────────────────
//
// 2026-09-02 의 실패를 **fixture 로 굳힌다.** 사람이 답하지 못한 다섯 물음이 화면의 첫
// 부분에서 직접 답해지는지 매번 다시 잰다.

const FAILED_PROBLEM: &str = "병렬로 모은 결과를 점수로 정렬할 때 순서가 실행마다 달라진다";
const FAILED_SUCCESS: &str = "같은 입력에 대해 100회 실행이 모두 같은 순서를 낸다";
const FAILED_LESSON: &str =
    "점수만 사용하는 안정 정렬은 비결정적인 병렬 수집 순서를 그대로 보존함";
const FAILED_HANDOFF: &str = "점수만으로는 동점의 순서를 정할 수 없었다";
const NEW_PROBLEM: &str = "동점일 때 고유 ID를 보조 키로 사용하면 순서가 고정되는가";
const NEW_SUCCESS: &str = "100회 결과가 같고 ID의 고유성이 확인된다";
const WORK_ACTION: &str = "점수와 ID의 복합 정렬을 구현하고 100회 반복 실행한다";
const WORK_DONE: &str = "100회 결과가 같고 ID의 고유성이 확인된다";

/// ```text
/// Interview success
/// ├─ Experiment failure   점수만 쓰는 안정 정렬은 병렬 수집 순서를 보존한다
/// └─ revisit 뒤 현재 Experiment   가설: 동점일 때 고유 ID 를 보조 키로
///      현재: Verify 열림
/// ```
fn reading_one(label: &str) -> PathBuf {
    let (mut session, dir) = started(label);

    // ── 실패한 첫 실험 ───────────────────────────────────────────────────
    let define = |problem: &str, success: &str| -> gil::Report {
        let rules = spec();
        full_report(&rules, CycleKind::Experiment, NodeKind::Define)
            .with("problem", problem)
            .with("success_condition", success)
    };
    opened(session.project_mut(), NodeKind::Define);
    session
        .close_step(define(FAILED_PROBLEM, FAILED_SUCCESS))
        .expect("문제를 고정한다");
    for kind in [NodeKind::Hypothesis, NodeKind::Verify, NodeKind::Analysis] {
        opened(session.project_mut(), kind);
        let rules = session.project().cycles().current().rules().clone();
        session
            .close_step(full_report(&rules, CycleKind::Experiment, kind))
            .expect("걷는다");
    }
    opened(session.project_mut(), NodeKind::Outcome);
    let rules = session.project().cycles().current().rules().clone();
    session
        .close_step(
            full_report(&rules, CycleKind::Experiment, NodeKind::Outcome)
                .with("verdict", "failure")
                .with("lesson", FAILED_LESSON)
                .with(ACTION, "close_cycle")
                .with(REASON, "이 갈래로는 순서를 고정할 수 없다"),
        )
        .expect("판정을 닫는다");
    {
        let cycle = session.project().cycles().current();
        let last = cycle.steps().current().expect("판정에 서 있다");
        let mut report = cycle_report(cycle, "failure", last);
        report.insert(CYCLE_TARGET, "cycle:C1");
        report.insert("handoff_summary", FAILED_HANDOFF);
        session.close_cycle(report).expect("Cycle 을 닫는다");
        session.commit().expect("눕힌다");
    }
    drop(session);

    // ── 되돌아가 새 갈래를 연다 ──────────────────────────────────────────
    ok(&dir, &["revisit"]);
    ok(&dir, &["open", "experiment"]);

    // ── 새 실험을 Verify 가 열린 자리까지 ────────────────────────────────
    let mut session = ProjectSession::open(spec(), state_in(&dir)).expect("되살린다");
    opened(session.project_mut(), NodeKind::Define);
    session
        .close_step(define(NEW_PROBLEM, NEW_SUCCESS))
        .expect("새 문제를 고정한다");
    opened(session.project_mut(), NodeKind::Hypothesis);
    let rules = session.project().cycles().current().rules().clone();
    session
        .close_step(full_report(&rules, CycleKind::Experiment, NodeKind::Hypothesis))
        .expect("가설을 닫는다");
    session
        .open_action_step(
            NodeKind::Verify,
            contract("동점 순서가 고정되는지 본다", WORK_ACTION, WORK_DONE),
        )
        .expect("검증을 연다");
    session.commit().expect("눕힌다");
    drop(session);
    dir
}

#[test]
fn the_first_screen_answers_the_five_questions_of_reading_one() {
    let dir = reading_one("reading-one");
    let html = html_of(&dir);
    // 첫 부분 = 접힌 상세 기록 **앞**. 30초 안에 눈이 닿는 자리만 본다.
    let first = html
        .split("<details")
        .next()
        .expect("상세 기록이 뒤에 있다")
        .to_string();

    // ① 현재 질문과 성공 기준 — **둘이 함께** 있어야 한다.
    assert!(first.contains(NEW_PROBLEM), "현재 질문이 첫 화면에 없다");
    assert!(first.contains(NEW_SUCCESS), "성공 기준이 첫 화면에 없다");
    let 지금 = section_of(&first, "지금");
    assert!(지금.contains(NEW_PROBLEM) && 지금.contains(NEW_SUCCESS), "질문과 성공 기준이 떨어져 있다:\n{지금}");

    // ② 이전 실험의 실패 이유
    assert!(first.contains(FAILED_LESSON), "실패 이유가 첫 화면에 없다");
    assert!(first.contains(FAILED_HANDOFF), "무엇이 안 됐는지가 없다");

    // ③ 현재 새 가설 — 전환 서사 안에서.
    let 왜 = section_of(&first, "왜 여기 왔는가");
    assert!(왜.contains("현재의 새 가설"), "새 가설을 이름 붙이지 않았다:\n{왜}");
    assert!(왜.contains(NEW_PROBLEM), "{왜}");

    // ④ 지금 수행할 작업 — 손으로 하는 일.
    let 할일 = section_of(&first, "지금 할 일");
    assert!(할일.contains("작업 행동"), "{할일}");
    assert!(할일.contains(WORK_ACTION), "작업 행동이 없다:\n{할일}");
    assert!(할일.contains(WORK_DONE), "완료 조건이 없다:\n{할일}");

    // ⑤ 그 뒤에 칠 GIL 명령 — 작업 행동과 **다른 이름표로.**
    assert!(할일.contains("그 일이 끝나면"), "{할일}");
    assert!(할일.contains("<code>gil close</code>"), "GIL 명령이 없다:\n{할일}");

    // 그리고 순서가 계약이다.
    let at = |needle: &str| first.find(needle).unwrap_or_else(|| panic!("{needle} 이 없다"));
    assert!(at("<h2>지금</h2>") < at("<h2>지금 할 일</h2>"), "순서가 뒤집혔다");
    assert!(at("<h2>지금 할 일</h2>") < at("<h2>여정</h2>"), "순서가 뒤집혔다");
    assert!(at("<h2>여정</h2>") < at("<h2>왜 여기 왔는가</h2>"), "순서가 뒤집혔다");
}

#[test]
fn the_old_next_direction_is_never_dressed_as_the_present() {
    // 판독 실험 1 에서 사람이 걸린 바로 그 자리다.
    let dir = reading_one("reading-one-old-direction");
    let html = html_of(&dir);
    let first = html.split("<details").next().expect("앞부분").to_string();

    // 과거의 방향은 첫 화면에서 **「지금 할 일」 뒤**에, 그리고 「당시」라는 이름으로만.
    let 할일 = section_of(&first, "지금 할 일");
    assert!(!할일.contains("당시 다음 방향"), "과거 방향이 지금 할 일에 섞였다");
    assert!(!할일.contains("close_cycle"), "내부 칸 이름이 지금 할 일에 있다:\n{할일}");
    if first.contains("당시 다음 방향") {
        assert!(
            first.find("<h2>지금 할 일</h2>") < first.find("당시 다음 방향"),
            "과거 방향이 지금 할 일보다 위에 있다"
        );
    }
    // 내부 칸 이름을 초보자용 큰 이름표로 쓰지 않는다.
    for internal in ["open_child", "revisit_from", "next_direction", "target_cycle_ref"] {
        assert!(
            !first.contains(&format!("<h2>{internal}</h2>")),
            "{internal} 을 큰 제목으로 썼다"
        );
        assert!(
            !first.contains(&format!("<dt>{internal}</dt>")),
            "{internal} 을 이름표로 썼다"
        );
    }
}

/// 제목 하나가 이끄는 절만 잘라 낸다.
fn section_of(html: &str, title: &str) -> String {
    let at = html
        .find(&format!("<h2>{title}</h2>"))
        .unwrap_or_else(|| panic!("{title} 절이 없다"));
    let rest = &html[at..];
    let end = rest.find("</section>").unwrap_or(rest.len());
    rest[..end].to_string()
}

/// 세 표현이 **같은 사실**을 말하는지 — 좌표가 아니라 사실을.
#[test]
fn the_three_projections_tell_the_same_story() {
    let dir = reading_one("three-projections");
    let seen = monitor(&dir);
    let plain = rendered(&dir);
    let html = html_of(&dir);
    // 그림이 말하는 것 = SVG 와 그 접근성 요약이 함께 있는 절.
    let picture = html
        .split("<section class=\"picture\">")
        .nth(1)
        .and_then(|rest| rest.split("</section>").next())
        .expect("그림 절이 있다")
        .to_string();

    // ① 보여야 하는 CycleRef 는 셋 다에 있다.
    let shown = [
        seen.current_cycle.facts.cycle_ref.to_string(),
        seen.active_lineage[0].cycle_ref.to_string(),
        seen.inactive_cycles[0].cycle_ref.to_string(),
    ];
    for address in &shown {
        assert!(plain.contains(address), "글에 {address} 가 없다");
        assert!(html.contains(address), "HTML 에 {address} 가 없다");
        assert!(picture.contains(address), "그림에 {address} 가 없다");
    }

    // ② 앞으로 나아간 것과 되돌아간 것이 **서로 다른 문법으로** 나타난다.
    //    진행은 선이고, 되돌아감은 **선이 아니라 lane 출발점의 글**이다.
    assert!(picture.contains("class=\"g-turn\""), "갈래로 나아가는 선이 없다");
    assert!(picture.contains("class=\"g-lane\""), "lane 이 없다");
    assert!(picture.contains("실패 뒤"), "되돌아감의 유래가 없다:\n{picture}");
    assert!(picture.contains("다시 시도"), "되돌아감을 말하지 않는다");
    // 그리고 **위로 향하는 화살표가 없다** — 화살촉은 아래를 가리키는 모양 하나뿐이다.
    for head in picture.lines().filter(|line| line.contains("class=\"g-head\"")) {
        assert!(head.contains("l -4 -7 l 8 0 z"), "위를 가리키는 화살촉이 생겼다: {head}");
    }

    // ③ 활성과 비활성이 셋 다에서 갈린다.
    assert!(picture.contains("현재 Cycle"), "그림이 지금을 말하지 않는다");
    assert!(picture.contains("지나온 갈래"), "그림이 두고 온 갈래를 말하지 않는다");
    assert!(picture.contains("class=\"g-stop\""), "끝난 갈래를 막지 않았다");
    assert!(plain.contains("활성 경로") && plain.contains("지나온 갈래"), "{plain}");

    // ④ 종류·상태·판정.
    assert!(picture.contains("인터뷰") && picture.contains("실험"), "{picture}");
    for word in ["성공", "실패", "열림"] {
        assert!(picture.contains(word), "그림에 {word} 이 없다");
    }

    // ⑤ 현재 Cycle 과 현재 Step.
    let here_step = seen.current_step.as_ref().expect("열린 자리").step_ref.to_string();
    assert!(plain.contains(&here_step) && html.contains(&here_step), "현재 Step 이 없다");
    assert!(picture.contains(&here_step), "그림에 현재 Step 이 없다");
    assert!(picture.contains("검증"), "그림이 Step 의 종류를 말하지 않는다");
    // 그림의 기본 node 는 Step 이다 — 과거 Cycle 의 Step 도 빠지지 않는다.
    for step in seen.timeline.iter().flat_map(|entry| &entry.steps) {
        assert!(
            picture.contains(&step.step_ref.to_string()),
            "그림에 {} 가 없다",
            step.step_ref
        );
    }

    // ⑥ 질문 · 성공 기준 · 작업 행동 · 완료 조건 · GIL 명령 — 글과 HTML 에 모두.
    let define = seen.current_cycle.facts.experiment_definition.as_ref().expect("정의");
    let will = seen.current_will.as_ref().expect("걸린 행동");
    for fact in [
        define.problem.as_str(),
        define.success_condition.as_str(),
        will.next_action.as_str(),
        will.done_when.as_str(),
    ] {
        assert!(plain.contains(fact), "글에 {fact:?} 가 없다");
        assert!(html.contains(fact), "HTML 에 {fact:?} 가 없다");
    }
    let command = seen
        .next_actions
        .iter()
        .find_map(|action| action.command.as_deref())
        .expect("다음 명령");
    assert!(plain.contains(command) && html.contains(command), "{command} 가 없다");
}

#[test]
fn the_plain_text_gains_no_drawing() {
    // 글은 **참조 표현**으로 남는다. ASCII 그림을 더하지 않는다.
    let dir = reading_one("plain-stays-plain");
    let plain = rendered(&dir);
    for shape in ["<svg", "─", "│", "├", "└", "┌", "┐", "╭", "▔", "+--", "|  |"] {
        assert!(!plain.contains(shape), "글에 그림이 들어갔다: {shape:?}");
    }
    // 그리고 사실은 그대로 있다.
    assert!(plain.contains("cycle:C2") && plain.contains("cycle:C3"), "{plain}");
}

// ── ⑥ 전체 Step 시간선 ────────────────────────────────────────────────────
//
// Step DAG 를 그리려면 **모든 Cycle 의 Step 이** 필요하다. 그러나 Cycle 해상도의 계약은
// 그대로 두었으므로, 이 절은 새 칸 하나가 구조의 순서를 그대로 옮겼는지만 잰다.

#[test]
fn the_timeline_holds_every_cycle_in_the_order_the_domain_issued_them() {
    let dir = reading_one("timeline-issue-order");
    let seen = monitor(&dir);

    // 도메인이 발급한 순서를 **직접** 읽어 와 견준다 — 시험이 순서를 지어내지 않는다.
    let session = ProjectSession::open(spec(), state_in(&dir)).expect("되살린다");
    let issued: Vec<String> = session
        .project()
        .cycles()
        .nodes()
        .iter()
        .map(|cycle| cycle.id().to_ref().to_string())
        .collect();
    drop(session);

    let shown: Vec<String> = seen
        .timeline
        .iter()
        .map(|entry| entry.facts.cycle_ref.to_string())
        .collect();
    assert_eq!(shown, issued, "시간선이 발급 순서와 다르다");
    assert!(shown.len() >= 3, "이 시나리오는 Cycle 셋이다: {shown:?}");
}

#[test]
fn every_cycle_keeps_the_step_order_the_walk_made() {
    let dir = reading_one("timeline-step-order");
    let seen = monitor(&dir);
    let session = ProjectSession::open(spec(), state_in(&dir)).expect("되살린다");

    for entry in &seen.timeline {
        let cycle = session
            .project()
            .cycles()
            .nodes()
            .iter()
            .find(|cycle| cycle.id().to_ref() == entry.facts.cycle_ref)
            .expect("도메인에 있는 Cycle");
        let made: Vec<String> = cycle
            .steps()
            .nodes()
            .iter()
            .map(|node| cycle.step_ref(node.id).to_string())
            .collect();
        let shown: Vec<String> = entry.steps.iter().map(|s| s.step_ref.to_string()).collect();
        assert_eq!(shown, made, "{} 의 Step 순서가 다르다", entry.facts.cycle_ref);
    }
}

#[test]
fn the_past_and_the_abandoned_cycles_bring_their_steps_too() {
    let dir = reading_one("timeline-past-steps");
    let seen = monitor(&dir);

    // 계보 위의 조상(C1)도, 두고 온 실패 갈래(C2)도 Step 을 지니고 온다.
    for address in ["cycle:C1", "cycle:C2"] {
        let entry = seen
            .timeline
            .iter()
            .find(|entry| entry.facts.cycle_ref.to_string() == address)
            .unwrap_or_else(|| panic!("{address} 이 시간선에 없다"));
        assert!(!entry.steps.is_empty(), "{address} 의 Step 이 비었다");
    }
    // 그런데 Cycle 해상도의 계약은 그대로다 — 조상은 여전히 Step 을 지니지 못한다.
    let ancestor = &seen.active_lineage[0];
    assert_eq!(ancestor.cycle_ref.to_string(), "cycle:C1");
    // (타입에 `steps` 칸이 없으므로 이 줄이 컴파일되는 것 자체가 그 증거다.)
    let _: &gil::CycleFacts = ancestor;
}

#[test]
fn the_order_follows_structure_even_when_the_numbers_do_not() {
    // `reading_one` 은 C1 → C2(실패) → 되돌아가 C3. 계보는 [C1, C3] 이고 C2 는 그 사이의
    // 번호를 쓴다 — **번호로 정렬하면 C2 가 계보 한가운데로 끼어든다.**
    let dir = reading_one("timeline-not-by-number");
    let seen = monitor(&dir);
    let at = |address: &str| {
        seen.timeline
            .iter()
            .position(|entry| entry.facts.cycle_ref.to_string() == address)
            .unwrap_or_else(|| panic!("{address} 이 없다"))
    };
    // 구조가 정한 순서: 부모는 언제나 자식보다 먼저다.
    assert!(at("cycle:C1") < at("cycle:C2"), "부모가 자식보다 뒤에 있다");
    assert!(at("cycle:C1") < at("cycle:C3"), "부모가 자식보다 뒤에 있다");
    // 되돌아감의 출처도 새 시도보다 먼저다.
    assert!(at("cycle:C2") < at("cycle:C3"), "실패한 갈래가 새 시도보다 뒤에 있다");
    // 그리고 그 순서는 발급 순서이지 정렬한 결과가 아니다.
    let addresses: Vec<String> = seen.timeline.iter().map(|e| e.facts.cycle_ref.to_string()).collect();
    let mut sorted = addresses.clone();
    sorted.sort();
    assert_eq!(addresses, sorted, "이 시나리오에서는 우연히 같다 — 위 구조 단언이 본체다");
}

#[test]
fn a_summary_is_the_report_field_itself_not_a_retelling() {
    let dir = reading_one("timeline-summary-source");
    let seen = monitor(&dir);
    let session = ProjectSession::open(spec(), state_in(&dir)).expect("되살린다");

    // kind 마다 정해진 칸 하나에서 **원문 그대로** 온다.
    let field_of = |kind: NodeKind| -> Option<&'static str> {
        match kind {
            NodeKind::Question => Some("question"),
            NodeKind::Interpretation | NodeKind::Analysis => Some("interpretation"),
            NodeKind::Synthesis => Some("statement"),
            NodeKind::Define => Some("problem"),
            NodeKind::Hypothesis => Some("hypothesis"),
            NodeKind::Verify => Some("result"),
            NodeKind::Outcome => Some("lesson"),
            NodeKind::CycleEntry | NodeKind::CycleExit => None,
        }
    };
    let mut checked = 0usize;
    for entry in &seen.timeline {
        let cycle = session
            .project()
            .cycles()
            .nodes()
            .iter()
            .find(|cycle| cycle.id().to_ref() == entry.facts.cycle_ref)
            .expect("도메인에 있는 Cycle");
        for step in &entry.steps {
            let node = cycle
                .steps()
                .nodes()
                .iter()
                .find(|node| cycle.step_ref(node.id) == step.step_ref)
                .expect("도메인에 있는 Step");
            let expected = field_of(step.kind)
                .and_then(|field| node.report.as_ref()?.get(field))
                .map(str::to_string);
            assert_eq!(step.summary, expected, "{} 의 요약이 원문이 아니다", step.step_ref);
            if expected.is_some() {
                checked += 1;
            }
        }
    }
    assert!(checked >= 5, "요약이 있는 Step 을 충분히 보지 못했다: {checked}");

    // 그리고 그 값이 실제로 사람이 적은 그 문장이다.
    let define = seen
        .timeline
        .iter()
        .flat_map(|entry| &entry.steps)
        .find(|step| step.kind == NodeKind::Define && step.summary.is_some())
        .expect("닫힌 Define");
    assert!(
        define.summary.as_deref() == Some(FAILED_PROBLEM)
            || define.summary.as_deref() == Some(NEW_PROBLEM),
        "{:?}",
        define.summary
    );
}

#[test]
fn an_open_step_has_no_summary_yet() {
    let dir = reading_one("timeline-open-step");
    let seen = monitor(&dir);
    let open: Vec<&gil::StepFacts> = seen
        .timeline
        .iter()
        .flat_map(|entry| &entry.steps)
        .filter(|step| step.state == gil::NodeStatus::Open)
        .collect();
    assert!(!open.is_empty(), "이 시나리오에는 열린 Verify 가 있다");
    for step in open {
        assert_eq!(step.summary, None, "{} 가 닫히기 전에 요약을 지녔다", step.step_ref);
    }
    // 경계 표식도 Report 를 지니지 않는다.
    for step in seen.timeline.iter().flat_map(|entry| &entry.steps) {
        if matches!(step.kind, NodeKind::CycleEntry | NodeKind::CycleExit) {
            assert_eq!(step.summary, None, "경계가 요약을 지녔다");
        }
    }
}

#[test]
fn a_long_summary_survives_whole_in_the_read_model() {
    let dir = bare("timeline-long-summary");
    write(&dir, "work.txt", "처음");
    let long = "가".repeat(3000);
    let mut session = ProjectSession::start(spec(), state_in(&dir)).expect("시작한다");
    *session.project_mut() = bootstrap_from(session.project().clone());
    opened(session.project_mut(), NodeKind::Define);
    let rules = spec();
    session
        .close_step(
            full_report(&rules, CycleKind::Experiment, NodeKind::Define)
                .with("problem", long.clone())
                .with("success_condition", "짧다"),
        )
        .expect("문제를 고정한다");
    session.commit().expect("눕힌다");
    drop(session);

    let seen = monitor(&dir);
    let define = seen
        .timeline
        .iter()
        .flat_map(|entry| &entry.steps)
        .find(|step| step.kind == NodeKind::Define)
        .expect("Define");
    // **read model 은 자르지 않는다.** 자르는 것은 그리는 쪽의 일이다.
    assert_eq!(define.summary.as_deref(), Some(long.as_str()), "원문이 잘렸다");
}

#[test]
fn the_timeline_writes_nothing_and_leaves_no_lock() {
    let dir = reading_one("timeline-costs-nothing");
    let before = fs::read(state_in(&dir)).expect("상태를 읽는다");
    let world_before = fs::read(dir.join("work.txt")).ok();

    // (훑기 횟수 자체는 crate 안의 계수기가 잰다 —
    //  `monitor::tests::the_timeline_costs_no_extra_look`.)
    let session = ProjectSession::open(spec(), state_in(&dir)).expect("되살린다");
    let seen = session.monitor().expect("Snapshot");
    drop(session);

    assert!(!seen.timeline.is_empty(), "시간선이 비었다");
    // 아무것도 쓰지 않았다.
    assert_eq!(before, fs::read(state_in(&dir)).expect("다시 읽는다"), "상태가 바뀌었다");
    assert_eq!(world_before, fs::read(dir.join("work.txt")).ok(), "작업 파일이 바뀌었다");
    // 그리고 잠금이 남지 않았다.
    assert!(ProjectSession::open(spec(), state_in(&dir)).is_ok(), "잠금이 남았다");
}

#[test]
fn the_plain_text_does_not_unroll_the_timeline() {
    // 새 칸이 생겼다고 글 화면이 전체 history 가 되지 않는다.
    let dir = reading_one("timeline-text-unchanged");
    let seen = monitor(&dir);
    let plain = rendered(&dir);

    // 글 화면이 적는 Step 은 **서 있는 자리 하나뿐**이다.
    let here = seen.current_step.as_ref().expect("열린 자리").step_ref.to_string();
    assert!(plain.contains(&here), "서 있는 자리가 없다:\n{plain}");

    // 시간선의 **다른 모든 Step 은 한 줄도 나오지 않는다** — 지금 Cycle 의 지나간
    // Step 도, 과거 Cycle 의 Step 도. 새 칸이 글 화면을 전체 history 로 만들지 않았다.
    let mut hidden = 0usize;
    for step in seen.timeline.iter().flat_map(|entry| &entry.steps) {
        let address = step.step_ref.to_string();
        if address == here {
            continue;
        }
        assert!(
            !plain.contains(&address),
            "글 화면이 Step {address} 를 늘어놓았다"
        );
        hidden += 1;
    }
    assert!(hidden >= 8, "감춰진 Step 이 너무 적어 이 시험이 잡는 것이 없다: {hidden}");

    // (글 화면이 새 칸을 아예 읽지 않는다는 것은 lib 시험이 바이트로 잰다 —
    //  `monitor::text::tests::the_text_never_reads_the_timeline`.)
}

// ── ⑦ 그림과 목록 — 같은 사실의 두 표현 ──────────────────────────────────

/// `<style>` 안의 규칙 하나를 잘라 낸다.
fn rule_of(html: &str, selector: &str) -> String {
    let style = html
        .split("<style>")
        .nth(1)
        .and_then(|rest| rest.split("</style>").next())
        .expect("stylesheet");
    let at = style
        .find(selector)
        .unwrap_or_else(|| panic!("{selector} 규칙이 없다"));
    let rest = &style[at..];
    let end = rest.find('}').map(|end| end + 1).unwrap_or(rest.len());
    rest[..end].to_string()
}

#[test]
fn the_wide_screen_shows_the_picture_and_folds_the_list_away_from_sight_only() {
    let dir = reading_one("two-shapes-wide");
    let html = html_of(&dir);

    // 둘 다 문서 안에 있다.
    assert!(html.contains("<svg class=\"graph\""), "그림이 없다");
    assert!(html.contains("<div class=\"for-readers\">"), "목록 감싸개가 없다");
    assert!(html.contains("<ol class=\"legend\">"), "목록이 없다");

    // 목록은 **눈에서만** 접힌다 — 접근성 나무에서 사라지지 않는다.
    let folded = rule_of(&html, ".for-readers {");
    assert!(folded.contains("position: absolute"), "{folded}");
    assert!(folded.contains("clip-path: inset(50%)"), "{folded}");
    assert!(!folded.contains("display: none"), "접근성까지 지웠다: {folded}");
    assert!(!folded.contains("visibility: hidden"), "접근성까지 지웠다: {folded}");
    // **속성**을 찾는다 — 주석에 적힌 낱말이 아니라.
    assert!(!html.contains("aria-hidden=\""), "aria-hidden 으로 지웠다");
    assert!(!html.contains(" hidden>") && !html.contains(" hidden=\""), "hidden 속성을 썼다");
}

#[test]
fn the_narrow_screen_hides_the_picture_and_reads_the_list_at_full_size() {
    let dir = reading_one("two-shapes-narrow");
    let html = html_of(&dir);

    // 전환은 media query 하나다.
    let narrow = html
        .split("@media (max-width: 699px)")
        .nth(1)
        .expect("좁은 화면 규칙이 없다");
    let block = &narrow[..narrow.find("\n}").map(|end| end + 2).unwrap_or(narrow.len())];
    assert!(block.contains("svg.graph { display: none; }"), "그림을 숨기지 않는다: {block}");
    assert!(block.contains("position: static"), "목록을 되돌리지 않는다: {block}");
    assert!(block.contains("clip-path: none"), "목록이 접힌 채로 남는다: {block}");
    // 본문 크기로 읽힌다 — 목록에 따로 줄인 글씨를 주지 않는다.
    assert!(!block.contains("font-size: 0.7"), "좁은 화면에서 더 줄였다: {block}");

    // 그리고 이 전환에 JavaScript 가 한 조각도 쓰이지 않는다.
    assert!(!html.contains("<script"), "JavaScript 가 들어왔다");
    assert!(!html.contains("onclick") && !html.contains("onload"), "사건 처리기가 들어왔다");
    assert!(!html.contains("@media (min-width"), "두 방향 규칙이 섞였다");
}

#[test]
fn both_shapes_carry_the_same_step_facts() {
    let dir = reading_one("two-shapes-same-facts");
    let seen = monitor(&dir);
    let html = html_of(&dir);
    let picture = html
        .split("<section class=\"picture\">")
        .nth(1)
        .and_then(|rest| rest.split("</section>").next())
        .expect("그림 절")
        .to_string();
    let svg = picture
        .split("<svg")
        .nth(1)
        .and_then(|rest| rest.split("</svg>").next())
        .expect("그림")
        .to_string();
    let list = picture
        .split("<div class=\"for-readers\">")
        .nth(1)
        .expect("목록")
        .to_string();

    // 두 표현이 **같은 Step 집합**을 말한다.
    for step in seen.timeline.iter().flat_map(|entry| &entry.steps) {
        let address = step.step_ref.to_string();
        assert!(svg.contains(&address), "그림에 {address} 가 없다");
        assert!(list.contains(&address), "목록에 {address} 가 없다");
    }
    // 같은 Cycle 집합과 같은 판정도.
    for entry in &seen.timeline {
        let address = entry.facts.cycle_ref.to_string();
        assert!(svg.contains(&address) || list.contains(&address), "{address} 가 없다");
    }
    for word in ["현재", "성공", "실패", "열림"] {
        assert!(svg.contains(word), "그림에 {word} 이 없다");
        assert!(list.contains(word), "목록에 {word} 이 없다");
    }
    // 되돌아감의 유래도 둘 다에.
    assert!(svg.contains("다시 시도") && list.contains("다시 시도"), "유래가 한쪽에만 있다");
}

#[test]
fn no_angle_bracket_placeholder_reaches_either_shape() {
    let dir = reading_one("two-shapes-no-placeholder");
    let html = html_of(&dir);
    let picture = html
        .split("<section class=\"picture\">")
        .nth(1)
        .and_then(|rest| rest.split("</section>").next())
        .expect("그림 절")
        .to_string();

    // `full_report` 가 채워 넣는 자리표시들 — 그림에도 목록에도 없다.
    for fake in ["question&gt;", "hypothesis&gt;", "result&gt;", "statement&gt;", "&lt;"] {
        assert!(!picture.contains(fake), "자리표시 {fake} 가 화면에 실렸다");
    }
    // 그러나 Step 은 전부 남아 있다.
    let seen = monitor(&dir);
    for step in seen.timeline.iter().flat_map(|entry| &entry.steps) {
        assert!(picture.contains(&step.step_ref.to_string()), "{} 가 사라졌다", step.step_ref);
    }
    // 그리고 **진짜 요약은 그대로 보인다.**
    assert!(picture.contains(FAILED_PROBLEM.chars().take(20).collect::<String>().as_str()),
        "진짜 요약이 사라졌다");
}

// ── ⑧ 시간선이 Cycle 의 사실을 함께 지닌다 ────────────────────────────────

#[test]
fn each_timeline_entry_carries_the_very_same_cycle_facts() {
    let dir = reading_one("timeline-same-facts");
    let seen = monitor(&dir);

    // 같은 Cycle 의 사실이 두 자리에 있으면 **같은 값**이어야 한다 — 같은 함수가 지었다.
    for entry in &seen.timeline {
        let address = entry.facts.cycle_ref.to_string();
        let elsewhere = seen
            .active_lineage
            .iter()
            .find(|facts| facts.cycle_ref.to_string() == address)
            .cloned()
            .or_else(|| {
                seen.inactive_cycles
                    .iter()
                    .find(|cycle| cycle.cycle_ref.to_string() == address)
                    .map(|cycle| gil::CycleFacts {
                        cycle_ref: cycle.cycle_ref,
                        kind: cycle.kind,
                        state: cycle.state,
                        parent_cycle_ref: cycle.parent_cycle_ref,
                        revisit_from_cycle_ref: cycle.revisit_from_cycle_ref,
                        // 계보 밖 목록은 정의를 지니지 않는다 — 그 칸만 견주지 않는다.
                        experiment_definition: entry.facts.experiment_definition.clone(),
                        report: cycle.report.clone(),
                    })
            })
            .unwrap_or_else(|| panic!("{address} 이 두 목록 어디에도 없다"));
        assert_eq!(entry.facts, elsewhere, "{address} 의 사실이 두 자리에서 다르다");
    }
}

#[test]
fn the_four_relations_are_exclusive_and_each_cycle_wears_exactly_one() {
    // `three_relations` 는 C1(계보) · C2(버림) · C3(그 밖) · C4(되돌아감 출처) · C5(지금).
    let dir = three_relations("timeline-four-relations");
    let seen = monitor(&dir);

    let relation = |address: &str| {
        seen.timeline
            .iter()
            .find(|entry| entry.facts.cycle_ref.to_string() == address)
            .unwrap_or_else(|| panic!("{address} 이 시간선에 없다"))
            .relation_to_current
    };
    assert_eq!(relation("cycle:C1"), TimelineRelation::ActivePath, "뿌리가 계보 밖이다");
    assert_eq!(relation("cycle:C2"), TimelineRelation::Abandoned);
    assert_eq!(relation("cycle:C3"), TimelineRelation::Other);
    assert_eq!(relation("cycle:C4"), TimelineRelation::RevisitSource);
    assert_eq!(relation("cycle:C5"), TimelineRelation::ActivePath, "지금 Cycle 이 계보 밖이다");

    // **한 Cycle 은 한 번만, 한 관계만.** 타입이 칸 하나라 둘을 동시에 지닐 수 없고,
    // 시간선에도 한 번만 나온다.
    let mut seen_once: Vec<String> = seen
        .timeline
        .iter()
        .map(|entry| entry.facts.cycle_ref.to_string())
        .collect();
    let before = seen_once.len();
    seen_once.sort();
    seen_once.dedup();
    assert_eq!(seen_once.len(), before, "한 Cycle 이 시간선에 두 번 나왔다");

    // 계보 위의 것은 전부 ActivePath 이고, 그 밖은 하나도 ActivePath 가 아니다.
    for facts in &seen.active_lineage {
        assert_eq!(relation(&facts.cycle_ref.to_string()), TimelineRelation::ActivePath);
    }
    for cycle in &seen.inactive_cycles {
        assert_ne!(
            relation(&cycle.cycle_ref.to_string()),
            TimelineRelation::ActivePath,
            "{} 이 계보 밖인데 활성이라고 한다",
            cycle.cycle_ref
        );
    }
}

#[test]
fn the_timeline_relation_and_the_inactive_relation_never_disagree() {
    // 두 값이 같은 함수에서 나온다 — 한쪽만 낡을 수 없다는 것을 여기서 잰다.
    let dir = three_relations("timeline-relations-agree");
    let seen = monitor(&dir);
    let mut checked = 0usize;
    for cycle in &seen.inactive_cycles {
        let entry = seen
            .timeline
            .iter()
            .find(|entry| entry.facts.cycle_ref == cycle.cycle_ref)
            .expect("시간선에 있다");
        let expected = match cycle.relation_to_current {
            CycleRelation::RevisitSource => TimelineRelation::RevisitSource,
            CycleRelation::Abandoned => TimelineRelation::Abandoned,
            CycleRelation::Other => TimelineRelation::Other,
        };
        assert_eq!(entry.relation_to_current, expected, "{} 에서 갈렸다", cycle.cycle_ref);
        checked += 1;
    }
    assert!(checked >= 3, "세 관계를 다 보지 못했다: {checked}");
}

#[test]
fn whether_a_cycle_is_the_current_one_is_read_from_the_current_reference() {
    // 시간선은 「지금인가」를 적어 두지 않는다. **하나의 자리**가 그것을 말한다.
    let dir = reading_one("timeline-current-derived");
    let seen = monitor(&dir);
    let here = &seen.current_cycle.facts.cycle_ref;
    let matched: Vec<&gil::TimelineCycleFacts> = seen
        .timeline
        .iter()
        .filter(|entry| &entry.facts.cycle_ref == here)
        .collect();
    assert_eq!(matched.len(), 1, "지금 Cycle 이 시간선에 하나가 아니다");
    assert_eq!(matched[0].relation_to_current, TimelineRelation::ActivePath);
    // 그리고 그 항목의 사실이 `current_cycle` 의 것과 같다.
    assert_eq!(matched[0].facts, seen.current_cycle.facts);
}

// ── ⑨ 고른 Step 하나의 상세 ──────────────────────────────────────────────

use gil::{DetailError, decode_detail_v1, encode_detail_v1, monitor_view_v1};

fn detail(dir: &Path, address: &str) -> Result<gil::NodeDetailV1, DetailError> {
    let session = ProjectSession::open(spec(), state_in(dir)).expect("되살린다");
    session.node_detail_v1(address.parse().expect("주소"))
}

#[test]
fn a_closed_step_brings_every_report_field_in_name_order() {
    let dir = reading_one("detail-name-order");
    let one = detail(&dir, "step:C2/S1").expect("닫힌 Define");

    assert_eq!(one.schema_version, 1);
    assert_eq!(one.step_ref, "step:C2/S1");
    assert_eq!(one.cycle_ref, "cycle:C2", "담긴 Cycle 이 아니다");
    assert_eq!(one.kind, gil::StepKindV1::Define);
    assert_eq!(one.state, gil::NodeStateV1::Closed);

    let report = one.report.as_ref().expect("닫힌 Step 은 Report 를 지닌다");
    let names: Vec<&str> = report.fields.iter().map(|at| at.name.as_str()).collect();
    let mut sorted = names.clone();
    sorted.sort_unstable();
    assert_eq!(names, sorted, "이름순이 아니다: {names:?}");
    assert!(names.contains(&"problem") && names.contains(&"success_condition"), "{names:?}");

    // 값이 원문 그대로다 — 도메인에서 직접 읽어 견준다.
    let session = ProjectSession::open(spec(), state_in(&dir)).expect("되살린다");
    let cycle = session
        .project()
        .cycles()
        .nodes()
        .iter()
        .find(|cycle| cycle.id().to_ref().to_string() == "cycle:C2")
        .expect("Cycle");
    let node = cycle
        .steps()
        .nodes()
        .iter()
        .find(|node| cycle.step_ref(node.id).to_string() == "step:C2/S1")
        .expect("Step");
    let truth = node.report.as_ref().expect("Report");
    assert_eq!(report.fields.len(), truth.field_names().count(), "칸 수가 다르다");
    for field in &report.fields {
        assert_eq!(Some(field.value.as_str()), truth.get(&field.name), "{} 의 값", field.name);
    }
}

#[test]
fn an_open_step_has_no_report_at_all() {
    let dir = reading_one("detail-open-step");
    let one = detail(&dir, "step:C3/S3").expect("열린 Verify");
    assert_eq!(one.state, gil::NodeStateV1::Open);
    assert_eq!(one.report, None, "닫히기 전에 Report 를 지어냈다");
    // 그래도 나머지 사실은 있다.
    assert_eq!(one.kind, gil::StepKindV1::Verify);
    assert_eq!(one.cycle_ref, "cycle:C3");
}

#[test]
fn a_boundary_is_never_a_step_so_it_is_simply_not_found() {
    // 경계(`cycle_entry`·`cycle_exit`)는 Step 이 아니다 — `Walk::open` 이 거절하므로
    // `Walk::nodes()` 에 들어갈 수 없다. 따라서 그것을 가리키는 StepRef 도 없다.
    let dir = reading_one("detail-boundary");
    let session = ProjectSession::open(spec(), state_in(&dir)).expect("되살린다");
    for cycle in session.project().cycles().nodes() {
        for node in cycle.steps().nodes() {
            assert!(
                !matches!(node.kind, NodeKind::CycleEntry | NodeKind::CycleExit),
                "경계가 Step 으로 저장돼 있다: {}",
                cycle.step_ref(node.id)
            );
        }
    }
    drop(session);
    // 그래서 상세 조회에서 경계는 「없음」으로만 나타난다.
    assert!(matches!(detail(&dir, "step:C1/S99"), Err(DetailError::NotFound { .. })));
}

#[test]
fn a_step_in_a_cycle_that_does_not_exist_is_refused() {
    let dir = reading_one("detail-no-cycle");
    assert_eq!(
        detail(&dir, "step:C99/S1"),
        Err(DetailError::NotFound { step_ref: "step:C99/S1".to_string() }),
        "없는 Cycle 의 Step 을 찾아 줬다"
    );
}

#[test]
fn a_missing_step_in_a_real_cycle_is_refused() {
    let dir = reading_one("detail-no-step");
    assert_eq!(
        detail(&dir, "step:C2/S99"),
        Err(DetailError::NotFound { step_ref: "step:C2/S99".to_string() }),
        "없는 Step 을 찾아 줬다"
    );
}

#[test]
fn the_same_bare_step_number_in_another_cycle_is_never_a_fallback() {
    // C1/S1 · C2/S1 · C3/S1 이 모두 있다. 청한 것만 답해야 한다.
    let dir = reading_one("detail-no-fallback");
    let kinds = [
        ("step:C1/S1", "cycle:C1", gil::StepKindV1::Question),
        ("step:C2/S1", "cycle:C2", gil::StepKindV1::Define),
        ("step:C3/S1", "cycle:C3", gil::StepKindV1::Define),
    ];
    for (address, cycle, kind) in kinds {
        let one = detail(&dir, address).unwrap_or_else(|_| panic!("{address}"));
        assert_eq!(one.step_ref, address, "다른 Step 으로 물러섰다");
        assert_eq!(one.cycle_ref, cycle, "다른 Cycle 로 물러섰다");
        assert_eq!(one.kind, kind);
    }
    // 셋이 실제로 서로 다른 사실이다 — 아니면 이 시험이 아무것도 재지 않는다.
    let first = detail(&dir, "step:C1/S1").expect("C1");
    let second = detail(&dir, "step:C2/S1").expect("C2");
    assert_ne!(first.report, second.report);
}

#[test]
fn a_field_the_grammar_does_not_name_still_arrives_under_its_own_name() {
    let dir = bare("detail-extra-field");
    write(&dir, "work.txt", "처음");
    let mut session = ProjectSession::start(spec(), state_in(&dir)).expect("시작한다");
    *session.project_mut() = bootstrap_from(session.project().clone());
    // **주소를 손으로 적지 않는다.** 앞선 bootstrap 이 이미 Step 을 몇 개 만들었다.
    let define = opened(session.project_mut(), NodeKind::Define);
    let rules = spec();
    session
        .close_step(
            full_report(&rules, CycleKind::Experiment, NodeKind::Define)
                .with("problem", "무엇이 문제인가")
                .with("success_condition", "무엇이면 성공인가")
                // 문법이 요구하지 않는 칸.
                .with("zz_extra", "문법에 없는 칸")
                .with("aa_extra", "이름순에서 맨 앞"),
        )
        .expect("문제를 고정한다");
    session.commit().expect("눕힌다");
    drop(session);

    let one = detail(&dir, &define.to_string()).expect("Define");
    let report = one.report.as_ref().expect("Report");
    let names: Vec<&str> = report.fields.iter().map(|at| at.name.as_str()).collect();
    assert!(names.contains(&"zz_extra") && names.contains(&"aa_extra"), "{names:?}");
    assert_eq!(names.first(), Some(&"aa_extra"), "이름순이 아니다: {names:?}");
    assert_eq!(names.last(), Some(&"zz_extra"), "이름순이 아니다: {names:?}");
    let value = |name: &str| {
        report.fields.iter().find(|at| at.name == name).map(|at| at.value.as_str())
    };
    assert_eq!(value("zz_extra"), Some("문법에 없는 칸"), "원문이 바뀌었다");
}

#[test]
fn a_nasty_report_value_round_trips_through_json_exactly() {
    let dir = bare("detail-nasty-json");
    write(&dir, "work.txt", "처음");
    let nasty = "따옴표 \" 역슬래시 \\ 줄바꿈 \n 탭 \t <script>alert(1)</script> & < >";
    let mut session = ProjectSession::start(spec(), state_in(&dir)).expect("시작한다");
    *session.project_mut() = bootstrap_from(session.project().clone());
    let define = opened(session.project_mut(), NodeKind::Define);
    let rules = spec();
    session
        .close_step(
            full_report(&rules, CycleKind::Experiment, NodeKind::Define)
                .with("problem", nasty)
                .with("success_condition", "가"),
        )
        .expect("문제를 고정한다");
    session.commit().expect("눕힌다");
    drop(session);

    let one = detail(&dir, &define.to_string()).expect("Define");
    let text = encode_detail_v1(&one).expect("옮긴다");
    let back = decode_detail_v1(&text).expect("되읽는다");
    assert_eq!(back, one, "왕복이 사실을 바꿨다");
    assert_eq!(encode_detail_v1(&back).expect("다시"), text, "왕복이 글자를 바꿨다");

    let value = back
        .report
        .expect("Report")
        .fields
        .into_iter()
        .find(|at| at.name == "problem")
        .expect("problem")
        .value;
    assert_eq!(value, nasty, "원문이 바뀌었다");
    // JSON escaping 만 했다 — HTML 로 바꾸지 않았다.
    assert!(text.contains("<script>") && !text.contains("&lt;"), "HTML escape 를 했다");
    assert!(text.contains("\\n") && text.contains("\\t") && text.contains("\\\""), "{text}");
}

#[test]
fn the_detail_json_follows_the_same_canonical_rules() {
    let dir = reading_one("detail-json-rules");
    let open = detail(&dir, "step:C3/S3").expect("열린 Step");
    let text = encode_detail_v1(&open).expect("옮긴다");

    assert!(text.contains("\"schema_version\":1"), "{text}");
    // 없는 Report 는 key 생략이 아니라 `null`.
    assert!(text.contains("\"report\":null"), "{text}");
    assert!(!text.contains('\n') && !text.contains(": "), "compact 가 아니다");
    // 모르는 칸은 지나친다.
    let widened = text.replacen("{\"schema_version\":1", "{\"tomorrow\":[1],\"schema_version\":1", 1);
    assert_eq!(decode_detail_v1(&widened).expect("지나친다"), open);
    // 모르는 판과 모르는 낱말은 거절한다.
    for found in [0u32, 2] {
        let other = text.replacen("\"schema_version\":1", &format!("\"schema_version\":{found}"), 1);
        assert!(decode_detail_v1(&other).is_err(), "판 {found} 을 읽었다");
    }
    let twisted = text.replacen("\"verify\"", "\"validate\"", 1);
    assert_ne!(twisted, text);
    assert!(decode_detail_v1(&twisted).is_err(), "모르는 낱말을 받아들였다");

    // 빈 배열은 `[]` — 칸이 없는 Report 라면.
    let empty = gil::NodeDetailV1 {
        report: Some(gil::ReportV1 { fields: vec![] }),
        ..open
    };
    assert!(encode_detail_v1(&empty).expect("옮긴다").contains("\"fields\":[]"));
}

#[test]
fn asking_for_a_detail_changes_nothing_and_observes_nothing_new() {
    let dir = reading_one("detail-read-only");
    let state = fs::read(state_in(&dir)).expect("상태를 읽는다");
    let work = fs::read(dir.join("work.txt")).ok();
    let objects = || {
        fn count(at: &Path) -> usize {
            fs::read_dir(at)
                .map(|entries| {
                    entries
                        .flatten()
                        .map(|one| match one.path().is_dir() {
                            true => count(&one.path()),
                            false => 1,
                        })
                        .sum()
                })
                .unwrap_or(0)
        }
        count(&dir.join(".gil/artifacts"))
    };
    let before = objects();
    let world_before = monitor(&dir).world.state;

    // 여러 번 물어도.
    for address in ["step:C1/S1", "step:C2/S3", "step:C3/S1", "step:C3/S3"] {
        assert!(detail(&dir, address).is_ok(), "{address}");
    }

    assert_eq!(state, fs::read(state_in(&dir)).expect("다시 읽는다"), "상태가 바뀌었다");
    assert_eq!(work, fs::read(dir.join("work.txt")).ok(), "작업 파일이 바뀌었다");
    assert_eq!(before, objects(), "창고에 객체가 늘었다");
    assert_eq!(world_before, monitor(&dir).world.state, "세계 상태가 바뀌었다");
    // 그리고 잠금이 남지 않았다.
    assert!(ProjectSession::open(spec(), state_in(&dir)).is_ok(), "잠금이 남았다");
}

#[test]
fn the_initial_view_still_carries_no_full_report() {
    let dir = reading_one("detail-view-stays-thin");
    let seen = monitor(&dir);
    let view = monitor_view_v1(&seen).expect("View");
    // Verify 를 고른다 — 그 Report 의 칸 이름은 초기 View 어디에도 나타나지 않는다.
    // (`problem`·`success_condition` 은 `experiment_definition` 으로, `verdict` 는 Cycle
    //  Report 로 **정당하게** 실리므로 그 셋으로는 이 규칙을 잴 수 없다.)
    let one = detail(&dir, "step:C2/S3").expect("닫힌 Verify");
    let report = one.report.as_ref().expect("Report");
    let hidden: Vec<&str> = report.fields.iter().map(|at| at.name.as_str()).collect();
    assert!(hidden.len() >= 2, "감춰진 칸이 너무 적다: {hidden:?}");

    let text = gil::encode_view_v1(&view).expect("옮긴다");
    for name in &hidden {
        assert!(
            !text.contains(&format!("\"{name}\":")),
            "초기 View 에 {name} 이 칸으로 실렸다"
        );
    }
    // View 의 Step 은 여전히 네 사실뿐이고, 대표 칸 한 줄만 지닌다.
    let step = view.timeline[1].steps.iter().find(|at| at.step_ref == "step:C2/S3").expect("Step");
    assert!(step.summary.is_some(), "대표 칸 한 줄은 있다");
    let value = |name: &str| {
        report.fields.iter().find(|at| at.name == name).map(|at| at.value.clone())
    };
    assert_eq!(step.summary, value("result"), "요약이 대표 칸의 원문이 아니다");
    assert_ne!(step.summary, value("execution"), "다른 칸을 요약으로 실었다");
}

#[test]
fn a_boundary_shaped_address_that_does_not_exist_is_still_not_found() {
    // 경계는 Step 이 아니므로 그것을 가리키는 주소도 없다. 「경계라서 거절」이 아니라
    // **「그런 Step 이 없다」**가 정확한 답이다.
    let dir = reading_one("detail-boundary-shaped");
    for address in ["step:C1/S1000", "step:C2/S999", "step:C3/S1000"] {
        assert_eq!(
            detail(&dir, address),
            Err(DetailError::NotFound { step_ref: address.to_string() }),
            "{address}"
        );
    }
    // 그리고 실제 Step 의 종류는 전부 여덟 중 하나다 — 경계가 새어 나오지 않는다.
    let seen = monitor(&dir);
    let view = monitor_view_v1(&seen).expect("View");
    let eight = [
        gil::StepKindV1::Question, gil::StepKindV1::Interpretation, gil::StepKindV1::Synthesis,
        gil::StepKindV1::Define, gil::StepKindV1::Hypothesis, gil::StepKindV1::Verify,
        gil::StepKindV1::Analysis, gil::StepKindV1::Outcome,
    ];
    assert_eq!(eight.len(), 8);
    let mut counted = 0usize;
    for one in &view.timeline {
        for step in &one.steps {
            assert!(eight.contains(&step.kind), "{} 가 여덟 밖이다", step.step_ref);
            counted += 1;
        }
        for step in &one.steps {
            let detailed = detail(&dir, &step.step_ref).expect("있는 Step");
            assert_eq!(detailed.kind, step.kind, "{} 의 종류가 두 자리에서 다르다", step.step_ref);
        }
    }
    assert!(counted >= 10, "본 Step 이 너무 적다: {counted}");
}
