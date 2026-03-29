# Decision: AI Integration Architecture

## Status
Proposed

## Context

Memoire stores a complete picture of a user's life: tasks, habits, goals, journal entries, notes, health logs, and nutrition logs. All of this data is already structured and per-user. The question is how to add AI capabilities that synthesize across it, without introducing significant operational complexity into what is otherwise a simple serverless stack.

## Decision

Add a single new Lambda (`lambda/ai/`) with two routes:

```
POST /ai/chat      — conversational, full user context, returns complete response
POST /ai/action    — non-conversational, targeted actions (summarize, extract, prompt)
```

Use `claude-sonnet-4-6`. No streaming. No server-side conversation history. No vector embeddings. AI is read-only — it never writes to DynamoDB directly.

## Architecture

### Backend: `lambda/ai/`

Three files mirroring the existing pattern:

**`handler.py`** — extracts JWT sub as `user_id`, parses body, delegates to router.

**`router.py`** — dispatches `POST /ai/chat` and `POST /ai/action` to the appropriate function.

**`context.py`** — the core of the feature. Queries all existing DynamoDB tables and assembles a system prompt. Two tiers:

- **Always included** (~2–3k tokens): active goals with descriptions, open/in-progress tasks with due dates (last 20), today's habits with completion status, last 7 journal entries (date, mood, first 200 chars of body), user's display name from settings.

- **Fetched on demand** based on action type: full journal bodies (reflection queries), note content (summarize/extract), full habit history (streak analysis), nutrition and health logs (health questions).

The `page` field sent from the frontend (which page the user is currently on) is used to weight relevant data higher in the always-included tier.

**`actions.py`** — specific non-chat handlers for inline feature actions. Each receives only the content relevant to that action rather than full user context.

### API Key Management

The Anthropic API key is stored in AWS Secrets Manager. The Lambda fetches it at cold start and caches it in memory for the lifetime of the execution environment. It is never passed to the frontend or logged.

### IAM

The AI Lambda is granted `dynamodb:Query` and `dynamodb:GetItem` on every existing table's ARN. No write permissions. This is a hard architectural boundary: AI observes, users act. Any AI-suggested changes (extracted tasks, new goals) go through the existing frontend modals with explicit user confirmation before hitting the existing CRUD endpoints.

### Terraform

- `terraform/lambda_ai.tf` — Lambda function, CloudWatch log group, API Gateway integration and routes, Lambda permission for API Gateway invocation.
- One IAM inline policy granting read-only access to all existing DynamoDB tables.
- One Secrets Manager secret (`/memoire/anthropic-api-key`) and one IAM permission for `secretsmanager:GetSecretValue`.
- No new DynamoDB table — AI is stateless.

### Frontend: Two Entry Points

**Global chat panel.** A floating button (bottom-right) opens a slide-in panel available on every page. Conversation history is kept in memory only — it resets when the panel is closed or the page is refreshed. Each message includes the message history and the current page name. The panel never stores history server-side.

**Inline actions.** Small contextual buttons per feature that call `/ai/action` with a `type` and specific content:

| Location | Action | Context sent |
|---|---|---|
| Note editor | Summarize | Note title + body |
| Note editor | Extract tasks | Note body |
| Journal editor | Suggest a prompt | Last 7 days of mood + recent activity summary |
| Goals page | Check alignment | Active goals + active tasks + habits |
| Home dashboard | Daily briefing | Compact full context |

**Home dashboard widget.** Renders a 2–3 sentence briefing on the home page. Generated once per calendar day and cached in `localStorage` keyed by date. If the cache is fresh, it renders instantly. If not, it calls `/ai/chat` with a fixed briefing prompt.

## Why Not Streaming

API Gateway HTTP API (which this project uses) buffers Lambda responses before sending them to the client. True server-sent event streaming requires either Lambda Function URLs (bypassing API Gateway, losing JWT auth) or a WebSocket API (significant new infrastructure). For a personal-use app, a 2–3 second wait with a loading state is acceptable. The complexity tradeoff does not justify streaming.

## Why Not Server-Side Conversation History

Storing conversation history in DynamoDB would require a new table, a new IAM policy, additional Lambda logic to fetch and trim history per user, and introduces a persistent record of everything the AI said. Keeping history client-side is simpler, costs nothing, and means there is nothing sensitive to manage. The downside — history lost on refresh — is acceptable for a personal tool.

## Why Not Vector Embeddings / RAG

At personal scale, a user's entire note corpus fits comfortably within Claude's 200k context window. A vector search pipeline (embedding model, vector DB, retrieval logic) would add operational complexity and cost that provides no practical benefit over simply sending the relevant content directly. If note volume grows to the point where context limits become a real constraint, this decision should be revisited.

## Why AI Never Writes Directly

Bypassing the existing CRUD endpoints would create two paths that can diverge: the AI path and the user path. Keeping AI suggestions as read-only recommendations that flow through the existing modals means validation, error handling, and DynamoDB interaction stay in one place. It also keeps the user in control — no action happens without a deliberate confirmation click.

## Phased Rollout

**Phase 1 — Global chat + context builder.** The context builder is the hardest part and the foundation everything else depends on. Chat alone unlocks all cross-cutting queries ("What should I focus on today?", "How was my week?", "What habits support my goals?").

**Phase 2 — Daily briefing widget.** High value, zero interaction required. Validates that the context builder produces useful output.

**Phase 3 — Inline actions.** Note summarize, journal prompt generation, goal alignment check. Each is a thin wrapper around the same infrastructure.

## Cost

Using `claude-sonnet-4-6` at personal scale:

- Compact context (3k tokens) + typical response (400 tokens) ≈ $0.01–0.02 per chat message
- Daily briefing (generated once per day, cached) ≈ $0.01
- Inline actions (smaller context) ≈ <$0.01 each

Effectively free for personal use.

## Consequences

- One new Lambda with read access to all tables — the broadest IAM scope in the project. Acceptable because it is read-only and scoped to the user's own data via the JWT `sub` claim.
- Anthropic API key is a new external dependency that must be rotated if compromised.
- Response latency is 2–5 seconds depending on context size — acceptable for conversational use, less ideal for inline actions where users expect immediacy. A loading state is required in all cases.
- No AI-generated content is persisted, which means the daily briefing must be regenerated if `localStorage` is cleared.
