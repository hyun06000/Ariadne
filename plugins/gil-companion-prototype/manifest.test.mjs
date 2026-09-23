// **Host adapter manifest 의 시험** — `node --test`
//
// Codex 와 Claude Code 는 별도 GIL 제품이 아니다. 같은 `server.mjs`·Core·Skill 을 쓰고
// manifest 만 나눈다. 여기서 지키는 것은 그 불변식 셋이다.
//
//   1. Host 하나가 MCP server 를 **정확히 하나** 등록한다 (이중 등록이 없다).
//   2. 두 manifest 가 **같은** server source·Skill·Core 로 내려앉는다.
//   3. manifest 와 marketplace 에 **개발자의 절대 경로가 없다**.

import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";

const PLUGIN = import.meta.dirname;
const REPO = resolve(PLUGIN, "..", "..");

const read = (p) => JSON.parse(readFileSync(p, "utf8"));

/** Host adapter — manifest 의 자리와, 그 Host 가 plugin root 를 부르는 이름. */
const HOSTS = [
  { host: "codex",       manifest: join(PLUGIN, ".codex-plugin", "plugin.json"),  root: "." },
  { host: "claude-code", manifest: join(PLUGIN, ".claude-plugin", "plugin.json"), root: "${CLAUDE_PLUGIN_ROOT}" },
];

/** Host 가 쓰는 root 표기를 실제 자리로 푼다 — Host 가 그러듯 **경로 앞머리로만** 푼다.
 *  root 표기로 시작하지 않는 값은 풀지 않는다: 그런 값은 Plugin 이 아니라 Host 의 cwd 에
 *  매이므로, 여기서 조용히 성공시키면 시험이 거짓말을 한다. */
function landsOn(value, rootToken, host) {
  assert.ok(value === rootToken || value.startsWith(`${rootToken}/`),
    `${host}: plugin root 표기(${rootToken})로 시작하지 않는다 — ${value}`);
  return resolve(PLUGIN + value.slice(rootToken.length));
}

test("두 Host 의 manifest 가 모두 있고 읽을 수 있다", () => {
  for (const { host, manifest } of HOSTS) {
    assert.ok(existsSync(manifest), `${host}: manifest 가 없다 — ${manifest}`);
    assert.doesNotThrow(() => read(manifest), `${host}: manifest 가 JSON 이 아니다`);
  }
});

test("Host 하나가 MCP server 를 정확히 하나 등록한다", () => {
  for (const { host, manifest } of HOSTS) {
    const m = read(manifest);
    assert.equal(typeof m.mcpServers, "object",
      `${host}: mcpServers 가 inline object 가 아니다 — 경로 문자열이면 Host 의 기본 탐색과 겹쳐 두 번 등록될 수 있다`);
    const keys = Object.keys(m.mcpServers);
    assert.deepEqual(keys, ["gil-companion"], `${host}: 등록된 server 가 하나가 아니다 — ${keys.join(", ")}`);
  }
});

test("plugin root 에 .mcp.json 이 없다 — Host 기본 탐색과 이중 등록되지 않는다", () => {
  assert.equal(existsSync(join(PLUGIN, ".mcp.json")), false,
    "plugin root 의 .mcp.json 은 두 Host 모두가 스스로 찾아내므로, inline 등록과 겹쳐 server 가 둘이 된다");
});

test("두 manifest 가 같은 server source 로 내려앉는다", () => {
  const landed = HOSTS.map(({ host, manifest, root }) => {
    const server = read(manifest).mcpServers["gil-companion"];
    assert.equal(server.command, "node", `${host}: command 가 node 가 아니다`);
    assert.equal(server.args.length, 1, `${host}: args 가 하나가 아니다`);
    return { host, entry: landsOn(server.args[0], root, host), cwd: landsOn(server.cwd, root, host) };
  });
  const common = join(PLUGIN, "server.mjs");
  for (const { host, entry, cwd } of landed) {
    assert.equal(entry, common, `${host}: 공용 server.mjs 가 아닌 곳을 연다 — ${entry}`);
    assert.equal(cwd, PLUGIN, `${host}: plugin root 바깥을 cwd 로 삼는다 — ${cwd}`);
  }
  assert.equal(new Set(landed.map((l) => l.entry)).size, 1, "두 Host 가 서로 다른 server 를 연다");
});

test("Skill 과 Core 는 plugin root 하나에만 있다", () => {
  assert.ok(existsSync(join(PLUGIN, "skills", "gil-companion", "SKILL.md")), "공용 Skill 이 없다");
  assert.ok(existsSync(join(PLUGIN, "core.mjs")), "공용 Core 배선이 없다");

  // adapter 디렉터리는 **manifest 만** 담는다. 여기에 server·Skill·Core 가 복제되면
  // 정본이 둘이 되고, 한쪽이 낡는다.
  for (const { host, manifest } of HOSTS) {
    const dir = dirname(manifest);
    const carried = readdirSync(dir);
    assert.deepEqual(carried, ["plugin.json"],
      `${host}: adapter 디렉터리가 manifest 말고 다른 것을 담았다 — ${carried.join(", ")}`);
  }
});

test("Codex manifest 의 Skill 자리가 공용 Skill 을 가리킨다", () => {
  const m = read(HOSTS[0].manifest);
  assert.equal(resolve(PLUGIN, m.skills), join(PLUGIN, "skills"));
  // Claude Code 는 skills/ 를 언제나 스스로 훑으므로 manifest 에 자리를 적지 않는다.
  assert.equal("skills" in read(HOSTS[1].manifest), false,
    "claude-code: skills 자리를 적었다 — Claude Code 는 skills/ 를 스스로 훑는다");
});

test("두 manifest 가 같은 plugin 이름을 말한다", () => {
  const names = HOSTS.map(({ manifest }) => read(manifest).name);
  assert.equal(new Set(names).size, 1, `Host 마다 이름이 다르다 — ${names.join(" vs ")}`);
});

test("manifest 와 marketplace 에 개발자의 절대 경로가 없다", () => {
  const home = homedir();
  const files = [
    ...HOSTS.map((h) => h.manifest),
    join(REPO, ".claude-plugin", "marketplace.json"),
  ];
  for (const file of files) {
    const said = readFileSync(file, "utf8");
    assert.equal(said.includes(home), false, `${file}: 개발자 home 이 적혀 있다`);
    for (const leak of ["/Users/", "/home/", "$HOME", "~/", REPO]) {
      assert.equal(said.includes(leak), false, `${file}: 기계에 매인 자리가 적혀 있다 — ${leak}`);
    }
  }
});

test("저장소 marketplace 가 local development 경로임을 스스로 밝힌다", () => {
  const p = join(REPO, ".claude-plugin", "marketplace.json");
  assert.ok(existsSync(p), "저장소 최상위 marketplace.json 이 없다");
  const m = read(p);

  assert.equal(m.plugins.length, 1);
  const [entry] = m.plugins;
  assert.equal(entry.name, read(HOSTS[1].manifest).name, "marketplace 가 다른 이름을 말한다");

  const source = resolve(REPO, entry.source);
  assert.equal(source, PLUGIN, `marketplace 가 정본이 아닌 곳을 가리킨다 — ${source}`);
  assert.ok(statSync(join(source, ".claude-plugin", "plugin.json")).isFile(),
    "marketplace 가 가리키는 자리에 Claude manifest 가 없다");

  // 비개발자 공개 배포로 보이면 안 된다. source clone 과 make-core.sh 가 **여전히** 필요하다.
  const told = `${m.metadata.description} ${entry.description}`.toLowerCase();
  for (const owed of ["local", "source clone", "make-core.sh"]) {
    assert.ok(told.includes(owed), `marketplace 가 밝히지 않은 것 — ${owed}`);
  }
});
