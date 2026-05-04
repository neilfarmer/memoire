package components

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"

	"github.com/neilfarmer/memoire/tui/internal/styles"
)

type SidebarItem struct {
	Key   string
	Label string
	Icon  string
}

type Sidebar struct {
	Items   []SidebarItem
	Active  string
	Width   int
	Focused bool
}

func (s Sidebar) View() string {
	if s.Width <= 0 {
		s.Width = 22
	}
	rows := make([]string, 0, len(s.Items)+3)
	rows = append(rows, lipgloss.NewStyle().Foreground(styles.Accent).Bold(true).Render(" memoire"))
	rows = append(rows, styles.MutedText.Render(strings.Repeat("─", s.Width-2)))
	for i, it := range s.Items {
		num := fmt.Sprintf("%d", (i%9)+1)
		icon := it.Icon
		if icon == "" {
			icon = "•"
		}
		row := fmt.Sprintf("  %s  %s  %s", styles.MutedText.Render(num), icon, it.Label)
		if it.Key == s.Active {
			row = lipgloss.NewStyle().
				Foreground(lipgloss.AdaptiveColor{Light: "#ffffff", Dark: "#0b0f14"}).
				Background(styles.Primary).
				Bold(true).
				Width(s.Width - 2).
				Render(fmt.Sprintf(" › %s  %s", icon, it.Label))
		}
		rows = append(rows, row)
	}
	rows = append(rows, "")
	rows = append(rows, styles.MutedText.Render(strings.Repeat("─", s.Width-2)))
	rows = append(rows, styles.MutedText.Render("  ? help    ⌘q quit"))

	box := styles.Box
	if s.Focused {
		box = styles.BoxFocused
	}
	return box.Width(s.Width).Render(lipgloss.JoinVertical(lipgloss.Left, rows...))
}
