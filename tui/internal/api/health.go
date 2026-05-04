package api

import (
	"net/url"
	"strconv"
)

type HealthFood struct {
	ID         string  `json:"id,omitempty"`
	Name       string  `json:"name"`
	Calories   float64 `json:"calories,omitempty"`
	Amount     float64 `json:"amount,omitempty"`
	Unit       string  `json:"unit,omitempty"`
	MealTypeID string  `json:"meal_type_id,omitempty"`
	Source     string  `json:"source,omitempty"`
}

type HealthExerciseSet struct {
	Reps   int     `json:"reps,omitempty"`
	Weight float64 `json:"weight,omitempty"`
}

type HealthExercise struct {
	Name         string              `json:"name"`
	Type         string              `json:"type,omitempty"`
	Sets         []HealthExerciseSet `json:"sets,omitempty"`
	DurationMin  float64             `json:"duration_min,omitempty"`
	DistanceKm   float64             `json:"distance_km,omitempty"`
	Intensity    float64             `json:"intensity,omitempty"`
	MuscleGroups []string            `json:"muscle_groups,omitempty"`
	Notes        string              `json:"notes,omitempty"`
	Timestamp    string              `json:"timestamp,omitempty"`
}

type HealthLog struct {
	LogDate        string           `json:"log_date"`
	Exercises      []HealthExercise `json:"exercises,omitempty"`
	Foods          []HealthFood     `json:"foods,omitempty"`
	Steps          int              `json:"steps,omitempty"`
	DistanceMi     float64          `json:"distance_mi,omitempty"`
	ActiveMinutes  int              `json:"active_minutes,omitempty"`
	CaloriesOut    float64          `json:"calories_out,omitempty"`
	Weight         float64          `json:"weight,omitempty"`
	Sleep          any              `json:"sleep,omitempty"`
	Notes          string           `json:"notes,omitempty"`
}

type HealthInput struct {
	Exercises     []HealthExercise `json:"exercises,omitempty"`
	Foods         []HealthFood     `json:"foods,omitempty"`
	Steps         *int             `json:"steps,omitempty"`
	DistanceMi    *float64         `json:"distance_mi,omitempty"`
	ActiveMinutes *int             `json:"active_minutes,omitempty"`
	CaloriesOut   *float64         `json:"calories_out,omitempty"`
	Weight        *float64         `json:"weight,omitempty"`
	Sleep         any              `json:"sleep,omitempty"`
	Notes         string           `json:"notes,omitempty"`
}

type HealthSummary map[string]any

type RecentExercise struct {
	Name         string              `json:"name"`
	Type         string              `json:"type,omitempty"`
	MuscleGroups []string            `json:"muscle_groups,omitempty"`
	Sets         []HealthExerciseSet `json:"sets,omitempty"`
	LastDate     string              `json:"last_date,omitempty"`
}

func (c *Client) ListHealthLogs() ([]HealthLog, error) {
	var out []HealthLog
	return out, c.Get("/health", &out)
}

func (c *Client) GetHealthLog(date string) (HealthLog, error) {
	var out HealthLog
	return out, c.Get("/health/"+url.PathEscape(date), &out)
}

func (c *Client) UpsertHealthLog(date string, in HealthInput) (HealthLog, error) {
	var out HealthLog
	return out, c.Put("/health/"+url.PathEscape(date), in, &out)
}

func (c *Client) DeleteHealthLog(date string) error {
	return c.Delete("/health/" + url.PathEscape(date))
}

func (c *Client) GetHealthSummary(days int) (HealthSummary, error) {
	q := url.Values{}
	if days > 0 {
		q.Set("days", strconv.Itoa(days))
	}
	var out HealthSummary
	return out, c.GetQ("/health/summary", q, &out)
}

func (c *Client) RecentExercises(query string, limit int) ([]RecentExercise, error) {
	q := url.Values{}
	if query != "" {
		q.Set("q", query)
	}
	if limit > 0 {
		q.Set("limit", strconv.Itoa(limit))
	}
	var out []RecentExercise
	return out, c.GetQ("/health/exercises/recent", q, &out)
}

func (c *Client) HealthHistory(days int) ([]HealthLog, error) {
	q := url.Values{}
	if days > 0 {
		q.Set("days", strconv.Itoa(days))
	}
	var out []HealthLog
	return out, c.GetQ("/health/history", q, &out)
}

func (c *Client) AddHealthFood(date string, food HealthFood) (HealthLog, error) {
	var out HealthLog
	return out, c.Post("/health/"+url.PathEscape(date)+"/foods", food, &out)
}

func (c *Client) DeleteHealthFood(date, foodID string) (HealthLog, error) {
	var out HealthLog
	return out, c.Do("DELETE", "/health/"+url.PathEscape(date)+"/foods/"+url.PathEscape(foodID), nil, &out)
}

func (c *Client) UpdateHealthTotals(date string, in map[string]any) (HealthLog, error) {
	var out HealthLog
	return out, c.Put("/health/"+url.PathEscape(date)+"/totals", in, &out)
}
