// fastlog.go — 한 번 읽고 여러 번 답한다 (2026-08-01, 상현님: "테스트 너무 오래 걸린다").
//
// ## 무엇이 느렸나 — 재고서 알았다
//
// 스텝 하나를 새기는 데 181ms 가 걸렸고, 그중 163ms 가 **git 프로세스 24개**였다. 그래프
// 크기와는 거의 무관했다(스텝 5개일 때나 30개일 때나 같았다) — 비용은 데이터가 아니라
// **호출 횟수**였다. 그리고 그 24번 중 대부분은 *같은 커밋들을* 트레일러만 바꿔 다시 읽는
// 것이었다: Gil-Chain 하나 보려고 한 번, Gil-Chain-Purpose 보려고 또 한 번.
//
// 읽기 캐시는 이미 있었지만 **명령줄 전체를 키로 삼아** 형식이 한 글자만 달라도 새 프로세스를
// 띄웠다. 캐시가 있었는데도 24번이었던 이유다.
//
// ## 무엇을 하나
//
// 범위(--branches·HEAD·…)마다 **딱 한 번** 원문(%H·%s·%P·%T·저자·%B)을 긁어 두고, 이후의
// `git log --format=…` 요청은 그 표에서 만들어 돌려준다. 트레일러는 본문(%B)에서 우리가
// 직접 판다 — git 의 트레일러 규칙과 같은 규칙으로(마지막 문단, `Key: value`, 이어지는 줄은
// 공백으로 시작).
//
// 모르는 지시자가 하나라도 있으면 **그냥 git 에 넘긴다.** 최적화가 정확성을 이기면 안 된다:
// 여기서 틀리면 그래프를 잘못 읽는 것이고, 그건 느린 것보다 나쁘다.
package main

import (
	"strings"
)

// rawCommit — 원문 한 줄. 트레일러는 필요할 때 본문에서 판다(대부분의 커밋은 안 쓰인다).
type rawCommit struct {
	sha, subj, parents, tree string
	an, ae, ad               string
	body                     string
	tr                       map[string][]string // lazy — nil 이면 아직 안 팠다
}

// trailersOf — 본문 마지막 문단에서 트레일러를 판다(git 과 같은 규칙).
func (c *rawCommit) trailersOf() map[string][]string {
	if c.tr != nil {
		return c.tr
	}
	c.tr = map[string][]string{}
	lines := strings.Split(strings.TrimRight(c.body, "\n"), "\n")
	// 마지막 문단(빈 줄 뒤)만 트레일러 후보다.
	start := 0
	for i := len(lines) - 1; i >= 0; i-- {
		if strings.TrimSpace(lines[i]) == "" {
			start = i + 1
			break
		}
	}
	var keys []string
	var vals []string
	okBlock := start < len(lines)
	for _, ln := range lines[start:] {
		if strings.HasPrefix(ln, " ") || strings.HasPrefix(ln, "\t") {
			if len(vals) > 0 { // 이어지는 줄
				vals[len(vals)-1] += "\n" + strings.TrimLeft(ln, " \t")
				continue
			}
			okBlock = false
			break
		}
		k, v, found := strings.Cut(ln, ": ")
		if !found || k == "" || strings.ContainsAny(k, " \t") {
			okBlock = false
			break
		}
		keys = append(keys, k)
		vals = append(vals, v)
	}
	if okBlock {
		for i, k := range keys {
			c.tr[k] = append(c.tr[k], vals[i])
		}
	}
	return c.tr
}

// rawScanCache — 범위별 원문 표. gitReadCache 와 같은 수명을 산다(쓰기가 있으면 버린다).
var rawScanCache = map[string][]*rawCommit{}

const rawFsep = "\x01"
const rawRsep = "\x02\n"

// rawScan — 이 범위의 커밋 원문을 한 번만 긁는다. 실패하면 nil(그러면 호출자가 git 에 넘긴다).
func rawScan(rest []string) []*rawCommit {
	key := strings.Join(rest, "\x00")
	if v, ok := rawScanCache[key]; ok {
		return v
	}
	f := "--format=%H" + rawFsep + "%s" + rawFsep + "%P" + rawFsep + "%T" + rawFsep +
		"%an" + rawFsep + "%ae" + rawFsep + "%aI" + rawFsep + "%B" + rawRsep
	out, err := gitTry(append([]string{"log", f}, rest...)...)
	if err != nil {
		rawScanCache[key] = nil
		return nil
	}
	var cs []*rawCommit
	for _, rec := range strings.Split(out, rawRsep) {
		rec = strings.TrimPrefix(rec, "\n")
		if strings.TrimSpace(rec) == "" {
			continue
		}
		p := strings.SplitN(rec, rawFsep, 8)
		if len(p) < 8 {
			continue
		}
		cs = append(cs, &rawCommit{sha: p[0], subj: p[1], parents: p[2], tree: p[3],
			an: p[4], ae: p[5], ad: p[6], body: p[7]})
	}
	rawScanCache[key] = cs
	return cs
}

// expandFormat — 한 커밋에 대해 --format 문자열을 펼친다. 모르는 지시자를 만나면 (,false).
func expandFormat(f string, c *rawCommit) (string, bool) {
	var b strings.Builder
	for i := 0; i < len(f); {
		if f[i] != '%' {
			b.WriteByte(f[i])
			i++
			continue
		}
		if i+1 >= len(f) {
			return "", false
		}
		switch f[i+1] {
		case 'H':
			b.WriteString(c.sha)
			i += 2
		case 'h':
			b.WriteString(first9(c.sha))
			i += 2
		case 's':
			b.WriteString(c.subj)
			i += 2
		case 'P':
			b.WriteString(c.parents)
			i += 2
		case 'T':
			b.WriteString(c.tree)
			i += 2
		case 'B':
			b.WriteString(c.body)
			i += 2
		case 'n':
			b.WriteString("\n")
			i += 2
		case 'a':
			if strings.HasPrefix(f[i:], "%an") {
				b.WriteString(c.an)
				i += 3
			} else if strings.HasPrefix(f[i:], "%ae") {
				b.WriteString(c.ae)
				i += 3
			} else if strings.HasPrefix(f[i:], "%aI") {
				b.WriteString(c.ad)
				i += 3
			} else {
				return "", false
			}
		case 'x':
			// %x1f 같은 16진 리터럴.
			if i+3 >= len(f) {
				return "", false
			}
			var v int
			for _, ch := range f[i+2 : i+4] {
				d := hexVal(byte(ch))
				if d < 0 {
					return "", false
				}
				v = v*16 + d
			}
			b.WriteByte(byte(v))
			i += 4
		case '(':
			end := strings.Index(f[i:], ")")
			if end < 0 {
				return "", false
			}
			spec := f[i+2 : i+end]
			i += end + 1
			const pre = "trailers:key="
			if !strings.HasPrefix(spec, pre) {
				return "", false
			}
			rest := spec[len(pre):]
			key, opts, _ := strings.Cut(rest, ",")
			// 우리가 쓰는 형태는 valueonly [+ separator=%x00] 둘뿐이다. 그 밖이면 git 에 넘긴다.
			sepStr := "\n"
			switch opts {
			case "valueonly":
			case "valueonly,separator=%x00":
				sepStr = "\x00"
			default:
				return "", false
			}
			vs := c.trailersOf()[key]
			b.WriteString(strings.Join(vs, sepStr))
		default:
			return "", false
		}
	}
	return b.String(), true
}

func hexVal(b byte) int {
	switch {
	case b >= '0' && b <= '9':
		return int(b - '0')
	case b >= 'a' && b <= 'f':
		return int(b-'a') + 10
	case b >= 'A' && b <= 'F':
		return int(b-'A') + 10
	}
	return -1
}

// fastGitLog — `git log --format=<F> <나머지>` 를 원문 표에서 만들어 돌려준다.
// 만들 수 없으면 (,false) — 그러면 호출자가 진짜 git 을 부른다.
func fastGitLog(args []string) (string, bool) {
	if !gitCacheOn || len(args) == 0 {
		return "", false
	}
	var format string
	var rest []string
	for _, a := range args {
		switch {
		case strings.HasPrefix(a, "--format="):
			if format != "" {
				return "", false
			}
			format = strings.TrimPrefix(a, "--format=")
		case strings.HasPrefix(a, "--pretty"), a == "-p", a == "--patch", a == "--stat",
			a == "--name-only", a == "--name-status", a == "--numstat", a == "--graph":
			return "", false // 원문 표로는 못 만드는 것들
		default:
			rest = append(rest, a)
		}
	}
	if format == "" {
		return "", false
	}
	cs := rawScan(rest)
	if cs == nil {
		return "", false
	}
	var b strings.Builder
	for _, c := range cs {
		s, ok := expandFormat(format, c)
		if !ok {
			return "", false
		}
		b.WriteString(s)
		b.WriteString("\n") // git 은 커밋마다 개행을 붙인다
	}
	return b.String(), true
}
