//! **앱 메뉴** — `⌘W` 와 `⌘Q` 가 각자 제 문으로 가게.
//!
//! macOS 는 기본 메뉴에 Close Window 를 넣어 주지 않는다. 그래서 `⌘W` 가 아무 일도 하지
//! 않았다(2026-09-14 실측). 창을 숨기는 길이 빨간 버튼 하나뿐이었던 셈이다.
//!
//! # 예정된 것을 쓰지 않는 이유
//!
//! Tauri 가 주는 `PredefinedMenuItem::quit` 은 OS 의 종료를 그대로 부른다. 그러면 우리의
//! **끝낸다는 뜻**(`begin_leaving`)이 서지 않은 채 종료 요청이 오고, `ExitRequested` 가
//! 그것을 가로채 앱이 끝나지 않는다. `close_window` 도 마찬가지로 플랫폼마다 다른 길로
//! 간다. 그래서 둘 다 **직접 만든 항목**으로 두고, 우리가 아는 문으로만 보낸다.
//!
//! ```text
//!   ⌘W   hide_main_window   설정을 눕히고 숨긴다. 파괴하지 않는다
//!   ⌘Q   quit               끝낸다는 뜻 → 마지막 flush → process 종료
//! ```

use tauri::menu::{Menu, MenuEvent, MenuItem, PredefinedMenuItem, Submenu};
use tauri::{AppHandle, Wry};

const HIDE: &str = "menu.hide-window";
const QUIT: &str = "menu.quit";

/// 메뉴를 세운다. 항목의 동작은 [`on_menu`] 하나가 받는다.
pub fn build(app: &AppHandle) -> Result<Menu<Wry>, tauri::Error> {
    let name = "GIL Companion";

    // 창을 숨긴다 — 빨간 버튼과 **같은 문**이다.
    let hide_window = MenuItem::with_id(app, HIDE, "창 숨기기", true, Some("CmdOrCtrl+W"))?;
    // 정말 끝낸다.
    let quit = MenuItem::with_id(app, QUIT, format!("{name} 종료"), true, Some("CmdOrCtrl+Q"))?;

    let app_menu = Submenu::with_items(
        app,
        name,
        true,
        &[
            &PredefinedMenuItem::about(app, None, None)?,
            &PredefinedMenuItem::separator(app)?,
            // 앱 전체를 감춘다 — 창 하나를 숨기는 것과는 다른 일이라 둘 다 둔다.
            &PredefinedMenuItem::hide(app, None)?,
            &PredefinedMenuItem::hide_others(app, None)?,
            &PredefinedMenuItem::show_all(app, None)?,
            &PredefinedMenuItem::separator(app)?,
            &quit,
        ],
    )?;

    let window_menu = Submenu::with_items(
        app,
        "창",
        true,
        &[
            &PredefinedMenuItem::minimize(app, None)?,
            &PredefinedMenuItem::separator(app)?,
            &hide_window,
        ],
    )?;

    // 글자를 고르고 붙여 넣는 것은 읽는 데 필요하다 — 쓰기가 아니다.
    let edit_menu = Submenu::with_items(
        app,
        "편집",
        true,
        &[
            &PredefinedMenuItem::copy(app, None)?,
            &PredefinedMenuItem::select_all(app, None)?,
        ],
    )?;

    Menu::with_items(app, &[&app_menu, &edit_menu, &window_menu])
}

/// 메뉴에서 온 것을 **이미 있는 두 문**으로 보낸다. 여기서 새로 구현하지 않는다.
pub fn on_menu(app: &AppHandle, event: MenuEvent) {
    match event.id().as_ref() {
        HIDE => {
            let _ = crate::lifetime::hide_main_window(app);
        }
        QUIT => crate::lifetime::quit(app),
        _ => {}
    }
}

#[cfg(test)]
mod tests {
    fn running(source: &str) -> String {
        let body = source.split_once("#[cfg(test)]").map(|(one, _)| one).unwrap_or(source);
        body.lines()
            .filter(|line| !line.trim_start().starts_with("//"))
            .collect::<Vec<_>>()
            .join("\n")
    }

    /// `⌘W` 와 `⌘Q` 는 **서로 다른 문**으로 간다.
    #[test]
    fn the_two_shortcuts_go_to_two_different_doors() {
        let code = running(include_str!("appmenu.rs"));
        assert!(code.contains("CmdOrCtrl+W"), "⌘W 가 붙어 있지 않다");
        assert!(code.contains("CmdOrCtrl+Q"), "⌘Q 가 붙어 있지 않다");

        let hide = code.find("HIDE =>").expect("숨기는 자리");
        let rest = &code[hide..];
        let hide_arm = &rest[..rest.find("QUIT =>").unwrap_or(rest.len())];
        assert!(hide_arm.contains("hide_main_window"), "⌘W 가 숨기는 문으로 가지 않는다");
        assert!(!hide_arm.contains("quit"), "⌘W 가 끝낸다");

        let quit_arm = &code[code.find("QUIT =>").expect("끝내는 자리")..];
        assert!(quit_arm.contains("lifetime::quit"), "⌘Q 가 끝내는 문으로 가지 않는다");
        assert!(!quit_arm.contains("hide_main_window"), "⌘Q 가 숨긴다");
    }

    /// 메뉴는 **제 방식으로 숨기거나 끝내지 않는다.**
    #[test]
    fn the_menu_implements_neither_hiding_nor_quitting_itself() {
        let code = running(include_str!("appmenu.rs"));
        for forbidden in [".hide()", ".close()", ".destroy()", "app.exit(", "process::exit"] {
            assert!(!code.contains(forbidden), "메뉴가 {forbidden} 로 제 일을 한다");
        }
        // 그리고 예정된 종료·닫기 항목을 쓰지 않는다 — 우리 문을 건너뛰기 때문이다.
        for forbidden in ["PredefinedMenuItem::quit", "PredefinedMenuItem::close_window"] {
            assert!(!code.contains(forbidden), "{forbidden} 이 우리 문을 건너뛴다");
        }
    }
}
