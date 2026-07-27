// extension.ts — gil 뷰어를 에디터 패널(WebView)에 실시간으로 띄운다.
//
// 방식(조사 확정): 확장이 `gil viewer serve` 를 자식 프로세스로 띄우고, asExternalUri 로
// 원격/Codespaces 까지 포트 포워딩한 뒤, WebView 가 그 localhost 를 iframe 으로 감싼다.
// 뷰어 코어는 하나도 안 바꾼다 — 1.5초 폴링 실시간 관전(● live)이 그대로 산다.
//
// Phase 1a: 뷰어 패널만. 인터랙션(노드클릭→Claude 호출, 승인/기각)은 다음 단계.
import * as vscode from "vscode";
import * as cp from "child_process";
import * as net from "net";
import * as http from "http";

let panel: vscode.WebviewPanel | undefined;
let server: cp.ChildProcess | undefined;

// 빈 포트 하나 찾는다(8790 부터). serve 가 이미 떠 있을 수 있으니 충돌을 피한다.
function findPort(start = 8790): Promise<number> {
  return new Promise((resolve) => {
    const s = net.createServer();
    s.once("error", () => resolve(findPort(start + 1)));
    s.listen(start, "127.0.0.1", () => {
      const port = (s.address() as net.AddressInfo).port;
      s.close(() => resolve(port));
    });
  });
}

// serve 가 실제로 응답할 때까지 기다린다(spawn 직후엔 아직 안 뜬다). 최대 ~5초.
function waitForServer(port: number, tries = 25): Promise<boolean> {
  return new Promise((resolve) => {
    const attempt = (left: number) => {
      const req = http.get(
        { host: "127.0.0.1", port, path: "/", timeout: 400 },
        (res) => {
          res.destroy();
          resolve(true);
        }
      );
      req.on("error", () => {
        if (left <= 0) return resolve(false);
        setTimeout(() => attempt(left - 1), 200);
      });
      req.on("timeout", () => {
        req.destroy();
        if (left <= 0) return resolve(false);
        setTimeout(() => attempt(left - 1), 200);
      });
    };
    attempt(tries);
  });
}

function iframeHtml(src: string): string {
  // WebView 컨테이너는 iframe 하나로 뷰어 localhost 를 감싼다. 뷰어 자체가 자기완결이라
  // 여기선 레이아웃만. allow-* 로 폴링 fetch·스크립트를 허용한다.
  return `<!doctype html><html><head><meta charset="utf-8">
<style>html,body{margin:0;padding:0;height:100%;width:100%;overflow:hidden}
#f{border:0;width:100%;height:100vh;display:block}</style></head>
<body><iframe id="f" src="${src}"
 sandbox="allow-scripts allow-same-origin allow-forms allow-popups"></iframe></body></html>`;
}

export function activate(context: vscode.ExtensionContext) {
  const open = vscode.commands.registerCommand("gilViewer.open", async () => {
    if (panel) {
      panel.reveal(vscode.ViewColumn.Beside);
      return;
    }
    const folder = vscode.workspace.workspaceFolders?.[0];
    if (!folder) {
      vscode.window.showErrorMessage("gil 뷰어: 열린 워크스페이스 폴더가 없다.");
      return;
    }
    const bin = vscode.workspace
      .getConfiguration("gilViewer")
      .get<string>("binaryPath", "gil");

    await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: "gil 뷰어 시작 중…" },
      async () => {
        const port = await findPort();
        server = cp.spawn(
          bin,
          ["viewer", "serve", "--repo", folder.uri.fsPath, "--port", String(port)],
          { env: { ...process.env, GIL_NO_VIEWER: "1" } } // 확장이 패널을 여니 브라우저 자동기동 억제
        );
        server.on("error", (err) => {
          vscode.window.showErrorMessage(
            `gil 뷰어: '${bin}' 실행 실패 — ${err.message}. gilViewer.binaryPath 설정을 확인하라.`
          );
        });

        const ready = await waitForServer(port);
        if (!ready) {
          vscode.window.showErrorMessage(
            "gil 뷰어: 서버가 응답하지 않는다. gil 이 설치돼 있고 이 폴더가 gil 저장소인지 확인하라."
          );
          server?.kill();
          server = undefined;
          return;
        }

        // 원격/Codespaces 에서도 localhost 에 닿게 자동 포트 포워딩.
        const external = await vscode.env.asExternalUri(
          vscode.Uri.parse(`http://127.0.0.1:${port}`)
        );

        panel = vscode.window.createWebviewPanel(
          "gilViewer",
          "gil 뷰어",
          vscode.ViewColumn.Beside,
          { enableScripts: true, retainContextWhenHidden: true }
        );
        panel.webview.html = iframeHtml(external.toString());

        panel.onDidDispose(() => {
          server?.kill();
          server = undefined;
          panel = undefined;
        });
      }
    );
  });

  context.subscriptions.push(open);
}

export function deactivate() {
  server?.kill();
  server = undefined;
}
