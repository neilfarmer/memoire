package screens

import (
	"fmt"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/neilfarmer/memoire/tui/internal/styles"
	"github.com/neilfarmer/memoire/tui/internal/ui/components"
)

// Placeholder is a stub screen used until the real implementation lands.
type Placeholder struct {
	Name   string
	width  int
	height int
}

func NewPlaceholder(name string) *Placeholder { return &Placeholder{Name: name} }

func (p *Placeholder) Init() tea.Cmd { return nil }

func (p *Placeholder) Update(_ tea.Msg) (tea.Model, tea.Cmd) { return p, nil }

func (p *Placeholder) View() string {
	body := fmt.Sprintf("%s screen — coming soon.\n\nPress ? for help.", p.Name)
	return lipgloss.Place(p.width, p.height, lipgloss.Center, lipgloss.Center,
		styles.MutedText.Render(body))
}

func (p *Placeholder) Title() string                  { return p.Name }
func (p *Placeholder) StatusHints() []string          { return nil }
func (p *Placeholder) Help() []components.HelpEntry   { return nil }
func (p *Placeholder) SetSize(width, height int)      { p.width, p.height = width, height }
