package components

import (
	"strings"

	"github.com/charmbracelet/lipgloss"

	"github.com/neilfarmer/memoire/tui/internal/styles"
)

// StatusBar renders the bottom hint footer plus an optional flash message.
type StatusBar struct {
	Screen string
	Mode   string
	Flash  string
	Hints  []string
	Width  int
}

func (s StatusBar) View() string {
	if s.Width <= 0 {
		s.Width = 80
	}
	rule := lipgloss.NewStyle().Foreground(styles.Border).Render(strings.Repeat("─", s.Width))

	leftBits := []string{}
	if s.Screen != "" {
		leftBits = append(leftBits, lipgloss.NewStyle().Foreground(styles.Accent).Bold(true).Render(s.Screen))
	}
	if s.Mode != "" {
		leftBits = append(leftBits, styles.MutedText.Render(s.Mode))
	}
	left := strings.Join(leftBits, "  ")

	hints := strings.Join(s.Hints, "  ")
	hintsRendered := lipgloss.NewStyle().Foreground(styles.Muted).Render(hints)

	flash := s.Flash

	leftWidth := lipgloss.Width(left)
	hintsWidth := lipgloss.Width(hintsRendered)
	flashWidth := s.Width - leftWidth - hintsWidth - 6
	if flashWidth < 0 {
		flashWidth = 0
	}
	flashCell := lipgloss.NewStyle().Width(flashWidth).Foreground(styles.Positive).Render(flash)

	row := lipgloss.JoinHorizontal(lipgloss.Top, left, "  ", flashCell, "  ", hintsRendered)
	bar := lipgloss.NewStyle().Width(s.Width).Padding(0, 1).Render(row)
	return lipgloss.JoinVertical(lipgloss.Left, rule, bar)
}
