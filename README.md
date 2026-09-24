# Fenerbahçe football calendar (auto-updating)

Every day, GitHub runs `build_calendar.py` twice. It combines the fixtures from Transfermarkt, ESPN and Sofascore (in that order of trust; each match's source is noted in the event) and rewrites `fenerbahce.ics`.
Kick-off times that aren't announced yet go on **Saturday 19:00** (Hamburg time) of that weekend and are marked **(TBA)**.

## One-time setup (~10 min)

1. Sign in at github.com (create a free account if you need one).
2. Click **+ → New repository**. Name it `fenerbahce-calendar` and set it to **Public** (Apple Calendar needs to read it without a password). Click **Create repository**.
3. On the new repo page, click **uploading an existing file**. Drag in **the contents** of this folder: `build_calendar.py`, `README.md` and the `.github` folder. Then click **Commit changes**.
   - On a Mac, `.github` is hidden. In Finder, press **Cmd + Shift + .** to show it.
   - If the folder doesn't upload, click **Add file → Create new file**, type the name `.github/workflows/update-calendar.yml`, paste in that file's contents, and commit.
4. Go to **Settings → Actions → General → Workflow permissions**, choose **Read and write permissions**, and click **Save**.
5. Open the **Actions** tab, click **Update Fenerbahçe calendar → Run workflow**, and wait about 1 minute for the green tick. `fenerbahce.ics` now appears in the repo.
6. In Apple Calendar, choose **File → New Calendar Subscription…** and paste:

   `webcal://raw.githubusercontent.com/YOUR-GITHUB-NAME/fenerbahce-calendar/main/fenerbahce.ics`

   Set **Auto-refresh** to **Every hour** (or Every day). Set **Location** to **iCloud** so it also syncs to your iPhone.

## Good to know
- If a run fails (a red ✗ in Actions), the old calendar stays as it is. Nothing gets deleted.
- GitHub pauses scheduled runs after 60 days with no changes (for example in the summer break). It emails you when this happens. Click **Enable workflow** in the Actions tab to start it again.
- You can change the settings at the top of `build_calendar.py` (TBA time, match length, 30-min reminder) by editing the file on GitHub.
