# File Storage

Notes support two types of user-uploaded files: pasted images and file attachments. Both are stored in the frontend S3 bucket (`memoire-dev-frontend`) but served differently.

## S3 Key Structure

```
note-images/      {user_id}/{uuid}.{ext}
note-attachments/ {user_id}/{note_id}/{att_id}/{filename}
```

The bucket is private (CloudFront OAC only). No object is publicly readable.

## Pasted Images

Images pasted into the note editor are uploaded directly from the browser to S3 via a presigned PUT URL.

**Upload flow:**
1. Browser detects image in clipboard paste event
2. `POST /notes/images` → Lambda generates presigned S3 PUT URL (5 min TTL), returns `{upload_url, image_url}`
3. Browser PUTs the file directly to S3
4. `image_url` (the S3 key, e.g. `note-images/{user_id}/{uuid}.png`) is embedded in the note body as `![](note-images/...)`

**Download flow:**
- When a note preview renders, `resolveNoteImages()` finds `<img>` tags whose `src` starts with `note-images/`
- Each image is fetched via `GET /notes/images?key={key}` with the Cognito JWT
- Lambda validates that `user_id` in the key matches the authenticated user, fetches from S3, returns binary
- Browser replaces the `src` with a local blob URL — the S3 path never reaches the browser

**IAM:** Lambda has `s3:PutObject` (upload URL generation) and `s3:GetObject` (serving) on `note-images/*`.

## File Attachments

Files attached via the Attach button follow the same upload pattern but metadata is stored in DynamoDB.

**Upload flow:**
1. Browser opens file picker
2. `POST /notes/{id}/attachments` with `{name, size, type}` → Lambda generates presigned S3 PUT URL, appends attachment record `{id, name, size, type, key, created_at}` to note's `attachments` list in DynamoDB, returns `{upload_url, attachment}`
3. Browser PUTs the file directly to S3

**Download flow:**
- `GET /notes/{id}/attachments/{att_id}` → Lambda looks up attachment by `att_id` in the note record, fetches from S3, returns binary with `Content-Disposition: attachment`
- Browser triggers a local file download via a blob URL — no S3 URL is ever exposed

**IAM:** Lambda has `s3:PutObject` (upload), `s3:GetObject` (download), and `s3:DeleteObject` (delete) on `note-attachments/*`.

## Security Model

- Presigned PUT URLs expire in 5 minutes and are scoped to a specific S3 key
- No presigned GET URLs are used — all downloads go through Lambda, which validates the JWT
- For images, the Lambda validates that the `user_id` component of the S3 key matches the authenticated user
- For attachments, the Lambda validates note ownership via DynamoDB before serving

## Known Limitation

Images pasted before the current security model was implemented were stored as full CloudFront URLs in the note body and remain publicly accessible by URL. See `todo.md` for the planned migration.
