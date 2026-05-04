package api

import "net/url"

type Link struct {
	SourceType string `json:"source_type,omitempty"`
	SourceID   string `json:"source_id,omitempty"`
	TargetType string `json:"target_type,omitempty"`
	TargetID   string `json:"target_id,omitempty"`
	Context    string `json:"context,omitempty"`
}

func (c *Client) OutboundLinks(sourceType, sourceID string) ([]Link, error) {
	q := url.Values{}
	if sourceType != "" {
		q.Set("source_type", sourceType)
	}
	if sourceID != "" {
		q.Set("source_id", sourceID)
	}
	if id := sourceID; id != "" && sourceType == "" {
		q.Set("id", id)
	}
	var out []Link
	return out, c.GetQ("/links", q, &out)
}

func (c *Client) Backlinks(targetType, targetID string) ([]Link, error) {
	q := url.Values{}
	if targetType != "" {
		q.Set("target_type", targetType)
	}
	if targetID != "" {
		q.Set("target_id", targetID)
	}
	if id := targetID; id != "" && targetType == "" {
		q.Set("id", id)
	}
	var out []Link
	return out, c.GetQ("/backlinks", q, &out)
}
