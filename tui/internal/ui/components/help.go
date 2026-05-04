package components

import (
	"strings"

	"github.com/charmbracelet/lipgloss"

	"github.com/neilfarmer/memoire/tui/internal/styles"
)

// HelpEntry pairs a key combo with its description.
type HelpEntry struct {
	Keys string
	Desc string
}

// HelpView renders the global help overlay. Each section has a heading and a
// list of key/description pairs.
func HelpView(width, height int, sections map[string][]HelpEntry, order []string) string {
	rows := []string{styles.Title.Render("Help"), ""}
	for _, name := range order {
		entries := sections[name]
		if len(entries) == 0 {
			continue
		}
		rows = append(rows, lipgloss.NewStyle().Foreground(styles.Primary).Bold(true).Render(name))
		for _, e := range entries {
			rows = append(rows, "  "+styles.KeyHint(e.Keys, e.Desc))
		}
		rows = append(rows, "")
	}
	rows = append(rows, styles.MutedText.Render("press ? again to close"))
	body := strings.Join(rows, "\n")

	w := width - 8
	if w > 80 {
		w = 80
	}
	if w < 30 {
		w = 30
	}
	box := styles.BoxFocused.Width(w).Render(body)
	return lipgloss.Place(width, height, lipgloss.Center, lipgloss.Center, box)
}
