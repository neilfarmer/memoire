# Admin Dashboard

The admin dashboard is accessible to users whose `user_id` is listed in the `admin_user_ids` Terraform variable.

## AI / Bedrock Usage

Shows a breakdown of Amazon Bedrock usage across all users.

**Per-user table (7-day and 30-day views):**
- User ID
- Model used
- Number of invocations
- Input tokens
- Output tokens
- Estimated cost (calculated from hardcoded Nova Lite/Pro pricing)

Data is read from each user's `assistant_memory` DynamoDB table (usage counters stored under `__usage__<model_id>` keys). There is no separate admin table — the Lambda queries all users' memory records.
