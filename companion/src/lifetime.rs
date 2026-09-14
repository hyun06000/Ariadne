//! **창 하나의 수명** — 숨고, 다시 서고, 끝나는 자리.
//!
//! Host UI Model §9.1: 「Companion process와 창은 Project나 Agent session마다 새로 만들지
//! 않는다.」 그 문장을 지키는 코드가 여기 있다.
//!
//! # 고친 것
//!
//! 2026-09-14 실측: 빨간 버튼을 누르면 창이 **파괴**되고 process 만 살아남았다. 그 뒤로는
//! 어느 길로 들어와도 보여 줄 창이 없었다 — 둘째 실행은 single-instance 가 끝내 버리고,
//! tray 도 Agent 도 빈 process 에 말을 걸 뿐이었다.
//!
//! ```text
//!   빨간 버튼 · ⌘W    창을 **숨긴다**. 파괴하지 않는다
//!   ⌘Q · tray 종료    끝낸다는 **뜻을 먼저 세우고** 그때만 파괴한다
//! ```
//!
//! # 다시 여는 길은 하나다
//!
//! 둘째 실행도, Dock 의 reopen 도, tray 아이콘도, Agent 의 `show_gil_companion` 도 전부
//! [`show_main_window`] 를 지난다. 네 벌로 두면 그중 하나만 `unminimize` 를 잊어도 사람은
//! 「어떤 길로는 열리는데 어떤 길로는 안 열린다」를 겪는다.

use std::sync::atomic::{AtomicBool, Ordering};

use tauri::{AppHandle, Manager, WebviewWindow};

/// 이 창의 이름. 한 자리에만 적는다.
pub const MAIN: &str = "main";

/// **끝내려는 중인가.**
///
/// 닫기를 가로채 숨기는 규칙과 진짜 종료를 가르는 것이 이 한 칸이다. 이것이 없으면 `⌘Q` 가
/// 보내는 닫기 요청까지 숨김으로 바뀌어, 앱이 영영 끝나지 않는다.
static LEAVING: AtomicBool = AtomicBool::new(false);

/// 이제부터는 진짜 끝이다 — 닫기를 가로채지 않는다.
pub fn begin_leaving() {
    LEAVING.store(true, Ordering::SeqCst);
}

pub fn is_leaving() -> bool {
    LEAVING.load(Ordering::SeqCst)
}

/// 창을 다시 보여 달라는 청이 어떻게 되었는가.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Shown {
    /// 있던 창을 앞으로 데려왔다.
    Raised,
    /// 창이 없어 다시 세웠다 — 있어서는 안 되지만, 조용히 성공하지는 않는다.
    Rebuilt,
}

/// **다시 여는 단 하나의 문.**
///
/// 하는 일은 넷뿐이다 — 찾고, 펴고, 보이고, 앞으로. 새 창을 만들지 않고, `argv`·`cwd`·최근
/// 폴더로 Project 를 짐작하지 않으며, `.gil` 을 다시 읽지도 않는다. **보여 주는 일**이지
/// 관측하는 일이 아니다.
///
/// 창이 없는 경우는 일어나서는 안 된다(정상 닫기는 숨길 뿐이다). 그래도 조용히 성공하지
/// 않는다 — 같은 bundle 과 설정으로 다시 세우고 [`Shown::Rebuilt`] 로 그 사실을 남긴다.
pub fn show_main_window(app: &AppHandle) -> Result<Shown, tauri::Error> {
    if let Some(window) = app.get_webview_window(MAIN) {
        raise(&window)?;
        return Ok(Shown::Raised);
    }
    // 여기에 닿았다면 수명 규칙이 깨진 것이다. 사람에게는 창이 열리는 것이 먼저이므로
    // 다시 세우되, 무슨 일이 있었는지는 부르는 쪽이 알 수 있게 한다.
    let window = crate::window::build(app)?;
    raise(&window)?;
    Ok(Shown::Rebuilt)
}

/// **숨기는 단 하나의 문.**
///
/// 빨간 버튼도 `⌘W` 도 여기로 온다. 파괴하지 않는다 — 숨길 뿐이다. 숨기기 전에 자리를
/// 눕히는 이유는, 사람이 창을 닫아 두고 그대로 기계를 끌 수도 있기 때문이다.
///
/// 두 벌로 두면 그중 하나만 설정을 눕히는 것을 잊는다. 그래서 하나다.
pub fn hide_main_window(app: &AppHandle) -> Result<(), tauri::Error> {
    crate::window::keep_now(app);
    if let Some(window) = app.get_webview_window(MAIN) {
        window.hide()?;
    }
    Ok(())
}

/// 있는 창을 사람 앞에 가져온다.
fn raise(window: &WebviewWindow) -> Result<(), tauri::Error> {
    // 최소화가 먼저다. 최소화된 창에 `show` 만 하면 Dock 에 머문 채로 남는다.
    if window.is_minimized().unwrap_or(false) {
        window.unminimize()?;
    }
    window.show()?;
    window.set_focus()?;
    Ok(())
}

/// **끝내는 단 하나의 문.**
///
/// `⌘Q` 도 tray 의 종료도 여기로 온다. 끝낸다는 뜻을 먼저 세우고, 미뤄 둔 설정을 **동기적으로**
/// 눕힌 뒤에 process 를 끝낸다. 순서가 뒤집히면 debounce 가 삼킨 마지막 자리가 사라진다.
pub fn quit(app: &AppHandle) {
    begin_leaving();
    crate::window::flush_now(app);
    app.exit(0);
}

#[cfg(test)]
mod tests {
    use super::*;

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

    #[test]
    fn the_quit_flag_starts_down_and_only_goes_up_on_purpose() {
        // 기본은 「끝내는 중이 아니다」 — 그래야 닫기가 숨김으로 바뀐다.
        assert!(!is_leaving(), "시작부터 끝내는 중이다");
        begin_leaving();
        assert!(is_leaving());
        // 되돌리는 문은 두지 않는다. 끝내기로 한 뒤에 마음을 바꾸는 길은 없다.
        assert!(!running(include_str!("lifetime.rs")).contains("fn cancel_leaving"));
    }

    /// **정상 닫기는 창을 파괴하지 않는다.**
    #[test]
    fn a_normal_close_hides_the_window_instead_of_destroying_it() {
        let code = running(include_str!("window.rs"));
        let at = code.find("CloseRequested").expect("닫기를 듣는 자리가 없다");
        let rest = &code[at..];
        let arm = &rest[..rest.find("_ =>").unwrap_or(rest.len())];

        assert!(arm.contains("is_leaving"), "끝내는 중인지 보지 않는다");
        assert!(arm.contains("prevent_close"), "닫기를 가로채지 않는다");
        // **제 방식으로 숨기지 않는다** — 하나뿐인 문으로 간다.
        assert!(arm.contains("hide_main_window"), "공용 문으로 가지 않는다");
        for forbidden in [".close()", ".destroy()", ".hide()"] {
            assert!(!arm.contains(forbidden), "닫기 자리에서 {forbidden} 를 직접 부른다");
        }
    }

    /// **숨기는 문은 하나이고, 그 문이 설정을 눕힌다.**
    #[test]
    fn every_way_of_closing_goes_through_one_door_that_saves_first() {
        let code = running(include_str!("lifetime.rs"));
        let body = body_of(&code, "pub fn hide_main_window");
        let saves = body.find("keep_now").expect("숨기기 전에 눕히지 않는다");
        let hides = body.find(".hide()").expect("숨기지 않는다");
        assert!(saves < hides, "숨긴 뒤에 눕힌다");
        assert!(!body.contains("destroy"), "숨기는 문이 창을 없앤다");

        // 빨간 버튼도 `⌘W` 도 이 문으로 온다. 그리고 **창을 숨기는 자리는 이곳뿐**이다.
        let menu = running(include_str!("appmenu.rs"));
        assert!(menu.contains("hide_main_window"), "메뉴가 다른 길로 숨긴다");
        let window = running(include_str!("window.rs"));
        assert!(window.contains("hide_main_window"), "닫기가 다른 길로 숨긴다");
        for (name, source) in [
            ("window.rs", &window),
            ("appmenu.rs", &menu),
            ("tray.rs", &running(include_str!("tray.rs"))),
            ("main.rs", &running(include_str!("main.rs"))),
        ] {
            assert!(
                !source.contains(".hide()"),
                "{name} 가 창을 제 방식으로 숨긴다"
            );
        }
    }

    /// **다시 여는 문은 하나다.**
    #[test]
    fn every_way_back_in_goes_through_one_door() {
        let main = running(include_str!("main.rs"));
        let tray = running(include_str!("tray.rs"));
        let adapter = running(include_str!("adapter.rs"));

        // 네 길 모두 같은 함수를 지난다.
        assert!(main.contains("single_instance"), "둘째 실행 자리가 없다");
        let second = main.split_once("single_instance").expect("둘째 실행").1;
        let second = second;
        assert!(second.contains("show_main_window"), "둘째 실행이 다른 길로 연다");

        assert!(main.contains("Reopen"), "Dock 의 reopen 을 듣지 않는다");
        let reopen = main.split_once("Reopen").expect("reopen").1;
        assert!(
            reopen[..300.min(reopen.len())].contains("show_main_window"),
            "Dock reopen 이 다른 길로 연다"
        );

        assert!(tray.contains("show_main_window"), "tray 가 다른 길로 연다");
        assert!(adapter.contains("show_main_window"), "Agent 문이 다른 길로 연다");

        // 그리고 **창을 만드는 자리는 하나뿐**이다.
        for (name, code) in [("main.rs", &main), ("tray.rs", &tray), ("adapter.rs", &adapter)] {
            assert!(
                !code.contains("WebviewWindowBuilder"),
                "{name} 가 창을 따로 만든다"
            );
        }
        let window = running(include_str!("window.rs"));
        assert_eq!(
            window.matches("WebviewWindowBuilder::new").count(),
            1,
            "창을 세우는 자리가 둘 이상이다"
        );
    }

    /// 다시 여는 길에서는 **Project 를 짐작하지 않는다.**
    #[test]
    fn reopening_never_guesses_a_project_or_reads_gil() {
        let code = running(include_str!("lifetime.rs"));
        // 짐작하지 않는다 — 문과 그 문이 부르는 손 둘 다.
        for marker in ["pub fn show_main_window", "fn raise"] {
            let body = body_of(&code, marker);
            for forbidden in [
                "argv", "cwd", "current_dir", "ProjectSession", "STATE_PATH",
                "view_of(", "detail_of(", "openable(", "remember(",
            ] {
                assert!(!body.contains(forbidden), "{marker} 가 {forbidden} 를 만진다");
            }
        }
        // 사람 앞에 가져오는 네 걸음은 `raise` 하나에 모여 있다 — 두 벌로 두면 그중
        // 하나만 `unminimize` 를 잊는다.
        let raising = body_of(&code, "fn raise");
        for must in ["is_minimized", "unminimize", "show()", "set_focus"] {
            assert!(raising.contains(must), "다시 여는 길에 {must} 가 없다");
        }
        // 그리고 새 창을 만들지 않는다 — 없을 때만, 그것도 알리면서 다시 세운다.
        let door = body_of(&code, "pub fn show_main_window");
        assert!(door.contains("get_webview_window"), "있던 창을 찾지 않는다");
        assert!(door.contains("Rebuilt"), "창이 없을 때 조용히 성공한다");
    }

    /// **끝내는 문도 하나다** — 그리고 끝내기 전에 반드시 눕힌다.
    #[test]
    fn quitting_flushes_before_it_exits() {
        let code = running(include_str!("lifetime.rs"));
        let body = body_of(&code, "pub fn quit");
        let leaving = body.find("begin_leaving").expect("끝낸다는 뜻을 세우지 않는다");
        let flush = body.find("flush_now").expect("눕히지 않는다");
        let exit = body.find("exit(").expect("끝내지 않는다");
        assert!(leaving < flush, "뜻을 세우기 전에 눕힌다");
        assert!(flush < exit, "눕히기 전에 끝낸다");

        // tray 의 종료도 같은 문을 지난다.
        let tray = running(include_str!("tray.rs"));
        assert!(tray.contains("lifetime::quit"), "tray 가 제 방식으로 끝낸다");
        assert!(!tray.contains("app.exit("), "tray 가 곧바로 끝낸다");
        assert!(!tray.contains("process::exit"), "tray 가 곧바로 끝낸다");
    }

    /// 창을 다 닫아도 끝나지 않는다 — menu bar 에 남아야 한다.
    #[test]
    fn closing_every_window_does_not_end_the_process() {
        let code = running(include_str!("main.rs"));
        let arm = after(&code, "ExitRequested");
        assert!(arm.contains("is_leaving"), "끝내는 중인지 보지 않는다");
        assert!(arm.contains("prevent_exit"), "창이 없으면 그냥 끝난다");
    }
}
