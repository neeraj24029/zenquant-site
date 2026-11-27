<p align="center"><img src="zenquant-logo-gold.webp" alt="ZenQuant" width="96"></p>

<h1 align="center">ZenQuant</h1>
<p align="center"><b>Zen in Mind. Quant in Action.</b><br>Risk-first, data-driven algorithmic investing.</p>
<p align="center"><a href="https://www.zenquantllp.com">www.zenquantllp.com</a></p>

---

This repository is the ZenQuant website. It is a single static page served by **GitHub Pages**, and a scheduled **GitHub Action** keeps its market data and featured video up to date.

## What's on the site

| Section | Content | Updates |
| --- | --- | --- |
| Markets | NIFTY 50 and Nasdaq-100 official end-of-day open, close, change, up/down badge, 1-month trend, breadth, top 5 gainers and losers | Automatically, twice a day |
| News | India market headlines, plus a live global feed from TradingView | Headlines automatically; global feed live |
| From our feed | Newest YouTube Short from [@NeerajPriyadarshi](https://www.youtube.com/@NeerajPriyadarshi), plus LinkedIn, Instagram, Facebook and YouTube follow cards | Short automatically |
| Approach, Risk | How decisions are made, risk controls, disclosure | Manually (edit `index.html`) |
| Contact | Telegram, LinkedIn and Instagram message buttons (no email address shown) | Manually |

Market data is end of day and informational only, not investment advice.

## Files

| File | Purpose |
| --- | --- |
| `index.html` | The whole site: layout, styles and scripts |
| `markets.json` | Market data, headlines and newest Short, written by the refresh |
| `markets.js` | Same data as a script, so the page also works when opened from disk |
| `scripts/fetch_markets.py` | The refresh script (Python standard library only) |
| `.github/workflows/markets.yml` | Schedule that runs the refresh |
| `zenquant-logo-gold.webp`, `og-image.png` | Logo/favicon and the 1200×630 link-preview image |
| `robots.txt`, `sitemap.xml` | Search engine guidance |
| `CNAME` | Connects the custom domain. **Do not delete.** |

## Automatic refresh

| Run (IST, approx.) | What it updates |
| --- | --- |
| 19:17 daily | NIFTY 50 close and movers (after NSE publishes its files), headlines, newest Short |
| 08:07 daily | Nasdaq-100 close and movers (after US after-hours trading ends), headlines, newest Short |

- **Sources.**
  - NSE archives: index close file, NIFTY 50 list, bhavcopy.
  - Nasdaq's public data service.
  - Google News RSS.
  - The YouTube channel feed.
  - No keys or logins needed.
- **No live prices.** A market that is trading when a run starts keeps its last close, so live prices are never mixed in.
- **Failures.** If an exchange refuses a request, the run retries. After that, the market keeps its last good data and the other market still updates. The run fails, and GitHub emails the owner, only when both exchanges fail.
- **Staleness guard.** If the data becomes 4 or more days old, the Markets and News sections and the ticker strip hide themselves.
- **Delays.** GitHub may start scheduled runs late. That delays an update but never makes it wrong.

**Manual refresh:** **Actions → Refresh market data → Run workflow**.

## Common edits

- **Text, sections, social links:** edit `index.html` (social links are in the `SOCIAL` list near the end), then commit. The site updates in about 2 minutes.
- **Run the refresh locally:**
  ```
  python scripts/fetch_markets.py
  ```
  Run it from the repository root; it rewrites `markets.json` and `markets.js`.
- **Undo a change:** every update is a separate commit. Revert the one you don't want.

## Brand

Royal blue `#0B4F9E` / `#062F66` with gold `#E4B241`. Gains are green and losses red; gold is never used for prices.
Fonts: Instrument Sans (headings), Inter (text), JetBrains Mono (numbers).

---

© ZenQuant. All rights reserved.
