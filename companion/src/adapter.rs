//! **실제 GIL Project 를 읽는 adapter** — Host UI Model §9.1.1 의 첫 조각.
//!
//! # 이 파일이 지는 책임
//!
//! ```text
//! 사람이 고른 폴더 → GIL 의 검증된 open 경로 → MonitorViewV1 · NodeDetailV1
//! ```
//!
//! 그게 전부다. Graph 의미도, Cycle 관계도, 요약도, 현재 위치도 여기서 만들지 않는다.
//! `.gil/state.yaml` 을 **열지도 해석하지도 않는다** — 그 파일을 아는 것은 `gil` crate 뿐이고,
//! 여기서는 그 crate 의 `open_read_only` 에 자리만 건넨다(§9.1.1-2).
//!
//! # 전부 읽기다 — **타입이 그것을 보장한다**
//!
//! 여는 문은 [`ProjectSession::open_read_only`] 하나뿐이고, 그것이 주는
//! [`ReadOnlySession`] 에는 `commit` 도 `project_mut` 도 없다. 이 파일이 프로젝트를 바꾸는
//! 코드를 쓰려 해도 **컴파일되지 않는다**. 규율로 지키면 언젠가 한 줄이 새어 나간다.
//!
//! 쓰는 쪽의 `ProjectSession::open` 은 미완의 복원을 되돌리고 tmp 잔해를 치운다 — 그것이
//! 옳다. 하지만 그 둘은 **파일을 옮기고 지우는 일**이라, 관찰만 하는 창이 하면 「보기만
//! 했는데 프로젝트가 달라졌다」가 된다. 그래서 읽기 전용 문은 그 일을 하지 않고, 복구가
//! 필요한 상태를 만나면 `needs_recovery` 로 그 사실만 말한다.
//!
//! # 잠금은 한 호출 안에서만 산다
//!
//! `ProjectSession::open` 은 **잠그고 나서 읽는다**. 그 session 을 창이 사는 동안 쥐고 있으면
//! 사람이 같은 Project 에서 `gil` 명령을 하나도 쓸 수 없다. 그래서 호출마다 열고, 읽고,
//! 곧바로 놓는다. 창이 기억하는 것은 **경로뿐**이다.
//!
//! # 창은 기다리는 동안에도 살아 있어야 한다
//!
//! 2026-09-12 실측: `blocking_pick_folder()` 를 `#[tauri::command]` 안에서 불렀더니 창이
//! 통째로 멈췄다. sample 이 가리킨 자리는 `Receiver::recv` — **NSApplication 의 event loop
//! 위에서** 기다리고 있었다. 그 loop 가 곧 창이므로, 거기서 기다리면 repaint 도 resize 도
//! 멈춘다.
//!
//! 그래서 이 파일의 모든 command 는 `async` 이고, 실제로 **기다리는 일**은 둘로 나뉜다.
//!
//! ```text
//!   고르개    pick_folder(callback) → channel → await     ← event loop 는 계속 돈다
//!   파일 읽기  spawn_blocking(…)            → await       ← worker 스레드에서
//! ```
//!
//! event loop 위에서 파일을 기다리는 자리가 하나도 없어야 한다.
//!
//! # 잠금은 await 를 건너지 않는다
//!
//! 등록부 잠금도, GIL 잠금도 `.await` 너머로 들고 가지 않는다. 등록부에서는 필요한 자리만
//! 복제하고 곧바로 놓는다. GIL session 은 worker 안에서 나고 worker 안에서 죽는다 — 고르개가
//! 열려 있는 동안 남의 `gil` 명령이 막히는 일이 없다.
//!
//! # 갱신은 수동 하나뿐
//!
//! watcher 도 자동 refresh 도 없다(§9.1.1). 사람이 새로고침을 누르면 **완전한 View** 를 다시
//! 읽는다. 부분 event 를 옛 View 에 합쳐 새 사실을 만드는 길은 여기 없다.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use gil::{
    DetailError, ProjectSession, ReadOnlySession, RuleSet, SessionError, StepRef, StoreError,
    ViewError, encode_detail_v1, encode_view_v1, monitor_view_v1,
};
use serde::Serialize;
use sha2::{Digest, Sha256};
use tauri::State;
use tauri::async_runtime;
use tauri_plugin_dialog::DialogExt;

/// 파일을 만지는 일을 **event loop 밖**에서 한다.
///
/// 여기 들어오는 것은 전부 GIL 의 읽기다 — 열고, 관측하고, 투영한다. 몇 밀리초든 몇 초든,
/// 그동안 창은 계속 그려지고 움직인다.
async fn off_the_loop<T, F>(work: F) -> Result<T, Refusal>
where
    F: FnOnce() -> Result<T, Refusal> + Send + 'static,
    T: Send + 'static,
{
    match async_runtime::spawn_blocking(work).await {
        Ok(done) => done,
        // worker 가 끝나지 못했다 — 사실을 얻지 못한 것이지 Project 가 상한 것이 아니다.
        Err(_) => Err(Refusal::new("unreadable", "읽기가 끝나지 못했다")),
    }
}

/// 창이 사는 동안 열어 둔 Project 들 — **경로가 사는 유일한 자리.**
///
/// View 도 detail 도 여기 담지 않는다. 담으면 그 순간부터 화면이 언제 적 사실인지 아무도
/// 모르게 된다. 사실은 늘 방금 연 session 에서 온다.
///
/// # 경로는 여기서 나가지 않는다
///
/// 화면으로 나가는 것은 **scope 와 사람이 읽을 이름** 둘뿐이다. UI 가 경로를 쥐면, 화면에
/// 오간 글자로 아무 자리나 열어 달라고 청할 수 있게 된다(§10). 그래서 `load_view` 도
/// `load_detail` 도 scope 만 받고, 어느 자리인지는 이 등록부가 안다.
#[derive(Default)]
pub struct Registry {
    known: Mutex<BTreeMap<String, Entry>>,
}

/// 등록부의 한 칸 — 어느 자리이고, 사람에게 뭐라고 보이고, 지금 열 수 있는가.
struct Entry {
    root: PathBuf,
    label: String,
    /// 설정에서 되살렸는데 **그 자리가 사라졌거나 다른 것이 되었다**.
    ///
    /// 목록에서 지우지 않는다 — 사람이 등록해 둔 사실은 남아 있고, 다른 Project 로 물러설
    /// 수도 없다(§9.1.2). 지금 열 수 없다는 것만 적어 둔다.
    unavailable: Option<&'static str>,
    /// 설정이 기억하는 차례. 작을수록 최근이다.
    order: usize,
}

/// 이 등록이 새로 든 것인가, 이미 있던 것인가.
#[derive(Debug, PartialEq, Eq)]
pub enum Entered {
    Fresh,
    Already,
}

/// 고르개가 돌려준 것, 또는 사람이 취소했다는 사실.
///
/// **취소는 오류가 아니다**(§9.1.1-8). `None` 으로 돌아가면 부르는 쪽은 아무것도 바꾸지
/// 않는다 — 지금 Project 도 마지막 View 도 그대로다.
///
/// **경로가 없다.** 여기 실리는 것은 scope 와 사람이 읽을 이름뿐이다.
#[derive(Serialize, Debug)]
pub struct Picked {
    scope_id: String,
    label: String,
    /// 지금 열 수 있는가. `Some` 이면 왜 못 여는지의 **낱말**이다(경로가 아니다).
    #[serde(skip_serializing_if = "Option::is_none")]
    unavailable: Option<&'static str>,
}

impl Picked {
    pub fn scope_id(&self) -> &str {
        &self.scope_id
    }
    pub fn label(&self) -> &str {
        &self.label
    }
}

impl Registry {
    /// 이 자리를 등록부에 들인다 — **scope 를 밖에서 받는다.**
    ///
    /// scope 계산을 인자로 뺀 이유는 하나다. 아래의 충돌 규칙은 「같은 scope 인데 다른
    /// 자리」일 때 무엇을 하는가인데, SHA-256 으로 그 상황을 실제로 만들 수는 없다. 그래서
    /// **계산된 scope 를 건네받는 좁은 틈**을 두어 시험이 그 상황을 직접 세운다.
    /// production 은 언제나 [`scope_of`] 가 낸 값을 넘긴다 — 해시를 약하게 만들지 않는다.
    ///
    /// ```text
    ///   scope 없음            → 새로 든다
    ///   scope 있고 자리 같음   → 그 칸을 그대로 쓴다
    ///   scope 있고 자리 다름   → **절대 합치지 않는다.** 거절한다
    /// ```
    ///
    /// 마지막 줄이 이 함수가 있는 이유다. 두 자리를 한 scope 아래 합치면 UI 는 두 Project 의
    /// View 와 상세를 같은 이름으로 받게 되고, 그것을 구별할 방법이 없다.
    pub fn remember(&self, scope: &str, root: &Path, label: &str) -> Result<Entered, Refusal> {
        let mut known = self.known.lock().expect("등록부");
        if let Some(seated) = known.get(scope) {
            if seated.root == root {
                return Ok(Entered::Already);
            }
            // **같은 이름, 다른 자리.** 일어날 리 없는 일이지만, 일어난다면 섞는 것보다
            // 멈추는 것이 낫다. 섞이면 어느 Project 의 사실인지 아무도 모른다.
            return Err(Refusal::new(
                "scope_collision",
                "서로 다른 두 Project 가 같은 주소를 받았다 — 섞지 않고 멈춘다",
            ));
        }
        known.insert(
            scope.to_string(),
            Entry {
                root: root.to_path_buf(),
                label: label.to_string(),
                unavailable: None,
                order: 0,
            },
        );
        Ok(Entered::Fresh)
    }

    /// 설정에서 되살린 한 칸 — 열리지 않는 것도 자리를 지킨다.
    pub fn restore(&self, scope: &str, root: &Path, label: &str, order: usize,
                   unavailable: Option<&'static str>) {
        self.known.lock().expect("등록부").insert(
            scope.to_string(),
            Entry {
                root: root.to_path_buf(),
                label: label.to_string(),
                unavailable,
                order,
            },
        );
    }

    /// 목록에서 지운다 — **등록부의 한 칸뿐**이다. Project 파일은 아무것도 건드리지 않는다.
    pub fn forget(&self, scope: &str) -> bool {
        self.known.lock().expect("등록부").remove(scope).is_some()
    }

    /// 이 scope 의 자리와 이름 — 설정에 적을 때 쓴다. 화면으로 나가지 않는다.
    pub fn seat_of(&self, scope: &str) -> Option<(PathBuf, String)> {
        self.known
            .lock()
            .expect("등록부")
            .get(scope)
            .map(|entry| (entry.root.clone(), entry.label.clone()))
    }

    /// 지금까지 든 Project 들 — **scope 와 이름뿐.** 최근에 쓴 것이 앞에 온다.
    pub fn listed(&self) -> Vec<Picked> {
        let known = self.known.lock().expect("등록부");
        let mut seats: Vec<(usize, Picked)> = known
            .iter()
            .map(|(scope_id, entry)| {
                (
                    entry.order,
                    Picked {
                        scope_id: scope_id.clone(),
                        label: entry.label.clone(),
                        unavailable: entry.unavailable,
                    },
                )
            })
            .collect();
        seats.sort_by(|one, other| one.0.cmp(&other.0).then_with(|| one.1.scope_id.cmp(&other.1.scope_id)));
        seats.into_iter().map(|(_, one)| one).collect()
    }

    /// 이 scope 의 자리. **등록부 밖으로 나가지 않는다.**
    fn root_of(&self, scope: &str) -> Result<PathBuf, Refusal> {
        let known = self.known.lock().expect("등록부");
        let entry = known
            .get(scope)
            .ok_or_else(|| Refusal::new("unknown_scope", "이 창이 연 Project 가 아니다"))?;
        // **못 여는 자리를 열어 보지 않는다.** 왜 못 여는지는 되살릴 때 이미 알았다.
        if let Some(why) = entry.unavailable {
            return Err(Refusal::new(why, UNAVAILABLE_SAID));
        }
        Ok(entry.root.clone())
    }

    /// 이 Project 를 목록에서 지웠을 때, 그것이 지금 보고 있던 것인가.
    pub fn holds(&self, scope: &str) -> bool {
        self.known.lock().expect("등록부").contains_key(scope)
    }

    /// 사람에게 보일 이름 — 고른 폴더의 이름 한 조각이다. 절대경로가 아니다.
    pub fn name_for(root: &Path) -> String {
        root.file_name()
            .map(|name| name.to_string_lossy().into_owned())
            .unwrap_or_else(|| "이름 없는 자리".to_string())
    }
}

/// 거절의 **종류**. UI 는 이 낱말로 갈래를 정하고, 글은 사람에게 보이기만 한다.
///
/// 글을 뜯어 뜻을 짐작하는 길을 남기지 않으려고 종류를 따로 싣는다(§9.1.1-7).
#[derive(Serialize, Debug)]
pub struct Refusal {
    code: &'static str,
    said: String,
}

impl Refusal {
    fn new(code: &'static str, said: impl Into<String>) -> Self {
        Refusal { code, said: said.into() }
    }
}

/// GIL 이 준 거절을 **종류를 잃지 않고** 옮긴다.
///
/// 한 갈래로 뭉개면 사람이 「잠시 뒤 다시」와 「이건 GIL Project 가 아니다」를 가릴 수 없다.
///
/// # 왜 GIL 의 글을 그대로 쓰지 않는가
///
/// GIL 의 오류 글에는 **절대경로가 박혀 있다** — CLI 에서는 그것이 옳다. 사람이 그 자리에
/// 서 있고, 어느 파일인지가 곧 다음 수이기 때문이다. 창은 다르다. 여기서 나간 글은 JS 와
/// DOM 을 지나므로, 경로가 실리면 화면에 오간 글자로 아무 자리나 열어 달라고 청할 수 있게
/// 된다(§10). 그래서 **글은 여기서 새로 쓴다.**
///
/// 경로가 아닌 것은 싣는다 — 저장 판의 번호, 남아 있는 복원 영역의 이름 같은 것들이다.
/// 그것이 없으면 사람은 무엇을 해야 할지 알 수 없다.
fn refuse_open(err: SessionError) -> Refusal {
    match err {
        // 다른 GIL 명령이 지금 이 Project 를 쥐고 있다. 곧 풀린다.
        SessionError::Busy { .. } => {
            Refusal::new("busy", "다른 GIL 명령이 이 Project 를 쥐고 있다")
        }
        // 잠금 자체를 걸 수 없었다 — 경쟁이 아니라 자리의 문제다.
        SessionError::LockUnavailable { .. } => {
            Refusal::new("unreadable", "이 Project 를 잠그지 못했다")
        }
        SessionError::Unreadable { .. } => {
            Refusal::new("unreadable", "이 Project 의 내부 저장소를 들여다보지 못했다")
        }
        SessionError::NoProjectDir { .. } => {
            Refusal::new("not_a_project", "고른 자리가 Project 안의 자리가 아니다")
        }
        // 미완의 복원이 남아 있다. **고치지 않는다** — 무엇이 남았는지만 전한다.
        // 남은 것의 **이름**은 경로가 아니라 restore 영역 안의 한 조각이라 실어도 된다.
        SessionError::NeedsRecovery { found, .. } => Refusal::new(
            "needs_recovery",
            format!("끝나지 않은 복원이 남아 있다 ({found})"),
        ),
        // 이 gil 이 읽지 않는 판이다. 지어내 읽지 않는다.
        SessionError::LegacyFormat { .. } => {
            Refusal::new("unsupported_format", "앞 형식의 기록이다")
        }
        SessionError::Store(inner) => match inner {
            // 그 자리에 걷기가 없다 — 아직 `gil start` 하지 않은 폴더다.
            StoreError::NotFound { .. } => {
                Refusal::new("not_a_project", "이 자리에 GIL 걷기가 없다")
            }
            StoreError::LegacyFormat { .. } => {
                Refusal::new("unsupported_format", "앞 형식의 기록이다")
            }
            // 판 번호는 경로가 아니다 — 사람이 무엇을 해야 할지 아는 데 필요하다.
            StoreError::UnknownFormat { found, known } => Refusal::new(
                "unsupported_format",
                format!("이 Companion 이 모르는 저장 판이다 (기록 v{found} · 아는 판 v{known})"),
            ),
            StoreError::PreviousFormat { found, current, .. } => Refusal::new(
                "unsupported_format",
                format!("더는 읽지 않는 앞 판이다 (기록 v{found} · 지금 판 v{current})"),
            ),
            StoreError::Read { .. } => Refusal::new("unreadable", "기록을 읽지 못했다"),
            // 읽히기는 하는데 말이 안 된다.
            _ => Refusal::new("damaged", "저장된 것을 읽었지만 말이 되지 않는다"),
        },
        // 세계를 들여다보지 못했다.
        SessionError::Observe { .. } => {
            Refusal::new("observe_failed", "Project 의 세계를 관측하지 못했다")
        }
        SessionError::Object { .. } => {
            Refusal::new("observe_failed", "저장된 객체를 읽지 못했다")
        }
        _ => Refusal::new("damaged", "이 Project 를 읽지 못했다"),
    }
}

/// 되살렸지만 지금은 열 수 없는 자리에 붙는 말. **경로를 담지 않는다.**
pub const UNAVAILABLE_SAID: &str =
    "등록해 둔 자리를 지금 찾을 수 없거나 다른 Project 가 되었다 — \
     폴더를 다시 고르거나 목록에서 지운다";

/// 투영이 거절한 것 — Grammar 가 v1 의 어휘 밖이다(§4.1).
fn refuse_view(err: ViewError) -> Refusal {
    // Grammar 낱말은 경로가 아니다 — 무엇이 낯선지 말해야 사람이 판단할 수 있다.
    Refusal::new("unsupported_vocabulary", err.to_string())
}

/// 이 자리를 열어 본다 — **`state.yaml` 을 읽지는 않는다.**
///
/// `ProjectSession::open` 은 `.gil/` 을 **먼저 잠그므로**, `.gil` 이 아예 없는 폴더에서는
/// 「잠글 수 없다」로 끝난다. 그 말은 사실이지만 사람에게는 틀린 말이다 — 자리의 문제가
/// 아니라 **여기가 GIL Project 가 아니라는 것**이다. 명세가 그 둘을 다른 거절로 남기라
/// 했으므로(§9.1.1-7) 여는 일보다 먼저 가른다.
///
/// 가르는 방법은 **그 자리에 파일이 있는가** 하나뿐이다. 열지도 해석하지도 않고, 경로는
/// `gil` 이 지닌 상수를 그대로 쓴다 — Companion 이 `.gil` 의 구조를 따로 아는 일이 없게(§9.1.1-2).
fn opened_at(root: &Path) -> Result<ReadOnlySession, Refusal> {
    let state_path = root.join(gil::STATE_PATH);
    if !state_path.is_file() {
        return Err(Refusal::new(
            "not_a_project",
            "이 자리에 GIL 걷기가 없다 — Project root 를 고른다",
        ));
    }
    // **읽기만 하는 문.** 복구도 잔해 회수도 저장도 하지 않는다(§9.1.1).
    ProjectSession::open_read_only(rules()?, &state_path).map_err(refuse_open)
}

fn rules() -> Result<RuleSet, Refusal> {
    RuleSet::builtin().map_err(|_| Refusal::new("damaged", "함께 실린 명세를 읽지 못했다"))
}

/// 이 자리의 **안정된 주소** — `project:` + SHA-256 **전체** 64자리 hex.
///
/// ```text
/// project:3fa2…(64자리)     ← canonical root 의 SHA-256 전부
/// ```
///
/// **자르지 않는다.** 앞 15자리(60비트)만 쓰면 「다른 Project 는 절대 같은 주소가 되지
/// 않는다」고 말할 수 없다 — 생일 문제로 수천만 개쯤에서 부딪칠 수 있는 크기다. 창이 그만큼
/// 많은 Project 를 열 일은 없지만, **말과 물건이 어긋난 채로 두지 않는다.** 전체 digest 는
/// 충돌을 가정에서 지운다.
///
/// 경로 원문을 쓰지 않는 이유는 따로 있다 — scope 이름이 곧 파일 경로면, 화면에 오간 이름
/// 으로 아무 자리나 열어 달라고 청할 수 있게 된다(§10). 그래서 wire 에도 UI 에도 경로가
/// 아니라 이 지문이 오간다.
pub fn scope_of(root: &Path) -> String {
    let mut digest = Sha256::new();
    digest.update(root.as_os_str().as_encoded_bytes());
    format!("project:{:x}", digest.finalize())
}

/// 사람이 고른 폴더 하나를 연다 — **추측하지 않는다**(§9.1.1-1).
///
/// cwd 도, 최근 폴더도, 열린 대화도 보지 않는다. 고른 자리 **그 자체**가 Project root 다.
/// 그 아래로 거슬러 올라가 `.gil` 을 찾지도 않는다 — 그것도 추측이다.
#[tauri::command]
pub async fn pick_project(
    app: tauri::AppHandle,
    registry: State<'_, Registry>,
) -> Result<Option<Picked>, Refusal> {
    // **고르개는 callback 으로 연다.** 여기서 기다리지 않는다 — 기다리면 그 기다림이 곧
    // event loop 위에 앉고, 창이 멈춘다(2026-09-12 실측).
    let (said, mut hear) = async_runtime::channel(1);
    app.dialog().file().pick_folder(move |picked| {
        // 칸이 하나 비어 있고 한 번만 보내므로 이 자리는 막히지 않는다.
        let _ = said.blocking_send(picked);
    });

    // 사람이 고르개를 만지는 동안 이 task 만 쉰다. 창은 계속 돈다.
    // **이 await 를 건널 때 쥐고 있는 잠금이 하나도 없다.**
    let Some(Some(picked)) = hear.recv().await else {
        // **아무 일도 일어나지 않았다.** 지금 Project 도 마지막 View 도 그대로다.
        return Ok(None);
    };
    let Ok(root) = picked.into_path() else {
        return Err(Refusal::new("unreadable", "고른 자리를 알 수 없다"));
    };

    // 자리를 펴고 열어 보는 일은 **파일을 만지는 일**이다. worker 로 넘긴다.
    let Some(root) = off_the_loop(move || {
        if !root.is_dir() {
            return Ok(None); // 폴더가 아니면 고른 적 없는 것과 같다
        }
        // 같은 폴더가 늘 같은 주소를 받도록 심볼릭 링크를 펴 둔다.
        let root = std::fs::canonicalize(&root).unwrap_or(root);
        // **여기서 한 번 열어 본다.** 열리지 않는 자리를 목록에 넣지 않는다.
        openable(&root)?;
        Ok(Some(root))
    })
    .await?
    else {
        return Ok(None);
    };

    // 읽기가 끝난 뒤에야 등록부를 건드린다 — 잠금은 이 몇 줄 동안만 산다.
    let scope_id = scope_of(&root);
    let label = Registry::name_for(&root);
    registry.remember(&scope_id, &root, &label)?;
    Ok(Some(Picked { scope_id, label, unavailable: None }))
}

/// 지금까지 사람이 연 Project 들 — **scope 와 이름뿐.**
#[tauri::command]
pub fn list_projects(registry: State<'_, Registry>) -> Vec<Picked> {
    registry.listed()
}

/// 이 창이 시작할 때 사람이 알아야 하는 것.
///
/// 마지막으로 보던 Project 가 무엇이었는지와, 설정을 읽지 못했다면 그 사실이다. 화면은
/// 이것을 받아 **그 하나만** 연다 — 등록된 모든 Project 를 읽지 않는다(§9.1.2).
#[derive(Serialize, Debug)]
pub struct Opening {
    last_selected: Option<String>,
    /// 설정을 읽지 못했다 — 이번 실행은 아무것도 적지 않는다.
    #[serde(skip_serializing_if = "Option::is_none")]
    settings_refusal: Option<SettingsSaid>,
}

#[derive(Serialize, Debug)]
pub struct SettingsSaid {
    code: &'static str,
    said: String,
}

#[tauri::command]
pub fn opening(desk: State<'_, crate::settings::Desk>) -> Opening {
    Opening {
        last_selected: desk.read(|settings| settings.last_selected.clone()),
        settings_refusal: desk.refusal().map(|one| SettingsSaid {
            code: one.code(),
            said: one.said(),
        }),
    }
}

/// 창을 앞으로 — **UI 가 부르는 같은 문.**
///
/// 화면 안에서 「창을 보여 줘」가 필요한 자리는 아직 없지만, Agent launcher 와 tray 와
/// 둘째 실행이 지나는 문이 하나라는 것을 UI 쪽에서도 확인할 수 있어야 한다.
#[tauri::command]
pub fn show_window(app: tauri::AppHandle) -> Result<&'static str, Refusal> {
    match crate::lifetime::show_main_window(&app) {
        Ok(crate::lifetime::Shown::Raised) => Ok("raised"),
        // 창이 없어 다시 세웠다 — 조용히 성공하지 않는다.
        Ok(crate::lifetime::Shown::Rebuilt) => Ok("rebuilt"),
        Err(_) => Err(Refusal::new("window_unavailable", "창을 보여 주지 못했다")),
    }
}

/// 목록에서 지운다 — **Companion 설정과 등록부의 한 칸뿐.**
///
/// Project directory · `.gil` · Artifact · Snapshot · Report 는 하나도 건드리지 않는다.
/// 그 자리를 열지도 않는다 — 지우는 데 그 Project 의 사실이 필요하지 않기 때문이다(§9.1.2).
#[tauri::command]
pub fn forget_project(
    app: tauri::AppHandle,
    scope_id: String,
    registry: State<'_, Registry>,
    desk: State<'_, crate::settings::Desk>,
) -> Result<(), Refusal> {
    if !registry.holds(&scope_id) {
        return Err(Refusal::new("unknown_scope", "이 창이 연 Project 가 아니다"));
    }
    registry.forget(&scope_id);
    let wrote = desk.change(|settings| {
        settings.forget(&scope_id);
    });
    // 뺀 것이 보고 있던 것이면 menu bar 는 이제 「선택한 Project 없음」이다.
    crate::tray::say_current(&app);
    wrote.map_err(|_| Refusal::new("settings_unwritable", "설정을 적지 못했다"))
}

/// 이 자리의 **완전한** `MonitorViewV1` 을 canonical JSON 으로.
///
/// Tauri 를 모른다 — 자리 하나를 받아 열고, 읽고, 놓는다. 새로고침도 이 함수를 다시 부르는
/// 것일 뿐이다. 부분 갱신이라는 개념이 없기 때문이다(§8 · §9.1.1-5).
pub fn view_of(root: &Path) -> Result<String, Refusal> {
    let session = opened_at(root)?;
    let seen = session.monitor().map_err(refuse_open)?;
    let view = monitor_view_v1(&seen).map_err(refuse_view)?;
    encode_view_v1(&view).map_err(|_| Refusal::new("damaged", "View 를 JSON 으로 적지 못했다"))
}

/// 이 자리의 Step 하나. 없으면 `None` — **가까운 것을 찾아 주지 않는다**.
pub fn detail_of(root: &Path, step_ref: &str) -> Result<Option<String>, Refusal> {
    // 주소로 읽히지 않는 글자는 Step 이 아니다.
    let Ok(step) = step_ref.parse::<StepRef>() else {
        return Ok(None);
    };
    let session = opened_at(root)?;
    match session.node_detail_v1(step) {
        Ok(detail) => encode_detail_v1(&detail)
            .map(Some)
            .map_err(|_| Refusal::new("damaged", "상세를 JSON 으로 적지 못했다")),
        // **없는 것은 없다.** 이 Project 에 그 Step 이 없다는 사실 그대로.
        Err(DetailError::NotFound { .. }) => Ok(None),
    }
}

/// 열리는 자리인지 한 번 확인한다 — 열리지 않는 곳을 목록에 넣지 않는다.
pub fn openable(root: &Path) -> Result<(), Refusal> {
    let session = opened_at(root)?;
    drop(session); // 잠금을 곧바로 놓는다 — 사람의 `gil` 명령을 막지 않는다
    Ok(())
}

#[tauri::command]
pub async fn load_view(
    app: tauri::AppHandle,
    scope_id: String,
    registry: State<'_, Registry>,
    desk: State<'_, crate::settings::Desk>,
) -> Result<String, Refusal> {
    // 자리만 복제하고 잠금을 놓는다. `root_of` 안에서 guard 가 떨어진다.
    let root = registry.root_of(&scope_id)?;
    let view = off_the_loop(move || view_of(&root)).await?;

    // **여기까지 왔을 때만** 마지막 선택과 차례를 갈아 끼운다(§9.1.2).
    //
    // 고른 것과 읽은 것은 다르다. 열지 못한 Project 가 마지막 정상 선택을 덮으면, 다음
    // 시작에서 창은 열리지 않는 자리를 먼저 연다.
    if let Some((seat, label)) = registry.seat_of(&scope_id) {
        let _ = desk.change(|settings| {
            settings.touch(&scope_id, &seat, &label);
            settings.last_selected = Some(scope_id.clone());
        });
        // menu bar 가 말하는 이름도 따라간다 — 두 자리가 다른 말을 하면 안 된다.
        crate::tray::say_current(&app);
    }
    Ok(view)
}

/// 고른 Step 하나의 `NodeDetailV1`.
///
/// **다른 Project 나 가까운 Step 으로 물러서지 않는다**(§7 · §9.1.1-4). scope 가 이 창이 모르는
/// 것이면 `unknown_scope`, 그 Project 에 그 Step 이 없으면 `null` 이다. 두 경우 모두 답은
/// 「없다」이지 다른 무엇이 아니다.
#[tauri::command]
pub async fn load_detail(
    scope_id: String,
    step_ref: String,
    registry: State<'_, Registry>,
) -> Result<Option<String>, Refusal> {
    let root = registry.root_of(&scope_id)?;
    off_the_loop(move || detail_of(&root, &step_ref)).await
}

#[cfg(test)]
mod tests {
    use super::*;

    // 바이트가 그대로인지 재는 시험은 `tests/companion.rs` 에 있다 — 거기서는 진짜 GIL
    // Project 를 세울 수 있고, 이 파일이 부르는 것과 **같은 네 걸음**을 그대로 밟는다.

    fn scratch(label: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("gil-adapter-{label}"));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).expect("자리를 만든다");
        dir
    }

    #[test]
    fn a_folder_without_a_walk_is_not_a_project_and_says_so() {
        let dir = scratch("bare");
        let refused = view_of(&dir).expect_err("걷기가 없는 자리다");
        assert_eq!(refused.code, "not_a_project");
        assert!(!refused.said.is_empty(), "사람에게 보일 말이 비었다");
    }

    #[test]
    fn a_missing_folder_is_refused_and_does_not_create_anything() {
        let dir = scratch("gone").join("없는-자리");
        let refused = view_of(&dir).expect_err("없는 자리다");
        assert_eq!(refused.code, "not_a_project");
        // **거절이 자리를 만들지 않는다.**
        assert!(!dir.exists(), "거절하면서 폴더를 만들었다");
    }

    #[test]
    fn the_same_folder_always_gets_the_same_name_and_others_never_do() {
        let one = scratch("scope-one");
        let other = scratch("scope-other");
        // 몇 번을 불러도 같다 — 창을 껐다 켜도 같다는 말과 같은 뜻이다. 이 함수는 시각도
        // 난수도 실행 순서도 보지 않고 **경로 하나만** 본다.
        assert_eq!(scope_of(&one), scope_of(&one), "같은 자리가 다른 이름을 받았다");
        assert_eq!(scope_of(&one), scope_of(&one.clone()), "부를 때마다 달라졌다");
        assert_ne!(scope_of(&one), scope_of(&other), "다른 자리가 같은 이름을 받았다");
    }

    #[test]
    fn a_symlink_to_the_same_root_is_the_same_project() {
        let real = scratch("scope-real");
        let link = std::env::temp_dir().join("gil-adapter-scope-link");
        let _ = std::fs::remove_file(&link);
        std::os::unix::fs::symlink(&real, &link).expect("링크를 건다");

        // adapter 가 하는 것과 같은 걸음 — 먼저 편다.
        let through = |at: &Path| scope_of(&std::fs::canonicalize(at).expect("편다"));
        assert_eq!(
            through(&real),
            through(&link),
            "같은 자리를 가리키는 링크가 다른 Project 가 되었다"
        );
        let _ = std::fs::remove_file(&link);
    }

    #[test]
    fn the_scope_is_a_whole_sha256_and_carries_no_path() {
        let root = scratch("scope-shape");
        let name = scope_of(&root);
        let digest = name.strip_prefix("project:").expect("project: 로 시작한다");

        // **자르지 않은 SHA-256 이다.** 64자리 hex — 앞자리만 쓰면 충돌을 가정에서 지울 수 없다.
        assert_eq!(digest.len(), 64, "{name} 이 64자리가 아니다");
        assert!(digest.chars().all(|c| c.is_ascii_hexdigit()), "{name} 이 hex 가 아니다");
        assert!(digest.chars().all(|c| !c.is_ascii_uppercase()), "hex 가 소문자가 아니다");

        // 그리고 **경로 원문이 한 조각도 들어 있지 않다**(§10).
        let path = root.display().to_string();
        assert!(!name.contains(&path), "경로가 통째로 새어 나왔다");
        for piece in path.split(['/', '-', '_', '.']).filter(|one| one.len() >= 4) {
            assert!(!name.contains(piece), "경로 조각 {piece:?} 가 새어 나왔다");
        }

        // 그 값은 canonical root 바이트의 SHA-256 **그대로**다 — 다른 재료를 섞지 않는다.
        let mut expected = Sha256::new();
        expected.update(root.as_os_str().as_encoded_bytes());
        assert_eq!(digest, format!("{:x}", expected.finalize()));
    }

    // ── 등록부의 경계 ──────────────────────────────────────────────

    #[test]
    fn two_different_roots_that_land_on_one_scope_are_refused_not_merged() {
        let registry = Registry::default();
        let one = scratch("collide-one");
        let other = scratch("collide-other");
        // **일부러 같은 주소를 준다.** SHA-256 으로 이 상황을 만들 수는 없으므로, 계산된
        // scope 를 건네받는 틈으로 그 상황 자체를 세운다. production 의 해시는 그대로다.
        let forced = "project:같은주소가나왔다고치자";

        assert_eq!(
            registry.remember(forced, &one, "one").expect("첫 자리"),
            Entered::Fresh
        );
        let refused = registry
            .remember(forced, &other, "other")
            .expect_err("다른 자리가 같은 주소를 받았다");
        assert_eq!(refused.code, "scope_collision");

        // **합쳐지지 않았다** — 등록부에는 먼저 든 자리 하나뿐이다.
        let listed = registry.listed();
        assert_eq!(listed.len(), 1, "두 자리가 한 칸에 섞였다");
        assert_eq!(listed[0].label, "one");
        // 그리고 그 scope 가 가리키는 자리는 여전히 첫 번째다.
        assert_eq!(registry.root_of(forced).expect("자리"), one);
    }

    #[test]
    fn registering_the_same_root_again_reuses_the_entry() {
        let registry = Registry::default();
        let root = scratch("again");
        let scope = scope_of(&root);

        assert_eq!(registry.remember(&scope, &root, "다시").expect("첫 번째"), Entered::Fresh);
        for _ in 0..3 {
            assert_eq!(
                registry.remember(&scope, &root, "다시").expect("또 골라도"),
                Entered::Already,
                "같은 자리를 다시 골랐는데 새 칸이 생겼다"
            );
        }
        assert_eq!(registry.listed().len(), 1, "같은 자리가 여러 칸이 되었다");
    }

    #[test]
    fn two_projects_with_the_same_display_name_stay_apart() {
        let registry = Registry::default();
        // 이름이 같은 두 자리 — 흔한 일이다(`~/a/gil` 과 `~/b/gil`).
        let first = scratch("same-name-a").join("일감");
        let second = scratch("same-name-b").join("일감");
        std::fs::create_dir_all(&first).expect("자리");
        std::fs::create_dir_all(&second).expect("자리");
        assert_eq!(Registry::name_for(&first), Registry::name_for(&second));

        registry
            .remember(&scope_of(&first), &first, &Registry::name_for(&first))
            .expect("첫 자리");
        registry
            .remember(&scope_of(&second), &second, &Registry::name_for(&second))
            .expect("둘째 자리");

        let listed = registry.listed();
        assert_eq!(listed.len(), 2, "이름이 같다고 한 칸이 되었다");
        assert_ne!(listed[0].scope_id, listed[1].scope_id, "주소까지 같아졌다");
        // **주소로 정확히 갈린다** — 이름이 같아도 서로의 자리를 내주지 않는다.
        assert_eq!(registry.root_of(&scope_of(&first)).expect("자리"), first);
        assert_eq!(registry.root_of(&scope_of(&second)).expect("자리"), second);
    }

    #[test]
    fn nothing_that_leaves_the_registry_carries_a_path() {
        let registry = Registry::default();
        let root = scratch("no-path-out").join("보이는이름");
        std::fs::create_dir_all(&root).expect("자리");
        let scope = scope_of(&root);
        registry.remember(&scope, &root, &Registry::name_for(&root)).expect("든다");

        // 화면으로 나가는 것은 이 둘뿐이고, 그 안에 절대경로가 없다.
        let listed = serde_json::to_string(&registry.listed()).expect("옮긴다");
        let picked = serde_json::to_string(&Picked {
            scope_id: scope.clone(),
            label: Registry::name_for(&root),
            unavailable: None,
        })
        .expect("옮긴다");

        let absolute = root.display().to_string();
        for said in [&listed, &picked, &scope] {
            assert!(!said.contains(&absolute), "절대경로가 실렸다: {said}");
            // 위쪽 디렉터리 이름도 한 조각도 새어 나가지 않는다. 마지막 한 조각만
            // **사람이 읽을 이름**으로 허락된다.
            for parent in root.parent().into_iter().flat_map(|at| at.components()) {
                let piece = parent.as_os_str().to_string_lossy().into_owned();
                if piece.len() >= 4 {
                    assert!(!said.contains(&piece), "경로 조각 {piece:?} 가 실렸다: {said}");
                }
            }
        }
        assert!(listed.contains("보이는이름"), "사람이 읽을 이름이 빠졌다");
    }

    #[test]
    fn a_refusal_never_carries_an_absolute_path() {
        let bare = scratch("refusal-no-path");
        let nested = bare.join("아래").join("더-아래");
        std::fs::create_dir_all(&nested).expect("자리");

        for at in [&bare, &nested] {
            let refused = view_of(at).expect_err("걷기가 없는 자리다");
            let absolute = at.display().to_string();
            assert!(
                !refused.said.contains(&absolute),
                "거절에 절대경로가 실렸다: {}",
                refused.said
            );
            for piece in absolute.split('/').filter(|one| one.len() >= 4) {
                assert!(
                    !refused.said.contains(piece),
                    "거절에 경로 조각 {piece:?} 가 실렸다: {}",
                    refused.said
                );
            }
            assert!(!refused.said.is_empty(), "사람에게 보일 말이 비었다");
        }
    }

    #[test]
    fn an_unknown_scope_is_refused_without_saying_where_anything_lives() {
        let registry = Registry::default();
        let refused = registry.root_of("project:없는주소").expect_err("모르는 주소");
        assert_eq!(refused.code, "unknown_scope");
        assert!(!refused.said.contains('/'), "자리를 흘렸다: {}", refused.said);
    }

    // ── event loop 를 막지 않는다 ──────────────────────────────────

    /// 주석을 걷어낸 코드만 — `//!`·`//` 줄과 `/* */` 덩이를 지운다.
    fn without_comments(source: &str) -> String {
        let mut text = String::with_capacity(source.len());
        let mut rest = source;
        while let Some(open) = rest.find("/*") {
            text.push_str(&rest[..open]);
            match rest[open..].find("*/") {
                Some(close) => rest = &rest[open + close + 2..],
                None => {
                    rest = "";
                    break;
                }
            }
        }
        text.push_str(rest);
        text.lines()
            .map(|line| match line.find("//") {
                Some(at) => &line[..at],
                None => line,
            })
            .collect::<Vec<_>>()
            .join("\n")
    }

    /// 이 파일에서 **실제로 도는 코드**만 — 주석도, 시험 자신도 뺀다.
    ///
    /// 시험 안에는 금지된 이름이 글자로 적혀 있다(무엇을 금지하는지 말해야 하므로).
    /// 그것을 세면 시험이 제 꼬리를 문다.
    fn running_code() -> String {
        let source = include_str!("adapter.rs");
        let body = source
            .split_once("#[cfg(test)]")
            .map(|(before, _)| before)
            .unwrap_or(source);
        without_comments(body)
    }

    #[test]
    fn no_command_waits_for_a_dialog_on_the_event_loop() {
        let code = running_code();

        // **부르는 자리가 하나도 없다.** 계보를 적은 주석에는 그 이름이 나온다 — 그것을
        // 걷어냈다는 사실이야말로 이 시험이 지키려는 것이다(2026-09-12 실측).
        for forbidden in [
            "blocking_pick_folder",
            "blocking_pick_file",
            "block_on(",
            "blocking_recv(",
        ] {
            assert!(!code.contains(forbidden), "{forbidden} 을 부르는 자리가 있다");
        }

        // 그리고 사람을 기다리는 command 는 전부 `async` 다.
        for name in ["pub async fn pick_project", "pub async fn load_view", "pub async fn load_detail"] {
            assert!(code.contains(name), "{name} 가 async 가 아니다");
        }
        // 파일을 만지는 일은 worker 경계를 지난다 — 셋 다.
        assert!(code.contains("spawn_blocking"), "worker 경계가 없다");
        assert_eq!(
            code.matches("off_the_loop(").count(),
            3,
            "pick_project · load_view · load_detail 셋 다 worker 를 거쳐야 한다"
        );
        // 그리고 GIL 을 여는 세 함수는 **worker 밖에서 불리지 않는다** — async 인 자리에
        // 그 이름이 직접 나오면 event loop 위에서 파일을 만진다는 뜻이다.
        for (command, opens) in [
            ("pub async fn pick_project", "openable("),
            ("pub async fn load_view", "view_of("),
            ("pub async fn load_detail", "detail_of("),
        ] {
            let body = code
                .split_once(command)
                .expect("그 command")
                .1;
            let head = &body[..body.find("\n}").unwrap_or(body.len())];
            let at = head.find(opens).expect("여는 자리");
            let wrapped = head[..at].rfind("off_the_loop(").is_some();
            assert!(wrapped, "{command} 가 {opens} 를 worker 밖에서 부른다");
        }
    }

    /// **잠금은 `await` 를 건너지 않는다** — 컴파일러가 그것을 지킨다.
    ///
    /// Tauri 의 async command 는 `Send` future 를 요구한다. `std::sync::MutexGuard` 가
    /// `await` 너머까지 살아 있으면 future 가 `!Send` 가 되어 **컴파일이 되지 않는다**.
    /// 그러니 이 crate 가 빌드된다는 사실이 곧 증거다. 여기서는 잠금을 만지는 함수가
    /// 전부 `async` 가 아님을 적어 두어, 누가 그것을 `async` 로 바꾸는 순간 눈에 띄게 한다.
    /// **설정을 적는 것은 살아 있는 창 하나뿐이다.**
    ///
    /// plugin 의 setup 은 등록 차례대로 돈다. single-instance 가 가장 먼저 서야, 이미 창이
    /// 하나 떠 있을 때 둘째 실행이 **그 자리에서 끝난다** — 앱의 `.setup()` 에 닿지 못하므로
    /// `Desk` 를 만들지도, 설정을 적지도 못한다. 차례가 뒤집히면 두 프로세스가 같은 파일을
    /// 두고 다투고, 마지막에 적은 쪽이 남의 변경을 지운다.
    ///
    /// 둘째 실행이 **무엇을 하는가**는 `lifetime.rs` 의 시험이 지킨다 — 그 일이 거기 살기
    /// 때문이다. 여기서는 **차례**만 본다.
    #[test]
    fn the_single_instance_guard_stands_before_anything_that_writes() {
        let main = include_str!("main.rs");
        let code = {
            let body = main.split_once("#[cfg(test)]").map(|(one, _)| one).unwrap_or(main);
            without_comments(body)
        };

        let guard = code.find("single_instance").expect("single-instance 가 없다");
        let desk = code.find("Desk::open").expect("설정을 여는 자리가 없다");
        assert!(guard < desk, "설정을 연 뒤에 single-instance 가 선다");
        let window = code.find("window::build").expect("창을 세우는 자리가 없다");
        assert!(guard < window, "창을 세운 뒤에 single-instance 가 선다");

        // **모든 plugin 중 첫 번째**다.
        let first = code.find(".plugin(").expect("plugin 이 없다");
        assert!(
            code[first..first + 80].contains("single_instance"),
            "single-instance 가 첫 plugin 이 아니다"
        );

        // 그 자리에서 Project 를 짐작하거나 읽지 않는다.
        let hand = &code[guard..desk];
        for forbidden in ["argv[", "argv.", "cwd.", "remember(", "openable("] {
            assert!(!hand.contains(forbidden), "둘째 실행이 {forbidden} 를 만진다");
        }
        for forbidden in ["view_of(", "detail_of(", "ProjectSession", "STATE_PATH"] {
            assert!(!hand.contains(forbidden), "둘째 실행이 {forbidden} 로 Project 를 읽는다");
        }
    }

    /// 창의 자리를 적는 길은 **하나**이고, 그 길은 정상 자리 규칙을 지난다.
    #[test]
    fn the_window_geometry_is_only_ever_written_through_the_normal_geometry_rule() {
        let source = include_str!("window.rs");
        let code = {
            let body = source.split_once("#[cfg(test)]").map(|(one, _)| one).unwrap_or(source);
            without_comments(body)
        };
        // `settings.window = …` 은 `remember(…)` 말고 다른 것을 받지 않는다.
        // 줄 단위로 보지 않는다 — 대입이 두 줄에 걸칠 수 있다.
        let mut at = 0usize;
        let mut writes = 0usize;
        while let Some(found) = code[at..].find("settings.window =") {
            let start = at + found;
            let span = &code[start..(start + 160).min(code.len())];
            assert!(
                span.contains("remember("),
                "정상 자리 규칙을 지나지 않고 적는다: {}",
                span.lines().take(2).collect::<Vec<_>>().join(" ")
            );
            writes += 1;
            at = start + 1;
        }
        assert_eq!(writes, 1, "창의 자리를 적는 자리가 {writes}곳이다");
        assert_eq!(
            code.matches("geometry::remember(").count(),
            1,
            "정상 자리 규칙을 부르는 자리가 둘 이상이다"
        );

        // 그리고 **다른 어느 파일도** 창의 자리를 직접 적지 않는다.
        for other in [include_str!("main.rs"), include_str!("tray.rs"), include_str!("adapter.rs")] {
            let body = other.split_once("#[cfg(test)]").map(|(one, _)| one).unwrap_or(other);
            assert!(
                !without_comments(body).contains("settings.window ="),
                "창의 자리를 적는 자리가 window.rs 밖에 있다"
            );
        }
    }

    #[test]
    fn the_registry_lock_never_crosses_an_await() {
        let code = running_code();
        for line in code.lines() {
            if !line.contains(".lock()") {
                continue;
            }
            assert!(!line.contains(".await"), "잠금과 await 가 한 줄에 있다: {line}");
        }
        // 잠금을 쥐는 세 함수는 동기다. 동기 함수 안에는 `await` 가 있을 수 없다.
        for sync in [
            "pub fn remember(",
            "pub fn listed(",
            "fn root_of(",
        ] {
            assert!(code.contains(sync), "{sync} 가 사라졌거나 async 가 되었다");
        }
    }

    // ── 설정에서 되살리기 ──────────────────────────────────────────

    use crate::settings::{CompanionSettings, SavedProject};

    /// **앱을 껐다 켜는 일**을 흉내 낸다 — 설정 파일 하나만 남기고 전부 새로 만든다.
    fn restart(dir: &Path) -> (Registry, crate::settings::Desk) {
        let desk = crate::settings::Desk::open(dir);
        let registry = Registry::default();
        let saved = desk.read(|one| one.projects.clone());
        restore_registry(&registry, &saved);
        (registry, desk)
    }

    #[test]
    fn restarting_brings_back_the_list_and_the_last_good_selection() {
        let config = scratch("restart-config");
        let one = std::fs::canonicalize(scratch("restart-one")).expect("편다");
        let other = std::fs::canonicalize(scratch("restart-two")).expect("편다");

        // 첫 실행 — 둘을 들이고, 둘째를 성공적으로 읽었다고 하자.
        {
            let (registry, desk) = restart(&config);
            for (root, label) in [(&one, "하나"), (&other, "둘")] {
                let scope = scope_of(root);
                registry.remember(&scope, root, label).expect("든다");
                desk.change(|settings| settings.touch(&scope, root, label)).expect("적는다");
            }
            desk.change(|settings| settings.last_selected = Some(scope_of(&other)))
                .expect("적는다");
        }

        // **껐다 켰다.** 설정 파일 말고는 아무것도 이어지지 않는다.
        let (registry, desk) = restart(&config);
        let listed = registry.listed();
        assert_eq!(listed.len(), 2, "목록이 돌아오지 않았다");
        // 가장 최근에 쓴 것이 앞이다.
        assert_eq!(listed[0].label, "둘");
        assert_eq!(listed[1].label, "하나");
        assert!(listed.iter().all(|one| one.unavailable.is_none()), "멀쩡한데 못 쓴다고 한다");
        assert_eq!(
            desk.read(|settings| settings.last_selected.clone()),
            Some(scope_of(&other)),
            "마지막 선택이 돌아오지 않았다"
        );
        // 그리고 그 하나는 실제로 열 수 있다.
        assert_eq!(registry.root_of(&scope_of(&other)).expect("자리"), other);
    }

    #[test]
    fn a_failed_open_never_overwrites_the_last_good_selection() {
        let config = scratch("restart-keep-selection");
        let good = std::fs::canonicalize(scratch("restart-good")).expect("편다");
        let (registry, desk) = restart(&config);
        let good_scope = scope_of(&good);
        registry.remember(&good_scope, &good, "좋은 것").expect("든다");
        desk.change(|settings| {
            settings.touch(&good_scope, &good, "좋은 것");
            settings.last_selected = Some(good_scope.clone());
        })
        .expect("적는다");

        // 열리지 않는 자리를 골랐다 — 목록에 들어가지도 못한다.
        let bad = scratch("restart-bad");
        assert!(openable(&bad).is_err(), "걷기가 없는 자리가 열렸다");
        // 그리고 고르개를 취소했다 — 아무 일도 없었다.

        // **마지막 정상 선택이 그대로다.**
        assert_eq!(
            desk.read(|settings| settings.last_selected.clone()),
            Some(good_scope.clone()),
            "열지 못한 Project 가 마지막 선택을 덮었다"
        );
        let order: Vec<String> =
            desk.read(|settings| settings.projects.iter().map(|one| one.label.clone()).collect());
        assert_eq!(order, ["좋은 것"], "MRU 가 바뀌었다");
    }

    #[test]
    fn a_saved_project_that_is_still_there_comes_back_usable() {
        let registry = Registry::default();
        let root = std::fs::canonicalize(scratch("restore-alive")).expect("편다");
        let saved = vec![SavedProject {
            root: root.clone(),
            scope_id: scope_of(&root),
            label: "살아 있다".to_string(),
        }];

        assert_eq!(restore_registry(&registry, &saved), 1, "쓸 수 있는 칸이 없다");
        let listed = registry.listed();
        assert_eq!(listed.len(), 1);
        assert_eq!(listed[0].unavailable, None, "멀쩡한 자리가 못 쓴다고 적혔다");
        assert_eq!(registry.root_of(&saved[0].scope_id).expect("자리"), root);
    }

    #[test]
    fn a_project_that_moved_away_is_unavailable_and_never_falls_back() {
        let registry = Registry::default();
        let gone = scratch("restore-gone");
        let scope = scope_of(&gone);
        std::fs::remove_dir_all(&gone).expect("치운다");
        // 그리고 멀쩡한 Project 가 옆에 하나 있다 — **그쪽으로 물러서면 안 된다.**
        let alive = std::fs::canonicalize(scratch("restore-neighbour")).expect("편다");

        let saved = vec![
            SavedProject { root: gone.clone(), scope_id: scope.clone(), label: "사라진 것".into() },
            SavedProject {
                root: alive.clone(),
                scope_id: scope_of(&alive),
                label: "옆의 것".into(),
            },
        ];
        assert_eq!(restore_registry(&registry, &saved), 1, "살아 있는 칸이 하나여야 한다");

        let listed = registry.listed();
        assert_eq!(listed.len(), 2, "사라진 항목을 목록에서 지웠다");
        assert_eq!(listed[0].unavailable, Some("project_missing"));
        assert_eq!(listed[1].unavailable, None);

        // **열어 달라고 해도 다른 자리를 주지 않는다.**
        let refused = registry.root_of(&scope).expect_err("사라진 자리다");
        assert_eq!(refused.code, "project_missing");
        assert!(!refused.said.contains('/'), "거절에 자리가 실렸다: {}", refused.said);
    }

    #[test]
    fn a_folder_that_now_holds_a_different_project_is_not_merged() {
        let registry = Registry::default();
        let root = std::fs::canonicalize(scratch("restore-swapped")).expect("편다");
        // 저장해 둔 주소가 지금 계산되는 것과 다르다 — 그 자리에 다른 것이 있다는 뜻이다.
        let saved = vec![SavedProject {
            root: root.clone(),
            scope_id: "project:옛날에적어둔다른주소".to_string(),
            label: "바뀐 것".to_string(),
        }];
        assert_eq!(restore_registry(&registry, &saved), 0, "합쳐 버렸다");

        let listed = registry.listed();
        assert_eq!(listed[0].unavailable, Some("project_moved"));
        let refused = registry.root_of("project:옛날에적어둔다른주소").expect_err("못 연다");
        assert_eq!(refused.code, "project_moved");
    }

    #[test]
    fn the_saved_order_is_the_order_the_window_shows() {
        let registry = Registry::default();
        let mut saved = Vec::new();
        for name in ["셋", "둘", "하나"] {
            let root = std::fs::canonicalize(scratch(&format!("order-{name}"))).expect("편다");
            saved.push(SavedProject {
                root: root.clone(),
                scope_id: scope_of(&root),
                label: name.to_string(),
            });
        }
        restore_registry(&registry, &saved);
        let shown: Vec<String> = registry.listed().into_iter().map(|one| one.label).collect();
        assert_eq!(shown, ["셋", "둘", "하나"], "저장된 차례를 잃었다");
    }

    #[test]
    fn forgetting_a_project_removes_only_the_entry() {
        let registry = Registry::default();
        let root = std::fs::canonicalize(scratch("forget-one")).expect("편다");
        let scope = scope_of(&root);
        registry.remember(&scope, &root, "지울 것").expect("든다");
        assert!(registry.holds(&scope));

        assert!(registry.forget(&scope), "지우지 못했다");
        assert!(!registry.holds(&scope));
        assert!(registry.listed().is_empty());
        // **자리는 그대로 있다.** 지운 것은 이름뿐이다.
        assert!(root.is_dir(), "Project 폴더가 사라졌다");
    }

    #[test]
    fn settings_and_registry_agree_on_what_was_forgotten() {
        let registry = Registry::default();
        let mut settings = CompanionSettings::default();
        let mut scopes = Vec::new();
        for name in ["가", "나"] {
            let root = std::fs::canonicalize(scratch(&format!("pair-{name}"))).expect("편다");
            let scope = scope_of(&root);
            settings.touch(&scope, &root, name);
            scopes.push(scope);
        }
        settings.last_selected = Some(scopes[0].clone());
        restore_registry(&registry, &settings.projects);

        registry.forget(&scopes[0]);
        settings.forget(&scopes[0]);

        assert_eq!(registry.listed().len(), 1);
        assert_eq!(settings.projects.len(), 1);
        // 지운 것이 보고 있던 것이면 **빈 선택**으로 간다.
        assert_eq!(settings.last_selected, None, "남은 것을 골라 버렸다");
    }

    #[test]
    fn a_step_address_that_is_not_an_address_is_simply_absent() {
        let dir = scratch("bad-ref");
        // 자리를 열기도 전에 「주소가 아니다」로 끝난다 — 비슷한 Step 을 찾지 않는다.
        assert_eq!(detail_of(&dir, "이건 주소가 아니다").expect("거절이 아니다"), None);
        assert_eq!(detail_of(&dir, "").expect("거절이 아니다"), None);
    }
}

// ── 설정에서 되살리기 ──────────────────────────────────────────────────
//
// Host UI Model §9.1.2. 시작할 때 하는 일은 **설정을 읽는 것뿐**이고, 등록해 두었다는
// 이유로 모든 Project 의 Graph 나 Artifact 세계를 읽지 않는다.

/// 저장해 둔 목록을 등록부로 되살린다 — **파일 하나도 열지 않는다.**
///
/// 하는 일은 자리를 다시 펴서(`canonicalize`) 주소를 **다시 계산**하는 것뿐이다.
///
/// ```text
///   자리가 없다            → unavailable("project_missing")
///   주소가 달라졌다         → unavailable("project_moved")   ← 합치지 않는다
///   같다                   → 쓸 수 있는 칸
/// ```
///
/// 저장된 주소를 믿고 합치지 않는 이유는 하나다. 그 자리에 지금 **다른 Project 가** 있을 수
/// 있고, 그러면 사람이 등록해 둔 것과 화면이 보여 주는 것이 달라진다(§9.1.2).
pub fn restore_registry(
    registry: &Registry,
    saved: &[crate::settings::SavedProject],
) -> usize {
    let mut alive = 0;
    for (order, one) in saved.iter().enumerate() {
        let (root, unavailable) = match std::fs::canonicalize(&one.root) {
            Err(_) => (one.root.clone(), Some("project_missing")),
            Ok(found) => {
                if scope_of(&found) == one.scope_id {
                    alive += 1;
                    (found, None)
                } else {
                    // **같은 Project 로 합치지 않는다.** 주소가 곧 그 자리이기 때문이다.
                    (found, Some("project_moved"))
                }
            }
        };
        registry.restore(&one.scope_id, &root, &one.label, order, unavailable);
    }
    alive
}
