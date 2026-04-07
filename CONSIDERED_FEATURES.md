# Considered Features

Features that have been evaluated but not implemented, with context for future reference.

---

## Voice Input via Amazon Transcribe

**Status:** Not implemented — cost/complexity not justified yet  
**Would replace:** Web Speech API (browser-native, currently used)

### Problem with current implementation
The Web Speech API silently fails in some browsers/environments — the mic button pulses but no text appears, with no errors in the console. It depends on Google's speech servers and has inconsistent browser support.

### Proposed approach
1. `MediaRecorder` captures audio in the browser (works in all browsers)
2. User clicks mic to start, clicks again to stop
3. Audio blob POSTed to a new `POST /assistant/transcribe` Lambda endpoint
4. Lambda uploads to S3 (temporary), starts Amazon Transcribe batch job, polls result
5. Text returned and placed in the input box (~1–3s delay after stopping)

**Tradeoffs vs Web Speech API:**
- No real-time interim text while speaking (full result appears after stopping)
- Small processing delay (1–3s)
- Works in every browser, no Google dependency, no silent failures

### Cost estimate (Amazon Transcribe)
- $0.024/minute, billed in 15-second minimums
- Free tier: 60 min/month for first 12 months

| Usage | Monthly cost |
|---|---|
| Single user, ~20 clips/day (~15s each) | ~$3.60/month |
| Single user, year 1 (free tier offset) | ~$2.16/month |
| 10 active users | ~$36/month |

S3 temporary storage: negligible (small audio files deleted immediately after transcription).

**Note:** Amazon Transcribe Streaming would give real-time results but requires a WebSocket proxy through API Gateway — significantly more infrastructure for marginal UX gain.

---

## Integrated Diagramming Tool (Excalidraw)

**Status:** Not implemented — planned  
**Use case:** Architecture diagrams, editable over time

### Plan

Embed [Excalidraw](https://excalidraw.com) via CDN (React + `@excalidraw/excalidraw` UMD build) — no build step required, consistent with the existing vanilla JS app. Adds ~3MB of JS loaded only on the Diagrams page.

**UX:**
- "Diagrams" section in sidebar → dedicated page
- Left panel: list of saved diagrams (name, last updated), "+ New Diagram" button
- Right panel: full Excalidraw canvas
- Manual save button (no auto-save) — user explicitly saves when ready
- No export or sharing needed

**Backend:**
- New DynamoDB table: `diagrams` (`user_id` PK, `diagram_id` SK)
- Attributes: `title`, `elements` (JSON), `app_state` (JSON), `created_at`, `updated_at`
- New Lambda: `lambda/diagrams/` following standard handler/router/crud pattern
- Routes: `GET /diagrams`, `POST /diagrams`, `PUT /diagrams/{id}`, `DELETE /diagrams/{id}`

**Frontend integration:**
```js
// Load via CDN — only on the diagrams page
React.createElement(ExcalidrawLib.Excalidraw, {
  initialData: { elements, appState },
  onChange: (elements, appState) => { /* store in memory until save */ },
})
```

**Data size:** Excalidraw JSON for a typical architecture diagram is 10–100KB — well within DynamoDB's 400KB item limit.

### Tradeoffs
- ~3MB CDN payload (React + Excalidraw) on first load of the page, cached after
- No offline support — requires network to load Excalidraw assets
- No collaboration or sharing (intentional — personal tool only)
