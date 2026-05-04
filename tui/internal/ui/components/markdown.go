package components

import (
	"github.com/charmbracelet/glamour"
)

// RenderMarkdown returns a styled markdown rendering. width=0 picks an auto width.
//
// IMPORTANT: do NOT use glamour.WithAutoStyle() here. AutoStyle issues an OSC
// 11 (background colour) query against the terminal on every renderer
// construction. Some terminals (Ghostty, certain iTerm/tmux combinations)
// reply via stdin, bubbletea reads the reply as fake key events, and the
// resulting feedback loop freezes the program. Pin a fixed dark style.
func RenderMarkdown(body string, width int) string {
	if body == "" {
		return ""
	}
	opts := []glamour.TermRendererOption{
		glamour.WithStandardStyle("dark"),
	}
	if width > 0 {
		opts = append(opts, glamour.WithWordWrap(width))
	}
	r, err := glamour.NewTermRenderer(opts...)
	if err != nil {
		return body
	}
	out, err := r.Render(body)
	if err != nil {
		return body
	}
	return out
}
