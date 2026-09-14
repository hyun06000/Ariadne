//! **menu bar 의 작은 자리** — 숨어 있는 Companion 을 사람이 다시 찾는 곳.
//!
//! 창을 숨기면 process 는 살아 있지만 화면에는 아무 흔적이 없다. 그 상태에서 사람이 앱을
//! 다시 여는 길은 터미널뿐이었다 — 그것이 제품 UX 일 수 없다.
//!
//! # 여기서 하지 않는 일
//!
//! tray 는 **사실을 읽지 않는다.** 현재 Project 의 이름은 이미 등록부가 지닌 값이고,
//! `새로고침` 은 창에 **hint 한 줄**을 보낼 뿐이다. Node·edge·Report 를 직접 읽거나 부분
//! 갱신을 만들면 화면과 tray 가 서로 다른 사실을 말하게 된다(§8).
//!
//! 그리고 `open`·`close`·`revisit`·`restore` 같은 GIL 쓰기 동작은 두지 않는다 — Companion 은
//! 읽기 전용이다(§9).

use tauri::menu::{CheckMenuItem, Menu, MenuEvent, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager};

use crate::adapter::Registry;
use crate::lifetime;
use crate::settings;

const OPEN: &str = "open";
const CURRENT: &str = "current";
const REFRESH: &str = "refresh";
const AUTOSTART: &str = "autostart";
const QUIT: &str = "quit";

/// 고른 Project 가 없을 때 그 자리에 적는 말. **거짓 이름을 짓지 않는다.**
const NOTHING: &str = "선택한 Project 없음";

/// 지금 보고 있는 Project 의 **사람이 읽을 이름**.
///
/// 절대경로도 canonical root 도 실리지 않는다(§9.1.2 · §10). 이름이 같은 것이 둘 이상이면
/// 화면과 **같은 규칙**으로 짧은 꼬리를 붙인다 — 두 자리가 서로 다른 말을 하면 안 된다.
fn current_name(app: &AppHandle) -> String {
    let chosen = app.state::<settings::Desk>().read(|one| one.last_selected.clone());
    let Some(scope) = chosen else { return NOTHING.to_string() };
    let listed = app.state::<Registry>().listed();
    let Some(here) = listed.iter().find(|one| one.scope_id() == scope) else {
        return NOTHING.to_string();
    };
    let twins = listed.iter().filter(|one| one.label() == here.label()).count();
    if twins < 2 {
        return here.label().to_string();
    }
    let tail: String = scope.split(':').next_back().unwrap_or("").chars().take(6).collect();
    format!("{} ({tail})", here.label())
}

/// menu bar 에 작은 자리를 만든다.
///
/// tray 를 세우지 못하는 자리(지원하지 않는 desktop)에서도 창과 Agent launcher 는 그대로
/// 동작해야 하므로, 실패를 앱의 실패로 삼지 않는다.
pub fn install(app: &AppHandle, autostart_on: bool) -> Result<(), tauri::Error> {
    let open = MenuItem::with_id(app, OPEN, "GIL Companion 열기", true, None::<&str>)?;
    // 상태를 보여 주는 자리다 — 눌러도 Project 를 바꾸지 않는다.
    let current = MenuItem::with_id(app, CURRENT, current_name(app), false, None::<&str>)?;
    let refresh = MenuItem::with_id(app, REFRESH, "새로고침", true, None::<&str>)?;
    let autostart =
        CheckMenuItem::with_id(app, AUTOSTART, "로그인 시 시작", true, autostart_on, None::<&str>)?;
    let quit = MenuItem::with_id(app, QUIT, "종료", true, None::<&str>)?;
    let menu = Menu::with_items(
        app,
        &[
            &open,
            &PredefinedMenuItem::separator(app)?,
            &current,
            &refresh,
            &PredefinedMenuItem::separator(app)?,
            &autostart,
            &PredefinedMenuItem::separator(app)?,
            &quit,
        ],
    )?;

    app.manage(Labels { current: current.clone(), autostart: autostart.clone() });

    // **template 아이콘이다** — 색이 없고 알파만 있다. macOS 의 menu bar 는 밝기에 따라
    // 색이 뒤집히는데, template 로 두면 OS 가 그때그때 칠해 주므로 light·dark 어느 쪽에서도
    // 읽힌다. 색이 든 앱 아이콘을 그대로 쓰면 한쪽에서 뭉개진 덩어리가 된다.
    let mark = tauri::image::Image::from_bytes(include_bytes!("../icons/trayTemplate@2x.png"))
        .unwrap_or_else(|_| app.default_window_icon().expect("앱 아이콘").clone());

    TrayIconBuilder::with_id("gil")
        .icon(mark)
        .icon_as_template(true)
        .tooltip("GIL Companion")
        .menu(&menu)
        // 아이콘을 왼쪽으로 누르면 메뉴가 아니라 **창이 열린다.**
        .show_menu_on_left_click(false)
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                // 기본 클릭도 **같은 문**을 지난다.
                let _ = lifetime::show_main_window(tray.app_handle());
            }
        })
        .on_menu_event(on_menu)
        .build(app)?;
    Ok(())
}

fn on_menu(app: &AppHandle, event: MenuEvent) {
    match event.id().as_ref() {
        OPEN => {
            let _ = lifetime::show_main_window(app);
        }
        REFRESH => {
            // **hint 한 줄뿐이다.** 여기서 Project 를 읽지 않는다 — 창이 제 경계로
            // 완전한 `MonitorViewV1` 을 다시 조회한다(§8 · §9.1.1-5).
            //
            // 창이 숨어 있어도 보낸다. 받는 쪽은 읽기만 하므로 Project 파일이 바뀌지 않는다.
            let _ = app.emit("gil://refresh", ());
        }
        AUTOSTART => crate::autostart::toggle(app),
        QUIT => lifetime::quit(app),
        // 현재 Project 이름은 **상태 표시**다. 눌러도 아무 일도 하지 않는다.
        _ => {}
    }
}

/// tray 가 들고 있는, 글자가 바뀌는 항목들.
///
/// 메뉴를 통째로 다시 세우지 않고 글자만 갈아 끼운다 — 다시 세우면 열려 있던 메뉴가 닫히고
/// check 상태가 흔들린다.
pub struct Labels {
    current: MenuItem<tauri::Wry>,
    autostart: CheckMenuItem<tauri::Wry>,
}

/// 보고 있는 Project 가 바뀌었으니 tray 의 이름도 따라간다.
pub fn say_current(app: &AppHandle) {
    let Some(labels) = app.try_state::<Labels>() else { return };
    let _ = labels.current.set_text(current_name(app));
}

/// OS 에 실제로 등록된 상태를 tray 의 표시에 맞춘다.
pub fn say_autostart(app: &AppHandle, on: bool) {
    let Some(labels) = app.try_state::<Labels>() else { return };
    let _ = labels.autostart.set_checked(on);
}

#[cfg(test)]
mod tests {
    /// 주석을 걷어낸, **실제로 도는 코드**만.
    ///
    /// 줄 **맨 앞**의 `//` 만 지운다. 글자 가운데의 `//` 를 지우면 `"gil://refresh"` 같은
    /// 이름이 반토막 난다 — 실측으로 걸린 자리다.
    fn running(source: &str) -> String {
        let body = source.split_once("#[cfg(test)]").map(|(one, _)| one).unwrap_or(source);
        body.lines()
            .filter(|line| !line.trim_start().starts_with("//"))
            .collect::<Vec<_>>()
            .join("\n")
    }

    /// `marker` 부터 최대 `chars` 글자. **글자 경계에서 자른다** — 한글 한 자가 세 바이트라
    /// 바이트로 자르면 한가운데가 잘려 터진다(실측).
    fn after<'a>(code: &'a str, marker: &str) -> &'a str {
        let at = code.find(marker).unwrap_or_else(|| panic!("{marker} 를 찾지 못했다"));
        &code[at..]
    }

    /// 그 함수의 **본문만** — 다음 함수까지 읽어 엉뚱한 곳에서 걸리지 않게.
    fn body_of<'a>(code: &'a str, marker: &str) -> &'a str {
        let rest = after(code, marker);
        &rest[..rest.find("\n}").map(|at| at + 2).unwrap_or(rest.len())]
    }

    /// **tray 는 사실을 읽지 않는다.**
    ///
    /// 새로고침은 hint 한 줄이고, 창이 제 경계로 완전한 View 를 다시 조회한다(§8). tray 가
    /// Node·edge·Report 를 직접 읽으면 화면과 tray 가 서로 다른 사실을 말하게 된다.
    #[test]
    fn the_tray_sends_a_hint_and_never_reads_the_graph() {
        let code = running(include_str!("tray.rs"));
        for forbidden in [
            "view_of(", "detail_of(", "monitor_view_v1", "ProjectSession", "STATE_PATH",
            "openable(", "encode_view_v1", "NodeDetailV1",
        ] {
            assert!(!code.contains(forbidden), "tray 가 {forbidden} 로 사실을 읽는다");
        }
        // 새로고침이 하는 일은 한 줄 보내는 것뿐이다.
        let arm = after(&code, "REFRESH =>");
        assert!(arm.contains("emit("), "hint 를 보내지 않는다");
        assert!(arm.contains("gil://refresh"), "약속된 이름으로 보내지 않는다");
    }

    /// **GIL 을 바꾸는 동작은 두지 않는다** — Companion 은 읽기 전용이다(§9).
    #[test]
    fn the_tray_offers_no_way_to_change_a_project() {
        let code = running(include_str!("tray.rs"));
        for forbidden in [
            "open_cycle", "close_step", "close_cycle", "revisit", "restore",
            "approve", "reject", "commit(",
        ] {
            assert!(!code.contains(forbidden), "tray 에 {forbidden} 가 있다");
        }
    }

    /// tray 에 **절대경로가 실리지 않는다**(§9.1.2 · §10).
    #[test]
    fn the_tray_never_shows_a_path() {
        let code = running(include_str!("tray.rs"));
        // 이름을 만드는 자리는 등록부의 `label` 과 scope 의 꼬리만 쓴다.
        let body = body_of(&code, "fn current_name");
        for forbidden in ["root", "display()", "canonicalize", "PathBuf", "Path::"] {
            assert!(!body.contains(forbidden), "tray 이름이 {forbidden} 를 만진다");
        }
        assert!(body.contains("label()"), "사람이 읽을 이름을 쓰지 않는다");
        // 같은 이름이 둘이면 **화면과 같은 규칙**으로 꼬리를 붙인다.
        assert!(body.contains("twins"), "같은 이름을 구별하지 않는다");
        // 고른 것이 없으면 거짓 이름을 짓지 않는다.
        assert!(body.contains("NOTHING"), "고른 것이 없을 때의 말이 없다");
    }

    /// 메뉴에 있어야 하는 것들.
    #[test]
    fn the_menu_offers_exactly_what_the_contract_asks() {
        let code = running(include_str!("tray.rs"));
        for said in [
            "GIL Companion 열기",
            "새로고침",
            "로그인 시 시작",
            "종료",
            "선택한 Project 없음",
        ] {
            assert!(code.contains(said), "메뉴에 {said:?} 가 없다");
        }
        // 아이콘 기본 클릭은 메뉴가 아니라 창이다.
        assert!(code.contains("show_menu_on_left_click(false)"), "기본 클릭이 메뉴를 연다");
        // template 아이콘이라 light·dark 어느 쪽에서도 읽힌다.
        assert!(code.contains("icon_as_template(true)"), "template 아이콘이 아니다");
        assert!(code.contains("trayTemplate"), "template 그림을 쓰지 않는다");
    }
}
