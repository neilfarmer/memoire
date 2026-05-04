package screens

import (
	"fmt"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/huh"
	"github.com/charmbracelet/lipgloss"

	"github.com/neilfarmer/memoire/tui/internal/api"
	"github.com/neilfarmer/memoire/tui/internal/styles"
	"github.com/neilfarmer/memoire/tui/internal/ui/components"
)

type journalMode int

const (
	journalView journalMode = iota
	journalForm
	journalConfirmDelete
)

type Journal struct {
	client *api.Client
	width  int
	height int

	mode    journalMode
	loading bool
	err     error

	cursor   time.Time
	entries  map[string]bool
	current  api.JournalEntry
	loaded   bool
	form     *huh.Form
	formData journalFormState
}

type journalFormState struct {
	title string
	body  string
	mood  string
	tags  string
}

type journalListLoadedMsg struct {
	dates []string
	err   error
}

type journalEntryMsg struct {
	entry api.JournalEntry
	err   error
}

type journalMutatedMsg struct{ err error }

func newJournal(c *api.Client) *Journal {
	return &Journal{client: c, cursor: time.Now(), entries: map[string]bool{}}
}

func (j *Journal) Init() tea.Cmd {
	return tea.Batch(j.loadList(), j.loadEntry(j.cursor))
}

func (j *Journal) loadList() tea.Cmd {
	c := j.client
	return func() tea.Msg {
		summaries, err := c.ListJournal("")
		dates := make([]string, 0, len(summaries))
		for _, s := range summaries {
			dates = append(dates, s.EntryDate)
		}
		return journalListLoadedMsg{dates: dates, err: err}
	}
}

func (j *Journal) loadEntry(date time.Time) tea.Cmd {
	c := j.client
	d := date.Format("2006-01-02")
	return func() tea.Msg {
		entry, err := c.GetJournal(d)
		if err != nil {
			if api.IsNotFound(err) {
				return journalEntryMsg{entry: api.JournalEntry{EntryDate: d}, err: nil}
			}
			return journalEntryMsg{err: err}
		}
		return journalEntryMsg{entry: entry}
	}
}

func (j *Journal) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch m := msg.(type) {
	case journalListLoadedMsg:
		for _, d := range m.dates {
			j.entries[d] = true
		}
		j.err = m.err
		return j, nil
	case journalEntryMsg:
		j.err = m.err
		j.current = m.entry
		j.loaded = true
		return j, nil
	case journalMutatedMsg:
		j.err = m.err
		j.mode = journalView
		return j, tea.Batch(j.loadList(), j.loadEntry(j.cursor))
	case components.EditorClosedMsg:
		if m.Err != nil {
			j.err = m.Err
			return j, nil
		}
		j.formData.body = m.Content
		return j, nil
	case tea.KeyMsg:
		return j.handleKey(m)
	}
	if j.mode == journalForm && j.form != nil {
		f, cmd := j.form.Update(msg)
		if ff, ok := f.(*huh.Form); ok {
			j.form = ff
		}
		if j.form.State == huh.StateCompleted {
			return j, j.submit()
		}
		return j, cmd
	}
	return j, nil
}

func (j *Journal) handleKey(m tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch j.mode {
	case journalForm:
		if m.String() == "esc" {
			j.mode = journalView
			j.form = nil
			return j, nil
		}
		if m.String() == "ctrl+s" {
			return j, j.submit()
		}
		if m.String() == "ctrl+e" {
			return j, components.EditExternal(j.formData.body, ".md")
		}
		f, cmd := j.form.Update(m)
		if ff, ok := f.(*huh.Form); ok {
			j.form = ff
		}
		if j.form.State == huh.StateCompleted {
			return j, j.submit()
		}
		return j, cmd
	case journalConfirmDelete:
		if m.String() == "y" {
			return j, j.deleteEntry()
		}
		if m.String() == "n" || m.String() == "esc" {
			j.mode = journalView
		}
		return j, nil
	}
	switch m.String() {
	case "n", "right", "l":
		j.cursor = j.cursor.AddDate(0, 0, 1)
		j.loaded = false
		return j, j.loadEntry(j.cursor)
	case "p", "left", "h":
		j.cursor = j.cursor.AddDate(0, 0, -1)
		j.loaded = false
		return j, j.loadEntry(j.cursor)
	case "k", "up":
		j.cursor = j.cursor.AddDate(0, 0, -7)
		j.loaded = false
		return j, j.loadEntry(j.cursor)
	case "j", "down":
		j.cursor = j.cursor.AddDate(0, 0, 7)
		j.loaded = false
		return j, j.loadEntry(j.cursor)
	case "t":
		j.cursor = time.Now()
		j.loaded = false
		return j, j.loadEntry(j.cursor)
	case "e":
		return j, j.startEdit()
	case "d":
		if j.current.Content != "" || j.current.Body != "" {
			j.mode = journalConfirmDelete
		}
	case "r", "ctrl+r":
		return j, tea.Batch(j.loadList(), j.loadEntry(j.cursor))
	}
	return j, nil
}

func (j *Journal) startEdit() tea.Cmd {
	j.formData = journalFormState{
		title: j.current.Title,
		body:  firstNonEmpty(j.current.Content, j.current.Body),
		mood:  j.current.Mood,
		tags:  strings.Join(j.current.Tags, ", "),
	}
	d := &j.formData
	j.form = huh.NewForm(huh.NewGroup(
		huh.NewInput().Title("Title").Value(&d.title),
		huh.NewSelect[string]().Title("Mood").Options(
			huh.NewOption("(none)", ""),
			huh.NewOption("Great", "great"),
			huh.NewOption("Good", "good"),
			huh.NewOption("Okay", "okay"),
			huh.NewOption("Bad", "bad"),
			huh.NewOption("Terrible", "terrible"),
		).Value(&d.mood),
		huh.NewText().Title("Body (markdown — ctrl+e for $EDITOR)").Value(&d.body).Lines(10),
		huh.NewInput().Title("Tags (comma separated)").Value(&d.tags),
	))
	j.mode = journalForm
	return j.form.Init()
}

func firstNonEmpty(opts ...string) string {
	for _, s := range opts {
		if s != "" {
			return s
		}
	}
	return ""
}

func (j *Journal) submit() tea.Cmd {
	d := j.formData
	in := api.JournalInput{
		Title:   d.title,
		Content: d.body,
		Body:    d.body,
		Mood:    d.mood,
		Tags:    splitTags(d.tags),
	}
	date := j.cursor.Format("2006-01-02")
	c := j.client
	j.form = nil
	j.mode = journalView
	return func() tea.Msg {
		_, err := c.UpsertJournal(date, in)
		return journalMutatedMsg{err: err}
	}
}

func (j *Journal) deleteEntry() tea.Cmd {
	date := j.cursor.Format("2006-01-02")
	c := j.client
	return func() tea.Msg { return journalMutatedMsg{err: c.DeleteJournal(date)} }
}

func (j *Journal) View() string {
	if j.mode == journalForm && j.form != nil {
		if j.form != nil {
			return lipgloss.JoinVertical(lipgloss.Left, j.form.View(), "", components.FormHint())
		}
	}
	if j.mode == journalConfirmDelete {
		return components.ConfirmView("Delete this journal entry?", j.width, j.height)
	}
	calendar := components.DateGrid{Selected: j.cursor, Markers: j.entries}.View()
	header := styles.Title.Render(j.cursor.Format("Monday, 2 January 2006"))
	body := ""
	if !j.loaded {
		body = styles.MutedText.Render("Loading...")
	} else {
		content := firstNonEmpty(j.current.Content, j.current.Body)
		if content == "" {
			body = styles.MutedText.Render(fmt.Sprintf("No entry for %s. Press e to write one.", j.cursor.Format("2006-01-02")))
		} else {
			meta := []string{}
			if j.current.Mood != "" {
				meta = append(meta, "mood: "+j.current.Mood)
			}
			if len(j.current.Tags) > 0 {
				meta = append(meta, "#"+strings.Join(j.current.Tags, " #"))
			}
			rows := []string{}
			if len(meta) > 0 {
				rows = append(rows, styles.MutedText.Render(strings.Join(meta, " · ")))
			}
			rows = append(rows, components.RenderMarkdown(content, j.width-32))
			body = strings.Join(rows, "\n")
		}
	}
	right := lipgloss.JoinVertical(lipgloss.Left,
		header,
		"",
		body,
		"",
		styles.MutedText.Render("← prev day · → next day · t today · e write · d delete"),
	)
	return lipgloss.JoinHorizontal(lipgloss.Top, calendar, "  ", right)
}

func (j *Journal) Title() string { return "Journal" }
func (j *Journal) StatusHints() []string {
	return []string{
		styles.KeyHint("←/→", "day"),
		styles.KeyHint("t", "today"),
		styles.KeyHint("e", "write"),
		styles.KeyHint("d", "delete"),
	}
}
func (j *Journal) Help() []components.HelpEntry {
	return []components.HelpEntry{
		{Keys: "←/→ or h/l or n/p", Desc: "previous / next day"},
		{Keys: "↑/↓ or j/k", Desc: "previous / next week"},
		{Keys: "t", Desc: "jump to today"},
		{Keys: "e", Desc: "edit entry"},
		{Keys: "d", Desc: "delete entry"},
		{Keys: "ctrl+e (in form)", Desc: "edit body in $EDITOR"},
	}
}
func (j *Journal) SetSize(w, h int) { j.width, j.height = w, h }
