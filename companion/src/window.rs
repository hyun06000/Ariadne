//! **창을 세우고, 그 자리를 기억한다.**
//!
//! 창을 만드는 자리가 하나여야 하는 이유는 [`crate::lifetime`] 이 말한 것과 같다 — 두 벌로
//! 두면 어느 길로 선 창은 문이 달려 있고 어느 길로 선 창은 없다.

use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager, WebviewWindow};

use crate::geometry;
use crate::lifetime::MAIN;
use crate::settings;

/// 창이 움직이는 동안 매 event 마다 적지 않는다 — 이만큼 잠잠해지면 한 번 적는다.
const SETTLE: Duration = Duration::from_millis(600);

/// 마지막으로 본 창의 상태와 언제 보았는가. 끝내기 전에 이 값을 눕힌다.
#[derive(Default)]
pub struct LastSeen {
    at: Mutex<Option<(Seen, Instant)>>,
}

/// 방금 창에서 읽은 그대로 — **아직 판단하지 않은 값**이다.
///
/// 이것을 마지막 정상 자리에 어떻게 반영할지는 [`geometry::remember`] 가 정한다. 창을 보는
/// 일과 무엇을 기억할지 정하는 일을 갈라 두면, 뒤의 것을 창 없이도 잴 수 있다.
#[derive(Clone, Copy)]
pub struct Seen {
    position: Option<[f64; 2]>,
    size: [f64; 2],
    maximized: bool,
}

/// 지금 창이 어디에 어떤 크기로 있는가 — **logical pixel** 로.
pub fn where_it_sits(window: &WebviewWindow) -> Option<Seen> {
    let scale = window.scale_factor().ok()?;
    let size = window.inner_size().ok()?.to_logical::<f64>(scale);
    let position = window
        .outer_position()
        .ok()
        .map(|at| at.to_logical::<f64>(scale))
        .map(|at| [at.x, at.y]);
    Some(Seen {
        position,
        size: [size.width, size.height],
        maximized: window.is_maximized().unwrap_or(false),
    })
}

/// 방금 본 것을 설정에 반영한다 — **정상 자리를 덮지 않는 규칙**을 지나서.
pub fn keep(desk: &settings::Desk, seen: Seen) {
    let _ = desk.change(|settings| {
        settings.window =
            geometry::remember(settings.window, seen.position, seen.size, seen.maximized);
    });
}

/// 지금 창이 서 있는 자리를 설정에 반영한다 — 숨기기 직전에 부른다.
pub fn keep_now(app: &AppHandle) {
    let Some(window) = app.get_webview_window(MAIN) else { return };
    let Some(now) = where_it_sits(&window) else { return };
    keep(&app.state::<settings::Desk>(), now);
}

/// 지금 창의 자리를 **곧바로** 눕힌다 — 미뤄 둔 것을 삼키지 않고.
///
/// 끝내기 직전에 부른다. debounce 는 「잠잠해지면 적는다」인데, 끝나는 순간에는 잠잠해질
/// 시간이 없다. 그래서 미뤄 둔 값을 여기서 거둔다.
pub fn flush_now(app: &AppHandle) {
    let desk = app.state::<settings::Desk>();

    // **미뤄 둔 값이 먼저다.**
    //
    // 그 값은 창이 멀쩡히 살아 있을 때 잰 것이다. 끝나는 순간의 창은 이미 허물어지는
    // 중이라, 그때 다시 재면 화면에 없는 크기나 뒤집힌 최대화 상태를 읽는다(2026-09-14
    // 실측: 520×900 이던 창이 종료 시각에 380×505·maximized 로 읽혔다).
    //
    // 움직인 적이 한 번도 없으면 미뤄 둔 값이 없다. 그때만, 그리고 창이 아직 보일 때만
    // 직접 잰다 — 처음 연 자리를 기억하기 위해서다.
    let last = app
        .state::<LastSeen>()
        .at
        .lock()
        .expect("마지막 자리")
        .map(|(one, _)| one)
        .or_else(|| {
            let window = app.get_webview_window(MAIN)?;
            window.is_visible().ok().filter(|visible| *visible)?;
            where_it_sits(&window)
        });
    match last {
        Some(seen) => keep(&desk, seen),
        None => {
            let _ = desk.flush();
        }
    }
    // 미뤄 둔 것을 비운다 — 다시 적을 일이 없다.
    *app.state::<LastSeen>().at.lock().expect("마지막 자리") = None;
}

/// 창에 한마디 전한다 — **사실이 아니라 이 창의 사정**이다.
///
/// 설정을 적지 못했다거나 자동 시작이 뜻대로 되지 않았다는 것 같은 말이다. Graph 의 사실은
/// 이 길로 다니지 않는다(§8).
pub fn tell(app: &AppHandle, code: &str, said: &str) {
    use tauri::Emitter;
    let _ = app.emit("gil://say", serde_json::json!({ "code": code, "said": said }));
}

/// 창을 세운다 — **이 자리 하나에서만.**
///
/// 설정이 기억하는 정상 자리를 먼저 세우고, 그 위에 최대화를 얹는다(§9.1.2). 문(`host.js`)은
/// 페이지가 실리기 전에 주입한다.
pub fn build(app: &AppHandle) -> Result<WebviewWindow, tauri::Error> {
    let want = app.state::<settings::Desk>().read(|one| one.window);

    // 아직 화면을 모르므로 최소 크기만 지켜 세우고, 선 뒤에 보이는 영역으로 들인다.
    let first = geometry::fit(want, &[]);
    let mut building = tauri::WebviewWindowBuilder::new(app, MAIN, tauri::WebviewUrl::default())
        .title("GIL Companion")
        .inner_size(first.size[0], first.size[1])
        .min_inner_size(geometry::MIN_WIDTH, geometry::MIN_HEIGHT)
        .resizable(true)
        .initialization_script(include_str!("host.js"));
    if let Some(at) = first.position {
        building = building.position(at[0], at[1]);
    }
    let window = building.build()?;

    // 창이 섰으니 이제 화면을 물어 **보이는 영역 안으로** 들인다.
    let fitted = geometry::fit(want, &screens(&window));
    if let Some(at) = fitted.position {
        let _ = window.set_position(tauri::LogicalPosition::new(at[0], at[1]));
    }
    let _ = window.set_size(tauri::LogicalSize::new(fitted.size[0], fitted.size[1]));
    // **정상 자리를 먼저, 최대화는 그 위에.**
    if fitted.maximized {
        let _ = window.maximize();
    }

    watch(app, &window);
    Ok(window)
}

/// 지금 연결된 display 들의 **보이는 영역** — 첫 칸이 기본 display 다.
fn screens(window: &WebviewWindow) -> Vec<geometry::Rect> {
    let primary = window.primary_monitor().ok().flatten();
    let mut seen: Vec<geometry::Rect> = Vec::new();
    let mut push = |monitor: &tauri::Monitor| {
        let scale = monitor.scale_factor();
        let area = monitor.work_area();
        seen.push(geometry::Rect::new(
            area.position.x as f64 / scale,
            area.position.y as f64 / scale,
            area.size.width as f64 / scale,
            area.size.height as f64 / scale,
        ));
    };
    if let Some(first) = &primary {
        push(first);
    }
    for monitor in window.available_monitors().unwrap_or_default() {
        if primary.as_ref().map(|one| one.name()) == Some(monitor.name()) {
            continue;
        }
        push(&monitor);
    }
    seen
}

/// 창에서 나는 일을 듣는다 — 자리를 기억하고, **닫기를 숨김으로 바꾼다.**
fn watch(app: &AppHandle, window: &WebviewWindow) {
    let handle = app.clone();
    window.clone().on_window_event(move |event| match event {
        tauri::WindowEvent::Moved(_) | tauri::WindowEvent::Resized(_) => {
            let Some(window) = handle.get_webview_window(MAIN) else { return };
            let Some(now) = where_it_sits(&window) else { return };
            let seen = handle.state::<LastSeen>();
            let write = {
                let mut at = seen.at.lock().expect("마지막 자리");
                let due = at
                    .as_ref()
                    .map(|(_, when)| when.elapsed() >= SETTLE)
                    .unwrap_or(true);
                *at = Some((now, Instant::now()));
                due
            };
            if write {
                keep(&handle.state::<settings::Desk>(), now);
            }
        }

        // **빨간 버튼과 `⌘W` 는 창을 끝내지 않는다.**
        //
        // 여기서 파괴하면 process 는 살아 있는데 보여 줄 창이 없어진다 — 그 뒤로는 tray 도
        // 둘째 실행도 Agent 도 빈 process 에 말을 걸 뿐이다(2026-09-14 실측).
        //
        // 끝내는 중이라면 가로채지 않는다. 그때는 정말 끝나야 한다.
        tauri::WindowEvent::CloseRequested { api, .. } => {
            if crate::lifetime::is_leaving() {
                return;
            }
            api.prevent_close();
            // **`⌘W` 와 똑같은 문으로 간다.** 두 벌로 두면 한쪽만 설정을 눕힌다.
            let _ = crate::lifetime::hide_main_window(&handle);
        }
        _ => {}
    });
}
