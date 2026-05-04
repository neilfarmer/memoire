package api

import "net/url"

type Bookmark struct {
	BookmarkID   string   `json:"bookmark_id"`
	URL          string   `json:"url"`
	Title        string   `json:"title,omitempty"`
	FaviconURL   string   `json:"favicon_url,omitempty"`
	ThumbnailURL string   `json:"thumbnail_url,omitempty"`
	Tags         []string `json:"tags,omitempty"`
	Note         string   `json:"note,omitempty"`
	Favourited   bool     `json:"favourited,omitempty"`
	CreatedAt    string   `json:"created_at,omitempty"`
}

type BookmarkInput struct {
	URL        string   `json:"url,omitempty"`
	Title      string   `json:"title,omitempty"`
	Tags       []string `json:"tags,omitempty"`
	Note       string   `json:"note,omitempty"`
	Favourited *bool    `json:"favourited,omitempty"`
}

func (c *Client) ListBookmarks(query, tag string) ([]Bookmark, error) {
	q := url.Values{}
	if query != "" {
		q.Set("q", query)
	}
	if tag != "" {
		q.Set("tag", tag)
	}
	var out []Bookmark
	return out, c.GetQ("/bookmarks", q, &out)
}

func (c *Client) GetBookmark(id string) (Bookmark, error) {
	var out Bookmark
	return out, c.Get("/bookmarks/"+url.PathEscape(id), &out)
}

func (c *Client) CreateBookmark(in BookmarkInput) (Bookmark, error) {
	var out Bookmark
	return out, c.Post("/bookmarks", in, &out)
}

func (c *Client) UpdateBookmark(id string, in BookmarkInput) (Bookmark, error) {
	var out Bookmark
	return out, c.Put("/bookmarks/"+url.PathEscape(id), in, &out)
}

func (c *Client) DeleteBookmark(id string) error {
	return c.Delete("/bookmarks/" + url.PathEscape(id))
}
