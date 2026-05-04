package screens

import (
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/table"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/huh"
	"github.com/charmbracelet/lipgloss"

	"github.com/neilfarmer/memoire/tui/internal/api"
	"github.com/neilfarmer/memoire/tui/internal/styles"
	"github.com/neilfarmer/memoire/tui/internal/ui/components"
)

type taskMode int

const (
	taskList taskMode = iota
	taskDetail
	taskForm
	taskCalendar
	taskConfirmDelete
)

type Tasks struct {
	client *api.Client

	mode    taskMode
	width   int
	height  int
	loading bool
	err     error

	tasks    []api.Task
	filtered []api.Task
	filter   string
	sortMode string
	tbl      table.Model

	form     *huh.Form
	formData taskFormState
}

type taskFormState struct {
	id          string
	title       string
	description string
	status      string
	priority    string
	dueDate     string
	tags        string
	scheduled   string
	duration    string
}

type tasksLoadedMsg struct {
	tasks []api.Task
	err   error
}
type tasksMutatedMsg struct{ err error }

func newTasks(c *api.Client) *Tasks {
	t := &Tasks{client: c, filter: "all", sortMode: "smart"}
	t.tbl = components.NewTable(taskCols(80), nil, 18)
	return t
}

func taskCols(width int) []components.Column {
	titleW := width - 12 - 9 - 12 - 14
	if titleW < 20 {
		titleW = 20
	}
	return []components.Column{
		{Title: "STATUS", Width: 12},
		{Title: "PRI", Width: 9},
		{Title: "DUE", Width: 12},
		{Title: "TITLE", Width: titleW},
		{Title: "TAGS", Width: 14},
	}
}

func (t *Tasks) Init() tea.Cmd { return t.refresh() }

func (t *Tasks) refresh() tea.Cmd {
	c := t.client
	return func() tea.Msg {
		out, err := c.ListTasks()
		return tasksLoadedMsg{tasks: out, err: err}
	}
}

func (t *Tasks) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch m := msg.(type) {
	case tasksLoadedMsg:
		t.loading = false
		t.err = m.err
		t.tasks = m.tasks
		t.refilter()
		return t, nil
	case tasksMutatedMsg:
		if m.err != nil {
			t.err = m.err
		}
		return t, t.refresh()
	case tea.KeyMsg:
		return t.handleKey(m)
	}
	if t.mode == taskForm && t.form != nil {
		f, cmd := t.form.Update(msg)
		if ff, ok := f.(*huh.Form); ok {
			t.form = ff
		}
		if t.form.State == huh.StateCompleted {
			return t, t.submitForm()
		}
		return t, cmd
	}
	if t.mode == taskList {
		var cmd tea.Cmd
		t.tbl, cmd = t.tbl.Update(msg)
		return t, cmd
	}
	return t, nil
}

func (t *Tasks) handleKey(m tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch t.mode {
	case taskConfirmDelete:
		if m.String() == "y" {
			t.mode = taskList
			return t, t.deleteSelected()
		}
		if m.String() == "n" || m.String() == "esc" {
			t.mode = taskList
			return t, nil
		}
		return t, nil
	case taskDetail:
		switch m.String() {
		case "esc", "q":
			t.mode = taskList
		case "e":
			return t, t.startEdit()
		case "d":
			t.mode = taskConfirmDelete
		}
		return t, nil
	case taskForm:
		if m.String() == "esc" {
			t.mode = taskList
			t.form = nil
			return t, nil
		}
		if m.String() == "ctrl+s" {
			return t, t.submitForm()
		}
		f, cmd := t.form.Update(m)
		if ff, ok := f.(*huh.Form); ok {
			t.form = ff
		}
		if t.form.State == huh.StateCompleted {
			return t, t.submitForm()
		}
		return t, cmd
	case taskCalendar:
		if m.String() == "esc" || m.String() == "c" {
			t.mode = taskList
		}
		return t, nil
	}
	switch m.String() {
	case "enter":
		if t.tbl.Cursor() < len(t.filtered) {
			t.mode = taskDetail
		}
		return t, nil
	case "n":
		return t, t.startNew()
	case "e":
		return t, t.startEdit()
	case "d":
		if t.tbl.Cursor() < len(t.filtered) {
			t.mode = taskConfirmDelete
		}
	case "r", "ctrl+r":
		t.loading = true
		return t, t.refresh()
	case "a":
		return t, t.autoSchedule()
	case "c":
		t.mode = taskCalendar
	case "f":
		t.filter = nextFilter(t.filter)
		t.refilter()
	case "s":
		t.sortMode = nextSort(t.sortMode)
		t.refilter()
	}
	var cmd tea.Cmd
	t.tbl, cmd = t.tbl.Update(m)
	return t, cmd
}

func nextFilter(cur string) string {
	o := []string{"all", "todo", "in_progress", "done"}
	for i, x := range o {
		if x == cur {
			return o[(i+1)%len(o)]
		}
	}
	return "all"
}

func nextSort(cur string) string {
	o := []string{"smart", "due", "priority", "title"}
	for i, x := range o {
		if x == cur {
			return o[(i+1)%len(o)]
		}
	}
	return "smart"
}

func (t *Tasks) refilter() {
	filtered := make([]api.Task, 0, len(t.tasks))
	for _, x := range t.tasks {
		switch t.filter {
		case "all":
			filtered = append(filtered, x)
		case "todo":
			if x.Status == "" || x.Status == "todo" {
				filtered = append(filtered, x)
			}
		case "in_progress":
			if x.Status == "in_progress" {
				filtered = append(filtered, x)
			}
		case "done":
			if x.Status == "done" {
				filtered = append(filtered, x)
			}
		}
	}
	sort.Slice(filtered, func(i, j int) bool {
		switch t.sortMode {
		case "due":
			return filtered[i].DueDate < filtered[j].DueDate
		case "priority":
			return priorityRank(filtered[i].Priority) < priorityRank(filtered[j].Priority)
		case "title":
			return strings.ToLower(filtered[i].Title) < strings.ToLower(filtered[j].Title)
		}
		return smartLess(filtered[i], filtered[j])
	})
	t.filtered = filtered
	rows := make([]components.Row, 0, len(filtered))
	for _, x := range filtered {
		status := x.Status
		if status == "" {
			status = "todo"
		}
		rows = append(rows, components.Row{
			status,
			orDash(x.Priority),
			orDash(x.DueDate),
			x.Title,
			truncate(strings.Join(x.Tags, ","), 14),
		})
	}
	t.tbl.SetRows(rows)
}

func smartLess(a, b api.Task) bool {
	today := time.Now().Format("2006-01-02")
	overdueA := a.DueDate != "" && a.DueDate < today && a.Status != "done"
	overdueB := b.DueDate != "" && b.DueDate < today && b.Status != "done"
	if overdueA != overdueB {
		return overdueA
	}
	if a.DueDate != b.DueDate {
		return a.DueDate < b.DueDate
	}
	return priorityRank(a.Priority) < priorityRank(b.Priority)
}

func priorityRank(p string) int {
	switch p {
	case "high":
		return 0
	case "medium":
		return 1
	case "low":
		return 2
	}
	return 3
}

func orDash(s string) string {
	if s == "" {
		return "—"
	}
	return s
}

func (t *Tasks) startNew() tea.Cmd {
	t.formData = taskFormState{status: "todo", priority: "medium"}
	t.form = t.newForm("New task")
	t.mode = taskForm
	return t.form.Init()
}

func (t *Tasks) startEdit() tea.Cmd {
	idx := t.tbl.Cursor()
	if idx < 0 || idx >= len(t.filtered) {
		return nil
	}
	x := t.filtered[idx]
	t.formData = taskFormState{
		id:          x.TaskID,
		title:       x.Title,
		description: x.Description,
		status:      x.Status,
		priority:    x.Priority,
		dueDate:     x.DueDate,
		tags:        strings.Join(x.Tags, ", "),
		scheduled:   x.ScheduledStart,
		duration:    fmt.Sprintf("%d", x.DurationMinutes),
	}
	t.form = t.newForm("Edit task")
	t.mode = taskForm
	return t.form.Init()
}

func (t *Tasks) newForm(title string) *huh.Form {
	d := &t.formData
	return huh.NewForm(
		huh.NewGroup(
			huh.NewInput().Title("Title").Value(&d.title).Validate(func(s string) error {
				if strings.TrimSpace(s) == "" {
					return fmt.Errorf("required")
				}
				return nil
			}),
			huh.NewText().Title("Description").Value(&d.description).Lines(4),
			huh.NewSelect[string]().Title("Status").Options(
				huh.NewOption("To Do", "todo"),
				huh.NewOption("In Progress", "in_progress"),
				huh.NewOption("Done", "done"),
			).Value(&d.status),
			huh.NewSelect[string]().Title("Priority").Options(
				huh.NewOption("High", "high"),
				huh.NewOption("Medium", "medium"),
				huh.NewOption("Low", "low"),
			).Value(&d.priority),
			huh.NewInput().Title("Due date (YYYY-MM-DD)").Value(&d.dueDate).Validate(validateOptionalDate),
			huh.NewInput().Title("Tags (comma separated)").Value(&d.tags),
			huh.NewInput().Title("Scheduled start (RFC3339, optional)").Value(&d.scheduled),
			huh.NewInput().Title("Duration minutes (optional)").Value(&d.duration),
		),
	).WithTheme(huh.ThemeBase())
}

func validateOptionalDate(s string) error {
	s = strings.TrimSpace(s)
	if s == "" {
		return nil
	}
	if _, err := time.Parse("2006-01-02", s); err != nil {
		return fmt.Errorf("expected YYYY-MM-DD")
	}
	return nil
}

func (t *Tasks) submitForm() tea.Cmd {
	d := t.formData
	tags := splitTags(d.tags)
	in := api.TaskInput{
		Title:          strings.TrimSpace(d.title),
		Description:    d.description,
		Status:         d.status,
		Priority:       d.priority,
		DueDate:        strings.TrimSpace(d.dueDate),
		Tags:           tags,
		ScheduledStart: strings.TrimSpace(d.scheduled),
	}
	if dur, err := parseInt(d.duration); err == nil && dur > 0 {
		in.DurationMinutes = dur
	}
	t.mode = taskList
	t.form = nil
	id := d.id
	c := t.client
	return func() tea.Msg {
		var err error
		if id == "" {
			_, err = c.CreateTask(in)
		} else {
			_, err = c.UpdateTask(id, in)
		}
		return tasksMutatedMsg{err: err}
	}
}

func splitTags(s string) []string {
	parts := strings.Split(s, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}

func parseInt(s string) (int, error) {
	s = strings.TrimSpace(s)
	if s == "" {
		return 0, fmt.Errorf("empty")
	}
	var n int
	_, err := fmt.Sscanf(s, "%d", &n)
	return n, err
}

func (t *Tasks) deleteSelected() tea.Cmd {
	idx := t.tbl.Cursor()
	if idx < 0 || idx >= len(t.filtered) {
		return nil
	}
	id := t.filtered[idx].TaskID
	c := t.client
	return func() tea.Msg {
		return tasksMutatedMsg{err: c.DeleteTask(id)}
	}
}

func (t *Tasks) autoSchedule() tea.Cmd {
	c := t.client
	return func() tea.Msg {
		_, err := c.AutoScheduleTasks(map[string]any{"horizon_days": 7})
		return tasksMutatedMsg{err: err}
	}
}

func (t *Tasks) View() string {
	if t.loading && len(t.tasks) == 0 {
		return styles.MutedText.Render("Loading tasks...")
	}
	switch t.mode {
	case taskForm:
		if t.form != nil {
			return lipgloss.JoinVertical(lipgloss.Left, t.form.View(), "", components.FormHint())
		}
	case taskDetail:
		return t.detailView()
	case taskCalendar:
		return t.calendarView()
	case taskConfirmDelete:
		return components.ConfirmView("Delete this task?", t.width, t.height)
	}
	pills := renderPills(t.filter, []string{"all", "todo", "in_progress", "done"})
	sortBadge := styles.MutedText.Render("sort: " + t.sortMode)
	header := lipgloss.JoinHorizontal(lipgloss.Top, pills, "  ", sortBadge)
	tableHeight := t.height - 8
	if tableHeight < 5 {
		tableHeight = 5
	}
	t.tbl.SetHeight(tableHeight)
	t.tbl.SetColumns(taskCols(t.width - 6))
	hints := []string{
		styles.KeyHint("↵", "details"),
		styles.KeyHint("n", "new"),
		styles.KeyHint("e", "edit"),
		styles.KeyHint("d", "delete"),
		styles.KeyHint("f", "filter"),
		styles.KeyHint("s", "sort"),
		styles.KeyHint("a", "auto-schedule"),
		styles.KeyHint("c", "agenda"),
	}
	tableBox := components.FrameTable("Tasks", len(t.filtered), t.tbl, hints, true)
	return lipgloss.JoinVertical(lipgloss.Left, header, "", tableBox)
}

func renderPills(active string, options []string) string {
	parts := make([]string, 0, len(options))
	for _, o := range options {
		if o == active {
			parts = append(parts, styles.PillActive.Render(o))
		} else {
			parts = append(parts, styles.Pill.Render(o))
		}
	}
	return lipgloss.JoinHorizontal(lipgloss.Top, parts...)
}

func (t *Tasks) detailView() string {
	idx := t.tbl.Cursor()
	if idx < 0 || idx >= len(t.filtered) {
		return ""
	}
	x := t.filtered[idx]
	rows := []string{
		components.Crumbs("Tasks", x.Title),
		"",
		styles.Title.Render(x.Title),
		"",
		"Status:    " + styles.StatusColor(x.Status).Render(orDash(x.Status)),
		"Priority:  " + styles.PriorityColor(x.Priority).Render(orDash(x.Priority)),
	}
	if x.DueDate != "" {
		rows = append(rows, "Due:       "+x.DueDate)
	}
	if x.ScheduledStart != "" {
		rows = append(rows, "Scheduled: "+x.ScheduledStart)
	}
	if len(x.Tags) > 0 {
		rows = append(rows, "Tags:      "+strings.Join(x.Tags, ", "))
	}
	if x.Description != "" {
		rows = append(rows, "", components.RenderMarkdown(x.Description, t.width-6))
	}
	rows = append(rows, "", styles.MutedText.Render("<e> edit  <d> delete  <esc> back"))
	return styles.Box.Render(strings.Join(rows, "\n"))
}

func (t *Tasks) calendarView() string {
	c := t.client
	from := time.Now().Format("2006-01-02")
	to := time.Now().AddDate(0, 0, 7).Format("2006-01-02")
	rows := []string{
		components.Crumbs("Tasks", "Agenda"),
		"",
		styles.Title.Render(fmt.Sprintf("Agenda %s — %s", from, to)),
	}
	tasks, err := c.TasksCalendar(from, to)
	if err != nil {
		rows = append(rows, styles.DangerText.Render(err.Error()))
	} else if len(tasks) == 0 {
		rows = append(rows, styles.MutedText.Render("Nothing scheduled."))
	} else {
		for _, x := range tasks {
			rows = append(rows, fmt.Sprintf("%s  %s", x.ScheduledStart, x.Title))
		}
	}
	rows = append(rows, "", styles.MutedText.Render("<esc> back"))
	return styles.Box.Render(strings.Join(rows, "\n"))
}

func (t *Tasks) Title() string { return "Tasks" }
func (t *Tasks) StatusHints() []string {
	return []string{
		styles.KeyHint("n", "new"),
		styles.KeyHint("↵", "open"),
		styles.KeyHint("e", "edit"),
		styles.KeyHint("d", "delete"),
		styles.KeyHint("f", "filter"),
		styles.KeyHint("a", "auto-schedule"),
	}
}
func (t *Tasks) Help() []components.HelpEntry {
	return []components.HelpEntry{
		{Keys: "↑/↓", Desc: "select row"},
		{Keys: "↵ enter", Desc: "open detail"},
		{Keys: "esc", Desc: "back"},
		{Keys: "n", Desc: "new task"},
		{Keys: "e", Desc: "edit selected"},
		{Keys: "d", Desc: "delete selected"},
		{Keys: "f", Desc: "cycle filter (all/todo/in-progress/done)"},
		{Keys: "s", Desc: "cycle sort (smart/due/priority/title)"},
		{Keys: "c", Desc: "agenda for next 7 days"},
		{Keys: "a", Desc: "auto-schedule unscheduled tasks"},
		{Keys: "r", Desc: "refresh"},
	}
}
func (t *Tasks) SetSize(w, h int) {
	t.width, t.height = w, h
	t.tbl.SetColumns(taskCols(w - 6))
	if h-8 > 0 {
		t.tbl.SetHeight(h - 8)
	}
}
