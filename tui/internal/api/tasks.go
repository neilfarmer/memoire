package api

import (
	"net/url"
)

type Task struct {
	TaskID          string   `json:"task_id"`
	UserID          string   `json:"user_id,omitempty"`
	Title           string   `json:"title"`
	Description     string   `json:"description,omitempty"`
	Status          string   `json:"status,omitempty"`
	Priority        string   `json:"priority,omitempty"`
	DueDate         string   `json:"due_date,omitempty"`
	Tags            []string `json:"tags,omitempty"`
	ScheduledStart  string   `json:"scheduled_start,omitempty"`
	DurationMinutes int      `json:"duration_minutes,omitempty"`
	Notifications   bool     `json:"notifications,omitempty"`
	RecurrenceRule  any      `json:"recurrence_rule,omitempty"`
	CreatedAt       string   `json:"created_at,omitempty"`
	UpdatedAt       string   `json:"updated_at,omitempty"`
}

type TaskInput struct {
	Title           string   `json:"title,omitempty"`
	Description     string   `json:"description,omitempty"`
	Status          string   `json:"status,omitempty"`
	Priority        string   `json:"priority,omitempty"`
	DueDate         string   `json:"due_date,omitempty"`
	Tags            []string `json:"tags,omitempty"`
	ScheduledStart  string   `json:"scheduled_start,omitempty"`
	DurationMinutes int      `json:"duration_minutes,omitempty"`
	Notifications   *bool    `json:"notifications,omitempty"`
	RecurrenceRule  any      `json:"recurrence_rule,omitempty"`
}

func (c *Client) ListTasks() ([]Task, error) {
	var out []Task
	return out, c.Get("/tasks", &out)
}

func (c *Client) GetTask(id string) (Task, error) {
	var out Task
	return out, c.Get("/tasks/"+url.PathEscape(id), &out)
}

func (c *Client) CreateTask(in TaskInput) (Task, error) {
	var out Task
	return out, c.Post("/tasks", in, &out)
}

func (c *Client) UpdateTask(id string, in TaskInput) (Task, error) {
	var out Task
	return out, c.Put("/tasks/"+url.PathEscape(id), in, &out)
}

func (c *Client) DeleteTask(id string) error {
	return c.Delete("/tasks/" + url.PathEscape(id))
}

func (c *Client) TasksCalendar(from, to string) ([]Task, error) {
	q := url.Values{}
	if from != "" {
		q.Set("from", from)
	}
	if to != "" {
		q.Set("to", to)
	}
	var out []Task
	return out, c.GetQ("/tasks/calendar", q, &out)
}

type AutoScheduleResult struct {
	Scheduled []Task `json:"scheduled"`
	Skipped   []Task `json:"skipped,omitempty"`
}

func (c *Client) AutoScheduleTasks(in map[string]any) (AutoScheduleResult, error) {
	var out AutoScheduleResult
	return out, c.Post("/tasks/auto-schedule", in, &out)
}
