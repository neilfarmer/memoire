package components

import (
	"github.com/charmbracelet/lipgloss"

	"github.com/neilfarmer/memoire/tui/internal/styles"
)

// ConfirmView renders a centred yes/no dialog.
func ConfirmView(prompt string, width, height int) string {
	dialog := styles.BoxFocused.Width(50).Render(
		lipgloss.JoinVertical(lipgloss.Left,
			styles.Title.Render(prompt),
			"",
			styles.MutedText.Render("y to confirm, n or esc to cancel"),
		),
	)
	return lipgloss.Place(width, height, lipgloss.Center, lipgloss.Center, dialog)
}
