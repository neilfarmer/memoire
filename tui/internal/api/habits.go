package api

import "net/url"

type HabitHistory struct {
	Date string `json:"date"`
	Done bool   `json:"done"`
}

type Habit struct {
	HabitID       string         `json:"habit_id"`
	Name          string         `json:"name"`
	Description   string         `json:"description,omitempty"`
	Icon          string         `json:"icon,omitempty"`
	Frequency     string         `json:"frequency,omitempty"`
	NotifyTime    string         `json:"notify_time,omitempty"`
	TimeOfDay     string         `json:"time_of_day,omitempty"`
	History       []HabitHistory `json:"history,omitempty"`
	CurrentStreak int            `json:"current_streak,omitempty"`
	BestStreak    int            `json:"best_streak,omitempty"`
	DoneToday     bool           `json:"done_today,omitempty"`
}

type HabitInput struct {
	Name        string `json:"name,omitempty"`
	Description string `json:"description,omitempty"`
	Icon        string `json:"icon,omitempty"`
	Frequency   string `json:"frequency,omitempty"`
	NotifyTime  string `json:"notify_time,omitempty"`
	TimeOfDay   string `json:"time_of_day,omitempty"`
}

func (c *Client) ListHabits() ([]Habit, error) {
	var out []Habit
	return out, c.Get("/habits", &out)
}

func (c *Client) CreateHabit(in HabitInput) (Habit, error) {
	var out Habit
	return out, c.Post("/habits", in, &out)
}

func (c *Client) UpdateHabit(id string, in HabitInput) (Habit, error) {
	var out Habit
	return out, c.Put("/habits/"+url.PathEscape(id), in, &out)
}

func (c *Client) DeleteHabit(id string) error {
	return c.Delete("/habits/" + url.PathEscape(id))
}

type HabitToggleResult struct {
	HabitID string `json:"habit_id"`
	LogDate string `json:"log_date"`
	Done    bool   `json:"done"`
}

func (c *Client) ToggleHabit(id, date string) (HabitToggleResult, error) {
	q := url.Values{}
	if date != "" {
		q.Set("date", date)
	}
	body := map[string]any{}
	if date != "" {
		body["log_date"] = date
	}
	var out HabitToggleResult
	return out, c.DoQuery("POST", "/habits/"+url.PathEscape(id)+"/toggle", q, body, &out)
}
