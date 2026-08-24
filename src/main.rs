//! `gil` — 걷기를 부를 수 있게 하는 가장 얇은 표면.
//!
//! 여기에는 규칙도 판정도 없다. 하는 일은 셋뿐이다: 저장된 것을 세우고, 라이브러리에
//! 한 수를 넘기고, 결과를 사람의 말로 적는다. 거절의 이유도 라이브러리의 말을 그대로 옮긴다 —
//! 여기서 다시 쓰면 같은 판정이 두 자리에서 서로 다르게 말하게 된다.

use std::io::{self, IsTerminal, Read};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use gil::{
    ActionContract, CloseContract, CycleKind, NodeKind, Project, Report, RuleSet, StoreError,
    context, load, next_moves, save, story,
};

fn main() -> ExitCode {
    match run() {
        Ok(text) => {
            print!("{text}");
            ExitCode::SUCCESS
        }
        Err(message) => {
            eprintln!("{message}");
            ExitCode::FAILURE
        }
    }
}

fn run() -> Result<String, String> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let command = args.first().map(String::as_str).unwrap_or("--help");

    match command {
        "--help" | "-h" | "help" => Ok(help()),
        "--version" | "-V" | "version" => Ok(format!("gil {}\n", env!("CARGO_PKG_VERSION"))),
        "start" => start(),
        // **`--help` 는 요청이 아니다.** stdin 없는 실제 Open·Close 로 읽으면, 계약을
        // 물어본 사람이 빈 Report 를 낸 것으로 거절당한다(실사용 M2C 보고).
        "open" if asks_for_help(args.get(1)) => open_help(),
        "close" if asks_for_help(args.get(1)) => close_help(),
        "open" => open(args.get(1)),
        "close" => close(),
        "revisit" => revisit(),
        "status" => status(),
        "story" => Ok(story(open_session()?.project.cycles())),
        "context" => Ok(context(&open_session()?.project)),
        "cycle" => cycle(args.get(1).map(String::as_str), args.get(2)),
        other => Err(format!(
            "{other:?} 는 gil 이 아는 명령이 아니다.\n\n{}",
            help()
        )),
    }
}

/// 도움말을 물은 것인가 — 여는·닫는 요청이 아니라.
fn asks_for_help(argument: Option<&String>) -> bool {
    matches!(
        argument.map(String::as_str),
        Some("--help" | "-h" | "help")
    )
}

/// 지금 이어 걷고 있는 Cycle Graph — 그리고 **그것이 어느 파일인지**.
///
/// 자리를 함께 들고 다닌다. 읽은 파일과 쓰는 파일이 갈리면 적은 것이 다른 데로 간다.
struct Session {
    project: Project,
    path: PathBuf,
}

/// 저장된 것이 어디에 있는가 — 그리고 그것이 이 gil 이 읽는 형식인가.
enum Found {
    State(PathBuf),
    /// 앞 형식의 파일. 읽지 않지만 **있다는 사실은 말한다.**
    Legacy(PathBuf),
}

/// 여기서 위로 거슬러 오르며 **가장 가까운** 저장을 찾는다.
///
/// Agent 는 소스·시험·하위 패키지 폴더를 계속 오간다. 서 있는 자리에서만 찾으면 명령마다
/// 뿌리로 돌아가야 하고, 잊으면 **같은 프로젝트에 두 번째 기록이 조용히 생긴다**
/// (실사용 보고 #125).
fn find_gil() -> Result<Option<Found>, String> {
    let here = std::env::current_dir().map_err(|err| format!("지금 어디인지 알 수 없다: {err}"))?;
    for dir in here.ancestors() {
        let state = dir.join(gil::STATE_PATH);
        if state.exists() {
            return Ok(Some(Found::State(state)));
        }
        // 같은 `.gil` 안에 앞 형식만 있는 경우다. 위로 더 올라가기 전에 여기서 멈춘다 —
        // 조용히 지나치면 사람은 제 기록이 사라진 줄 안다.
        let legacy = dir.join(gil::LEGACY_WALK_PATH);
        if legacy.exists() {
            return Ok(Some(Found::Legacy(legacy)));
        }
    }
    Ok(None)
}

/// 여기에 새로 눕힐 자리. **언제나 온전한 경로다** — 반쪽 경로는 서 있는 자리에 따라
/// 다른 것을 가리킨다.
fn state_path_here() -> Result<PathBuf, String> {
    let here = std::env::current_dir().map_err(|err| format!("지금 어디인지 알 수 없다: {err}"))?;
    Ok(here.join(gil::STATE_PATH))
}

/// 이 기록이 서 있는 자리가 아닌 곳에 누워 있는가.
fn found_above(path: &Path) -> bool {
    match state_path_here() {
        Ok(here) => path != here,
        Err(_) => false,
    }
}

fn rules() -> Result<RuleSet, String> {
    RuleSet::builtin().map_err(|err| format!("함께 실린 명세를 읽지 못했다: {err}"))
}

fn open_session() -> Result<Session, String> {
    let path = match find_gil()? {
        Some(Found::State(path)) => path,
        Some(Found::Legacy(path)) => {
            return Err(StoreError::LegacyFormat {
                path: path.display().to_string(),
            }
            .to_string());
        }
        None => {
            return Err(format!(
                "여기서도 그 위 어디에서도 걷기를 못 찾았다 ({}) — `gil start` 로 시작한다",
                gil::STATE_PATH
            ));
        }
    };

    let project = load(rules()?, &path).map_err(|err| match err {
        // 방금 있는 것을 보고 왔다. 그새 사라졌다면 그건 다른 이야기다.
        StoreError::NotFound { .. } => format!("저장된 것이 사라졌다: {}", path.display()),
        other => other.to_string(),
    })?;
    Ok(Session { project, path })
}

impl Session {
    /// 읽어 온 **그 파일**에 도로 눕힌다.
    fn write(&self) -> Result<(), String> {
        save(&self.project, &self.path).map_err(|err| err.to_string())
    }
}

// ── 명령 ───────────────────────────────────────────────────────────────────

fn start() -> Result<String, String> {
    // 위에 이미 기록이 있으면 여기서 새로 시작하지 않는다 — 그러면 한 프로젝트에
    // 기록이 둘이 되고, 어느 쪽에 적히는지는 서 있는 자리가 정하게 된다.
    match find_gil()? {
        Some(Found::State(existing)) => {
            return Err(refusal(
                "여기서 새로 시작할 수 없다.",
                &format!("이미 걷고 있다 ({}).", existing.display()),
                "여기서 따로 시작하면 한 프로젝트에 기록이 둘이 된다.\n\
                 정말 다시 시작하려면 그 파일을 직접 치워라 — gil 은 적힌 사고를 지우지 않는다.",
                "gil status",
            ));
        }
        Some(Found::Legacy(path)) => {
            return Err(StoreError::LegacyFormat {
                path: path.display().to_string(),
            }
            .to_string());
        }
        None => {}
    }

    let session = Session {
        project: Project::start(rules()?),
        path: state_path_here()?,
    };
    session.write()?;

    let cycle = session.project.cycles().current();
    Ok(format!(
        "프로젝트를 시작했다.\n\
         현재: {} · {}\n\n\
         다음\n  \
         사용자가 무엇을 원하는지 확인한다.\n\n\
         실행\n  \
         gil open\n\n\
         기록: {}\n",
        cycle.id().to_ref(),
        cycle.kind(),
        session.path.display()
    ))
}

/// 지금 이 자리가 무엇을 여는 자리인가.
///
/// **AI 가 Step 과 Cycle 경계를 따로 외우지 않게 한다**(Agent UX Model §2). 어느 계층을
/// 여는지는 세계의 상태가 이미 알고 있으므로, 그것을 사람에게 묻지 않는다.
enum Place {
    /// 지금 열려 있는 자리를 먼저 닫아야 한다.
    CloseThisStep,
    /// 이 Cycle 안에서 다음 Step 을 연다.
    Step(Vec<NodeKind>),
    /// Step Graph 가 끝 경계에 닿았다 — 이제 Cycle 을 닫는다.
    CloseThisCycle,
    /// 닫힌 Cycle 뒤에서 다음 Cycle 을 연다.
    Cycle(Vec<CycleKind>),
    /// 여기서 열 수 있는 것이 없다.
    Nothing(String),
}

fn place(session: &Session) -> Place {
    let cycles = session.project.cycles();
    let cycle = cycles.current();

    if cycle.is_closed() {
        return match cycles.why_not_open_child() {
            None => Place::Cycle(CycleKind::ALL.to_vec()),
            Some(why) => Place::Nothing(why.to_string()),
        };
    }

    let walk = cycle.steps();
    if walk
        .current()
        .and_then(|id| walk.node(id))
        .is_some_and(|node| !node.is_closed())
    {
        return Place::CloseThisStep;
    }

    let openable = cycle.openable_here();
    if !openable.is_empty() {
        return Place::Step(openable);
    }
    match cycle.can_close() {
        true => Place::CloseThisCycle,
        false => Place::Nothing("이 Cycle 안에서 더 갈 곳이 없다".to_string()),
    }
}

/// `gil open [종류]` — **어느 계층을 여는지는 GIL 이 판정한다.**
fn open(name: Option<&String>) -> Result<String, String> {
    let mut session = open_session()?;
    match place(&session) {
        Place::CloseThisStep => {
            let cycle = session.project.cycles().current();
            let here = here_ref(cycle).expect("열려 있는 자리가 있다");
            Err(refusal(
                "지금은 열 자리가 아니다.",
                &format!("{here} 이(가) 아직 열려 있다."),
                "그 자리의 Report 를 적어 먼저 닫는다.",
                "gil close",
            ))
        }
        Place::CloseThisCycle => Err(refusal(
            "지금은 열 자리가 아니다.",
            "이 Cycle 안의 판정이 닫혀 이제 Cycle 을 닫을 자리다.",
            "Cycle Report 를 적어 이 Cycle 을 닫는다.",
            "gil close",
        )),
        Place::Nothing(why) => Err(refusal(
            "여기서는 아무것도 열 수 없다.",
            &why,
            "지금 어디인지 확인한다.",
            "gil status",
        )),
        Place::Step(openable) => open_step(&mut session, name, &openable),
        Place::Cycle(openable) => open_cycle(&mut session, name, &openable),
    }
}

fn open_step(
    session: &mut Session,
    name: Option<&String>,
    openable: &[NodeKind],
) -> Result<String, String> {
    let kind = match name {
        Some(name) => NodeKind::parse(name).ok_or_else(|| {
            refusal(
                &format!("{name:?} 는 gil 이 아는 종류가 아니다."),
                "이름을 잘못 적었다.",
                &format!("지금 열 수 있는 것: {}", names(openable)),
                "gil open",
            )
        })?,
        // 갈 곳이 하나면 묻지 않는다 — 아는 것을 다시 묻는 것은 마찰이다.
        None => match openable {
            [only] => *only,
            many => {
                return Err(refusal(
                    "무엇을 열지 정해야 한다.",
                    &format!("지금 열 수 있는 것이 {}개다.", many.len()),
                    &format!(
                        "종류를 골라 적는다.\n  {}",
                        choices(session.project.cycles().current(), many)
                    ),
                    "gil open <종류>",
                ));
            }
        },
    };

    // 실행형 자리는 **무엇을 하려는지 적지 않으면 열지 않는다.** 그 계약은 Report 와 같은
    // field 문법으로 stdin 에 오지만 Close Report 가 아니다 — 행동 계약이다.
    let hint = contract_skeleton(kind);
    let contract = read_contract(&hint)?;

    let opened = session
        .project
        .open_action_step(kind, contract)
        // 거절의 이유는 라이브러리의 말을 **그대로** 옮긴다. 여기서 다시 쓰면 같은 판정이
        // 두 자리에서 서로 다르게 말하게 된다. 더하는 것은 복구로 가는 길뿐이다.
        .map_err(|err| {
            refusal(
                &format!("{kind} 를 열 수 없다."),
                &err.to_string(),
                &format!("지금 열 수 있는 것: {}", names(openable)),
                "gil open",
            )
        })?;
    session.write()?;
    Ok(opened_step(session, opened))
}

fn open_cycle(
    session: &mut Session,
    name: Option<&String>,
    openable: &[CycleKind],
) -> Result<String, String> {
    let Some(name) = name else {
        // 고를 것이 하나뿐이면 묻지 않는다. 설명은 **고를 때만** 필요하다.
        if let [only] = openable {
            return open_this_cycle(session, *only);
        }
        return Err(refusal(
            "무엇을 열지 정해야 한다.",
            &format!("지금 열 수 있는 것이 {}개다.", openable.len()),
            &format!(
                "종류를 골라 적는다.\n  {}",
                cycle_choices(session, openable)
            ),
            "gil open <종류>",
        ));
    };
    let kind = CycleKind::parse(name).ok_or_else(|| {
        refusal(
            &format!("{name:?} 는 gil 이 아는 Cycle 종류가 아니다."),
            "이름을 잘못 적었다.",
            &format!("지금 열 수 있는 것: {}", cycle_names(openable)),
            "gil open <종류>",
        )
    })?;
    open_this_cycle(session, kind)
}

fn open_this_cycle(session: &mut Session, kind: CycleKind) -> Result<String, String> {
    session.project.open_child_cycle(kind).map_err(|err| {
        refusal(
            &format!("{kind} Cycle 을 열 수 없다."),
            &err.to_string(),
            "지금 어디인지 확인한다.",
            "gil status",
        )
    })?;
    session.write()?;
    Ok(opened_cycle(session))
}

/// 고를 Cycle Kind 들 — **설명은 문법이 갖는다.**
///
/// 이름과 그 한 줄을 여기 옮겨 적지 않는다. Kind 가 늘면 `gil-spec.yaml` 한 자리만 고치면
/// 화면도 함께 는다(Agent UX Model §4.2).
fn cycle_choices(session: &Session, kinds: &[CycleKind]) -> String {
    let rules = session.project.cycles().current().rules();
    let width = kinds
        .iter()
        .map(|kind| kind.as_str().len())
        .max()
        .unwrap_or(0);
    kinds
        .iter()
        .map(|kind| {
            let description = rules
                .cycle_rules(*kind)
                .map(|rules| rules.description.as_str())
                .unwrap_or_default();
            format!("{:<width$}  {description}", kind.as_str(), width = width)
        })
        .collect::<Vec<_>>()
        .join("\n  ")
}

/// `gil close` — **무엇을 닫는지는 GIL 이 판정한다.**
fn close() -> Result<String, String> {
    let mut session = open_session()?;
    match place(&session) {
        Place::CloseThisStep => close_step(&mut session),
        Place::CloseThisCycle => close_cycle(&mut session),
        Place::Step(openable) => Err(refusal(
            "닫을 것이 없다.",
            "열려 있는 자리가 없다.",
            &format!("먼저 다음 자리를 연다 — 지금 열 수 있는 것: {}", names(&openable)),
            "gil open",
        )),
        Place::Cycle(_) => Err(refusal(
            "닫을 것이 없다.",
            "이 Cycle 은 이미 닫혔다.",
            "다음 Cycle 을 연다.",
            "gil open <종류>",
        )),
        Place::Nothing(why) => Err(refusal(
            "닫을 것이 없다.",
            &why,
            "지금 어디인지 확인한다.",
            "gil status",
        )),
    }
}

fn close_step(session: &mut Session) -> Result<String, String> {
    let cycle = session.project.cycles().current();
    let node = cycle
        .steps()
        .current()
        .and_then(|id| cycle.steps().node(id))
        .expect("열려 있는 자리가 있다");
    let kind = node.kind;
    let here = cycle.step_ref(node.id);
    let contract = cycle
        .step_contract(node.id, kind)
        .expect("열린 자리의 종류는 문법이 선언한 것이다");
    let hint = skeleton_of(&contract, cycle);

    let report = read_report(&hint)?;
    // **한 번에 확정된다** — Report·Closed·Will Done·Journey 판이 함께 눕거나, 아무것도
    // 눕지 않는다. 거절되면 열린 자리도 걸린 행동도 그대로다.
    let closed = session.project.close_action_step(report).map_err(|err| {
        refusal(
            &format!("{here} · {kind} 를 닫을 수 없다."),
            &err.to_string(),
            &format!("{}\n\n{hint}", FIX_IT),
            "gil close",
        )
    })?;
    session.write()?;
    Ok(closed_step(session, &closed))
}

fn close_cycle(session: &mut Session) -> Result<String, String> {
    let cycle = session.project.cycles().current();
    let here = cycle.id().to_ref();
    let kind = cycle.kind();
    let contract = cycle.close_contract().expect("문법이 이 Cycle Kind 를 선언했다");
    let hint = skeleton_of(&contract, cycle);

    let report = read_report(&hint)?;
    let closed = session.project.close_cycle(report).map_err(|err| {
        refusal(
            &format!("{here} · {kind} 를 닫을 수 없다."),
            &err.to_string(),
            &format!("{}\n\n{hint}", FIX_IT),
            "gil close",
        )
    })?;
    session.write()?;
    Ok(closed_cycle(session, &closed))
}

fn revisit() -> Result<String, String> {
    let mut session = open_session()?;
    session
        .project
        .cycles_mut()
        .current_mut()
        .revisit_step()
        .map_err(|err| err.to_string())?;
    session.write()?;
    Ok(where_now(&session))
}

fn status() -> Result<String, String> {
    Ok(where_now(&open_session()?))
}

/// `gil cycle …` — 옛 자리. `gil open`·`gil close` 가 두 계층을 함께 판정하므로 더는
/// 기본 경로가 아니지만, 이미 이 이름을 쓰던 손을 끊지 않으려고 남겨 둔다.
fn cycle(sub: Option<&str>, argument: Option<&String>) -> Result<String, String> {
    match sub {
        Some("close") => close(),
        Some("open") => {
            let mut session = open_session()?;
            match place(&session) {
                Place::Cycle(openable) => open_cycle(&mut session, argument, &openable),
                _ => open(argument),
            }
        }
        Some(other) => Err(refusal(
            &format!("{other:?} 는 `gil cycle` 이 아는 것이 아니다."),
            "`gil cycle` 은 `open` 과 `close` 만 안다.",
            "이제 두 계층을 함께 판정하는 짧은 이름을 쓴다.",
            "gil open · gil close",
        )),
        None => Err(refusal(
            "`gil cycle` 뒤에 무엇을 할지 적지 않았다.",
            "무엇을 하려는지 알 수 없다.",
            "이제 두 계층을 함께 판정하는 짧은 이름을 쓴다.",
            "gil open · gil close",
        )),
    }
}

// ── 상태에 민감한 도움말 — 읽기만 한다 ────────────────────────────────────

/// `gil close --help` — **지금 자리의 Close 계약만.**
///
/// 이 명령은 상태를 한 글자도 바꾸지 않는다. 저장하지 않고, Report 를 읽지 않고,
/// stdin 을 기다리지 않는다. 그래서 `Session::write` 로 가는 길이 여기엔 없다.
///
/// 실사용 M2C 에서 `gil close --help` 가 **stdin 없는 실제 Close** 로 처리됐다 —
/// 계약을 물어본 사람이 빈 Report 를 낸 것으로 거절당했다. 그 자리가 여기다.
fn close_help() -> Result<String, String> {
    let Some(session) = session_for_help()? else {
        return Ok(no_project_yet("gil close"));
    };
    let cycle = session.project.cycles().current();

    let contract = match place(&session) {
        Place::CloseThisStep => step_contract(cycle),
        Place::CloseThisCycle => cycle_contract(cycle),
        // 닫을 자리가 아니면 **무엇을 먼저 해야 하는지**를 말한다.
        Place::Step(openable) => {
            return Ok(format!(
                "지금은 닫을 자리가 아니다.\n\n먼저 할 일\n  다음 걸음을 연다 — \
                 열 수 있는 것: {}\n\n실행\n  gil open --help\n",
                names(&openable)
            ));
        }
        Place::Cycle(_) => {
            return Ok(String::from(
                "지금은 닫을 자리가 아니다.\n\n먼저 할 일\n  이 Cycle 은 이미 닫혔다. \
                 다음 Cycle 을 연다.\n\n실행\n  gil open --help\n",
            ));
        }
        Place::Nothing(why) => {
            return Ok(format!(
                "지금은 닫을 자리가 아니다.\n\n이유\n  {why}\n\n실행\n  gil status\n"
            ));
        }
    };

    let Some(contract) = contract else {
        return Ok(String::from("지금 자리의 Close 계약을 문법에서 찾지 못했다.\n"));
    };
    Ok(format!(
        "닫을 대상\n  {}\n\n필요한 Report\n{}\n입력 골격\n{}\n",
        contract.subject(),
        contract.constraints("  "),
        skeleton_of(&contract, cycle)
    ))
}

/// `gil open --help` — **지금 자리에서 열 수 있는 것과 그 계약만.**
///
/// 마찬가지로 아무것도 바꾸지 않고 stdin 을 기다리지 않는다.
fn open_help() -> Result<String, String> {
    let Some(session) = session_for_help()? else {
        return Ok(no_project_yet("gil open"));
    };
    let cycle = session.project.cycles().current();

    match place(&session) {
        // 열린 자리가 있으면 여는 법이 아니라 **먼저 할 일**을 말한다.
        Place::CloseThisStep => {
            let here = here_ref(cycle).expect("열려 있는 자리가 있다");
            let will = session.project.active_will();
            let mut out = format!("지금은 열 자리가 아니다.\n\n이유\n  {here} 이(가) 아직 열려 있다.\n");
            if let Some(will) = will {
                out.push_str(&format!("\n지금 할 일\n{}\n", indent(will.next_action())));
                out.push_str(&format!("\n완료 조건\n{}\n", indent(will.done_when())));
            }
            out.push_str("\n먼저 할 일\n  실제 작업을 마친 뒤 그 자리를 닫는다.\n\n실행\n  gil close --help\n");
            Ok(out)
        }
        Place::CloseThisCycle => Ok(String::from(
            "지금은 열 자리가 아니다.\n\n이유\n  이 Cycle 안의 판정이 닫혀 이제 Cycle 을 \
             닫을 자리다.\n\n실행\n  gil close --help\n",
        )),
        Place::Nothing(why) => Ok(format!(
            "지금은 열 자리가 아니다.\n\n이유\n  {why}\n\n실행\n  gil status\n"
        )),
        // 실행형 Step — **행동 계약이 필요하다.**
        Place::Step(openable) => {
            let mut out = String::from("열 수 있는 것\n");
            match openable.as_slice() {
                [only] => {
                    out.push_str(&format!("  {only}  {}\n", step_description(cycle, *only)));
                    out.push_str(&format!("\n행동 계약\n{}\n", action_skeleton(None)));
                }
                many => {
                    out.push_str(&format!("  {}\n", choices(cycle, many)));
                    out.push_str(&format!("\n행동 계약\n{}\n", action_skeleton(Some("<종류>"))));
                }
            }
            out.push_str(
                "\n세 칸은 지금 대화와 작업에 맞게 **네가** 적는다 — GIL 은 Node 종류만 보고 \
                 그 내용을 지어내지 않는다.\n",
            );
            Ok(out)
        }
        // 컨테이너 Cycle — **행동 계약이 필요 없다.**
        Place::Cycle(openable) => Ok(format!(
            "열 수 있는 것 (Cycle)\n  {}\n\n\
             Cycle 은 안의 Graph 를 담는 그릇이라 행동 계약 없이 연다.\n\n\
             실행\n  gil open <종류>\n",
            cycle_choices(&session, &openable)
        )),
    }
}

/// 저장이 있으면 세우고, 아직 없으면 없다고 답한다 — help 는 없다고 실패하지 않는다.
fn session_for_help() -> Result<Option<Session>, String> {
    match find_gil()? {
        None => Ok(None),
        Some(_) => open_session().map(Some),
    }
}

/// 아직 프로젝트가 없다 — 일반적인 사용법과 시작하는 법.
fn no_project_yet(command: &str) -> String {
    format!(
        "아직 이 자리에 프로젝트가 없다 ({}).\n\n\
         {command} 는 **지금 자리의 계약**을 보여 주는 명령이라, 걷기가 있어야 답할 수 있다.\n\n\
         한 바퀴\n  \
         start → open(행동 계약) → 실제 작업 → close(Report) → open → …\n\n\
         실행\n  gil start\n",
        gil::STATE_PATH
    )
}

// ── 명령이 돌려주는 영수증 ─────────────────────────────────────────────────

/// 방금 연 자리 — **무엇을 열었고, 닫으려면 무엇이 필요하고, 다음에 무엇을 하는가.**
///
/// 전체 Journey 도 과거 Report 도 여기 다시 싣지 않는다(Agent UX Model §3). 같은 대화에는
/// 이미 있는 것이고, 없다면 그것은 `gil context` 의 몫이다.
fn opened_step(session: &Session, opened: gil::Opened) -> String {
    let cycle = session.project.cycles().current();
    let contract = cycle.contract_of_kind(opened.kind);
    let will = session
        .project
        .active_will()
        .expect("실행형 자리는 Will 과 함께 열린다");

    // `지금 할 일` 과 `완료 조건` 은 방금 저장한 Will 에서 **투영한다** — 여기서 다시 쓰지
    // 않는다. `objective` 는 저장하되 무조건 되풀이하지 않는다(Agent UX Model §4.2).
    let mut out = format!("열었다: {} · {}\n", opened.step, opened.kind);
    out.push_str(&format!("\n지금 할 일\n{}\n", indent(will.next_action())));
    out.push_str(&format!("\n완료 조건\n{}\n", indent(will.done_when())));
    // **닫기 전에 계약을 미리 알려 준다.** 허용값을 오류로 알아내게 두지 않는다
    // (실사용 M2C 보고). 말은 여기서 짓지 않고 문법에서 읽는다.
    if let Some(contract) = &contract
        && !contract.fields().is_empty()
    {
        out.push_str("\n닫을 때 필요한 것\n");
        out.push_str(&contract.constraints("  "));
    }
    // **`실행` 블록을 두지 않는다.** 여기서 `gil close` 를 강조하면 실제 작업 전에 Node 부터
    // 닫는 오류가 난다(Agent UX Model §4.2) — 다음 수는 CLI 가 아니라 실제 세계에 있다.
    out
}

fn opened_cycle(session: &Session) -> String {
    let cycles = session.project.cycles();
    let cycle = cycles.current();
    let mut out = format!("열었다: {} · {}", cycle.id().to_ref(), cycle.kind());
    match cycle.parent() {
        Some(parent) => out.push_str(&format!(" · 부모 {}\n", parent.to_ref())),
        None => out.push('\n'),
    }
    out.push_str(&next_block(cycle));
    out
}

fn closed_step(session: &Session, closed: &gil::Closed) -> String {
    let cycle = session.project.cycles().current();
    // 방금 낸 판을 한 줄로 적는다 — 방금 제출한 Report 도 Will 전체도 되풀이하지 않는다.
    format!(
        "닫았다: {} · {}\n기록됨: {}\n{}",
        closed.step,
        closed.kind,
        closed.journey,
        next_block(cycle)
    )
}

fn closed_cycle(session: &Session, closed: &gil::ClosedCycle) -> String {
    let (here, kind) = (closed.cycle, closed.kind);
    let cycles = session.project.cycles();
    let cycle = cycles.current();
    let verdict = cycle
        .report()
        .and_then(|report| report.get("verdict"))
        .unwrap_or("");

    // 컨테이너는 판을 만들지 않는다 — 그때 서 있던 판을 그대로 provenance 로 적었다.
    let mut out = format!(
        "닫았다: {here} · {kind} · {verdict}\n기록됨: {} (판은 늘지 않는다)\n\n다음\n",
        closed.journey
    );
    match cycles.why_not_open_child() {
        None => {
            out.push_str(&format!(
                "  열 수 있는 것\n  {}\n\n실행\n  gil open <종류>\n",
                cycle_choices(session, &CycleKind::ALL)
            ));
        }
        Some(why) => {
            out.push_str(&format!("  {why}\n\n실행\n  gil status\n"));
        }
    }
    out
}

/// 다음에 열 수 있는 것 — 하나면 `gil open`, 여럿이면 고르라고 한다.
fn next_block(cycle: &gil::Cycle) -> String {
    let openable = cycle.openable_here();
    match openable.as_slice() {
        [] if cycle.can_close() => {
            "\n다음\n  이 Cycle 의 Report 를 적어 닫는다\n\n실행\n  gil close\n".to_string()
        }
        [] => "\n다음\n  여기서 할 수 있는 것이 없다\n\n실행\n  gil status\n".to_string(),
        [_only] => format!(
            "\n다음\n  열 수 있는 것: {}\n\n실행\n  gil open\n",
            names(&openable)
        ),
        many => format!(
            "\n다음\n  열 수 있는 것\n  {}\n\n실행\n  gil open <종류>\n",
            choices(cycle, many)
        ),
    }
}

/// 여러 종류가 가능할 때 — 이름과 **그 자리가 무엇을 하는 자리인지.**
///
/// 설명을 여기 옮겨 적지 않는다. Kind 가 늘면 `gil-spec.yaml` 한 자리만 고치면 화면도
/// 함께 는다(Agent UX Model §4.2) — Cycle Kind 를 고르는 자리와 같은 규칙이다.
fn choices(cycle: &gil::Cycle, kinds: &[NodeKind]) -> String {
    let width = kinds
        .iter()
        .map(|kind| kind.as_str().len())
        .max()
        .unwrap_or(0);
    kinds
        .iter()
        .map(|kind| {
            format!(
                "{:<width$}  {}",
                kind.as_str(),
                step_description(cycle, *kind),
                width = width
            )
        })
        .collect::<Vec<_>>()
        .join("\n  ")
}

/// 그 Step Kind 가 무엇을 하는 자리인지 — **문법이 갖는 한 줄.**
fn step_description(cycle: &gil::Cycle, kind: NodeKind) -> &str {
    cycle
        .rules()
        .rules(cycle.kind(), kind)
        .map(|rules| rules.description.as_str())
        .unwrap_or_default()
}

/// 거절 — **무엇이 · 왜 · 지금 무엇을 · 다음 명령.** 넷을 늘 갖춘다.
///
/// 짧게 만들려고 까닭이나 복구를 빼지 않는다(Agent UX Model §9). 전체 문맥을 붙이지도
/// 않는다 — 복구에 필요한 국소 정보만.
fn refusal(what: &str, why: &str, todo: &str, run: &str) -> String {
    format!(
        "거절: {what}\n\n이유\n{}\n\n지금 해야 할 일\n{}\n\n실행\n  {run}\n",
        indent(why),
        indent(todo)
    )
}

/// 여러 줄짜리 토막을 한 단 들여쓴다 — 뒷줄이 제목처럼 보이지 않게.
fn indent(text: &str) -> String {
    text.lines()
        .map(|line| match line.is_empty() {
            true => String::new(),
            false => format!("  {line}"),
        })
        .collect::<Vec<_>>()
        .join("\n")
}

/// 지금 열려 있는 Step 을 닫는 계약. 열린 자리가 없으면 없다.
fn step_contract(cycle: &gil::Cycle) -> Option<CloseContract> {
    let walk = cycle.steps();
    let node = walk.node(walk.current()?)?;
    match node.is_closed() {
        true => None,
        false => cycle.step_contract(node.id, node.kind),
    }
}

/// Cycle 자신을 닫는 계약 — `outcome_ref` 는 **가리켜야 하는 그 주소**가 이미 정해져 있다.
fn cycle_contract(cycle: &gil::Cycle) -> Option<CloseContract> {
    cycle.close_contract()
}

/// 그 계약의 골격. Cycle Report 의 `outcome_ref` 만 값을 미리 채워 준다.
fn skeleton_of(contract: &CloseContract, cycle: &gil::Cycle) -> String {
    let last = cycle
        .steps()
        .current()
        .map(|id| cycle.step_ref(id).to_string());
    contract.skeleton(|field| match field {
        "outcome_ref" => last.clone(),
        _ => None,
    })
}

fn names(kinds: &[NodeKind]) -> String {
    kinds
        .iter()
        .map(|kind| kind.as_str())
        .collect::<Vec<_>>()
        .join(", ")
}

fn cycle_names(kinds: &[CycleKind]) -> String {
    kinds
        .iter()
        .map(|kind| kind.as_str())
        .collect::<Vec<_>>()
        .join(", ")
}

/// 지금 열려 있는 자리의 주소.
fn here_ref(cycle: &gil::Cycle) -> Option<gil::StepRef> {
    let walk = cycle.steps();
    let node = walk.node(walk.current()?)?;
    match node.is_closed() {
        true => None,
        false => Some(cycle.step_ref(node.id)),
    }
}

// ── 지금 어디인가 ──────────────────────────────────────────────────────────

/// 지금 어디인가 — 어느 Cycle · 무엇을 이어받았나 · 어느 Step · 다음에 무엇을 할 수 있나.
///
/// 기록이 **서 있는 자리에 없으면** 어느 파일인지를 먼저 말한다. 있으면 말하지 않는다 —
/// 예사로운 일에 줄을 쓰면 정작 알려야 할 때 그 줄이 안 읽힌다.
fn where_now(session: &Session) -> String {
    let cycles = session.project.cycles();
    let cycle = cycles.current();
    let walk = cycle.steps();
    let mut out = String::new();

    if found_above(&session.path) {
        out.push_str(&format!("기록: {}\n", session.path.display()));
    }

    // ① 어느 Cycle 인가 — 이름·종류·상태, 그리고 어디에서 이어받았는가.
    let state = match cycle.report().and_then(|report| report.get("verdict")) {
        Some(verdict) => format!("닫힘 · {verdict}"),
        None => "열림".to_string(),
    };
    out.push_str(&format!("{} {} ({state})", cycle.id(), cycle.kind()));
    match cycle.parent() {
        Some(parent) => out.push_str(&format!(" · 부모 {parent}\n")),
        None => out.push_str(" · 뿌리\n"),
    }

    // ② 무엇을 이어받았는가. **원본은 부모에게 있다** — 여기서는 있다는 사실만 말한다.
    if let Some(parent) = cycle.parent() {
        match cycles.inherited_report(cycle.id()).is_some() {
            true => out.push_str(&format!(
                "이어받음: {parent} 의 Cycle Report — 그 내용은 `gil story` 에 있다\n"
            )),
            false => out.push_str(&format!("이어받음: {parent} (Cycle Report 가 없다)\n")),
        }
    }

    // ③ 그 Cycle 안에서 어느 Step 에 서 있는가.
    let here = walk.current().and_then(|id| walk.node(id));
    match here {
        Some(node) => out.push_str(&format!("자리: {} {} ({})\n", node.id, node.kind, node.status)),
        None => out.push_str("자리: 아직 아무것도 열지 않았다\n"),
    }
    out.push_str(&format!(
        "걸어온 것: Cycle {}개 · 이 Cycle 의 Step {}개 (닫힘 {})\n",
        cycles.nodes().len(),
        walk.nodes().len(),
        walk.history().count()
    ));

    // ④ 지금 누가 행동하며 무엇을 하려는가 — **짧게.** 전체 Journey 는 펼치지 않는다.
    let existence = session.project.current_existence();
    out.push_str(&format!(
        "존재: {} · {}\n",
        existence.id(),
        existence.current_journey()
    ));
    match session.project.active_will() {
        Some(will) => out.push_str(&format!(
            "하려는 것: {} · {} — {}\n",
            will.id(),
            will.target(),
            first_line(will.next_action())
        )),
        None => out.push_str("하려는 것: 걸린 행동이 없다\n"),
    }

    // ⑤ 다음에 무엇을 할 수 있는가. **안내는 실행과 같은 자리에서 나온다.**
    out.push_str(&next_moves(cycles));
    out
}

/// 여러 줄이면 첫 줄만 — `gil status` 는 세 줄로 답하는 자리다.
fn first_line(text: &str) -> String {
    match text.lines().next() {
        Some(first) if first.len() < text.len() => format!("{first} …"),
        Some(first) => first.to_string(),
        None => String::new(),
    }
}

// ── stdin 에서 Report 를 받는다 ────────────────────────────────────────────

/// 거절이 가리키는 복구 — **계약 전체는 여기서 되풀이하지 않는다.**
///
/// 거절은 빠진 값과 고치는 법에 집중하고, 어떤 값을 적을 수 있는지는 `gil close --help` 와
/// Open Receipt 가 같은 문법에서 읽어 말한다. 셋이 각자 설명을 지으면 반드시 갈린다.
const FIX_IT: &str = "아래 꼴로 다시 적는다 — 어떤 값을 적을 수 있는지는 `gil close --help`.";

/// Report 는 stdin 으로만 받는다.
///
/// 통로를 하나로 둔다. 같은 것을 플래그로도 받으면 두 통로가 생기고, 그러면 둘이 어긋날 때
/// 무엇이 실제로 실렸는지 아무도 모른다 — 옛 도구가 가장 깊게 물린 상처가 그것이다.
///
/// 보여 주는 꼴은 **지금 이 Node 의 것**이다. 상관없는 예시를 보여 주면 읽는 쪽은 그것을
/// 베끼고, 베낀 것은 또 거절당한다.
fn read_report(skeleton: &str) -> Result<Report, String> {
    if io::stdin().is_terminal() {
        return Err(refusal(
            "Report 를 받지 못했다.",
            "Report 는 stdin 으로 받는데 터미널이 붙어 있다 — 여기서 기다리지 않는다.",
            &format!("{FIX_IT}\n\n{skeleton}"),
            "gil close",
        ));
    }

    let mut text = String::new();
    io::stdin()
        .read_to_string(&mut text)
        .map_err(|err| format!("stdin 을 읽지 못했다: {err}"))?;

    // 빈 글도 그대로 넘긴다 — 무엇이 빠졌는지는 문법이 말한다(여기서 짐작하지 않는다).
    Report::parse(&text).map_err(|err| {
        refusal(
            "적어 준 글을 Report 로 읽지 못했다.",
            &err.to_string(),
            &format!("{FIX_IT}\n\n{skeleton}"),
            "gil close",
        )
    })
}

/// 실행형 자리를 여는 **행동 계약**의 골격.
///
/// GIL 은 Node Kind 만 보고 그 내용을 지어내지 않는다(Will Model §7) — `question` 이라는
/// 이름은 *무엇을* 물을지 모른다. 그래서 값은 비워 두고 칸만 보여 준다.
fn contract_skeleton(kind: NodeKind) -> String {
    action_skeleton(Some(kind.as_str()))
}

/// 행동 계약의 골격 — 종류를 적어야 하는 자리면 그것까지.
fn action_skeleton(kind: Option<&str>) -> String {
    let named = match kind {
        Some(kind) => format!(" {kind}"),
        None => String::new(),
    };
    let mut out = format!("  gil open{named} <<'EOF'\n");
    for field in [gil::OBJECTIVE, gil::NEXT_ACTION, gil::DONE_WHEN] {
        out.push_str(&format!("  {field}: …\n"));
    }
    out.push_str("  EOF");
    out
}

/// 행동 계약은 stdin 으로만 받는다 — Report 와 같은 통로, 같은 문법.
///
/// **여기서 기다리지 않는다.** 터미널이 붙어 있으면 대화형 입력을 열지 않고 골격을 보여
/// 준다(Will Model §11: *"별도 대화형 입력을 암묵적으로 기다리지 않는다"*). 상태는 한 글자도
/// 바뀌지 않는다 — 아직 아무것도 열지 않았다.
fn read_contract(skeleton: &str) -> Result<ActionContract, String> {
    let refuse = |why: String| {
        refusal(
            "무엇을 하려는지 적지 않았다.",
            &why,
            &format!(
                "아래 꼴로 적는다 — 지금 대화와 작업에 맞는 내용을 **네가** 적는다.\n\n{skeleton}"
            ),
            "gil open",
        )
    };

    if io::stdin().is_terminal() {
        return Err(refuse(
            "실행형 자리는 행동 계약과 함께 열리는데 터미널이 붙어 있다 — 여기서 기다리지 않는다."
                .to_string(),
        ));
    }
    let mut text = String::new();
    io::stdin()
        .read_to_string(&mut text)
        .map_err(|err| format!("stdin 을 읽지 못했다: {err}"))?;

    let report = Report::parse(&text).map_err(|err| refuse(err.to_string()))?;
    ActionContract::from_report(&report).map_err(|err| refuse(err.to_string()))
}

// ── 안내 ───────────────────────────────────────────────────────────────────

/// `gil --help` — **평상시에 외워야 하는 것만.**
///
/// 전체 문법도, 모든 Step Kind 도 여기 늘어놓지 않는다(Agent UX Model §2·§9). 지금 무엇을
/// 열 수 있는지는 **매 명령의 출력이** 말하고, 그것이 이 도구가 가르치는 방식이다.
fn help() -> String {
    String::from(
        "gil — 사고의 한 걸음을 열고, 실제로 하고, 적어서 닫는다.\n\n\
         평상시\n  \
         gil start   프로젝트를 시작하고 최초 Interview 를 연다\n  \
         gil open    다음 한 걸음을 연다 — **무엇을 하려는지 적어서** (stdin)\n  \
         gil close   실제 작업을 마친 뒤 Report 를 적어 그 걸음을 닫는다 (stdin)\n\n\
         실행형 걸음은 행동 계약과 함께 열린다. GIL 은 그 내용을 지어내지 않는다.\n\n  \
         gil open <<'EOF'\n  \
         objective:   무엇을 이루려는가\n  \
         next_action: 지금 실제 세계에서 가장 먼저 할 일 (gil 명령이 아니다)\n  \
         done_when:   무엇을 보면 끝났다고 할 수 있는가\n  \
         EOF\n\n\
         Cycle 은 그릇이라 계약 없이 열린다 — `gil open <종류>`.\n\n\
         한 바퀴\n  \
         start → open → 실제 작업 → close → open → …\n  \
         Step 과 Cycle 의 경계는 gil 이 판정한다. 어느 계층인지 외우지 않아도 된다.\n\n\
         지금 자리의 계약이 궁금하면 — **읽기만 하고 아무것도 바꾸지 않는다.**\n  \
         gil open --help    지금 열 수 있는 것과 행동 계약의 꼴\n  \
         gil close --help   지금 자리를 닫는 데 필요한 칸과 그 값들의 뜻\n\n\
         이어받을 때\n  \
         gil context   새 세션·인수인계·맥락을 잃었을 때 지금 자리를 복원한다\n  \
         gil status    지금 어디인지 세 줄로 답한다\n  \
         gil story     걸어온 것을 사람의 말로 읽는다\n\n\
         Report 를 적는 꼴 — 적은 글자가 그대로 값이 된다. 주석도, 인용도, 형 변환도 없다.\n\n  \
         gil close <<'EOF'\n  \
         problem: 줄 끝까지 그대로다 — #7 도 3.10 도 그냥 글자다\n  \
         next_direction:\n  \
         \x20 action: close_cycle          (들여쓰면 이름이 점으로 이어진다)\n  \
         interpretation: |\n  \
         \x20 여러 줄은 이렇게 연다.\n  \
         EOF\n\n\
         Cycle 을 닫을 때 판정을 가리키는 칸은 **주소**다 — 화면의 `#4` 가 아니라:\n\n  \
         outcome_ref: step:C1/S4\n\n\
         무엇을 적어야 하는지는 `gil open` 과 `gil close` 가 그 자리에서 알려 준다.\n\n\
         옛 이름 (호환)\n  \
         gil cycle open · gil cycle close   이제 `gil open` · `gil close` 가 함께 판정한다\n  \
         gil revisit                        닫힌 판정에 이미 적혀 있는 되돌아감을 밟는다\n  \
         gil --version                      판을 밝힌다\n",
    )
}
