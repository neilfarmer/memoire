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

type habitMode int

const (
	habitList habitMode = iota
	habitForm
	habitConfirmDelete
)

type Habits struct {
	client *api.Client

	mode    habitMode
	width   int
	height  int
	loading bool
	err     error

	habits  []api.Habit
	cursor  int
	form    *huh.Form
	formIn  habitFormState
}

type habitFormState struct {
	id         string
	name       string
	desc       string
	frequency  string
	notifyTime string
	timeOfDay  string
}

type habitsLoadedMsg struct {
	habits []api.Habit
	err    error
}

type habitsMutatedMsg struct{ err error }

func newHabits(c *api.Client) *Habits {
	return &Habits{client: c}
}

func (h *Habits) Init() tea.Cmd { return h.refresh() }

func (h *Habits) refresh() tea.Cmd {
	c := h.client
	return func() tea.Msg {
		habits, err := c.ListHabits()
		return habitsLoadedMsg{habits: habits, err: err}
	}
}

func (h *Habits) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch m := msg.(type) {
	case habitsLoadedMsg:
		h.loading = false
		h.err = m.err
		h.habits = m.habits
		if h.cursor >= len(h.habits) {
			h.cursor = len(h.habits) - 1
		}
		if h.cursor < 0 {
			h.cursor = 0
		}
		return h, nil
	case habitsMutatedMsg:
		h.err = m.err
		h.mode = habitList
		return h, h.refresh()
	case tea.KeyMsg:
		return h.handleKey(m)
	}
	if h.mode == habitForm && h.form != nil {
		f, cmd := h.form.Update(msg)
		if ff, ok := f.(*huh.Form); ok {
			h.form = ff
		}
		if h.form.State == huh.StateCompleted {
			return h, h.submit()
		}
		return h, cmd
	}
	return h, nil
}

func (h *Habits) handleKey(m tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch h.mode {
	case habitConfirmDelete:
		if m.String() == "y" {
			return h, h.deleteSelected()
		}
		if m.String() == "n" || m.String() == "esc" {
			h.mode = habitList
		}
		return h, nil
	case habitForm:
		if m.String() == "esc" {
			h.mode = habitList
			h.form = nil
			return h, nil
		}
		if m.String() == "ctrl+s" {
			return h, h.submit()
		}
		f, cmd := h.form.Update(m)
		if ff, ok := f.(*huh.Form); ok {
			h.form = ff
		}
		if h.form.State == huh.StateCompleted {
			return h, h.submit()
		}
		return h, cmd
	}
	switch m.String() {
	case "up", "k":
		if h.cursor > 0 {
			h.cursor--
		}
	case "down", "j":
		if h.cursor < len(h.habits)-1 {
			h.cursor++
		}
	case " ", "space":
		if len(h.habits) > 0 {
			return h, h.toggleSelected("")
		}
	case "n":
		return h, h.startNew()
	case "e":
		return h, h.startEdit()
	case "d":
		if len(h.habits) > 0 {
			h.mode = habitConfirmDelete
		}
	case "r", "ctrl+r":
		return h, h.refresh()
	}
	return h, nil
}

func (h *Habits) toggleSelected(date string) tea.Cmd {
	if h.cursor >= len(h.habits) {
		return nil
	}
	id := h.habits[h.cursor].HabitID
	c := h.client
	return func() tea.Msg {
		_, err := c.ToggleHabit(id, date)
		return habitsMutatedMsg{err: err}
	}
}

func (h *Habits) startNew() tea.Cmd {
	h.formIn = habitFormState{frequency: "daily", timeOfDay: "anytime"}
	h.form = h.newForm("New habit")
	h.mode = habitForm
	return h.form.Init()
}

func (h *Habits) startEdit() tea.Cmd {
	if h.cursor >= len(h.habits) {
		return nil
	}
	x := h.habits[h.cursor]
	h.formIn = habitFormState{
		id: x.HabitID, name: x.Name, desc: x.Description,
		frequency: x.Frequency, notifyTime: x.NotifyTime, timeOfDay: x.TimeOfDay,
	}
	h.form = h.newForm("Edit habit")
	h.mode = habitForm
	return h.form.Init()
}

func (h *Habits) newForm(title string) *huh.Form {
	d := &h.formIn
	return huh.NewForm(huh.NewGroup(
		huh.NewInput().Title("Name").Value(&d.name).Validate(func(s string) error {
			if strings.TrimSpace(s) == "" {
				return fmt.Errorf("required")
			}
			return nil
		}),
		huh.NewText().Title("Description").Value(&d.desc).Lines(3),
		huh.NewSelect[string]().Title("Frequency").Options(
			huh.NewOption("Daily", "daily"),
			huh.NewOption("Weekly", "weekly"),
		).Value(&d.frequency),
		huh.NewSelect[string]().Title("Time of day").Options(
			huh.NewOption("Anytime", "anytime"),
			huh.NewOption("Morning", "morning"),
			huh.NewOption("Afternoon", "afternoon"),
			huh.NewOption("Evening", "evening"),
		).Value(&d.timeOfDay),
		huh.NewInput().Title("Notify time (HH:MM UTC, optional)").Value(&d.notifyTime),
	))
}

func (h *Habits) submit() tea.Cmd {
	d := h.formIn
	in := api.HabitInput{
		Name:        strings.TrimSpace(d.name),
		Description: d.desc,
		Frequency:   d.frequency,
		TimeOfDay:   d.timeOfDay,
		NotifyTime:  strings.TrimSpace(d.notifyTime),
	}
	id := d.id
	c := h.client
	h.form = nil
	h.mode = habitList
	return func() tea.Msg {
		var err error
		if id == "" {
			_, err = c.CreateHabit(in)
		} else {
			_, err = c.UpdateHabit(id, in)
		}
		return habitsMutatedMsg{err: err}
	}
}

func (h *Habits) deleteSelected() tea.Cmd {
	if h.cursor >= len(h.habits) {
		return nil
	}
	id := h.habits[h.cursor].HabitID
	c := h.client
	return func() tea.Msg { return habitsMutatedMsg{err: c.DeleteHabit(id)} }
}

func (h *Habits) View() string {
	if h.mode == habitForm {
		if h.form != nil {
			return lipgloss.JoinVertical(lipgloss.Left, h.form.View(), "", components.FormHint())
		}
	}
	if h.mode == habitConfirmDelete {
		return components.ConfirmView("Delete this habit?", h.width, h.height)
	}
	if h.loading && len(h.habits) == 0 {
		return styles.MutedText.Render("Loading habits...")
	}
	if len(h.habits) == 0 {
		return styles.MutedText.Render("No habits yet. Press n to create one.")
	}
	rows := []string{}
	for i, x := range h.habits {
		head := fmt.Sprintf("%-30s  streak %d  best %d", truncate(x.Name, 30), x.CurrentStreak, x.BestStreak)
		hist := renderHistory(x.History)
		row := head + "\n" + styles.MutedText.Render(hist)
		if i == h.cursor {
			row = styles.BoxFocused.Render(row)
		} else {
			row = styles.Box.Render(row)
		}
		rows = append(rows, row)
	}
	return lipgloss.JoinVertical(lipgloss.Left, rows...)
}

func renderHistory(history []api.HabitHistory) string {
	// Show the last 30 days. Map by date for lookup.
	byDate := map[string]bool{}
	for _, h := range history {
		byDate[h.Date] = h.Done
	}
	out := strings.Builder{}
	for i := 29; i >= 0; i-- {
		d := time.Now().AddDate(0, 0, -i).Format("2006-01-02")
		if byDate[d] {
			out.WriteString("■ ")
		} else {
			out.WriteString("· ")
		}
	}
	return out.String()
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n-1] + "…"
}

func (h *Habits) Title() string { return "Habits" }
func (h *Habits) StatusHints() []string {
	return []string{
		styles.KeyHint("space", "toggle today"),
		styles.KeyHint("n", "new"),
		styles.KeyHint("e", "edit"),
		styles.KeyHint("d", "delete"),
	}
}
func (h *Habits) Help() []components.HelpEntry {
	return []components.HelpEntry{
		{Keys: "↑/↓ or j/k", Desc: "select habit"},
		{Keys: "space", Desc: "toggle today's completion"},
		{Keys: "n", Desc: "new habit"},
		{Keys: "e", Desc: "edit habit"},
		{Keys: "d", Desc: "delete habit"},
		{Keys: "r", Desc: "refresh"},
	}
}
func (h *Habits) SetSize(w, ht int) { h.width, h.height = w, ht }
