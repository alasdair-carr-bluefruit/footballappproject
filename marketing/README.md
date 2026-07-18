# Level — marketing site (apex: keepthingslevel.com)

Static site for the apex domain, **separate from the app** (which lives on
`app.keepthingslevel.com`). Plain HTML/CSS/JS — no build step.

```
marketing/
├── index.html        ← landing (hero, features, video, early-access form)
├── about.html        ← founder / about page
├── style.css         ← Level brand styles
├── main.js           ← early-access form submit + explainer-video swap
├── robots.txt        ← allows all crawlers; points to the sitemap
├── sitemap.xml       ← add each new page/blog post here
├── llms.txt          ← summary for AI answer engines (AIO/GEO)
└── assets/
    ├── brand/        ← logo/lockup (copied from ../assets/brand)
    │   └── og-image.svg ← social-share card SOURCE (export → og-image.png, see SEO below)
    └── explainer.mp4 ← ⬅ DROP YOUR VIDEO HERE (see below)
```

## SEO / AIO
- `index.html` + `about.html` carry canonical, OG and Twitter-card tags; the
  homepage also has `Organization` + `SoftwareApplication` JSON-LD.
- **Share image:** `assets/brand/og-image.png` (1200×630). Source is
  `assets/brand/og-image.svg` — re-export to PNG if you edit the source.
- After deploy, submit `https://keepthingslevel.com/sitemap.xml` to Google Search
  Console and Bing Webmaster Tools.
- Blog posts (see roadmap Phase I) go in `marketing/blog/` as plain HTML — remember
  to add each to `sitemap.xml`.

## The explainer video
Embedded from YouTube (not hosted in the repo — avoids Pages' file-size cap and
git bloat). It's a vertical **Short** in a 9:16 frame, loaded privacy-friendly via
`youtube-nocookie.com`. To swap the video, change the ID in the `.video-embed`
iframe `src` in `index.html` (currently `-lPhWvHGhkU`).

## The early-access form
Posts to **`https://app.keepthingslevel.com/api/early-access`** (the app), which
emails the request to you via Resend.
- Recipient defaults to `alasdair.carr@gmail.com` — override with the app env var
  `EARLY_ACCESS_EMAIL`.
- The email's **reply-to is the submitter**, so replying goes straight back to them.
- A honeypot field drops obvious bots.
- CORS for the apex is already allowed in the app (`MARKETING_ORIGINS`, defaults to
  `https://keepthingslevel.com` + `www`). If you host the site anywhere else first
  (e.g. a `*.pages.dev` preview), add that origin to `MARKETING_ORIGINS` or the
  form will be blocked cross-origin.
- ⚠️ The endpoint ships with the app — **deploy the app first** (it's on
  `feat/multi-user`) or the form will 404 until then.

## Deploy to Cloudflare Pages (recommended — your DNS is already there)
Two options:

**A. Dashboard (Git-connected)**
1. Cloudflare → **Workers & Pages → Create → Pages → Connect to Git** → this repo.
2. Build settings: **Framework preset = None**, **Build command = (blank)**,
   **Build output directory = `marketing`**.
3. Deploy. You'll get a `*.pages.dev` URL to preview.
4. **Custom domains** → add `keepthingslevel.com` and `www.keepthingslevel.com`.
   Because DNS is already in Cloudflare, Pages wires the records and TLS itself
   (apex works natively here — no ALIAS/flattening headache).

**B. CLI (one-off / manual)**
```bash
npx wrangler pages deploy marketing --project-name=level-site
```
then add the custom domains in the dashboard as in A.4.

> Apex note: make sure the apex isn't still pointing at Railway (we detached it
> earlier). Pages will manage the apex + www records once you add them as custom
> domains.
