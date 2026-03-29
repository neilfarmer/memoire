# Cost Analysis

All pricing is **us-east-1** as of mid-2025. Costs assume a single AWS account where Memoire is the primary workload — free tier allowances are applied in full.

---

## Free Tier Summary

Understanding what is permanently free vs. what expires after 12 months matters for long-term cost.

| Service | Free allowance | Expires? |
|---|---|---|
| Lambda | 1M requests/month + 400K GB-seconds/month | Never |
| DynamoDB | 25 GB storage + 25 WCU + 25 RCU (provisioned) | Never |
| CloudFront | 1 TB transfer/month + 10M HTTPS requests/month | Never |
| S3 | 5 GB storage + 20K GET + 2K PUT/month | 12 months only |
| Cognito | 50,000 MAU | Never |
| EventBridge | 14M events/month | Never |
| CloudWatch Logs | 5 GB ingestion/month + 5 GB storage | Never |
| API Gateway HTTP API | None — billed from first request | — |
| Cost Explorer API | None — $0.01 per API call | — |
| DynamoDB PITR | $0.20/GB/month of table data | Never |

The S3 free tier expiring after 12 months is largely irrelevant — at personal scale, the frontend and note attachments will cost under $0.01/month regardless.

---

## Usage Tiers

Three personas are modelled below. Pick the one closest to your actual use.

### Tier 1 — Light (occasional use, 1–2 sessions/week)

**Assumptions:**
- 2 sessions/week, ~15 API calls per session
- 1 home page load per session (1 Cost Explorer call)
- Notes: ~10 notes, no large attachments
- Journal: 2–3 entries/week

**API call volume:** ~120/month

| | Daily | Weekly | Monthly | Yearly |
|---|---|---|---|---|
| Sessions | 0.3 | 2 | 8 | 96 |
| API calls | 4 | 30 | 120 | 1,440 |
| Cost Explorer calls | 0.3 | 2 | 8 | 96 |

| Service | Monthly cost | Notes |
|---|---|---|
| Cost Explorer API | **$0.08** | 8 home page loads × $0.01 |
| API Gateway | <$0.01 | 120 requests × $0.000001 |
| Lambda | $0 | Well within free tier |
| DynamoDB | $0 | Well within free tier |
| CloudFront + S3 | $0 | Within free tier |
| CloudWatch Logs | $0 | Within free tier |
| DynamoDB PITR | ~$0 | <1 MB of table data |
| **Total** | **~$0.08/month** | |

| Period | Cost |
|---|---|
| Daily | ~$0.003 |
| Weekly | ~$0.02 |
| Monthly | ~$0.08 |
| Yearly | **~$1.00** |

---

### Tier 2 — Personal daily (primary daily driver)

**Assumptions:**
- 1–2 sessions/day, ~50 API calls/day
- 1 home page load per day (1 Cost Explorer call)
- Notes: ~50 notes, occasional image attachments (~50 MB total in S3)
- Journal: daily entries
- Habits: 3–5 habits tracked daily
- Pomodoro: used on task days

**API call volume:** ~1,500/month

| | Daily | Weekly | Monthly | Yearly |
|---|---|---|---|---|
| Sessions | 1.5 | 10 | 45 | 540 |
| API calls | 50 | 350 | 1,500 | 18,000 |
| Cost Explorer calls | 1 | 7 | 30 | 365 |

| Service | Monthly cost | Notes |
|---|---|---|
| Cost Explorer API | **$0.30** | 30 home page loads × $0.01 |
| API Gateway | $0.002 | 1,500 × $0.000001 |
| Lambda | $0 | 1,500 invocations, ~100 ms avg at 128 MB = 19.2 GB-s; free tier is 400,000 GB-s |
| DynamoDB reads | $0 | ~3,000 RCUs at $0.25/million = $0.0008 |
| DynamoDB writes | $0 | ~1,500 WCUs at $1.25/million = $0.002 |
| S3 storage (50 MB notes) | $0 | Well within free tier (5 GB/12 months, then $0.023/GB) |
| S3 requests | $0 | Within free tier |
| CloudFront | $0 | Well within free tier |
| CloudWatch Logs | $0 | ~5 MB/month, within free tier |
| DynamoDB PITR | ~$0 | ~5 MB of table data × $0.20/GB = $0.001 |
| **Total** | **~$0.30/month** | |

| Period | Cost |
|---|---|
| Daily | ~$0.01 |
| Weekly | ~$0.07 |
| Monthly | ~$0.30 |
| Yearly | **~$3.65** |

---

### Tier 3 — Power user (heavy notes, attachments, frequent deploys)

**Assumptions:**
- 3+ sessions/day, ~150 API calls/day
- 2 home page loads/day (2 Cost Explorer calls)
- Notes: ~500 notes, significant image attachments (~2 GB total in S3)
- Journal: daily entries, long-form writing
- 50+ deploys/month (active development)
- Health and nutrition logged daily

**API call volume:** ~4,500/month

| | Daily | Weekly | Monthly | Yearly |
|---|---|---|---|---|
| Sessions | 3 | 21 | 90 | 1,080 |
| API calls | 150 | 1,050 | 4,500 | 54,000 |
| Cost Explorer calls | 2 | 14 | 60 | 720 |

| Service | Monthly cost | Notes |
|---|---|---|
| Cost Explorer API | **$0.60** | 60 home page loads × $0.01 |
| API Gateway | $0.005 | 4,500 × $0.000001 |
| Lambda | $0 | 4,500 invocations, still well within free tier |
| DynamoDB reads/writes | $0.01 | ~15,000 ops total |
| S3 storage (2 GB notes, after free tier expires) | $0.05 | 2 GB × $0.023/GB |
| S3 GET requests (note image loads) | $0.01 | ~25,000 GETs × $0.0004/1K |
| S3 PUT requests (uploads) | <$0.01 | ~500 PUTs × $0.005/1K |
| CloudFront | $0 | Within free tier |
| CloudWatch Logs | $0 | ~15 MB/month, within free tier |
| DynamoDB PITR | $0.01 | ~50 MB of table data |
| CloudFront invalidations (50 deploys) | $0 | First 1,000 paths/month free; each `make deploy-auto` = 1 path |
| **Total** | **~$0.70/month** | |

| Period | Cost |
|---|---|
| Daily | ~$0.02 |
| Weekly | ~$0.16 |
| Monthly | ~$0.70 |
| Yearly | **~$8.40** |

---

## Cost Driver Analysis

### Cost Explorer API — the dominant cost

Every load of the home page triggers one `GetCostAndUsage` API call at **$0.01 flat, no free tier**. This is the only service in Memoire that has meaningful cost at personal scale.

| Home loads/day | Monthly cost | Yearly cost |
|---|---|---|
| 0.5 (every other day) | $0.15 | $1.83 |
| 1 | $0.30 | $3.65 |
| 2 | $0.60 | $7.30 |
| 5 | $1.50 | $18.25 |

**Mitigation options (not yet implemented):**
- Cache the Cost Explorer response in DynamoDB with a 1-hour or 24-hour TTL. First load of the day pays $0.01; subsequent loads are free.
- Remove the home dashboard cost widget entirely if cost visibility isn't needed.

### Lambda — effectively free

At personal scale, Lambda compute is never the cost driver. The free tier covers:
- 1,000,000 requests/month
- 400,000 GB-seconds/month

Memoire at Tier 2 uses roughly 1,500 invocations/month at ~100 ms average and 128 MB — consuming about 19 GB-seconds, or **less than 0.005% of the free tier**.

Reserved concurrency (`lambda_max_concurrency = 5`) caps blast radius but does not affect cost. Reserved concurrency itself is free.

### DynamoDB — effectively free

On-demand billing means you pay only for what you use. At Tier 2:
- ~3,000 read request units/month = $0.00075
- ~1,500 write request units/month = $0.001875
- Storage: <5 MB across 10 tables = negligible

PITR (now enabled on all 10 tables) adds $0.20/GB/month of table data. At <10 MB of total data, this rounds to $0.

### S3 — free for 12 months, then minimal

The 5 GB free tier covers the first 12 months. After that, note attachment storage costs $0.023/GB/month. 1 GB of note images = $0.023/month = $0.28/year. The S3 lifecycle rules (90 days → Infrequent Access, 365 days → Glacier IR) reduce this further for older attachments:
- Standard: $0.023/GB/month
- Standard-IA: $0.0125/GB/month (46% cheaper)
- Glacier Instant Retrieval: $0.004/GB/month (83% cheaper)

### API Gateway — negligible

HTTP API pricing is $1.00/million requests. Tier 2 (1,500 requests/month) costs $0.0015/month.

### CloudFront — free

1 TB of data transfer and 10 million HTTPS requests are permanently free. Memoire will never exceed this for a personal deployment.

---

## Yearly Cost Summary

| Tier | Daily | Weekly | Monthly | Yearly |
|---|---|---|---|---|
| Light (2 sessions/week) | ~$0.003 | ~$0.02 | ~$0.08 | **~$1.00** |
| Personal daily | ~$0.01 | ~$0.07 | ~$0.30 | **~$3.65** |
| Power user | ~$0.02 | ~$0.16 | ~$0.70 | **~$8.40** |

In all tiers, Cost Explorer is 85–90% of total spend. Everything else is rounding error.

---

## Cost Optimisation Opportunities

| Optimisation | Effort | Saving |
|---|---|---|
| Cache Cost Explorer response (1h TTL in DynamoDB) | Medium | Up to 90% of total bill |
| Remove home cost widget | Low | Up to 90% of total bill |
| S3 lifecycle rules for note attachments | Done | ~46–83% on attachment storage after year 1 |
| DynamoDB on-demand (vs. provisioned) | Already using on-demand | Correct choice at this scale |
| Lambda reserved concurrency cap | Done | Caps runaway cost from bugs |
| Budget alerts at $10/$20/$30 | Done | Early warning before costs spike |
