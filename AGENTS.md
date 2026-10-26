# READ FIRST: this site deploys to VERCEL, not Cloudflare

gaspessential.com is the Vercel project `gasp-essential`. Push or merge to `main` and Vercel builds and serves it (a preview per PR). `api/` holds Vercel functions.
**Do not** run `wrangler`, add a `wrangler.toml`, or set up Cloudflare Workers/Pages builds for this repo. A Cloudflare "Workers Builds: gasp-essential" check on PRs is a stray connection with no config: it fails every time and deploys nothing. Ignore it; Vercel is the only check that matters.
Cloudflare is used only by the lead fleet API (repo `gasp-agency-primary`, folder `fleet-api/`).

Site build rules: see CLAUDE.md.
