package api

import (
	"net/url"
	"strconv"
)

type Meal struct {
	Name     string  `json:"name"`
	Calories float64 `json:"calories,omitempty"`
	Protein  float64 `json:"protein,omitempty"`
	Carbs    float64 `json:"carbs,omitempty"`
	Fat      float64 `json:"fat,omitempty"`
	Notes    string  `json:"notes,omitempty"`
}

type NutritionLog struct {
	LogDate string `json:"log_date"`
	Meals   []Meal `json:"meals,omitempty"`
	Notes   string `json:"notes,omitempty"`
}

type NutritionInput struct {
	Meals []Meal `json:"meals,omitempty"`
	Notes string `json:"notes,omitempty"`
}

type NutritionSummary map[string]any

func (c *Client) ListNutritionLogs() ([]NutritionLog, error) {
	var out []NutritionLog
	return out, c.Get("/nutrition", &out)
}

func (c *Client) GetNutritionLog(date string) (NutritionLog, error) {
	var out NutritionLog
	return out, c.Get("/nutrition/"+url.PathEscape(date), &out)
}

func (c *Client) UpsertNutritionLog(date string, in NutritionInput) (NutritionLog, error) {
	var out NutritionLog
	return out, c.Put("/nutrition/"+url.PathEscape(date), in, &out)
}

func (c *Client) DeleteNutritionLog(date string) error {
	return c.Delete("/nutrition/" + url.PathEscape(date))
}

func (c *Client) NutritionSummary(from, to string) (NutritionSummary, error) {
	q := url.Values{}
	if from != "" {
		q.Set("from", from)
	}
	if to != "" {
		q.Set("to", to)
	}
	var out NutritionSummary
	return out, c.GetQ("/nutrition/summary", q, &out)
}

func (c *Client) RecentMeals(query string, limit int) ([]Meal, error) {
	q := url.Values{}
	if query != "" {
		q.Set("q", query)
	}
	if limit > 0 {
		q.Set("limit", strconv.Itoa(limit))
	}
	var out []Meal
	return out, c.GetQ("/nutrition/meals/recent", q, &out)
}
