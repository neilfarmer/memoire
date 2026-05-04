package screens

import (
	"errors"
	"strings"

	"github.com/charmbracelet/bubbles/table"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/huh"
	"github.com/charmbracelet/lipgloss"

	"github.com/neilfarmer/memoire/tui/internal/api"
	"github.com/neilfarmer/memoire/tui/internal/styles"
	"github.com/neilfarmer/memoire/tui/internal/ui/components"
)

type tokenMode int

const (
	tokenView tokenMode = iota
	tokenForm
	tokenConfirmDelete
	tokenShowSecret
)

type Tokens struct {
	client *api.Client
	width  int
	height int

	mode    tokenMode
	loading bool
	err     error

	patForbidden bool
	tokens       []api.Token
	tbl          table.Model

	form          *huh.Form
	formName      string
	createdSecret string
}

type tokensLoadedMsg struct {
	tokens       []api.Token
	patForbidden bool
	err          error
}
type tokenCreatedMsg struct {
	token api.Token
	err   error
}
type tokenMutatedMsg struct{ err error }

func newTokens(c *api.Client) *Tokens {
	t := &Tokens{client: c}
	t.tbl = components.NewTable(tokenCols(80), nil, 14)
	return t
}

func tokenCols(w int) []components.Column {
	nameW := w - 24 - 24
	if nameW < 16 {
		nameW = 16
	}
	return []components.Column{
		{Title: "NAME", Width: nameW},
		{Title: "CREATED", Width: 24},
		{Title: "LAST USED", Width: 24},
	}
}

func (t *Tokens) Init() tea.Cmd { return t.refresh() }

func (t *Tokens) refresh() tea.Cmd {
	c := t.client
	return func() tea.Msg {
		out, err := c.ListTokens()
		if errors.Is(err, api.ErrPATForbidden) {
			return tokensLoadedMsg{patForbidden: true}
		}
		return tokensLoadedMsg{tokens: out, err: err}
	}
}

func (t *Tokens) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch m := msg.(type) {
	case tokensLoadedMsg:
		t.loading = false
		t.err = m.err
		t.tokens = m.tokens
		t.patForbidden = m.patForbidden
		t.refreshRows()
		return t, nil
	case tokenCreatedMsg:
		if m.err != nil {
			t.err = m.err
			t.mode = tokenView
			return t, nil
		}
		t.createdSecret = m.token.Token
		t.mode = tokenShowSecret
		return t, t.refresh()
	case tokenMutatedMsg:
		t.err = m.err
		t.mode = tokenView
		return t, t.refresh()
	case tea.KeyMsg:
		return t.handleKey(m)
	}
	if t.mode == tokenForm && t.form != nil {
		f, cmd := t.form.Update(msg)
		if x, ok := f.(*huh.Form); ok {
			t.form = x
		}
		if t.form.State == huh.StateCompleted {
			return t, t.submit()
		}
		return t, cmd
	}
	if t.mode == tokenView {
		var cmd tea.Cmd
		t.tbl, cmd = t.tbl.Update(msg)
		return t, cmd
	}
	return t, nil
}

func (t *Tokens) refreshRows() {
	rows := make([]components.Row, 0, len(t.tokens))
	for _, x := range t.tokens {
		rows = append(rows, components.Row{x.Name, orDash(x.CreatedAt), orDash(x.LastUsedAt)})
	}
	t.tbl.SetRows(rows)
}

func (t *Tokens) handleKey(m tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch t.mode {
	case tokenShowSecret:
		if m.String() == "esc" || m.String() == "enter" || m.String() == "q" {
			t.mode = tokenView
			t.createdSecret = ""
		}
		return t, nil
	case tokenForm:
		if m.String() == "esc" {
			t.mode = tokenView
			t.form = nil
			return t, nil
		}
		if m.String() == "ctrl+s" {
			return t, t.submit()
		}
		f, cmd := t.form.Update(m)
		if x, ok := f.(*huh.Form); ok {
			t.form = x
		}
		if t.form.State == huh.StateCompleted {
			return t, t.submit()
		}
		return t, cmd
	case tokenConfirmDelete:
		if m.String() == "y" {
			return t, t.deleteSelected()
		}
		if m.String() == "n" || m.String() == "esc" {
			t.mode = tokenView
		}
		return t, nil
	}
	if t.patForbidden {
		return t, nil
	}
	switch m.String() {
	case "n":
		return t, t.startNew()
	case "d":
		if len(t.tokens) > 0 {
			t.mode = tokenConfirmDelete
		}
	case "r", "ctrl+r":
		return t, t.refresh()
	}
	var cmd tea.Cmd
	t.tbl, cmd = t.tbl.Update(m)
	return t, cmd
}

func (t *Tokens) startNew() tea.Cmd {
	t.formName = ""
	t.form = huh.NewForm(huh.NewGroup(
		huh.NewInput().Title("Token name").Value(&t.formName).Validate(notEmpty),
	))
	t.mode = tokenForm
	return t.form.Init()
}

func (t *Tokens) submit() tea.Cmd {
	c := t.client
	name := strings.TrimSpace(t.formName)
	t.form = nil
	t.mode = tokenView // reset mode so next render does not call form.View() on nil
	return func() tea.Msg {
		tok, err := c.CreateToken(name)
		return tokenCreatedMsg{token: tok, err: err}
	}
}

func (t *Tokens) deleteSelected() tea.Cmd {
	idx := t.tbl.Cursor()
	if idx >= len(t.tokens) {
		return nil
	}
	id := t.tokens[idx].TokenID
	c := t.client
	return func() tea.Msg { return tokenMutatedMsg{err: c.DeleteToken(id)} }
}

func (t *Tokens) View() string {
	if t.mode == tokenForm && t.form != nil {
		return lipgloss.JoinVertical(lipgloss.Left, t.form.View(), "", components.FormHint())
	}
	if t.mode == tokenConfirmDelete {
		return components.ConfirmView("Revoke this token?", t.width, t.height)
	}
	if t.mode == tokenShowSecret {
		return t.secretView()
	}
	if t.loading {
		return styles.MutedText.Render("Loading tokens...")
	}
	if t.patForbidden {
		rows := []string{
			styles.Title.Render("Personal Access Tokens"),
			"",
			styles.DangerText.Render("Token management not available in PAT-authenticated session."),
			styles.MutedText.Render("Sign in via web UI to create or revoke tokens."),
		}
		return styles.Box.Render(strings.Join(rows, "\n"))
	}
	t.tbl.SetColumns(tokenCols(t.width - 6))
	if t.height-6 > 0 {
		t.tbl.SetHeight(t.height - 6)
	}
	hints := []string{
		styles.KeyHint("n", "new"),
		styles.KeyHint("d", "revoke"),
	}
	return components.FrameTable("Personal Access Tokens", len(t.tokens), t.tbl, hints, true)
}

func (t *Tokens) secretView() string {
	rows := []string{
		styles.Title.Render("New token created"),
		"",
		styles.MutedText.Render("Copy this value now. It will not be shown again."),
		"",
		styles.SuccessText.Render(t.createdSecret),
		"",
		styles.MutedText.Render("press enter or esc to dismiss"),
	}
	return lipgloss.Place(t.width, t.height, lipgloss.Center, lipgloss.Center,
		styles.BoxFocused.Render(strings.Join(rows, "\n")))
}

func (t *Tokens) Title() string { return "Tokens" }
func (t *Tokens) StatusHints() []string {
	if t.patForbidden {
		return []string{styles.MutedText.Render("PAT auth · read-only")}
	}
	return []string{
		styles.KeyHint("n", "new"),
		styles.KeyHint("d", "revoke"),
	}
}
func (t *Tokens) Help() []components.HelpEntry {
	return []components.HelpEntry{
		{Keys: "↑/↓", Desc: "select row"},
		{Keys: "n", Desc: "create new token"},
		{Keys: "d", Desc: "revoke selected"},
		{Keys: "r", Desc: "refresh"},
	}
}
func (t *Tokens) SetSize(w, h int) { t.width, t.height = w, h }
