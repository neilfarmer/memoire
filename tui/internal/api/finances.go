package api

import "net/url"

type Debt struct {
	DebtID          string  `json:"debt_id"`
	Name            string  `json:"name"`
	Type            string  `json:"type,omitempty"`
	Balance         float64 `json:"balance,omitempty"`
	APR             float64 `json:"apr,omitempty"`
	MonthlyPayment  float64 `json:"monthly_payment,omitempty"`
	OriginalBalance float64 `json:"original_balance,omitempty"`
	Notes           string  `json:"notes,omitempty"`
	PayoffMonths    int     `json:"payoff_months,omitempty"`
	TotalInterest   float64 `json:"total_interest,omitempty"`
}

type DebtInput struct {
	Name            string  `json:"name,omitempty"`
	Type            string  `json:"type,omitempty"`
	Balance         float64 `json:"balance,omitempty"`
	APR             float64 `json:"apr,omitempty"`
	MonthlyPayment  float64 `json:"monthly_payment,omitempty"`
	OriginalBalance float64 `json:"original_balance,omitempty"`
	Notes           string  `json:"notes,omitempty"`
}

type Income struct {
	IncomeID      string  `json:"income_id"`
	Name          string  `json:"name"`
	Amount        float64 `json:"amount,omitempty"`
	Frequency     string  `json:"frequency,omitempty"`
	MonthlyAmount float64 `json:"monthly_amount,omitempty"`
	Notes         string  `json:"notes,omitempty"`
	StartDate     string  `json:"start_date,omitempty"`
}

type IncomeInput struct {
	Name      string  `json:"name,omitempty"`
	Amount    float64 `json:"amount,omitempty"`
	Frequency string  `json:"frequency,omitempty"`
	Notes     string  `json:"notes,omitempty"`
	StartDate string  `json:"start_date,omitempty"`
}

type FixedExpense struct {
	ExpenseID     string  `json:"expense_id"`
	Name          string  `json:"name,omitempty"`
	Category      string  `json:"category,omitempty"`
	Amount        float64 `json:"amount,omitempty"`
	Frequency     string  `json:"frequency,omitempty"`
	MonthlyAmount float64 `json:"monthly_amount,omitempty"`
	DueDay        int     `json:"due_day,omitempty"`
	Notes         string  `json:"notes,omitempty"`
}

type FixedExpenseInput struct {
	Name      string  `json:"name,omitempty"`
	Category  string  `json:"category,omitempty"`
	Amount    float64 `json:"amount,omitempty"`
	Frequency string  `json:"frequency,omitempty"`
	DueDay    int     `json:"due_day,omitempty"`
	Notes     string  `json:"notes,omitempty"`
}

type FinancesSummary struct {
	TotalIncome   float64 `json:"total_income,omitempty"`
	TotalExpenses float64 `json:"total_expenses,omitempty"`
	TotalDebt     float64 `json:"total_debt,omitempty"`
	NetCashFlow   float64 `json:"net_cash_flow,omitempty"`
	NetWorth      float64 `json:"net_worth,omitempty"`
}

func (c *Client) ListDebts() ([]Debt, error) {
	var out []Debt
	return out, c.Get("/debts", &out)
}
func (c *Client) CreateDebt(in DebtInput) (Debt, error) {
	var out Debt
	return out, c.Post("/debts", in, &out)
}
func (c *Client) UpdateDebt(id string, in DebtInput) (Debt, error) {
	var out Debt
	return out, c.Put("/debts/"+url.PathEscape(id), in, &out)
}
func (c *Client) DeleteDebt(id string) error { return c.Delete("/debts/" + url.PathEscape(id)) }

func (c *Client) ListIncome() ([]Income, error) {
	var out []Income
	return out, c.Get("/income", &out)
}
func (c *Client) CreateIncome(in IncomeInput) (Income, error) {
	var out Income
	return out, c.Post("/income", in, &out)
}
func (c *Client) UpdateIncome(id string, in IncomeInput) (Income, error) {
	var out Income
	return out, c.Put("/income/"+url.PathEscape(id), in, &out)
}
func (c *Client) DeleteIncome(id string) error { return c.Delete("/income/" + url.PathEscape(id)) }

func (c *Client) ListFixedExpenses() ([]FixedExpense, error) {
	var out []FixedExpense
	return out, c.Get("/fixed-expenses", &out)
}
func (c *Client) CreateFixedExpense(in FixedExpenseInput) (FixedExpense, error) {
	var out FixedExpense
	return out, c.Post("/fixed-expenses", in, &out)
}
func (c *Client) UpdateFixedExpense(id string, in FixedExpenseInput) (FixedExpense, error) {
	var out FixedExpense
	return out, c.Put("/fixed-expenses/"+url.PathEscape(id), in, &out)
}
func (c *Client) DeleteFixedExpense(id string) error {
	return c.Delete("/fixed-expenses/" + url.PathEscape(id))
}

func (c *Client) FinancesSummary() (FinancesSummary, error) {
	var out FinancesSummary
	return out, c.Get("/finances/summary", &out)
}
