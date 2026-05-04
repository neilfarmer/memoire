package screens

import (
	"fmt"
	"sort"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/neilfarmer/memoire/tui/internal/api"
	"github.com/neilfarmer/memoire/tui/internal/styles"
	"github.com/neilfarmer/memoire/tui/internal/ui/components"
)

type Admin struct {
	client *api.Client
	width  int
	height int

	loading bool
	err     error
	costs   api.Costs
	stats   api.AdminStats
}

type adminLoadedMsg struct {
	costs api.Costs
	stats api.AdminStats
	err   error
}

func newAdmin(c *api.Client) *Admin { return &Admin{client: c} }

func (a *Admin) Init() tea.Cmd { return a.refresh() }

func (a *Admin) refresh() tea.Cmd {
	c := a.client
	return func() tea.Msg {
		costs, _ := c.Costs()
		stats, err := c.AdminStats()
		return adminLoadedMsg{costs: costs, stats: stats, err: err}
	}
}

func (a *Admin) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch m := msg.(type) {
	case adminLoadedMsg:
		a.loading = false
		a.err = m.err
		a.costs = m.costs
		a.stats = m.stats
		return a, nil
	case tea.KeyMsg:
		if m.String() == "r" || m.String() == "ctrl+r" {
			return a, a.refresh()
		}
	}
	return a, nil
}

func (a *Admin) View() string {
	if a.loading {
		return styles.MutedText.Render("Loading admin stats...")
	}
	rows := []string{styles.Title.Render("Costs (this month)")}
	rows = append(rows, mapTable(a.costs)...)
	rows = append(rows, "", styles.Title.Render("Stats"))
	rows = append(rows, mapTable(a.stats)...)
	if a.err != nil {
		rows = append(rows, "", styles.DangerText.Render(a.err.Error()))
	}
	rows = append(rows, "", styles.MutedText.Render("r refresh"))
	return lipgloss.JoinVertical(lipgloss.Left, rows...)
}

func mapTable(m map[string]any) []string {
	if m == nil {
		return []string{styles.MutedText.Render("(unavailable)")}
	}
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	out := make([]string, 0, len(keys))
	for _, k := range keys {
		out = append(out, fmt.Sprintf("  %-32s %v", k, formatVal(m[k])))
	}
	return out
}

func formatVal(v any) string {
	switch x := v.(type) {
	case float64:
		return fmt.Sprintf("%.4f", x)
	case map[string]any:
		parts := []string{}
		for k, vv := range x {
			parts = append(parts, fmt.Sprintf("%s=%v", k, vv))
		}
		return strings.Join(parts, " ")
	default:
		return fmt.Sprintf("%v", v)
	}
}

func (a *Admin) Title() string         { return "Admin" }
func (a *Admin) StatusHints() []string { return []string{styles.KeyHint("r", "refresh")} }
func (a *Admin) Help() []components.HelpEntry {
	return []components.HelpEntry{{Keys: "r", Desc: "refresh stats"}}
}
func (a *Admin) SetSize(w, h int) { a.width, a.height = w, h }
