package api

import "net/url"

type Favorite struct {
	FavoriteID  string   `json:"favorite_id"`
	Type        string   `json:"type,omitempty"`
	ResourceID  string   `json:"resource_id,omitempty"`
	URL         string   `json:"url,omitempty"`
	Title       string   `json:"title,omitempty"`
	FeedTitle   string   `json:"feed_title,omitempty"`
	Image       string   `json:"image,omitempty"`
	Description string   `json:"description,omitempty"`
	Published   string   `json:"published,omitempty"`
	Tags        []string `json:"tags,omitempty"`
	CreatedAt   string   `json:"created_at,omitempty"`
}

type FavoriteInput struct {
	Type        string   `json:"type,omitempty"`
	ResourceID  string   `json:"resource_id,omitempty"`
	URL         string   `json:"url,omitempty"`
	Title       string   `json:"title,omitempty"`
	FeedTitle   string   `json:"feed_title,omitempty"`
	Image       string   `json:"image,omitempty"`
	Description string   `json:"description,omitempty"`
	Published   string   `json:"published,omitempty"`
	Tags        []string `json:"tags,omitempty"`
}

func (c *Client) ListFavorites() ([]Favorite, error) {
	var out []Favorite
	return out, c.Get("/favorites", &out)
}

func (c *Client) CreateFavorite(in FavoriteInput) (Favorite, error) {
	var out Favorite
	return out, c.Post("/favorites", in, &out)
}

func (c *Client) UpdateFavoriteTags(id string, tags []string) (Favorite, error) {
	var out Favorite
	return out, c.Patch("/favorites/"+url.PathEscape(id), map[string]any{"tags": tags}, &out)
}

func (c *Client) DeleteFavorite(id string) error {
	return c.Delete("/favorites/" + url.PathEscape(id))
}
