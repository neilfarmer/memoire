package screens

import (
	"strings"

	"github.com/charmbracelet/bubbles/table"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/neilfarmer/memoire/tui/internal/api"
	"github.com/neilfarmer/memoire/tui/internal/styles"
	"github.com/neilfarmer/memoire/tui/internal/ui/components"
)

type Favorites struct {
	client *api.Client
	width  int
	height int

	loading bool
	err     error
	items   []api.Favorite
	tbl     table.Model
	confirm bool
}

type favoritesLoadedMsg struct {
	items []api.Favorite
	err   error
}
type favoritesMutatedMsg struct{ err error }

func newFavorites(c *api.Client) *Favorites {
	f := &Favorites{client: c}
	f.tbl = components.NewTable(favoriteCols(80), nil, 18)
	return f
}

func favoriteCols(w int) []components.Column {
	urlW := w - 22 - 30 - 18
	if urlW < 16 {
		urlW = 16
	}
	return []components.Column{
		{Title: "TITLE", Width: 30},
		{Title: "FEED", Width: 18},
		{Title: "URL", Width: urlW},
		{Title: "TAGS", Width: 22},
	}
}

func (f *Favorites) Init() tea.Cmd { return f.refresh() }

func (f *Favorites) refresh() tea.Cmd {
	c := f.client
	return func() tea.Msg {
		out, err := c.ListFavorites()
		return favoritesLoadedMsg{items: out, err: err}
	}
}

func (f *Favorites) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch m := msg.(type) {
	case favoritesLoadedMsg:
		f.loading = false
		f.err = m.err
		f.items = m.items
		f.refreshRows()
		return f, nil
	case favoritesMutatedMsg:
		f.err = m.err
		f.confirm = false
		return f, f.refresh()
	case components.OpenedURLMsg:
		return f, nil
	case tea.KeyMsg:
		return f.handleKey(m)
	}
	var cmd tea.Cmd
	f.tbl, cmd = f.tbl.Update(msg)
	return f, cmd
}

func (f *Favorites) refreshRows() {
	rows := make([]components.Row, 0, len(f.items))
	for _, x := range f.items {
		title := x.Title
		if title == "" {
			title = "(untitled)"
		}
		rows = append(rows, components.Row{
			truncate(title, 30),
			truncate(x.FeedTitle, 18),
			truncate(x.URL, 60),
			truncate(strings.Join(x.Tags, ","), 22),
		})
	}
	f.tbl.SetRows(rows)
}

func (f *Favorites) handleKey(m tea.KeyMsg) (tea.Model, tea.Cmd) {
	if f.confirm {
		if m.String() == "y" {
			return f, f.deleteSelected()
		}
		if m.String() == "n" || m.String() == "esc" {
			f.confirm = false
		}
		return f, nil
	}
	switch m.String() {
	case "o", "enter":
		if x := f.selected(); x != nil {
			return f, components.OpenURL(x.URL)
		}
	case "d":
		if f.selected() != nil {
			f.confirm = true
		}
	case "r", "ctrl+r":
		return f, f.refresh()
	}
	var cmd tea.Cmd
	f.tbl, cmd = f.tbl.Update(m)
	return f, cmd
}

func (f *Favorites) selected() *api.Favorite {
	idx := f.tbl.Cursor()
	if idx < 0 || idx >= len(f.items) {
		return nil
	}
	return &f.items[idx]
}

func (f *Favorites) deleteSelected() tea.Cmd {
	x := f.selected()
	if x == nil {
		return nil
	}
	id := x.FavoriteID
	c := f.client
	return func() tea.Msg { return favoritesMutatedMsg{err: c.DeleteFavorite(id)} }
}

func (f *Favorites) View() string {
	if f.confirm {
		return components.ConfirmView("Remove this favorite?", f.width, f.height)
	}
	if f.loading && len(f.items) == 0 {
		return styles.MutedText.Render("Loading favorites...")
	}
	f.tbl.SetColumns(favoriteCols(f.width - 6))
	if f.height-6 > 0 {
		f.tbl.SetHeight(f.height - 6)
	}
	hints := []string{
		styles.KeyHint("↵/o", "open"),
		styles.KeyHint("d", "remove"),
		styles.KeyHint("/", "filter"),
	}
	return lipgloss.JoinVertical(lipgloss.Left, components.FrameTable("Favorites", len(f.items), f.tbl, hints, true))
}

func (f *Favorites) Title() string { return "Favorites" }
func (f *Favorites) StatusHints() []string {
	return []string{
		styles.KeyHint("o", "open"),
		styles.KeyHint("d", "remove"),
	}
}
func (f *Favorites) Help() []components.HelpEntry {
	return []components.HelpEntry{
		{Keys: "↑/↓", Desc: "select row"},
		{Keys: "↵ enter or o", Desc: "open URL in browser"},
		{Keys: "d", Desc: "remove favorite"},
		{Keys: "r", Desc: "refresh"},
	}
}
func (f *Favorites) SetSize(w, h int) {
	f.width, f.height = w, h
	f.tbl.SetColumns(favoriteCols(w - 6))
	if h-6 > 0 {
		f.tbl.SetHeight(h - 6)
	}
}
