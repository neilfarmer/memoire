package api

type Costs map[string]any
type AdminStats map[string]any

func (c *Client) Costs() (Costs, error) {
	out := Costs{}
	return out, c.Get("/home/costs", &out)
}

func (c *Client) AdminStats() (AdminStats, error) {
	out := AdminStats{}
	return out, c.Get("/admin/stats", &out)
}
