package api

import "net/url"

type JournalSummary struct {
	EntryDate    string `json:"entry_date"`
	TitlePreview string `json:"title_preview,omitempty"`
	UpdatedAt    string `json:"updated_at,omitempty"`
}

type JournalEntry struct {
	EntryDate string   `json:"entry_date"`
	Title     string   `json:"title,omitempty"`
	Content   string   `json:"content,omitempty"`
	Body      string   `json:"body,omitempty"`
	Mood      string   `json:"mood,omitempty"`
	Tags      []string `json:"tags,omitempty"`
	UpdatedAt string   `json:"updated_at,omitempty"`
}

type JournalInput struct {
	Title   string   `json:"title,omitempty"`
	Content string   `json:"content,omitempty"`
	Body    string   `json:"body,omitempty"`
	Mood    string   `json:"mood,omitempty"`
	Tags    []string `json:"tags,omitempty"`
}

func (c *Client) ListJournal(query string) ([]JournalSummary, error) {
	q := url.Values{}
	if query != "" {
		q.Set("q", query)
	}
	var out []JournalSummary
	return out, c.GetQ("/journal", q, &out)
}

func (c *Client) GetJournal(date string) (JournalEntry, error) {
	var out JournalEntry
	return out, c.Get("/journal/"+url.PathEscape(date), &out)
}

func (c *Client) UpsertJournal(date string, in JournalInput) (JournalEntry, error) {
	var out JournalEntry
	return out, c.Put("/journal/"+url.PathEscape(date), in, &out)
}

func (c *Client) DeleteJournal(date string) error {
	return c.Delete("/journal/" + url.PathEscape(date))
}
