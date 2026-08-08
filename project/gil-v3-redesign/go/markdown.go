// markdown.go — 스텝 본문을 **읽히는 모양**으로 그린다 (상현님).
//
// 왜 필요한가. 스텝 본문은 커밋 메시지에 들어가는 **실험 기획서이자 보고서**다. 에이전트는
// 그걸 마크다운으로 쓴다(표·강조·코드블록·그림) — 뷰어가 그렇게 렌더한다고 문서가 약속해
// 왔고, 실제로 그렇게 쓰인다. 그런데 카드는 그 본문을 **날것 그대로** 찍고 있었다: 표는
// `| 회차 | p95 |` 라는 파이프 줄로, 강조는 `**여기서 닫는다**` 라는 별 네 개로. 사람이
// 판단하려고 보는 화면에서 **가장 정보가 많은 칸이 가장 안 읽히는 칸**이었다.
//
// **두 벌이라는 것을 알고 쓴다.** 뷰어는 같은 일을 브라우저 JS 로 한다
// (viewer_serve.go 의 renderMarkdown). 카드 조각은 Go 가 만들어 앱에 넣어 주는 물건이라
// (레이아웃은 Go 하나에만 — mcp_ui_status.go) 여기서 렌더해야 하고, `gil status --card` 로
// 시험이 실제로 읽을 수 있는 것도 이쪽뿐이다. 규칙은 **한 자리에 적는다**: docs/gil/reports.md.
// 둘이 갈리면 같은 보고서가 두 화면에서 다르게 보인다 — 갈리기 전에 여기 적어 둔다.
//
// 안전. 본문은 저장소의 커밋에서 온다(사람·에이전트가 쓴 것). 그래도 **날 HTML 을 그대로
// 통과시키지 않는다**: 글자는 전부 이스케이프하고 우리가 아는 태그만 만든다. 그림 두 가지는
// 예외적으로 통과시키되 안전한 통로로만 — 자세한 건 mdImage·mdSVGBlock 참조.
package main

import (
	"encoding/base64"
	"regexp"
	"strings"
)

var (
	reMdHeading = regexp.MustCompile(`^(#{1,6})\s+(.*)$`)
	reMdQuote   = regexp.MustCompile(`^\s*>\s?`)
	reMdUL      = regexp.MustCompile(`^\s*[-*]\s+(.*)$`)
	reMdOL      = regexp.MustCompile(`^\s*\d+\.\s+(.*)$`)
	reMdRow     = regexp.MustCompile(`^\s*\|.*\|\s*$`)
	reMdSep     = regexp.MustCompile(`^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$`)
	reMdBlock   = regexp.MustCompile("^(#{1,6}\\s|```|\\s*[-*]\\s|\\s*\\d+\\.\\s|\\s*>)")

	reMdImage  = regexp.MustCompile(`!\[([^\]]*)\]\(([^)]+)\)`)
	reMdLink   = regexp.MustCompile(`\[([^\]]+)\]\((https?://[^)]+)\)`)
	reMdCode   = regexp.MustCompile("`([^`]+)`")
	reMdBold   = regexp.MustCompile(`\*\*([^*]+)\*\*`)
	reMdItalic = regexp.MustCompile(`(^|[^*])\*([^*]+)\*`)
	reMdBr     = regexp.MustCompile(`(?i)&lt;br\s*/?&gt;`)
)

func mdEsc(s string) string {
	return strings.NewReplacer("&", "&amp;", "<", "&lt;", ">", "&gt;").Replace(s)
}

// attrSafe — 속성 값 안에 들어가는 문자열. mdEsc 는 따옴표를 안 건드리므로(본문 글자에서는
// 그게 옳다) 속성으로 갈 때만 여기서 접는다. 안 접으면 주소 안의 따옴표 하나로 속성을
// 빠져나가 우리가 안 만든 태그가 선다.
func attrSafe(s string) string {
	return strings.ReplaceAll(s, `"`, "&quot;")
}

// mdImage — 그림 하나. **data: 만 통과시킨다.**
//
// 외부 주소를 막는 이유는 두 가지다. ① 카드는 호스트의 샌드박스 iframe 안에서 도니 바깥
// 요청이 대개 막힌다 — 통과시켜 봐야 깨진 그림이 뜬다. ② 더 중요한 것: 본문에 박힌 외부
// 이미지 주소는 **저장소 내용을 바깥으로 내보내는 통로**가 된다(주소에 실어 보내면 그만이다).
// 보고서에 그림을 넣으라고 요구하면서 그 통로를 열어 둘 수는 없다.
//
// 그리고 **막은 것을 감추지 않는다** — 빈 자리를 남기면 사람은 그림이 없는 줄 안다.
func mdImage(alt, src string) string {
	if strings.HasPrefix(src, "data:image/") {
		return `<img class="mdimg" alt="` + attrSafe(alt) + `" src="` + attrSafe(src) + `" loading="lazy">`
	}
	return `<span class="mdnote">[그림 "` + alt + `" 은 카드에서 안 뜬다 — 바깥 주소 대신 ` +
		`data:image/... 로 본문에 심어라]</span>`
}

// mdSVGBlock — 본문에 그대로 쓴 &lt;svg&gt;…&lt;/svg&gt; 를 **그림 한 장으로** 만든다.
//
// 왜 <img> 로 감싸나. SVG 를 문서에 그대로 넣으면 그 안의 스크립트·외부 참조가 카드 문맥에서
// 산다 — 우리가 안 만든 태그를 통과시키는 것이라 여기서 가장 위험한 자리다. 그런데 같은 SVG
// 를 `<img src="data:image/svg+xml;...">` 로 실으면 브라우저가 **스크립트를 실행하지 않고
// 바깥 요청도 하지 않는다**(이미지 문맥의 규칙이다). 그림은 그대로 보이고 위험만 사라진다.
func mdSVGBlock(raw string) string {
	enc := base64.StdEncoding.EncodeToString([]byte(raw))
	return `<img class="mdimg" alt="svg" src="data:image/svg+xml;base64,` + enc + `" loading="lazy">`
}

// mdInlineHTML — 한 줄 안의 마크다운. 제목·표의 칸·문단이 다 이걸 거친다.
func mdInlineHTML(s string) string {
	s = mdEsc(s)
	// 그림이 링크보다 먼저다 — `![x](y)` 의 `[x](y)` 부분이 링크로 먼저 먹히면 안 된다.
	s = reMdImage.ReplaceAllStringFunc(s, func(m string) string {
		g := reMdImage.FindStringSubmatch(m)
		return mdImage(g[1], g[2])
	})
	s = reMdLink.ReplaceAllStringFunc(s, func(m string) string {
		g := reMdLink.FindStringSubmatch(m)
		return `<a href="` + attrSafe(g[2]) + `" target="_blank" rel="noopener">` + g[1] + `</a>`
	})
	s = reMdCode.ReplaceAllString(s, `<code>${1}</code>`)
	s = reMdBold.ReplaceAllString(s, `<strong>${1}</strong>`)
	s = reMdItalic.ReplaceAllString(s, `${1}<em>${2}</em>`)
	// 본문에 글자로 쓴 <br> 은 줄바꿈으로 되돌린다(위에서 이스케이프됐던 것).
	s = reMdBr.ReplaceAllString(s, "<br>")
	return s
}

// mdCells — 표 한 행을 칸으로. **이스케이프된 파이프(\|)는 칸 구분이 아니다** — 칸 안의
// 인라인 코드에 든 파이프가 표를 찢던 결함(뷰어가 v3.41.0 에 치른 값, 같은 규칙을 쓴다).
func mdCells(s string) []string {
	s = strings.TrimSpace(s)
	s = strings.TrimPrefix(s, "|")
	s = strings.TrimSuffix(s, "|")
	var out []string
	var cur strings.Builder
	for i := 0; i < len(s); i++ {
		if s[i] == '\\' && i+1 < len(s) && s[i+1] == '|' {
			cur.WriteByte('|')
			i++
			continue
		}
		if s[i] == '|' {
			out = append(out, strings.TrimSpace(cur.String()))
			cur.Reset()
			continue
		}
		cur.WriteByte(s[i])
	}
	out = append(out, strings.TrimSpace(cur.String()))
	return out
}

func mdIsRow(s string) bool { return reMdRow.MatchString(s) }
func mdIsSep(s string) bool { return reMdSep.MatchString(s) && strings.Contains(s, "-") }

// mdToHTML — 본문 한 덩어리. 지원: 제목 · 굵게 · 기울임 · 인라인코드 · 코드블록 · 표 ·
// 리스트 · 인용 · 문단 · 그림(data:) · 날 SVG. 규칙의 진실원은 docs/gil/reports.md.
func mdToHTML(src string) string {
	if strings.TrimSpace(src) == "" {
		return ""
	}
	lines := strings.Split(src, "\n")
	var b strings.Builder
	list := "" // ul | ol | ""
	closeList := func() {
		if list != "" {
			b.WriteString("</" + list + ">")
			list = ""
		}
	}
	for i := 0; i < len(lines); i++ {
		ln := lines[i]

		// 코드블록.
		if strings.HasPrefix(strings.TrimSpace(ln), "```") {
			closeList()
			var code []string
			i++
			for i < len(lines) && !strings.HasPrefix(strings.TrimSpace(lines[i]), "```") {
				code = append(code, lines[i])
				i++
			}
			b.WriteString(`<pre class="code">` + mdEsc(strings.Join(code, "\n")) + `</pre>`)
			continue
		}

		// 날 SVG — 여는 태그부터 닫는 태그까지 통째로 그림 한 장.
		if strings.HasPrefix(strings.TrimSpace(ln), "<svg") {
			closeList()
			var raw []string
			for i < len(lines) {
				raw = append(raw, lines[i])
				if strings.Contains(lines[i], "</svg>") {
					break
				}
				i++
			}
			// 닫는 태그를 못 만났으면 그림이 아니다 — 지어내지 않고 글자로 남긴다.
			joined := strings.Join(raw, "\n")
			if !strings.Contains(joined, "</svg>") {
				b.WriteString(`<pre class="code">` + mdEsc(joined) + `</pre>`)
				continue
			}
			b.WriteString(mdSVGBlock(joined))
			continue
		}

		if h := reMdHeading.FindStringSubmatch(ln); h != nil {
			closeList()
			lv := itoa(len(h[1]))
			b.WriteString("<h" + lv + ">" + mdInlineHTML(h[2]) + "</h" + lv + ">")
			continue
		}
		if reMdQuote.MatchString(ln) {
			closeList()
			b.WriteString("<blockquote>" + mdInlineHTML(reMdQuote.ReplaceAllString(ln, "")) + "</blockquote>")
			continue
		}

		// 표 — 머리행 + 구분행이 붙어 있을 때만.
		if mdIsRow(ln) && i+1 < len(lines) && mdIsSep(lines[i+1]) {
			closeList()
			head := mdCells(ln)
			b.WriteString(`<table><thead><tr>`)
			for _, c := range head {
				b.WriteString("<th>" + mdInlineHTML(c) + "</th>")
			}
			b.WriteString("</tr></thead><tbody>")
			i += 2
			for i < len(lines) && mdIsRow(lines[i]) && !mdIsSep(lines[i]) {
				cs := mdCells(lines[i])
				// 칸 수를 머리행에 맞춘다(GFM). 한 행이 어긋난 순간 표 전체가 밀려 보인다 —
				// 사람이 "표가 깨졌다"고 말하는 그 모양이다.
				for len(cs) < len(head) {
					cs = append(cs, "")
				}
				cs = cs[:len(head)]
				b.WriteString("<tr>")
				for _, c := range cs {
					b.WriteString("<td>" + mdInlineHTML(c) + "</td>")
				}
				b.WriteString("</tr>")
				i++
			}
			i--
			b.WriteString("</tbody></table>")
			continue
		}

		if m := reMdUL.FindStringSubmatch(ln); m != nil {
			if list != "ul" {
				closeList()
				b.WriteString("<ul>")
				list = "ul"
			}
			b.WriteString("<li>" + mdInlineHTML(m[1]) + "</li>")
			continue
		}
		if m := reMdOL.FindStringSubmatch(ln); m != nil {
			if list != "ol" {
				closeList()
				b.WriteString("<ol>")
				list = "ol"
			}
			b.WriteString("<li>" + mdInlineHTML(m[1]) + "</li>")
			continue
		}
		if strings.TrimSpace(ln) == "" {
			closeList()
			continue
		}

		// 문단 — 이어지는 줄을 모은다. 다만 **표는 문단의 일부가 아니다**: 빈 줄 없이 문단에
		// 붙은 표(에이전트 보고서에서 아주 흔하다)를 문단이 삼키면 표 문법이 날것으로 찍힌다.
		closeList()
		para := ln
		startsTable := func(k int) bool {
			return k+1 < len(lines) && mdIsRow(lines[k]) && mdIsSep(lines[k+1])
		}
		for i+1 < len(lines) && strings.TrimSpace(lines[i+1]) != "" &&
			!reMdBlock.MatchString(lines[i+1]) && !startsTable(i+1) &&
			!strings.HasPrefix(strings.TrimSpace(lines[i+1]), "<svg") {
			i++
			para += "<br>" + lines[i]
		}
		b.WriteString("<p>" + mdInlineHTML(para) + "</p>")
	}
	closeList()
	return b.String()
}
