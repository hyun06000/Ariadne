// **Tauri 판 `window.GIL_HOST`** — 공용 bundle 이 여는 문에 실제 GIL Project 를 단다.
//
// 이 글은 `ui/` 가 아니라 `companion/` 에 있다. 그래야 공용 bundle 이 Tauri 를 **한 글자도**
// 모른 채로 남는다(§9.1 · §2). 창이 뜨기 전에 주입되므로 `ui/host.js` 의 fixture 문보다
// 먼저 자리를 잡고, fixture 문은 이미 누가 달아 둔 것을 보고 물러선다.
//
// 여기서 하는 일은 옮기는 것뿐이다 — Graph 도 Cycle 관계도 요약도 만들지 않는다.

(() => {
  "use strict";
  const invoke = (name, args) => window.__TAURI_INTERNALS__.invoke(name, args);

  // Rust 가 준 거절을 **종류를 지닌 채** 던진다. UI 는 `code` 로 갈래를 정하고 `said` 는
  // 사람에게 보이기만 한다 — 글을 뜯어 뜻을 짐작하는 길을 만들지 않는다(§9.1.1-7).
  const pass = async (name, args) => {
    try {
      return await invoke(name, args);
    } catch (refusal) {
      const error = new Error((refusal && refusal.said) || "GIL 이 거절했다");
      error.code = (refusal && refusal.code) || "damaged";
      error.said = error.message;
      throw error;
    }
  };

  window.GIL_HOST = {
    async listProjects() {
      return pass("list_projects");
    },

    /** 사람이 폴더를 고른다. 취소는 `null` — **아무것도 바꾸지 않는다**(§9.1.1-8). */
    async addProject() {
      return pass("pick_project");
    },

    /** 언제나 **완전한 View** 하나. 새로고침도 이 문으로 온다(§8 · §9.1.1-5). */
    async loadView(scopeId) {
      return JSON.parse(await pass("load_view", { scopeId }));
    },

    /** 없으면 없다 — 비슷한 Step 으로 물러서지 않는다(§7 · §9.1.1-4). */
    async loadDetail(scopeId, stepRef) {
      const said = await pass("load_detail", { scopeId, stepRef });
      return said === null || said === undefined ? null : JSON.parse(said);
    },

    /** 시작할 때 알아야 하는 것 — 마지막으로 보던 scope 와 설정의 사정(§9.1.2). */
    async opening() {
      return pass("opening");
    },

    /** 목록에서 지운다. **Project 파일은 하나도 건드리지 않는다**(§9.1.2). */
    async forgetProject(scopeId) {
      return pass("forget_project", { scopeId });
    },

    /** 창을 앞으로 — tray·둘째 실행·Agent 가 지나는 그 문. */
    async showWindow() {
      return pass("show_window");
    },

    /**
     * 창 밖에서 오는 말을 듣는다.
     *
     *   `gil://refresh`  menu bar 가 누른 새로고침 — **hint 한 줄이다.** 사실이 아니다.
     *   `gil://say`      이 창의 사정(자동 시작이 뜻대로 안 됐다 같은 것)
     *
     * hint 를 받은 쪽은 제 경계로 **완전한 View** 를 다시 조회한다. 부분 갱신을 합쳐
     * 사실을 만들지 않는다(§8).
     */
    listen(what, hear) {
      const room = window.__TAURI_INTERNALS__;
      if (!room || typeof room.invoke !== "function") return;
      // Tauri v2 의 event 는 `plugin:event|listen` 으로 등록한다.
      room.invoke("plugin:event|listen", {
        event: what,
        target: { kind: "Any" },
        handler: room.transformCallback((message) => hear(message && message.payload)),
      });
    },
  };
})();
