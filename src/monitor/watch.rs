//! **파일이 바뀌었을지 모른다** — 그 한 마디만 전하는 자리.
//!
//! `gil monitor --serve` 의 worker 와 Desktop Companion 이 **같은 감시**를 쓴다. 두 벌로
//! 두면 한쪽만 `.gil` 잡음을 거르게 되고, 그러면 관측이 관측을 부르는 고리가 한쪽에만
//! 생긴다.
//!
//! 여기서 나가는 것은 「다시 볼 때가 되었을지도 모른다」뿐이다. 경로도 종류도 순서도
//! 나가지 않는다(Monitor Model §8.3).

use std::path::Path;

// ── 감시 ───────────────────────────────────────────────────────────────────

/// 루트 `.gil/` 안에서 **유일하게 뜻이 있는** 파일.
///
/// Graph 의 논리 상태 전부가 한 번의 교체로 여기서 확정된다(Storage Model §2). 그래서
/// 이 하나만 보면 되고, 나머지는 보아서는 안 된다.
const GRAPH_FILE: &str = "state.yaml";

/// 감시를 쥐고 있는 자리. **떨어뜨리면 감시가 멈춘다.**
///
/// 무엇을 쥐고 있는지 바깥에 알리지 않는다 — 감시기의 타입이 공개 계약이 되면 그것을
/// 바꾸는 일이 부르는 쪽을 깨뜨린다.
pub struct Watching(#[allow(dead_code)] Box<dyn std::any::Any + Send>);

impl std::fmt::Debug for Watching {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("Watching")
    }
}

/// 프로젝트를 감시한다 — **한 가지 말만 전한다.**
///
/// `hint` 가 불리는 것이 전부다. 경로도, 사건의 종류도, 순서도, 바뀐 파일의 목록도 전하지
/// 않고 어디에도 남기지 않는다. **여기서 프로젝트의 사실을 판정하지 않는다** — 사실은
/// 언제나 다음 전체 조회가 정한다.
///
/// `hint` 는 프로젝트를 열지 않아야 한다. 잠금을 얻으려 해서도 안 된다. 감시 갈래가 잠금을
/// 기다리기 시작하면 그 순간 감시는 프로젝트를 붙드는 쪽이 된다.
///
/// 돌려주는 [`Watching`] 을 떨어뜨리면 감시가 끝난다.
pub fn watch_hints(
    root: &Path,
    hint: impl Fn() + Send + 'static,
) -> Result<Watching, String> {
    use notify::{RecursiveMode, Watcher};

    let gil = root.join(crate::artifact::GIL_DIR);
    let mut watcher = notify::recommended_watcher(move |event: notify::Result<notify::Event>| {
        let Ok(event) = event else {
            // 감시가 흘린 사건은 hint 로 만들지 않는다 — 무엇을 놓쳤는지 모르는 채로
            // 관측을 부르는 것이 되고, 그래도 reconciliation 기한이 수렴을 맡는다.
            return;
        };
        if !event.paths.iter().any(|path| worth_looking(path, &gil)) {
            return;
        }
        hint();
    })
    .map_err(|said| said.to_string())?;
    watcher
        .watch(root, RecursiveMode::Recursive)
        .map_err(|said| said.to_string())?;
    Ok(Watching(Box::new(watcher)))
}

/// 이 경로의 변화가 **다시 볼 만한 것인가.**
///
/// ```text
/// <root>/.gil/state.yaml        예 — Graph 의 논리 상태가 여기서 확정된다
/// <root>/.gil/ 그 밖의 모든 것   아니오 — 잠금·tmp·object store·restore 임시
/// <root>/ 의 일반 파일           예 — Artifact 세계
/// 더 깊은 곳의 .gil/            예 — 중첩 GIL 경계다. **거르지 않는다.**
/// ```
///
/// # 왜 루트 `.gil/` 만 조용한가
///
/// 관측 자체가 그 안을 만진다 — 잠금을 걸고, 필요하면 중단 복구를 한다. 그것을 hint 로
/// 되받으면 **관측이 관측을 부르는 고리**가 된다.
///
/// ```text
/// 관측 → .gil 사건 → hint → 관측 → .gil 사건 → …     ← 이 고리를 끊는다
/// ```
///
/// # 왜 더 깊은 `.gil` 은 거르지 않는가
///
/// Artifact Model §3.4 에서 그것은 제외 대상이 아니라 **관측 거절 사유**다. 걸러 버리면
/// 사람이 중첩 GIL 을 만들어 둔 사실이 화면에 영영 나타나지 않는다. 걸러 내지 않으므로
/// 다음 조회가 거절하고, 화면이 그 거절을 보인다.
///
/// **이 filter 는 사실을 판정하지 않는다.** 「다시 볼 필요조차 없는 Monitor 자신의 잡음」
/// 하나만 덜어낸다.
pub(crate) fn worth_looking(path: &Path, gil: &Path) -> bool {
    match path.strip_prefix(gil) {
        // 루트 `.gil/` 밖 — Artifact 세계다.
        Err(_) => true,
        // 루트 `.gil/` 자신(빈 나머지)도, 그 안의 다른 무엇도 아니다.
        Ok(rest) => rest == Path::new(GRAPH_FILE),
    }
}


#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_filter_is_deaf_only_to_gils_own_noise() {
        let root = Path::new("/p");
        let gil = root.join(crate::artifact::GIL_DIR);
        // 다시 볼 만한 것.
        for path in [
            "/p/a.txt",
            "/p/깊은/자리/b.rs",
            "/p/.gil/state.yaml",
            // 더 깊은 곳의 `.gil` — 제외 대상이 아니라 **관측 거절 사유**다(Artifact §3.4).
            "/p/안쪽/.gil",
            "/p/안쪽/.gil/state.yaml",
            // `.gil` 이라는 이름의 일반 파일은 중첩 저장소가 아니다.
            "/p/.gilignore",
        ] {
            assert!(
                worth_looking(Path::new(path), &gil),
                "{path} 을 못 본 척했다"
            );
        }
        // Monitor 자신의 잡음.
        for path in [
            "/p/.gil",
            "/p/.gil/project.lock",
            "/p/.gil/artifacts/tmp/무언가",
            "/p/.gil/artifacts/blobs/sha256/ab/cdef",
            "/p/.gil/artifacts/manifests/sha256/ab/cdef",
            "/p/.gil/restore/active/PLAN",
            "/p/.gil/restore/preparing-1234-x/backup/0",
            "/p/.gil/state.yaml.tmp",
        ] {
            assert!(
                !worth_looking(Path::new(path), &gil),
                "{path} 을 다시 볼 만하다고 했다"
            );
        }
    }
}
