// smoke is a tiny harness that renders every screen with a stub API client
// and prints the resulting frame. Run with `go run ./tui/cmd/smoke`.
package main

import (
	"fmt"
	"os"
	"strings"

	tea "github.com/charmbracelet/bubbletea"

	"github.com/neilfarmer/memoire/tui/internal/api"
	"github.com/neilfarmer/memoire/tui/internal/ui"
)

func main() {
	client := api.New("https://example.invalid", "pat_smoke")
	app := ui.New(client, ui.DefaultFactories(client))
	_ = app.Init()
	model, _ := app.Update(tea.WindowSizeMsg{Width: 120, Height: 40})
	for i, s := range ui.SidebarOrder {
		var m tea.Model
		if i < 9 {
			m, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{rune('1' + i)}})
		} else {
			m, _ = model.Update(ui.NavigateMsg{To: s})
		}
		model = m
		out := model.View()
		header := fmt.Sprintf("=== %s (%d chars) ===", ui.SidebarLabels[s], len(out))
		fmt.Fprintln(os.Stdout, header)
		fmt.Fprintln(os.Stdout, strings.Repeat("-", len(header)))
		fmt.Fprintln(os.Stdout, out)
		fmt.Fprintln(os.Stdout)
	}
}
