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

type nutritionMode int

const (
	nutritionView nutritionMode = iota
	nutritionAddMeal
	nutritionConfirmDelete
)

type Nutrition struct {
	client *api.Client
	width  int
	height int

	mode    nutritionMode
	loading bool
	err     error

	cursor  time.Time
	current api.NutritionLog
	loaded  bool

	form    *huh.Form
	formIn  mealFormState
}

type mealFormState struct {
	name     string
	calories string
	protein  string
	carbs    string
	fat      string
	notes    string
}

type nutritionLogMsg struct {
	log api.NutritionLog
	err error
}
type nutritionMutatedMsg struct{ err error }

func newNutrition(c *api.Client) *Nutrition {
	return &Nutrition{client: c, cursor: time.Now()}
}

func (n *Nutrition) Init() tea.Cmd { return n.loadDay() }

func (n *Nutrition) loadDay() tea.Cmd {
	c := n.client
	d := n.cursor.Format("2006-01-02")
	return func() tea.Msg {
		log, err := c.GetNutritionLog(d)
		if err != nil && api.IsNotFound(err) {
			return nutritionLogMsg{log: api.NutritionLog{LogDate: d}}
		}
		return nutritionLogMsg{log: log, err: err}
	}
}

func (n *Nutrition) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch m := msg.(type) {
	case nutritionLogMsg:
		n.err = m.err
		n.current = m.log
		n.loaded = true
		return n, nil
	case nutritionMutatedMsg:
		n.err = m.err
		n.mode = nutritionView
		return n, n.loadDay()
	case tea.KeyMsg:
		return n.handleKey(m)
	}
	if n.mode == nutritionAddMeal && n.form != nil {
		f, cmd := n.form.Update(msg)
		if ff, ok := f.(*huh.Form); ok {
			n.form = ff
		}
		if n.form.State == huh.StateCompleted {
			return n, n.submitMeal()
		}
		return n, cmd
	}
	return n, nil
}

func (n *Nutrition) handleKey(m tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch n.mode {
	case nutritionAddMeal:
		if m.String() == "esc" {
			n.mode = nutritionView
			n.form = nil
			return n, nil
		}
		if m.String() == "ctrl+s" {
			return n, n.submitMeal()
		}
		f, cmd := n.form.Update(m)
		if ff, ok := f.(*huh.Form); ok {
			n.form = ff
		}
		if n.form.State == huh.StateCompleted {
			return n, n.submitMeal()
		}
		return n, cmd
	case nutritionConfirmDelete:
		if m.String() == "y" {
			return n, n.deleteCurrent()
		}
		if m.String() == "n" || m.String() == "esc" {
			n.mode = nutritionView
		}
		return n, nil
	}
	switch m.String() {
	case "left", "h":
		n.cursor = n.cursor.AddDate(0, 0, -1)
		return n, n.loadDay()
	case "right", "l":
		n.cursor = n.cursor.AddDate(0, 0, 1)
		return n, n.loadDay()
	case "t":
		n.cursor = time.Now()
		return n, n.loadDay()
	case "n":
		return n, n.startAddMeal()
	case "x":
		// remove last meal
		if len(n.current.Meals) > 0 {
			n.current.Meals = n.current.Meals[:len(n.current.Meals)-1]
			return n, n.persist()
		}
	case "d":
		n.mode = nutritionConfirmDelete
	case "r", "ctrl+r":
		return n, n.loadDay()
	}
	return n, nil
}

func (n *Nutrition) startAddMeal() tea.Cmd {
	n.formIn = mealFormState{}
	d := &n.formIn
	n.form = huh.NewForm(huh.NewGroup(
		huh.NewInput().Title("Name").Value(&d.name).Validate(func(s string) error {
			if strings.TrimSpace(s) == "" {
				return fmt.Errorf("required")
			}
			return nil
		}),
		huh.NewInput().Title("Calories").Value(&d.calories),
		huh.NewInput().Title("Protein (g)").Value(&d.protein),
		huh.NewInput().Title("Carbs (g)").Value(&d.carbs),
		huh.NewInput().Title("Fat (g)").Value(&d.fat),
	))
	n.mode = nutritionAddMeal
	return n.form.Init()
}

func (n *Nutrition) submitMeal() tea.Cmd {
	d := n.formIn
	cal, _ := parseFloat(d.calories)
	pro, _ := parseFloat(d.protein)
	car, _ := parseFloat(d.carbs)
	fat, _ := parseFloat(d.fat)
	meal := api.Meal{Name: strings.TrimSpace(d.name), Calories: cal, Protein: pro, Carbs: car, Fat: fat}
	n.current.Meals = append(n.current.Meals, meal)
	n.form = nil
	n.mode = nutritionView
	return n.persist()
}

func (n *Nutrition) persist() tea.Cmd {
	c := n.client
	d := n.cursor.Format("2006-01-02")
	in := api.NutritionInput{Meals: n.current.Meals, Notes: n.current.Notes}
	return func() tea.Msg {
		_, err := c.UpsertNutritionLog(d, in)
		return nutritionMutatedMsg{err: err}
	}
}

func (n *Nutrition) deleteCurrent() tea.Cmd {
	c := n.client
	d := n.cursor.Format("2006-01-02")
	return func() tea.Msg { return nutritionMutatedMsg{err: c.DeleteNutritionLog(d)} }
}

func (n *Nutrition) View() string {
	if n.mode == nutritionAddMeal {
		if n.form != nil {
			return lipgloss.JoinVertical(lipgloss.Left, n.form.View(), "", components.FormHint())
		}
	}
	if n.mode == nutritionConfirmDelete {
		return components.ConfirmView("Delete nutrition log for "+n.cursor.Format("2006-01-02")+"?", n.width, n.height)
	}
	if !n.loaded {
		return styles.MutedText.Render("Loading...")
	}
	header := styles.Title.Render(n.cursor.Format("Monday, 2 January 2006"))
	totals := mealTotals(n.current.Meals)
	statRow := fmt.Sprintf("Calories %g  ·  Protein %gg  ·  Carbs %gg  ·  Fat %gg",
		totals.Calories, totals.Protein, totals.Carbs, totals.Fat)
	rows := []string{header, styles.MutedText.Render(statRow), ""}
	if len(n.current.Meals) == 0 {
		rows = append(rows, styles.MutedText.Render("No meals logged yet. Press n to add."))
	} else {
		for _, m := range n.current.Meals {
			rows = append(rows, fmt.Sprintf("  %-24s %g cal · %gp / %gc / %gf",
				truncate(m.Name, 24), m.Calories, m.Protein, m.Carbs, m.Fat))
		}
	}
	rows = append(rows, "", styles.MutedText.Render("← prev · → next · t today · n add meal · x remove last · d delete day"))
	return lipgloss.JoinVertical(lipgloss.Left, rows...)
}

func mealTotals(meals []api.Meal) api.Meal {
	var t api.Meal
	for _, m := range meals {
		t.Calories += m.Calories
		t.Protein += m.Protein
		t.Carbs += m.Carbs
		t.Fat += m.Fat
	}
	return t
}

func (n *Nutrition) Title() string { return "Nutrition" }
func (n *Nutrition) StatusHints() []string {
	return []string{
		styles.KeyHint("←/→", "day"),
		styles.KeyHint("n", "add meal"),
		styles.KeyHint("x", "remove last"),
		styles.KeyHint("d", "delete day"),
	}
}
func (n *Nutrition) Help() []components.HelpEntry {
	return []components.HelpEntry{
		{Keys: "←/→ or h/l", Desc: "previous / next day"},
		{Keys: "t", Desc: "jump to today"},
		{Keys: "n", Desc: "add meal"},
		{Keys: "x", Desc: "remove last meal"},
		{Keys: "d", Desc: "delete entire day"},
	}
}
func (n *Nutrition) SetSize(w, h int) { n.width, n.height = w, h }
