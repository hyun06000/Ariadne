// viewer_retire.go — **은퇴한 것이 남긴 자리를 은퇴시킨 쪽이 치운다** (2026-08-10).
//
// 왜 이 파일이 필요한가. 브라우저 관전 서버는 `setsid`/DETACHED 로 부모에서 떼어져 떴다 —
// gil 이 죽어도 그 프로세스는 산다. 그리고 끄는 유일한 수단(`gil viewer stop`)이 뷰어와 함께
// 사라졌다. 그러면 이 릴리스로 올린 사람의 머신에는:
//
//	· 포트를 쥔 채 **낡은 그래프를 계속 보여주는** 서버가 남고(사람은 그걸 지금 상태로 읽는다),
//	· 바탕화면·Dock 의 런처는 `gil viewer open` 을 부르다 "은퇴했다"만 받는다.
//
// 도구가 자기가 만든 상태에서 빠져나올 길을 자기가 줘야 한다(v3.58.1 이 chain-merge --resume
// 에서 세운 규칙). 그래서 **뷰어를 지운 바이너리에 회수 명령을 남긴다.** 이 명령은 한 릴리스용
// 유물이고, 그 사실을 도움말이 적는다.
//
// 남의 것은 건드리지 않는다 — 포트가 열렸다는 사실은 주인을 말해 주지 않으므로, 옛 뷰어가
// 스스로 밝히는 `/whoami` 로 gil 뷰어임이 확인된 것만 끈다.
package main

import (
	"encoding/json"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"time"
)

// cmdViewerCleanup — gil viewer-cleanup [--dry-run]
func cmdViewerCleanup(args []string) {
	fs := newFlags("gil viewer-cleanup")
	dry := fs.boolFlag("dry-run")
	fs.parse(args)

	println2("gil viewer-cleanup — 은퇴한 브라우저 관전 창이 남긴 것을 치운다.")
	if *dry {
		println2("  (--dry-run: 무엇을 치울지만 말하고 아무것도 안 한다)")
	}
	println2("")

	stopped, seen := stopStrayViewers(*dry)
	if seen == 0 {
		println2("  떠 있는 옛 뷰어: 없다.")
	} else {
		println2("  떠 있는 옛 뷰어: " + itoa(seen) + "개" + orDefault(map[bool]string{true: " (끄지 않았다 — dry-run)"}[*dry], ""))
		for _, ln := range stopped {
			println2("    " + ln)
		}
	}
	println2("")

	found, removed := removeViewerLaunchers(*dry)
	if len(found) == 0 {
		println2("  만들어 둔 런처: 없다(알려진 자리에서).")
	} else {
		for _, ln := range found {
			println2("    " + ln)
		}
		if !*dry && removed == 0 {
			// **못 치웠으면 못 치웠다고 적는다.** 조용히 넘기면 사람은 치워진 줄 안다.
			println2("    ⚠ 하나도 지우지 못했다 — 위 경로를 직접 지워라.")
		}
	}
	println2("")
	println2("그림은 그대로 있다: " + surfaceCmd("graph") + " · " +
		"`gil graph --html --out <파일>` · MCP 호스트에서는 gil_graph·gil_status.")
}

// stopStrayViewers — 옛 뷰어가 쥐고 있는 포트를 훑어 **gil 뷰어임이 확인된 것만** 끈다.
//
// 포트 범위는 옛 뷰어의 기본(8790)과 그 폴백 대역이다. 열린 포트가 있어도 /whoami 가 gil
// 뷰어라고 답하지 않으면 남의 것이다 — 건드리지 않는다.
func stopStrayViewers(dry bool) ([]string, int) {
	var out []string
	seen := 0
	client := &http.Client{Timeout: 300 * time.Millisecond}
	for p := 8790; p <= 8809; p++ {
		port := itoa(p)
		c, err := net.DialTimeout("tcp", "127.0.0.1:"+port, 150*time.Millisecond)
		if err != nil {
			continue
		}
		c.Close()
		pid, repo := oldViewerAt(client, port)
		if pid <= 0 {
			continue // gil 뷰어가 아니다 — 남의 포트다
		}
		seen++
		where := repo
		if where == "" {
			where = "(어느 저장소인지 안 밝힌다 — 아주 옛 뷰어)"
		}
		if dry {
			out = append(out, "127.0.0.1:"+port+" (pid "+itoa(pid)+") → "+where)
			continue
		}
		proc, err := os.FindProcess(pid)
		if err != nil {
			out = append(out, "⚠ 127.0.0.1:"+port+" (pid "+itoa(pid)+"): 프로세스를 못 찾았다")
			continue
		}
		if err := proc.Signal(os.Interrupt); err != nil {
			if err2 := proc.Kill(); err2 != nil {
				out = append(out, "⚠ 127.0.0.1:"+port+" (pid "+itoa(pid)+"): 종료 실패 — "+err2.Error())
				continue
			}
		}
		out = append(out, "껐다: 127.0.0.1:"+port+" (pid "+itoa(pid)+") → "+where)
	}
	return out, seen
}

// oldViewerAt — 그 포트의 옛 뷰어가 밝히는 pid·저장소. gil 뷰어가 아니면 (0, "").
func oldViewerAt(c *http.Client, port string) (int, string) {
	resp, err := c.Get("http://127.0.0.1:" + port + "/whoami")
	if err != nil {
		return 0, ""
	}
	defer resp.Body.Close()
	b, err := io.ReadAll(io.LimitReader(resp.Body, 4096))
	if err != nil {
		return 0, ""
	}
	var got struct {
		Pid  int    `json:"pid"`
		Repo string `json:"repo"`
	}
	if json.Unmarshal(b, &got) != nil {
		return 0, ""
	}
	return got.Pid, strings.TrimSpace(got.Repo)
}

// removeViewerLaunchers — 옛 `gil viewer shortcut` 이 만든 런처를 알려진 자리에서 지운다.
//
// **알려진 자리뿐이다.** 옛 명령은 `--out` 으로 아무 데나 만들 수 있었고 gil 은 그 목록을
// 갖고 있지 않다. 그러니 여기서 "다 지웠다"고 말하면 거짓이다 — 지운 것만 말하고, 다른
// 자리에 만들었으면 그건 사람이 안다고 적는다.
func removeViewerLaunchers(dry bool) ([]string, int) {
	home, err := os.UserHomeDir()
	if err != nil || home == "" {
		return nil, 0
	}
	var cands []string
	switch runtime.GOOS {
	case "darwin":
		cands = globQuiet(filepath.Join(home, "Applications", "gil 뷰어 — *.app"))
	case "windows":
		cands = globQuiet(filepath.Join(home, "Desktop", "gil-viewer-*.cmd"))
	default:
		cands = globQuiet(filepath.Join(home, ".local", "share", "applications", "gil-viewer-*.desktop"))
	}
	var out []string
	removed := 0
	for _, p := range cands {
		if dry {
			out = append(out, "런처: "+p)
			continue
		}
		if err := os.RemoveAll(p); err != nil {
			out = append(out, "⚠ 런처를 못 지웠다: "+p+" — "+err.Error())
			continue
		}
		removed++
		out = append(out, "지웠다: "+p)
	}
	if len(out) > 0 {
		out = append(out, "(`--out` 으로 다른 자리에 만들었으면 gil 은 그 자리를 모른다 — 그건 직접 지워라.)")
	}
	return out, removed
}

func globQuiet(pattern string) []string {
	m, err := filepath.Glob(pattern)
	if err != nil {
		return nil
	}
	return m
}
