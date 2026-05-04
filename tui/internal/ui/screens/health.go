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

type healthMode int

const (
	healthView healthMode = iota
	healthForm
	healthSummary
	healthConfirmDelete
)

type Health struct {
	client *api.Client
	width  int
	height int

	mode    healthMode
	loading bool
	err     error

	cursor   time.Time
	current  api.HealthLog
	loaded   bool
	form     *huh.Form
	formIn   healthFormState
	summary  api.HealthSummary
}

type healthFormState struct {
	steps         string
	distanceMi    string
	activeMinutes string
	caloriesOut   string
	weight        string
	notes         string
}

type healthLogMsg struct {
	log api.HealthLog
	err error
}
type healthMutatedMsg struct{ err error }
type healthSummaryMsg struct {
	summary api.HealthSummary
	err     error
}

func newHealth(c *api.Client) *Health {
	return &Health{client: c, cursor: time.Now()}
}

func (h *Health) Init() tea.Cmd { return h.loadDay() }

func (h *Health) loadDay() tea.Cmd {
	c := h.client
	d := h.cursor.Format("2006-01-02")
	return func() tea.Msg {
		log, err := c.GetHealthLog(d)
		if err != nil && api.IsNotFound(err) {
			return healthLogMsg{log: api.HealthLog{LogDate: d}}
		}
		return healthLogMsg{log: log, err: err}
	}
}

func (h *Health) loadSummary() tea.Cmd {
	c := h.client
	return func() tea.Msg {
		s, err := c.GetHealthSummary(7)
		return healthSummaryMsg{summary: s, err: err}
	}
}

func (h *Health) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch m := msg.(type) {
	case healthLogMsg:
		h.err = m.err
		h.current = m.log
		h.loaded = true
		return h, nil
	case healthSummaryMsg:
		h.err = m.err
		h.summary = m.summary
		return h, nil
	case healthMutatedMsg:
		h.err = m.err
		h.mode = healthView
		return h, h.loadDay()
	case tea.KeyMsg:
		return h.handleKey(m)
	}
	if h.mode == healthForm && h.form != nil {
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

func (h *Health) handleKey(m tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch h.mode {
	case healthForm:
		if m.String() == "esc" {
			h.mode = healthView
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
	case healthSummary:
		if m.String() == "esc" || m.String() == "T" {
			h.mode = healthView
		}
		return h, nil
	case healthConfirmDelete:
		if m.String() == "y" {
			return h, h.deleteCurrent()
		}
		if m.String() == "n" || m.String() == "esc" {
			h.mode = healthView
		}
		return h, nil
	}
	switch m.String() {
	case "left", "h":
		h.cursor = h.cursor.AddDate(0, 0, -1)
		return h, h.loadDay()
	case "right", "l":
		h.cursor = h.cursor.AddDate(0, 0, 1)
		return h, h.loadDay()
	case "t":
		h.cursor = time.Now()
		return h, h.loadDay()
	case "e":
		return h, h.startEdit()
	case "d":
		h.mode = healthConfirmDelete
	case "T":
		h.mode = healthSummary
		return h, h.loadSummary()
	case "r", "ctrl+r":
		return h, h.loadDay()
	}
	return h, nil
}

func (h *Health) startEdit() tea.Cmd {
	x := h.current
	h.formIn = healthFormState{
		steps:         intStr(x.Steps),
		distanceMi:    floatStr(x.DistanceMi),
		activeMinutes: intStr(x.ActiveMinutes),
		caloriesOut:   floatStr(x.CaloriesOut),
		weight:        floatStr(x.Weight),
		notes:         x.Notes,
	}
	d := &h.formIn
	h.form = huh.NewForm(huh.NewGroup(
		huh.NewInput().Title("Steps").Value(&d.steps),
		huh.NewInput().Title("Distance (mi)").Value(&d.distanceMi),
		huh.NewInput().Title("Active minutes").Value(&d.activeMinutes),
		huh.NewInput().Title("Calories burned").Value(&d.caloriesOut),
		huh.NewInput().Title("Weight").Value(&d.weight),
		huh.NewText().Title("Notes").Value(&d.notes).Lines(3),
	))
	h.mode = healthForm
	return h.form.Init()
}

func (h *Health) submit() tea.Cmd {
	d := h.formIn
	in := api.HealthInput{Notes: d.notes}
	if v, err := parseInt(d.steps); err == nil && v >= 0 {
		in.Steps = &v
	}
	if v, err := parseFloat(d.distanceMi); err == nil && v >= 0 {
		in.DistanceMi = &v
	}
	if v, err := parseInt(d.activeMinutes); err == nil && v >= 0 {
		in.ActiveMinutes = &v
	}
	if v, err := parseFloat(d.caloriesOut); err == nil && v >= 0 {
		in.CaloriesOut = &v
	}
	if v, err := parseFloat(d.weight); err == nil && v >= 0 {
		in.Weight = &v
	}
	in.Exercises = h.current.Exercises
	in.Foods = h.current.Foods
	date := h.cursor.Format("2006-01-02")
	c := h.client
	h.form = nil
	h.mode = healthView
	return func() tea.Msg {
		_, err := c.UpsertHealthLog(date, in)
		return healthMutatedMsg{err: err}
	}
}

func parseFloat(s string) (float64, error) {
	s = strings.TrimSpace(s)
	if s == "" {
		return 0, fmt.Errorf("empty")
	}
	var f float64
	_, err := fmt.Sscanf(s, "%f", &f)
	return f, err
}

func intStr(n int) string     { return fmt.Sprintf("%d", n) }
func floatStr(f float64) string { return fmt.Sprintf("%g", f) }

func (h *Health) deleteCurrent() tea.Cmd {
	c := h.client
	d := h.cursor.Format("2006-01-02")
	return func() tea.Msg { return healthMutatedMsg{err: c.DeleteHealthLog(d)} }
}

func (h *Health) View() string {
	if h.mode == healthForm {
		if h.form != nil {
			return lipgloss.JoinVertical(lipgloss.Left, h.form.View(), "", components.FormHint())
		}
	}
	if h.mode == healthConfirmDelete {
		return components.ConfirmView("Delete health log for "+h.cursor.Format("2006-01-02")+"?", h.width, h.height)
	}
	if h.mode == healthSummary {
		return h.summaryView()
	}
	if !h.loaded {
		return styles.MutedText.Render("Loading...")
	}
	x := h.current
	stats := []components.SummaryStat{
		{Label: "Steps", Value: intStr(x.Steps)},
		{Label: "Distance", Value: fmt.Sprintf("%.2f mi", x.DistanceMi)},
		{Label: "Active min", Value: intStr(x.ActiveMinutes)},
		{Label: "Cal out", Value: floatStr(x.CaloriesOut)},
		{Label: "Weight", Value: floatStr(x.Weight)},
	}
	header := styles.Title.Render(h.cursor.Format("Monday, 2 January 2006"))
	rows := []string{
		header,
		"",
		components.SummaryView("Today", stats),
	}
	if len(x.Foods) > 0 {
		rows = append(rows, "", styles.Title.Render("Foods"))
		for _, f := range x.Foods {
			rows = append(rows, fmt.Sprintf("  %-24s %g %s · %g cal", truncate(f.Name, 24), f.Amount, f.Unit, f.Calories))
		}
	}
	if len(x.Exercises) > 0 {
		rows = append(rows, "", styles.Title.Render("Exercises"))
		for _, ex := range x.Exercises {
			meta := []string{ex.Type}
			if ex.DurationMin > 0 {
				meta = append(meta, fmt.Sprintf("%g min", ex.DurationMin))
			}
			if ex.DistanceKm > 0 {
				meta = append(meta, fmt.Sprintf("%g km", ex.DistanceKm))
			}
			if len(ex.Sets) > 0 {
				meta = append(meta, fmt.Sprintf("%d sets", len(ex.Sets)))
			}
			rows = append(rows, fmt.Sprintf("  %-24s %s", truncate(ex.Name, 24), strings.Join(meta, " · ")))
		}
	}
	if x.Notes != "" {
		rows = append(rows, "", styles.MutedText.Render(x.Notes))
	}
	rows = append(rows, "", styles.MutedText.Render("← prev · → next · t today · e edit · d delete · T trends"))
	return lipgloss.JoinVertical(lipgloss.Left, rows...)
}

func (h *Health) summaryView() string {
	rows := []string{styles.Title.Render("Last 7 days summary")}
	if h.summary == nil {
		rows = append(rows, styles.MutedText.Render("Loading..."))
	} else {
		for k, v := range h.summary {
			rows = append(rows, fmt.Sprintf("%-20s %v", k, v))
		}
	}
	rows = append(rows, "", styles.MutedText.Render("esc to return"))
	return strings.Join(rows, "\n")
}

func (h *Health) Title() string { return "Health" }
func (h *Health) StatusHints() []string {
	return []string{
		styles.KeyHint("←/→", "day"),
		styles.KeyHint("t", "today"),
		styles.KeyHint("e", "edit"),
		styles.KeyHint("T", "trends"),
		styles.KeyHint("d", "delete"),
	}
}
func (h *Health) Help() []components.HelpEntry {
	return []components.HelpEntry{
		{Keys: "←/→ or h/l", Desc: "previous / next day"},
		{Keys: "t", Desc: "jump to today"},
		{Keys: "e", Desc: "edit totals"},
		{Keys: "d", Desc: "delete this day's log"},
		{Keys: "T", Desc: "show 7-day summary"},
		{Keys: "r", Desc: "refresh"},
	}
}
func (h *Health) SetSize(w, ht int) { h.width, h.height = w, ht }
