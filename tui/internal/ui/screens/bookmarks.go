package screens

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/bubbles/table"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/huh"
	"github.com/charmbracelet/lipgloss"

	"github.com/neilfarmer/memoire/tui/internal/api"
	"github.com/neilfarmer/memoire/tui/internal/styles"
	"github.com/neilfarmer/memoire/tui/internal/ui/components"
)

type bookmarkMode int

const (
	bookmarkList bookmarkMode = iota
	bookmarkDetail
	bookmarkForm
	bookmarkConfirmDelete
)

type Bookmarks struct {
	client *api.Client
	width  int
	height int

	mode    bookmarkMode
	loading bool
	err     error

	items   []api.Bookmark
	tbl     table.Model
	tag     string
	form    *huh.Form
	formIn  bookmarkFormState
}

type bookmarkFormState struct {
	id    string
	url   string
	title string
	tags  string
	note  string
}

type bookmarksLoadedMsg struct {
	items []api.Bookmark
	err   error
}
type bookmarksMutatedMsg struct{ err error }

func newBookmarks(c *api.Client) *Bookmarks {
	b := &Bookmarks{client: c}
	b.tbl = components.NewTable(bookmarkCols(80), nil, 18)
	return b
}

func bookmarkCols(w int) []components.Column {
	urlW := w - 22 - 30
	if urlW < 20 {
		urlW = 20
	}
	return []components.Column{
		{Title: "TITLE", Width: 30},
		{Title: "URL", Width: urlW},
		{Title: "TAGS", Width: 22},
	}
}

func (b *Bookmarks) Init() tea.Cmd { return b.refresh() }

func (b *Bookmarks) refresh() tea.Cmd {
	c := b.client
	tag := b.tag
	return func() tea.Msg {
		out, err := c.ListBookmarks("", tag)
		return bookmarksLoadedMsg{items: out, err: err}
	}
}

func (b *Bookmarks) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch m := msg.(type) {
	case bookmarksLoadedMsg:
		b.loading = false
		b.err = m.err
		b.items = m.items
		b.refreshRows()
		return b, nil
	case bookmarksMutatedMsg:
		b.err = m.err
		b.mode = bookmarkList
		return b, b.refresh()
	case components.OpenedURLMsg:
		return b, nil
	case tea.KeyMsg:
		return b.handleKey(m)
	}
	if b.mode == bookmarkForm && b.form != nil {
		f, cmd := b.form.Update(msg)
		if x, ok := f.(*huh.Form); ok {
			b.form = x
		}
		if b.form.State == huh.StateCompleted {
			return b, b.submit()
		}
		return b, cmd
	}
	if b.mode == bookmarkList {
		var cmd tea.Cmd
		b.tbl, cmd = b.tbl.Update(msg)
		return b, cmd
	}
	return b, nil
}

func (b *Bookmarks) refreshRows() {
	rows := make([]components.Row, 0, len(b.items))
	for _, x := range b.items {
		title := x.Title
		if title == "" {
			title = "(untitled)"
		}
		rows = append(rows, components.Row{
			truncate(title, 30),
			truncate(x.URL, 60),
			truncate(strings.Join(x.Tags, ","), 22),
		})
	}
	b.tbl.SetRows(rows)
}

func (b *Bookmarks) handleKey(m tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch b.mode {
	case bookmarkConfirmDelete:
		if m.String() == "y" {
			return b, b.deleteSelected()
		}
		if m.String() == "n" || m.String() == "esc" {
			b.mode = bookmarkList
		}
		return b, nil
	case bookmarkDetail:
		switch m.String() {
		case "esc", "q":
			b.mode = bookmarkList
		case "e":
			return b, b.startEdit()
		case "d":
			b.mode = bookmarkConfirmDelete
		case "o":
			if x := b.selected(); x != nil {
				return b, components.OpenURL(x.URL)
			}
		}
		return b, nil
	case bookmarkForm:
		if m.String() == "esc" {
			b.mode = bookmarkList
			b.form = nil
			return b, nil
		}
		if m.String() == "ctrl+s" {
			return b, b.submit()
		}
		f, cmd := b.form.Update(m)
		if x, ok := f.(*huh.Form); ok {
			b.form = x
		}
		if b.form.State == huh.StateCompleted {
			return b, b.submit()
		}
		return b, cmd
	}
	switch m.String() {
	case "enter":
		if b.tbl.Cursor() < len(b.items) {
			b.mode = bookmarkDetail
		}
		return b, nil
	case "o":
		if x := b.selected(); x != nil {
			return b, components.OpenURL(x.URL)
		}
	case "n":
		return b, b.startNew()
	case "e":
		return b, b.startEdit()
	case "d":
		if b.tbl.Cursor() < len(b.items) {
			b.mode = bookmarkConfirmDelete
		}
	case "r", "ctrl+r":
		return b, b.refresh()
	}
	var cmd tea.Cmd
	b.tbl, cmd = b.tbl.Update(m)
	return b, cmd
}

func (b *Bookmarks) selected() *api.Bookmark {
	idx := b.tbl.Cursor()
	if idx < 0 || idx >= len(b.items) {
		return nil
	}
	return &b.items[idx]
}

func (b *Bookmarks) startNew() tea.Cmd {
	b.formIn = bookmarkFormState{}
	b.form = b.newForm()
	b.mode = bookmarkForm
	return b.form.Init()
}

func (b *Bookmarks) startEdit() tea.Cmd {
	x := b.selected()
	if x == nil {
		return nil
	}
	b.formIn = bookmarkFormState{
		id: x.BookmarkID, url: x.URL, title: x.Title,
		tags: strings.Join(x.Tags, ", "), note: x.Note,
	}
	b.form = b.newForm()
	b.mode = bookmarkForm
	return b.form.Init()
}

func (b *Bookmarks) newForm() *huh.Form {
	d := &b.formIn
	return huh.NewForm(huh.NewGroup(
		huh.NewInput().Title("URL").Value(&d.url).Validate(func(s string) error {
			if strings.TrimSpace(s) == "" {
				return fmt.Errorf("required")
			}
			return nil
		}),
		huh.NewInput().Title("Title").Value(&d.title),
		huh.NewInput().Title("Tags (comma separated)").Value(&d.tags),
		huh.NewText().Title("Note").Value(&d.note).Lines(3),
	))
}

func (b *Bookmarks) submit() tea.Cmd {
	d := b.formIn
	in := api.BookmarkInput{
		URL: strings.TrimSpace(d.url), Title: d.title,
		Tags: splitTags(d.tags), Note: d.note,
	}
	id := d.id
	c := b.client
	b.form = nil
	b.mode = bookmarkList
	return func() tea.Msg {
		var err error
		if id == "" {
			_, err = c.CreateBookmark(in)
		} else {
			_, err = c.UpdateBookmark(id, in)
		}
		return bookmarksMutatedMsg{err: err}
	}
}

func (b *Bookmarks) deleteSelected() tea.Cmd {
	x := b.selected()
	if x == nil {
		return nil
	}
	id := x.BookmarkID
	c := b.client
	return func() tea.Msg { return bookmarksMutatedMsg{err: c.DeleteBookmark(id)} }
}

func (b *Bookmarks) View() string {
	switch b.mode {
	case bookmarkForm:
		if b.form != nil {
			return lipgloss.JoinVertical(lipgloss.Left, b.form.View(), "", components.FormHint())
		}
	case bookmarkConfirmDelete:
		return components.ConfirmView("Delete this bookmark?", b.width, b.height)
	case bookmarkDetail:
		return b.detailView()
	}
	if b.loading && len(b.items) == 0 {
		return styles.MutedText.Render("Loading bookmarks...")
	}
	b.tbl.SetColumns(bookmarkCols(b.width - 6))
	if b.height-6 > 0 {
		b.tbl.SetHeight(b.height - 6)
	}
	hints := []string{
		styles.KeyHint("↵", "details"),
		styles.KeyHint("o", "open"),
		styles.KeyHint("n", "new"),
		styles.KeyHint("e", "edit"),
		styles.KeyHint("d", "delete"),
		styles.KeyHint("/", "filter"),
	}
	return lipgloss.JoinVertical(lipgloss.Left, components.FrameTable("Bookmarks", len(b.items), b.tbl, hints, true))
}

func (b *Bookmarks) detailView() string {
	x := b.selected()
	if x == nil {
		return ""
	}
	rows := []string{
		components.Crumbs("Bookmarks", x.Title),
		"",
		styles.Title.Render(x.Title),
		styles.MutedText.Render(x.URL),
		"",
	}
	if len(x.Tags) > 0 {
		rows = append(rows, "Tags: "+strings.Join(x.Tags, ", "))
	}
	if x.Note != "" {
		rows = append(rows, "", components.RenderMarkdown(x.Note, b.width-6))
	}
	rows = append(rows, "", styles.MutedText.Render("<o> open  <e> edit  <d> delete  <esc> back"))
	return styles.Box.Render(strings.Join(rows, "\n"))
}

func (b *Bookmarks) Title() string { return "Bookmarks" }
func (b *Bookmarks) StatusHints() []string {
	return []string{
		styles.KeyHint("n", "new"),
		styles.KeyHint("o", "open"),
		styles.KeyHint("e", "edit"),
		styles.KeyHint("d", "delete"),
	}
}
func (b *Bookmarks) Help() []components.HelpEntry {
	return []components.HelpEntry{
		{Keys: "↑/↓", Desc: "select row"},
		{Keys: "↵ enter", Desc: "open detail"},
		{Keys: "esc", Desc: "back"},
		{Keys: "/", Desc: "filter (built-in)"},
		{Keys: "o", Desc: "open URL in browser"},
		{Keys: "n", Desc: "new bookmark"},
		{Keys: "e", Desc: "edit"},
		{Keys: "d", Desc: "delete"},
	}
}
func (b *Bookmarks) SetSize(w, h int) {
	b.width, b.height = w, h
	b.tbl.SetColumns(bookmarkCols(w - 6))
	if h-6 > 0 {
		b.tbl.SetHeight(h - 6)
	}
}
