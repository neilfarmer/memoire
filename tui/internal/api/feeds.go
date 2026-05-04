package api

import (
	"net/url"
	"strconv"
)

type Feed struct {
	FeedID   string `json:"feed_id"`
	URL      string `json:"url"`
	Title    string `json:"title,omitempty"`
	LastSync string `json:"last_sync,omitempty"`
}

type Article struct {
	GUID       string `json:"guid,omitempty"`
	Title      string `json:"title,omitempty"`
	Link       string `json:"link,omitempty"`
	URL        string `json:"url,omitempty"`
	PubDate    string `json:"pub_date,omitempty"`
	SourceFeed string `json:"source_feed,omitempty"`
	Read       bool   `json:"read,omitempty"`
	Snippet    string `json:"snippet,omitempty"`
	Image      string `json:"image,omitempty"`
}

type ArticleText struct {
	Title string `json:"title,omitempty"`
	URL   string `json:"url,omitempty"`
	Text  string `json:"text"`
}

func (c *Client) ListFeeds() ([]Feed, error) {
	var out []Feed
	return out, c.Get("/feeds", &out)
}

func (c *Client) AddFeed(feedURL string) (Feed, error) {
	var out Feed
	return out, c.Post("/feeds", map[string]string{"url": feedURL}, &out)
}

func (c *Client) DeleteFeed(id string) error {
	return c.Delete("/feeds/" + url.PathEscape(id))
}

func (c *Client) ListFeedArticles(force bool) ([]Article, error) {
	q := url.Values{}
	if force {
		q.Set("force", "true")
	}
	var out []Article
	return out, c.GetQ("/feeds/articles", q, &out)
}

func (c *Client) FeedArticleText(articleURL string) (ArticleText, error) {
	q := url.Values{}
	q.Set("url", articleURL)
	var out ArticleText
	return out, c.GetQ("/feeds/article-text", q, &out)
}

func (c *Client) ReadArticles() ([]string, error) {
	var raw any
	if err := c.Get("/feeds/read", &raw); err != nil {
		return nil, err
	}
	switch v := raw.(type) {
	case []any:
		out := make([]string, 0, len(v))
		for _, item := range v {
			if s, ok := item.(string); ok {
				out = append(out, s)
			}
		}
		return out, nil
	default:
		return nil, nil
	}
}

func (c *Client) MarkArticlesRead(urls []string) (int, error) {
	var out struct {
		MarkedRead int `json:"marked_read"`
	}
	if err := c.Post("/feeds/read", map[string]any{"urls": urls}, &out); err != nil {
		return 0, err
	}
	return out.MarkedRead, nil
}

// FeedURL is a tiny helper for URL composition (currently unused but kept for
// symmetry with notes.AttachmentURL).
func (c *Client) FeedURL() string { return c.BaseURL + "/feeds" }

// ParseLimit is a small helper used by callers when echoing limits in the URL.
func ParseLimit(s string) int {
	n, _ := strconv.Atoi(s)
	return n
}
