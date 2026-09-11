// **fixture Host** — 공용 bundle 이 혼자서도 돌게 하는 가장 작은 문.
//
// GIL Host UI Model §9 의 adapter 책임 중 이 파일이 지는 것은 하나다: View 와 detail 을
// 건네주는 것. Cycle 관계도, lane 도, 요약도 여기서 계산하지 않는다 — 파일에 이미 있는
// canonical JSON 을 그대로 넘긴다.
//
// Tauri Companion 은 같은 이름의 문을 `invoke` 로 채운다(`companion/ui-host.js`). bundle 은
// 둘을 구별하지 못하고, 구별할 필요도 없다.
//
// **server 도 port 도 capability URL 도 없다.** 같은 자리에 놓인 파일을 읽을 뿐이다.

(() => {
  "use strict";

  const read = async (path) => {
    const answer = await fetch(path, { cache: "no-store" });
    if (!answer.ok) throw new Error(`${path} 을 읽지 못했다 (${answer.status})`);
    return answer.json();
  };

  let registry = null;
  const details = new Map();

  const folderOf = (scopeId) => String(scopeId).split(":").pop();

  window.GIL_HOST = {
    async listProjects() {
      if (!registry) registry = await read("fixtures/projects.json");
      return registry;
    },

    async loadView(scopeId) {
      // 언제나 **완전한 View 하나**다. 부분 갱신을 합쳐 사실을 만들지 않는다(§8).
      return read(`fixtures/${folderOf(scopeId)}/view.json`);
    },

    async loadDetail(scopeId, stepRef) {
      if (!details.has(scopeId)) {
        details.set(scopeId, await read(`fixtures/${folderOf(scopeId)}/details.json`));
      }
      // 없으면 없다 — 비슷한 Step 으로 물러서지 않는다(§7).
      return details.get(scopeId)[stepRef] || null;
    },
  };
})();
