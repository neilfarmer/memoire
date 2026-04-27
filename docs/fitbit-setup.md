# Fitbit Integration Setup

How to register a Fitbit OAuth2 app and wire its credentials into Memoire so
the Fitbit toggle in Settings works end-to-end.

## 1. Register the Fitbit app

Sign in at <https://dev.fitbit.com/apps/new> and submit the form with the
values below. All non-URL fields can be tuned to taste; the URLs and the
OAuth fields below are the ones the integration depends on.

| Field | Value |
|-------|-------|
| Application Name | `Memoire` |
| Description | Personal productivity dashboard. Pulls daily steps, food, weight, and sleep. |
| Application Website URL | `https://memoire-dev.edenforge.io` (dev) — `https://memoire.edenforge.io` (prod) |
| Organization | Memoire |
| Organization Website URL | same as Application Website URL |
| Terms of Service URL | same as Application Website URL |
| Privacy Policy URL | same as Application Website URL |
| OAuth 2.0 Application Type | **Client** (public client + PKCE; the Memoire backend never sees the user redirect) |
| Redirect URL | `https://memoire-dev.edenforge.io/` (dev) — `https://memoire.edenforge.io/` (prod) |
| Default Access Type | **Read Only** |

Notes:

- Fitbit rejects fragments (`#...`) in redirect URLs, so we register the
  app origin only. The frontend detects the OAuth `?code=...&state=...`
  query string on load and finishes the code exchange.
- HTTP `http://localhost` is accepted by Fitbit during local development.
  Add it as an additional redirect URL only if you run the frontend locally.
- "Health research app" form: not required — Memoire is single-user / self-hosted.

After submitting, copy the **OAuth 2.0 Client ID** and **Client Secret** from
the app detail page.

## 2. memoire-deploy environments

The deployment repo (`memoire-deploy`) hosts two environments. Use the URL
that matches the environment you are wiring up:

| Env | Frontend URL | Redirect URL to register |
|-----|--------------|--------------------------|
| dev | `https://memoire-dev.edenforge.io` | `https://memoire-dev.edenforge.io/` |
| prod | `https://memoire.edenforge.io` | `https://memoire.edenforge.io/` |

Register both redirect URLs on the same Fitbit app if you want one set of
credentials to cover dev and prod, or create two Fitbit apps for stricter
isolation.

## 3. Wire the credentials into Terraform

Add the values to the env's `terraform.tfvars` (in `memoire-deploy`) or
export them before `make deploy-auto`:

```hcl
fitbit_client_id     = "<client-id-from-fitbit>"
fitbit_client_secret = "<client-secret-from-fitbit>"
```

Both variables are declared in `terraform/variables.tf` and passed to the
`fitbit` and `fitbit_sync` Lambdas via environment variables. Leaving
`fitbit_client_id` empty disables the integration server-side — the
`/fitbit/auth/start` endpoint returns 503 in that case.

Apply the change:

```bash
AWS_PROFILE=universe make deploy-auto
```

## 4. Verify

1. Sign in to the deployed frontend.
2. Settings -> Integrations -> toggle **Fitbit** on.
3. Click **Connect Fitbit**, complete the Fitbit consent screen.
4. The browser returns to `/#/fitbit/callback`, the frontend exchanges the
   code, and a "Custom -> Fitbit" item appears in the left nav.
5. Open the Fitbit page. The first scheduled `fitbit_sync` run (every 30
   minutes) will populate steps, food, weight, and sleep. Use **Sync now**
   to trigger an immediate sync.

## 5. Rotating the secret

If you rotate the Fitbit client secret:

1. Update `fitbit_client_secret` in `terraform.tfvars`.
2. `make deploy-auto`.
3. Existing user tokens keep working — the secret is only used for
   `authorization_code` and `refresh_token` exchanges, both of which the
   Lambdas perform with the new value on the next call.
