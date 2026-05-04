package screens

import (
	"fmt"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/neilfarmer/memoire/tui/internal/api"
	"github.com/neilfarmer/memoire/tui/internal/styles"
	"github.com/neilfarmer/memoire/tui/internal/ui/components"
)

type Dashboard struct {
	client *api.Client
	width  int
	height int

	loading      bool
	err          error
	tasksToday   int
	tasksTotal   int
	tasksOverdue int
	habitsDone   int
	habitsTotal  int
	streak       int
	latestNote   string
	latestNoteAt string
}

type dashLoadedMsg struct {
	tasks  []api.Task
	habits []api.Habit
	notes  []api.NoteSummary
	err    error
}

func newDashboard(c *api.Client) *Dashboard {
	return &Dashboard{client: c, loading: true}
}

func (d *Dashboard) Init() tea.Cmd { return d.refresh() }

func (d *Dashboard) refresh() tea.Cmd {
	c := d.client
	return func() tea.Msg {
		var msg dashLoadedMsg
		if t, err := c.ListTasks(); err == nil {
			msg.tasks = t
		} else {
			msg.err = err
		}
		if h, err := c.ListHabits(); err == nil {
			msg.habits = h
		}
		if n, err := c.ListNotes(""); err == nil {
			msg.notes = n
		}
		return msg
	}
}

func (d *Dashboard) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch m := msg.(type) {
	case dashLoadedMsg:
		d.loading = false
		d.err = m.err
		today := time.Now().Format("2006-01-02")
		d.tasksTotal = len(m.tasks)
		d.tasksToday = 0
		d.tasksOverdue = 0
		for _, t := range m.tasks {
			if t.Status == "done" {
				continue
			}
			if t.DueDate == today {
				d.tasksToday++
			} else if t.DueDate != "" && t.DueDate < today {
				d.tasksOverdue++
			}
		}
		d.habitsTotal = len(m.habits)
		d.habitsDone = 0
		best := 0
		for _, h := range m.habits {
			if h.DoneToday {
				d.habitsDone++
			}
			if h.CurrentStreak > best {
				best = h.CurrentStreak
			}
		}
		d.streak = best
		if len(m.notes) > 0 {
			d.latestNote = m.notes[0].Title
			d.latestNoteAt = m.notes[0].UpdatedAt
		}
	case tea.KeyMsg:
		if m.String() == "r" || m.String() == "ctrl+r" {
			d.loading = true
			return d, d.refresh()
		}
	}
	return d, nil
}

func (d *Dashboard) View() string {
	if d.loading {
		return styles.MutedText.Render("Loading dashboard...")
	}
	if d.err != nil {
		return styles.DangerText.Render("Error: " + d.err.Error())
	}
	cardStyle := styles.Box.Width(d.width/2 - 4)
	tasksCard := cardStyle.Render(strings.Join([]string{
		styles.Title.Render("Tasks"),
		fmt.Sprintf("%d due today", d.tasksToday),
		fmt.Sprintf("%d overdue", d.tasksOverdue),
		styles.MutedText.Render(fmt.Sprintf("%d total", d.tasksTotal)),
	}, "\n"))
	habitsCard := cardStyle.Render(strings.Join([]string{
		styles.Title.Render("Habits"),
		fmt.Sprintf("%d / %d done today", d.habitsDone, d.habitsTotal),
		fmt.Sprintf("Best streak: %d days", d.streak),
		"",
		components.Bar(percent(d.habitsDone, d.habitsTotal), 18),
	}, "\n"))
	notesCard := cardStyle.Render(strings.Join([]string{
		styles.Title.Render("Latest note"),
		d.latestNote,
		styles.MutedText.Render(d.latestNoteAt),
	}, "\n"))
	greeting := styles.Title.Render(fmt.Sprintf("Good %s", greeting(time.Now())))
	row1 := lipgloss.JoinHorizontal(lipgloss.Top, tasksCard, "  ", habitsCard)
	return lipgloss.JoinVertical(lipgloss.Left,
		greeting,
		"",
		row1,
		"",
		notesCard,
		"",
		styles.MutedText.Render("press r to refresh"),
	)
}

func percent(num, denom int) int {
	if denom == 0 {
		return 0
	}
	return num * 100 / denom
}

func greeting(t time.Time) string {
	switch h := t.Hour(); {
	case h < 12:
		return "morning"
	case h < 18:
		return "afternoon"
	default:
		return "evening"
	}
}

func (d *Dashboard) Title() string         { return "Dashboard" }
func (d *Dashboard) StatusHints() []string { return []string{styles.KeyHint("r", "refresh")} }
func (d *Dashboard) Help() []components.HelpEntry {
	return []components.HelpEntry{{Keys: "r", Desc: "refresh"}}
}
func (d *Dashboard) SetSize(w, h int) { d.width, d.height = w, h }
