package api

type ExportResponse struct {
	URL string `json:"url"`
}

func (c *Client) Export() (ExportResponse, error) {
	var out ExportResponse
	return out, c.Get("/export", &out)
}
