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

type financeTab int

const (
	tabDebts financeTab = iota
	tabIncome
	tabExpenses
)

type financeMode int

const (
	financeList financeMode = iota
	financeForm
	financeConfirmDelete
)

type Finances struct {
	client *api.Client
	width  int
	height int

	mode    financeMode
	tab     financeTab
	loading bool
	err     error

	debts    []api.Debt
	incomes  []api.Income
	expenses []api.FixedExpense
	summary  api.FinancesSummary

	debtsTbl    table.Model
	incomesTbl  table.Model
	expensesTbl table.Model

	form   *huh.Form
	formIn financeFormState
}

type financeFormState struct {
	id          string
	name        string
	category    string
	debtType    string
	amount      string
	apr         string
	monthlyPay  string
	frequency   string
	dueDay      string
	notes       string
}

type financesLoadedMsg struct {
	debts    []api.Debt
	incomes  []api.Income
	expenses []api.FixedExpense
	summary  api.FinancesSummary
	err      error
}
type financesMutatedMsg struct{ err error }

func newFinances(c *api.Client) *Finances {
	f := &Finances{client: c}
	f.debtsTbl = components.NewTable(debtCols(80), nil, 14)
	f.incomesTbl = components.NewTable(incomeCols(80), nil, 14)
	f.expensesTbl = components.NewTable(expenseCols(80), nil, 14)
	return f
}

func debtCols(w int) []components.Column {
	nameW := w - 16 - 14 - 10 - 14
	if nameW < 16 {
		nameW = 16
	}
	return []components.Column{
		{Title: "TYPE", Width: 16},
		{Title: "BALANCE", Width: 14},
		{Title: "APR", Width: 10},
		{Title: "MONTHLY", Width: 14},
		{Title: "NAME", Width: nameW},
	}
}

func incomeCols(w int) []components.Column {
	nameW := w - 14 - 12 - 16
	if nameW < 16 {
		nameW = 16
	}
	return []components.Column{
		{Title: "AMOUNT", Width: 14},
		{Title: "FREQ", Width: 12},
		{Title: "MONTHLY", Width: 16},
		{Title: "NAME", Width: nameW},
	}
}

func expenseCols(w int) []components.Column {
	nameW := w - 16 - 14 - 12 - 16
	if nameW < 16 {
		nameW = 16
	}
	return []components.Column{
		{Title: "CATEGORY", Width: 16},
		{Title: "AMOUNT", Width: 14},
		{Title: "FREQ", Width: 12},
		{Title: "MONTHLY", Width: 16},
		{Title: "NAME", Width: nameW},
	}
}

func (f *Finances) Init() tea.Cmd { return f.refresh() }

func (f *Finances) refresh() tea.Cmd {
	c := f.client
	return func() tea.Msg {
		var msg financesLoadedMsg
		if d, err := c.ListDebts(); err == nil {
			msg.debts = d
		} else {
			msg.err = err
		}
		if inc, err := c.ListIncome(); err == nil {
			msg.incomes = inc
		}
		if e, err := c.ListFixedExpenses(); err == nil {
			msg.expenses = e
		}
		if s, err := c.FinancesSummary(); err == nil {
			msg.summary = s
		}
		return msg
	}
}

func (f *Finances) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch m := msg.(type) {
	case financesLoadedMsg:
		f.loading = false
		f.err = m.err
		f.debts = m.debts
		f.incomes = m.incomes
		f.expenses = m.expenses
		f.summary = m.summary
		f.refreshRows()
		return f, nil
	case financesMutatedMsg:
		f.err = m.err
		f.mode = financeList
		return f, f.refresh()
	case tea.KeyMsg:
		return f.handleKey(m)
	}
	if f.mode == financeForm && f.form != nil {
		ff, cmd := f.form.Update(msg)
		if x, ok := ff.(*huh.Form); ok {
			f.form = x
		}
		if f.form.State == huh.StateCompleted {
			return f, f.submit()
		}
		return f, cmd
	}
	if f.mode == financeList {
		var cmd tea.Cmd
		switch f.tab {
		case tabDebts:
			f.debtsTbl, cmd = f.debtsTbl.Update(msg)
		case tabIncome:
			f.incomesTbl, cmd = f.incomesTbl.Update(msg)
		case tabExpenses:
			f.expensesTbl, cmd = f.expensesTbl.Update(msg)
		}
		return f, cmd
	}
	return f, nil
}

func (f *Finances) refreshRows() {
	drows := make([]components.Row, 0, len(f.debts))
	for _, x := range f.debts {
		drows = append(drows, components.Row{
			truncate(orDash(x.Type), 16),
			fmt.Sprintf("$%.2f", x.Balance),
			fmt.Sprintf("%.2f%%", x.APR),
			fmt.Sprintf("$%.2f", x.MonthlyPayment),
			x.Name,
		})
	}
	f.debtsTbl.SetRows(drows)
	irows := make([]components.Row, 0, len(f.incomes))
	for _, x := range f.incomes {
		irows = append(irows, components.Row{
			fmt.Sprintf("$%.2f", x.Amount),
			truncate(orDash(x.Frequency), 12),
			fmt.Sprintf("$%.2f", x.MonthlyAmount),
			x.Name,
		})
	}
	f.incomesTbl.SetRows(irows)
	erows := make([]components.Row, 0, len(f.expenses))
	for _, x := range f.expenses {
		erows = append(erows, components.Row{
			truncate(orDash(x.Category), 16),
			fmt.Sprintf("$%.2f", x.Amount),
			truncate(orDash(x.Frequency), 12),
			fmt.Sprintf("$%.2f", x.MonthlyAmount),
			x.Name,
		})
	}
	f.expensesTbl.SetRows(erows)
}

func (f *Finances) handleKey(m tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch f.mode {
	case financeConfirmDelete:
		if m.String() == "y" {
			return f, f.deleteSelected()
		}
		if m.String() == "n" || m.String() == "esc" {
			f.mode = financeList
		}
		return f, nil
	case financeForm:
		if m.String() == "esc" {
			f.mode = financeList
			f.form = nil
			return f, nil
		}
		if m.String() == "ctrl+s" {
			return f, f.submit()
		}
		ff, cmd := f.form.Update(m)
		if x, ok := ff.(*huh.Form); ok {
			f.form = x
		}
		if f.form.State == huh.StateCompleted {
			return f, f.submit()
		}
		return f, cmd
	}
	switch m.String() {
	case "tab":
		f.tab = (f.tab + 1) % 3
	case "shift+tab":
		f.tab = (f.tab + 2) % 3
	case "n":
		return f, f.startNew()
	case "e":
		return f, f.startEdit()
	case "d":
		if f.tabLen() > 0 {
			f.mode = financeConfirmDelete
		}
	case "r", "ctrl+r":
		return f, f.refresh()
	}
	var cmd tea.Cmd
	switch f.tab {
	case tabDebts:
		f.debtsTbl, cmd = f.debtsTbl.Update(m)
	case tabIncome:
		f.incomesTbl, cmd = f.incomesTbl.Update(m)
	case tabExpenses:
		f.expensesTbl, cmd = f.expensesTbl.Update(m)
	}
	return f, cmd
}

func (f *Finances) tabLen() int {
	switch f.tab {
	case tabDebts:
		return len(f.debts)
	case tabIncome:
		return len(f.incomes)
	case tabExpenses:
		return len(f.expenses)
	}
	return 0
}

func (f *Finances) cursor() int {
	switch f.tab {
	case tabDebts:
		return f.debtsTbl.Cursor()
	case tabIncome:
		return f.incomesTbl.Cursor()
	case tabExpenses:
		return f.expensesTbl.Cursor()
	}
	return 0
}

func (f *Finances) startNew() tea.Cmd {
	f.formIn = financeFormState{frequency: "monthly", debtType: "credit_card", category: "other"}
	f.form = f.newForm()
	f.mode = financeForm
	return f.form.Init()
}

func (f *Finances) startEdit() tea.Cmd {
	idx := f.cursor()
	switch f.tab {
	case tabDebts:
		if idx >= len(f.debts) {
			return nil
		}
		x := f.debts[idx]
		f.formIn = financeFormState{id: x.DebtID, name: x.Name, debtType: x.Type,
			amount: floatStr(x.Balance), apr: floatStr(x.APR),
			monthlyPay: floatStr(x.MonthlyPayment), notes: x.Notes}
	case tabIncome:
		if idx >= len(f.incomes) {
			return nil
		}
		x := f.incomes[idx]
		f.formIn = financeFormState{id: x.IncomeID, name: x.Name,
			amount: floatStr(x.Amount), frequency: x.Frequency, notes: x.Notes}
	case tabExpenses:
		if idx >= len(f.expenses) {
			return nil
		}
		x := f.expenses[idx]
		f.formIn = financeFormState{id: x.ExpenseID, name: x.Name, category: x.Category,
			amount: floatStr(x.Amount), frequency: x.Frequency,
			dueDay: intStr(x.DueDay), notes: x.Notes}
	}
	f.form = f.newForm()
	f.mode = financeForm
	return f.form.Init()
}

func (f *Finances) newForm() *huh.Form {
	d := &f.formIn
	switch f.tab {
	case tabDebts:
		return huh.NewForm(huh.NewGroup(
			huh.NewInput().Title("Name").Value(&d.name).Validate(notEmpty),
			huh.NewSelect[string]().Title("Type").Options(
				huh.NewOption("Credit card", "credit_card"),
				huh.NewOption("Auto loan", "auto_loan"),
				huh.NewOption("Mortgage", "mortgage"),
				huh.NewOption("Student loan", "student_loan"),
				huh.NewOption("Personal loan", "personal_loan"),
				huh.NewOption("Line of credit", "line_of_credit"),
				huh.NewOption("Other", "other"),
			).Value(&d.debtType),
			huh.NewInput().Title("Balance").Value(&d.amount),
			huh.NewInput().Title("APR (%)").Value(&d.apr),
			huh.NewInput().Title("Monthly payment").Value(&d.monthlyPay),
			huh.NewText().Title("Notes").Value(&d.notes).Lines(2),
		))
	case tabIncome:
		return huh.NewForm(huh.NewGroup(
			huh.NewInput().Title("Source").Value(&d.name).Validate(notEmpty),
			huh.NewInput().Title("Amount").Value(&d.amount),
			huh.NewSelect[string]().Title("Frequency").Options(
				huh.NewOption("Monthly", "monthly"),
				huh.NewOption("Biweekly", "biweekly"),
				huh.NewOption("Weekly", "weekly"),
				huh.NewOption("Annual", "annual"),
			).Value(&d.frequency),
			huh.NewText().Title("Notes").Value(&d.notes).Lines(2),
		))
	case tabExpenses:
		return huh.NewForm(huh.NewGroup(
			huh.NewInput().Title("Name").Value(&d.name).Validate(notEmpty),
			huh.NewSelect[string]().Title("Category").Options(
				huh.NewOption("Housing", "housing"),
				huh.NewOption("Utilities", "utilities"),
				huh.NewOption("Subscriptions", "subscriptions"),
				huh.NewOption("Insurance", "insurance"),
				huh.NewOption("Food", "food"),
				huh.NewOption("Transport", "transport"),
				huh.NewOption("Healthcare", "healthcare"),
				huh.NewOption("Other", "other"),
			).Value(&d.category),
			huh.NewInput().Title("Amount").Value(&d.amount),
			huh.NewSelect[string]().Title("Frequency").Options(
				huh.NewOption("Monthly", "monthly"),
				huh.NewOption("Biweekly", "biweekly"),
				huh.NewOption("Weekly", "weekly"),
				huh.NewOption("Annual", "annual"),
			).Value(&d.frequency),
			huh.NewInput().Title("Due day").Value(&d.dueDay),
			huh.NewText().Title("Notes").Value(&d.notes).Lines(2),
		))
	}
	return huh.NewForm()
}

func notEmpty(s string) error {
	if strings.TrimSpace(s) == "" {
		return fmt.Errorf("required")
	}
	return nil
}

func (f *Finances) submit() tea.Cmd {
	d := f.formIn
	c := f.client
	id := d.id
	switch f.tab {
	case tabDebts:
		bal, _ := parseFloat(d.amount)
		apr, _ := parseFloat(d.apr)
		pay, _ := parseFloat(d.monthlyPay)
		in := api.DebtInput{Name: d.name, Type: d.debtType, Balance: bal, APR: apr, MonthlyPayment: pay, Notes: d.notes}
		f.form = nil
		f.mode = financeList
		return func() tea.Msg {
			var err error
			if id == "" {
				_, err = c.CreateDebt(in)
			} else {
				_, err = c.UpdateDebt(id, in)
			}
			return financesMutatedMsg{err: err}
		}
	case tabIncome:
		amt, _ := parseFloat(d.amount)
		in := api.IncomeInput{Name: d.name, Amount: amt, Frequency: d.frequency, Notes: d.notes}
		f.form = nil
		f.mode = financeList
		return func() tea.Msg {
			var err error
			if id == "" {
				_, err = c.CreateIncome(in)
			} else {
				_, err = c.UpdateIncome(id, in)
			}
			return financesMutatedMsg{err: err}
		}
	case tabExpenses:
		amt, _ := parseFloat(d.amount)
		dueDay, _ := parseInt(d.dueDay)
		in := api.FixedExpenseInput{Name: d.name, Category: d.category, Amount: amt, Frequency: d.frequency, DueDay: dueDay, Notes: d.notes}
		f.form = nil
		f.mode = financeList
		return func() tea.Msg {
			var err error
			if id == "" {
				_, err = c.CreateFixedExpense(in)
			} else {
				_, err = c.UpdateFixedExpense(id, in)
			}
			return financesMutatedMsg{err: err}
		}
	}
	return nil
}

func (f *Finances) deleteSelected() tea.Cmd {
	c := f.client
	idx := f.cursor()
	switch f.tab {
	case tabDebts:
		if idx >= len(f.debts) {
			return nil
		}
		id := f.debts[idx].DebtID
		return func() tea.Msg { return financesMutatedMsg{err: c.DeleteDebt(id)} }
	case tabIncome:
		if idx >= len(f.incomes) {
			return nil
		}
		id := f.incomes[idx].IncomeID
		return func() tea.Msg { return financesMutatedMsg{err: c.DeleteIncome(id)} }
	case tabExpenses:
		if idx >= len(f.expenses) {
			return nil
		}
		id := f.expenses[idx].ExpenseID
		return func() tea.Msg { return financesMutatedMsg{err: c.DeleteFixedExpense(id)} }
	}
	return nil
}

func (f *Finances) View() string {
	if f.mode == financeForm {
		if f.form != nil {
			return lipgloss.JoinVertical(lipgloss.Left, f.form.View(), "", components.FormHint())
		}
	}
	if f.mode == financeConfirmDelete {
		return components.ConfirmView("Delete this entry?", f.width, f.height)
	}
	tabs := f.renderTabs()
	summary := f.renderSummary()
	body := f.renderTab()
	return lipgloss.JoinVertical(lipgloss.Left, summary, "", tabs, "", body)
}

func (f *Finances) renderTabs() string {
	names := []string{"Debts", "Income", "Expenses"}
	parts := make([]string, len(names))
	for i, name := range names {
		if int(f.tab) == i {
			parts[i] = styles.PillActive.Render(name)
		} else {
			parts[i] = styles.Pill.Render(name)
		}
	}
	return lipgloss.JoinHorizontal(lipgloss.Top, parts...)
}

func (f *Finances) renderSummary() string {
	rows := []components.SummaryStat{
		{Label: "Income", Value: fmt.Sprintf("$%.2f", f.summary.TotalIncome)},
		{Label: "Outflow", Value: fmt.Sprintf("$%.2f", f.summary.TotalExpenses)},
		{Label: "Net", Value: fmt.Sprintf("$%.2f", f.summary.NetCashFlow)},
		{Label: "Total debt", Value: fmt.Sprintf("$%.2f", f.summary.TotalDebt)},
	}
	return styles.Box.Render(components.SummaryView("Summary", rows))
}

func (f *Finances) renderTab() string {
	width := f.width - 6
	height := f.height - 14
	if height < 5 {
		height = 5
	}
	hints := []string{
		styles.KeyHint("tab", "switch"),
		styles.KeyHint("n", "new"),
		styles.KeyHint("e", "edit"),
		styles.KeyHint("d", "delete"),
	}
	switch f.tab {
	case tabDebts:
		f.debtsTbl.SetColumns(debtCols(width))
		f.debtsTbl.SetHeight(height)
		return components.FrameTable("Debts", len(f.debts), f.debtsTbl, hints, true)
	case tabIncome:
		f.incomesTbl.SetColumns(incomeCols(width))
		f.incomesTbl.SetHeight(height)
		return components.FrameTable("Income", len(f.incomes), f.incomesTbl, hints, true)
	case tabExpenses:
		f.expensesTbl.SetColumns(expenseCols(width))
		f.expensesTbl.SetHeight(height)
		return components.FrameTable("Fixed expenses", len(f.expenses), f.expensesTbl, hints, true)
	}
	return ""
}

func (f *Finances) Title() string { return "Finances" }
func (f *Finances) StatusHints() []string {
	return []string{
		styles.KeyHint("tab", "tab"),
		styles.KeyHint("n", "new"),
		styles.KeyHint("e", "edit"),
		styles.KeyHint("d", "delete"),
	}
}
func (f *Finances) Help() []components.HelpEntry {
	return []components.HelpEntry{
		{Keys: "tab / shift+tab", Desc: "switch debts / income / expenses"},
		{Keys: "↑/↓", Desc: "select row"},
		{Keys: "n", Desc: "new entry"},
		{Keys: "e", Desc: "edit selected"},
		{Keys: "d", Desc: "delete selected"},
		{Keys: "r", Desc: "refresh"},
	}
}
func (f *Finances) SetSize(w, h int) { f.width, f.height = w, h }
