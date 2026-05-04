package components

import (
	"fmt"

	"github.com/charmbracelet/lipgloss"

	"github.com/neilfarmer/memoire/tui/internal/styles"
)

// Header renders the top banner: app name, current section, and a few
// context chips (host, auth method).
type Header struct {
	Section   string
	Connected bool
	APIHost   string
	Auth      string
	Width     int
}

func (h Header) View() string {
	if h.Width <= 0 {
		h.Width = 100
	}
	logo := lipgloss.NewStyle().Foreground(styles.Accent).Bold(true).Render("◆ memoire")
	sep := styles.MutedText.Render("│")
	section := lipgloss.NewStyle().Foreground(styles.Primary).Bold(true).Render(h.Section)

	chips := []string{}
	if h.Auth != "" {
		chips = append(chips, styles.Chip.Render("auth "+h.Auth))
	}
	if h.APIHost != "" {
		chips = append(chips, styles.Chip.Render(h.APIHost))
	}
	conn := "● online"
	connStyle := styles.SuccessText
	if !h.Connected {
		conn = "● offline"
		connStyle = styles.DangerText
	}
	chips = append(chips, connStyle.Render(conn))

	right := lipgloss.JoinHorizontal(lipgloss.Top, chips...)

	left := lipgloss.JoinHorizontal(lipgloss.Top, logo, "  ", sep, "  ", section)
	leftWidth := lipgloss.Width(left)
	rightWidth := lipgloss.Width(right)
	gap := h.Width - leftWidth - rightWidth - 2
	if gap < 1 {
		gap = 1
	}
	bar := lipgloss.JoinHorizontal(lipgloss.Top, left, lipgloss.NewStyle().Width(gap).Render(""), right)
	rule := lipgloss.NewStyle().Foreground(styles.Border).Render(repeat("─", h.Width))
	return lipgloss.JoinVertical(lipgloss.Left,
		lipgloss.NewStyle().Width(h.Width).Padding(0, 1).Render(bar),
		rule,
	)
}

func repeat(s string, n int) string {
	if n <= 0 {
		return ""
	}
	out := make([]byte, 0, len(s)*n)
	for i := 0; i < n; i++ {
		out = append(out, s...)
	}
	return string(out)
}

// Crumbs renders a breadcrumb trail used by drill-in views.
func Crumbs(parts ...string) string {
	if len(parts) == 0 {
		return ""
	}
	rendered := make([]string, 0, len(parts)*2-1)
	for i, p := range parts {
		if i == len(parts)-1 {
			rendered = append(rendered, lipgloss.NewStyle().Foreground(styles.Primary).Bold(true).Render(p))
		} else {
			rendered = append(rendered, styles.MutedText.Render(p))
		}
		if i < len(parts)-1 {
			rendered = append(rendered, styles.MutedText.Render("  ›  "))
		}
	}
	return lipgloss.JoinHorizontal(lipgloss.Top, rendered...)
}

// FormHint renders the standard "tab/ctrl+s/esc" hint shown beneath a huh form.
func FormHint() string {
	return MutedHint("<tab> next field  <shift+tab> prev  <ctrl+s> save  <esc> cancel")
}

// MutedHint wraps a string in muted color.
func MutedHint(s string) string {
	return lipgloss.NewStyle().Foreground(lipgloss.AdaptiveColor{Light: "#64748b", Dark: "#94a3b8"}).Render(s)
}

// CountBadge formats "[ N items ]" used in screen titles.
func CountBadge(n int, label string) string {
	if label == "" {
		label = "items"
	}
	if n == 1 {
		label = trimTrailingS(label)
	}
	return styles.MutedText.Render(fmt.Sprintf("[ %d %s ]", n, label))
}

func trimTrailingS(s string) string {
	if len(s) > 1 && s[len(s)-1] == 's' {
		return s[:len(s)-1]
	}
	return s
}
