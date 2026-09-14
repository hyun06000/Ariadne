//! **창의 자리를 화면 안으로 들인다** — Tauri 를 모르는 순수 계산.
//!
//! Host UI Model §9.1.2 가 요구하는 것은 둘이다.
//!
//!   1. 최소 크기를 지킨다
//!   2. 지금 연결된 display 의 **보이는 영역** 안에 둔다
//!
//! 이 파일이 창이나 monitor 를 직접 묻지 않는 이유는 하나다. 사라진 monitor 의 좌표에서
//! 창이 어디로 가야 하는가는 **계산**이지 창의 일이 아니다. 계산으로 떼어 두면 실제 화면
//! 없이도 그 규칙을 잴 수 있다 — 사라진 화면을 만들어 낼 수는 없으니까.

use serde::{Deserialize, Serialize};

/// 창이 작아질 수 있는 한계. 이보다 작으면 Step DAG 도 고르개도 읽을 수 없다.
pub const MIN_WIDTH: f64 = 380.0;
pub const MIN_HEIGHT: f64 = 420.0;

/// logical pixel 로 잰 네모. display 의 보이는 영역과 창이 같은 말을 쓴다.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Rect {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

impl Rect {
    pub fn new(x: f64, y: f64, width: f64, height: f64) -> Rect {
        Rect { x, y, width, height }
    }
    fn right(&self) -> f64 {
        self.x + self.width
    }
    fn bottom(&self) -> f64 {
        self.y + self.height
    }
    /// 이 점이 네모 안에 있는가 — 오른쪽·아래 모서리는 다음 화면의 것이다.
    fn holds(&self, x: f64, y: f64) -> bool {
        x >= self.x && x < self.right() && y >= self.y && y < self.bottom()
    }
}

/// 저장해 두는 창의 자리 — **logical pixel** 이다(§9.1.2).
///
/// 물리 pixel 로 적으면 display 의 배율이 바뀌었을 때 창이 엉뚱한 크기로 돌아온다.
///
/// # `position` 과 `size` 는 **마지막 정상 자리**다
///
/// 최대화된 창의 자리는 창의 자리가 아니라 **화면의 자리**다. 그것을 적어 두면 다음에
/// 최대화를 풀었을 때 화면 가득한 크기가 남고, 사람이 맞춰 둔 자리는 영영 사라진다.
///
/// 그래서 이 두 칸은 **최대화가 아니었을 때의 값**만 담는다. `maximized` 는 그와 별개의
/// 사실이다. 복원은 정상 자리를 먼저 세운 뒤 최대화를 얹는 차례로 한다.
///
/// `position` 이 `None` 인 것은 **정상 자리를 한 번도 몰랐을 때**뿐이다 — 첫 실행이 그렇다.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Geometry {
    /// 창을 어디에 둘 것인가. `null` 이면 **OS 가 정하게 둔다** — 처음 여는 창이 그렇다.
    #[serde(default)]
    pub position: Option<[f64; 2]>,
    pub size: [f64; 2],
    #[serde(default)]
    pub maximized: bool,
}

impl Default for Geometry {
    fn default() -> Geometry {
        Geometry { position: None, size: [520.0, 900.0], maximized: false }
    }
}

/// 저장된 자리를 **지금 있는 화면**에 맞춘다.
///
/// ```text
///   크기   최소보다 작으면 키우고, 화면보다 크면 줄인다
///   화면   창의 한가운데를 품은 화면을 고른다. 없으면 첫 화면(기본 display)
///   자리   그 화면의 보이는 영역 안으로 민다
/// ```
///
/// **어느 화면도 창을 품지 않을 때**가 이 함수가 있는 이유다. 저장할 때 있던 monitor 가
/// 사라졌거나 배치가 바뀌면 옛 좌표는 아무 데도 없는 자리를 가리킨다. 그대로 복원하면
/// 창이 보이지 않는 곳에서 열리고, 사람은 앱이 켜지지 않았다고 생각한다.
///
/// `screens` 는 각 display 의 **보이는 영역**(작업 표시줄·메뉴 막대를 뺀 자리)이고, 첫 칸이
/// 기본 display 다. 비어 있으면 판단할 근거가 없으므로 크기만 다듬고 자리는 OS 에 맡긴다.
pub fn fit(want: Geometry, screens: &[Rect]) -> Geometry {
    let Some(first) = screens.first() else {
        // 화면을 하나도 모른다 — 자리를 지어내지 않는다.
        return Geometry {
            position: None,
            size: [want.size[0].max(MIN_WIDTH), want.size[1].max(MIN_HEIGHT)],
            maximized: want.maximized,
        };
    };

    let Some(position) = want.position else {
        return Geometry {
            position: None,
            size: bounded(want.size, first),
            maximized: want.maximized,
        };
    };

    // 창의 한가운데가 어느 화면에 있는가. 모서리로 고르면 걸친 창이 엉뚱한 화면을 고른다.
    let middle = (position[0] + want.size[0] / 2.0, position[1] + want.size[1] / 2.0);
    let screen = screens
        .iter()
        .find(|one| one.holds(middle.0, middle.1))
        .unwrap_or(first);

    let size = bounded(want.size, screen);
    // 보이는 영역 안으로 민다. 창이 화면보다 크면 왼쪽 위를 맞춘다.
    let x = position[0].clamp(screen.x, (screen.right() - size[0]).max(screen.x));
    let y = position[1].clamp(screen.y, (screen.bottom() - size[1]).max(screen.y));

    Geometry { position: Some([x, y]), size, maximized: want.maximized }
}

/// 방금 본 창의 상태를 **마지막 정상 자리**에 반영한다.
///
/// ```text
///   최대화 중    자리와 크기는 **그대로 두고** maximized 만 true
///   보통         방금 본 자리와 크기로 갈아 끼우고 maximized 는 false
/// ```
///
/// 최대화 중에 오는 move·resize 는 화면 가득한 값이라 정상 자리를 덮으면 안 된다. 최대화를
/// 풀면 창이 제자리로 돌아가고, 그때 오는 event 가 정상 자리를 다시 적는다.
///
/// 창을 보는 일은 부르는 쪽이 한다 — 이 함수는 **무엇을 기억할 것인가**만 정한다.
pub fn remember(
    kept: Geometry,
    seen_position: Option<[f64; 2]>,
    seen_size: [f64; 2],
    maximized: bool,
) -> Geometry {
    if maximized {
        // **정상 자리를 지킨다.** 지금 보이는 크기는 화면의 것이지 창의 것이 아니다.
        return Geometry { position: kept.position, size: kept.size, maximized: true };
    }
    Geometry {
        // 자리를 알 수 없는 순간이 있다 — 그럴 때 옛 값을 지우지 않는다.
        position: seen_position.or(kept.position),
        size: seen_size,
        maximized: false,
    }
}

/// 최소보다 작지 않고 그 화면보다 크지 않게.
fn bounded(size: [f64; 2], screen: &Rect) -> [f64; 2] {
    [
        size[0].clamp(MIN_WIDTH, screen.width.max(MIN_WIDTH)),
        size[1].clamp(MIN_HEIGHT, screen.height.max(MIN_HEIGHT)),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    fn one_screen() -> Vec<Rect> {
        // 메뉴 막대를 뺀 자리 — y 가 0 이 아닌 것이 보통이다.
        vec![Rect::new(0.0, 25.0, 1710.0, 1080.0)]
    }

    #[test]
    fn a_window_already_on_screen_comes_back_exactly_where_it_was() {
        let want = Geometry { position: Some([200.0, 150.0]), size: [520.0, 900.0], maximized: false };
        assert_eq!(fit(want, &one_screen()), want, "제자리에 있던 창이 옮겨졌다");
    }

    #[test]
    fn maximized_survives_the_trip() {
        let want = Geometry { position: Some([0.0, 25.0]), size: [1710.0, 1080.0], maximized: true };
        assert!(fit(want, &one_screen()).maximized, "최대화 상태가 사라졌다");
    }

    #[test]
    fn a_window_off_to_the_right_is_pulled_back_in() {
        // 사라진 둘째 monitor 에 있던 창.
        let want = Geometry { position: Some([3000.0, 400.0]), size: [520.0, 900.0], maximized: false };
        let got = fit(want, &one_screen());
        let at = got.position.expect("자리");
        assert!(at[0] >= 0.0 && at[0] + got.size[0] <= 1710.0, "가로로 화면 밖이다: {at:?}");
        assert!(at[1] >= 25.0 && at[1] + got.size[1] <= 1105.0, "세로로 화면 밖이다: {at:?}");
    }

    #[test]
    fn a_window_above_the_menu_bar_is_pushed_down() {
        let want = Geometry { position: Some([100.0, -800.0]), size: [520.0, 900.0], maximized: false };
        let at = fit(want, &one_screen()).position.expect("자리");
        assert_eq!(at[1], 25.0, "보이는 영역 위로 올라갔다");
    }

    #[test]
    fn a_window_too_small_to_read_is_grown_to_the_minimum() {
        let want = Geometry { position: Some([10.0, 30.0]), size: [40.0, 20.0], maximized: false };
        let got = fit(want, &one_screen());
        assert_eq!(got.size, [MIN_WIDTH, MIN_HEIGHT], "최소 크기를 지키지 않았다");
    }

    #[test]
    fn a_window_larger_than_the_screen_is_trimmed_to_it() {
        let want = Geometry { position: Some([0.0, 25.0]), size: [9000.0, 9000.0], maximized: false };
        let got = fit(want, &one_screen());
        assert_eq!(got.size, [1710.0, 1080.0], "화면보다 큰 채로 돌아왔다");
        assert_eq!(got.position, Some([0.0, 25.0]));
    }

    #[test]
    fn the_screen_that_holds_the_window_is_the_one_that_bounds_it() {
        // 기본 화면 하나와, 오른쪽에 붙은 작은 화면 하나.
        let screens = vec![
            Rect::new(0.0, 25.0, 1710.0, 1080.0),
            Rect::new(1710.0, 0.0, 800.0, 600.0),
        ];
        let want = Geometry { position: Some([1800.0, 100.0]), size: [520.0, 900.0], maximized: false };
        let got = fit(want, &screens);
        // 둘째 화면이 품었으므로 그 화면의 높이로 줄고 그 안에 선다.
        assert_eq!(got.size[1], 600.0, "품은 화면의 크기를 따르지 않았다");
        let at = got.position.expect("자리");
        assert!(at[0] >= 1710.0 && at[0] + got.size[0] <= 2510.0, "둘째 화면 밖이다: {at:?}");
    }

    // ── 마지막 정상 자리 ───────────────────────────────────────────

    fn normal() -> Geometry {
        Geometry { position: Some([200.0, 150.0]), size: [520.0, 900.0], maximized: false }
    }

    #[test]
    fn maximizing_keeps_the_last_normal_geometry_and_only_raises_the_flag() {
        let kept = normal();
        // 최대화가 시작되면서 화면 가득한 값이 들어온다.
        let after = remember(kept, Some([0.0, 25.0]), [1710.0, 1080.0], true);
        assert_eq!(after.position, kept.position, "정상 자리가 덮였다");
        assert_eq!(after.size, kept.size, "정상 크기가 덮였다");
        assert!(after.maximized);
    }

    #[test]
    fn moves_and_resizes_while_maximized_never_touch_the_normal_geometry() {
        let mut kept = normal();
        // 최대화된 채로 이런저런 event 가 쏟아진다 — 화면을 옮겼거나 배율이 바뀌었거나.
        for (at, size) in [
            (Some([0.0, 25.0]), [1710.0, 1080.0]),
            (Some([1710.0, 0.0]), [800.0, 600.0]),
            (None, [3440.0, 1440.0]),
        ] {
            kept = remember(kept, at, size, true);
        }
        assert_eq!(kept.position, normal().position, "정상 자리가 덮였다");
        assert_eq!(kept.size, normal().size, "정상 크기가 덮였다");
        assert!(kept.maximized);
    }

    #[test]
    fn unmaximizing_writes_the_real_geometry_again() {
        let kept = remember(normal(), Some([0.0, 25.0]), [1710.0, 1080.0], true);
        // 최대화를 풀면 창이 제자리로 돌아가고, 그 자리가 다시 적힌다.
        let back = remember(kept, Some([200.0, 150.0]), [520.0, 900.0], false);
        assert_eq!(back, normal(), "정상 자리로 돌아오지 않았다");
    }

    #[test]
    fn maximized_false_survives_the_trip_too() {
        let kept = remember(normal(), Some([310.0, 90.0]), [600.0, 800.0], false);
        assert!(!kept.maximized);
        assert_eq!(kept.position, Some([310.0, 90.0]));
        assert_eq!(kept.size, [600.0, 800.0]);
    }

    #[test]
    fn a_position_we_never_knew_stays_unknown_but_one_we_knew_is_never_lost() {
        // 첫 실행 — 정상 자리를 한 번도 모른다.
        let first = Geometry::default();
        assert_eq!(first.position, None);
        let still = remember(first, None, [520.0, 900.0], false);
        assert_eq!(still.position, None, "모르던 자리를 지어냈다");

        // 한 번 알고 나면, 자리를 알 수 없는 event 가 와도 지우지 않는다.
        let known = remember(still, Some([40.0, 60.0]), [520.0, 900.0], false);
        assert_eq!(known.position, Some([40.0, 60.0]));
        let unknown = remember(known, None, [520.0, 900.0], false);
        assert_eq!(unknown.position, Some([40.0, 60.0]), "알던 자리를 잃었다");
    }

    #[test]
    fn the_last_normal_geometry_from_a_vanished_monitor_still_gets_clamped() {
        // 둘째 화면에서 쓰다가 최대화하고 껐다. 그 화면이 사라진 뒤 켠다.
        let kept = remember(
            Geometry { position: Some([2200.0, 300.0]), size: [700.0, 950.0], maximized: false },
            Some([1710.0, 0.0]),
            [800.0, 600.0],
            true,
        );
        assert_eq!(kept.position, Some([2200.0, 300.0]), "정상 자리가 덮였다");
        assert!(kept.maximized);

        // 복원은 **정상 자리를 먼저** 지금 화면에 맞춘다. 최대화는 그 위에 얹힌다.
        let fitted = fit(kept, &one_screen());
        let at = fitted.position.expect("자리");
        assert!(at[0] >= 0.0 && at[0] + fitted.size[0] <= 1710.0, "화면 밖이다: {at:?}");
        assert!(at[1] >= 25.0 && at[1] + fitted.size[1] <= 1105.0, "화면 밖이다: {at:?}");
        assert!(fitted.maximized, "최대화 상태를 잃었다");
    }

    #[test]
    fn no_position_stays_no_position() {
        let want = Geometry { position: None, size: [520.0, 900.0], maximized: false };
        assert_eq!(fit(want, &one_screen()).position, None, "없던 자리를 지어냈다");
    }

    #[test]
    fn with_no_screens_at_all_only_the_size_is_tidied() {
        let want = Geometry { position: Some([3000.0, 3000.0]), size: [10.0, 10.0], maximized: true };
        let got = fit(want, &[]);
        assert_eq!(got.position, None, "화면을 모르는데 자리를 정했다");
        assert_eq!(got.size, [MIN_WIDTH, MIN_HEIGHT]);
        assert!(got.maximized);
    }
}
