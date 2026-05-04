package screens

import (
	tea "github.com/charmbracelet/bubbletea"

	"github.com/neilfarmer/memoire/tui/internal/ui/components"
)

// Screen is implemented by every feature view. It extends tea.Model with a
// few hooks the root app uses to render the chrome (header section name,
// status-bar key hints, help overlay entries).
type Screen interface {
	tea.Model
	Title() string
	StatusHints() []string
	Help() []components.HelpEntry
	SetSize(width, height int)
}
