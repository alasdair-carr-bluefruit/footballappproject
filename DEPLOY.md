# Deploying a Demo Instance

This guide covers setting up a fresh hosted instance of Gaffer using **Neon** (free PostgreSQL database) and **Render** (free web hosting). Both have free tiers that are fine for a single coach.

---

## 1. Set up the database on Neon

1. Go to [neon.tech](https://neon.tech) and create a free account
2. Create a new **Project** — name it anything (e.g. `gaffer`)
3. Once created, go to the project dashboard and find the **Connection String**
   - It looks like: `postgresql://user:password@ep-xxx.eu-west-2.aws.neon.tech/neondb?sslmode=require`
   - Copy it — you'll need it in the next step
   - **Important:** make sure the URL starts with `postgresql://` not `postgres://`

That's all you need from Neon. The app creates its own tables on first launch.

---

## 2. Deploy on Render

1. Go to [render.com](https://render.com) and create a free account
2. Click **New → Web Service**
3. Connect your GitHub account and select the `footballappproject` repository
4. Render will detect the `render.yaml` file automatically — the build and start commands are already configured there
5. Before deploying, add one **Environment Variable**:

   | Key | Value |
   |-----|-------|
   | `DATABASE_URL` | *(paste the Neon connection string from step 1)* |

6. Click **Create Web Service**

Render will build and deploy the app. First deploy takes a few minutes. Once it's live you'll get a URL like `https://gaffer.onrender.com`.

---

## Notes

- **Free tier sleep:** Render's free tier spins down after 15 minutes of inactivity. The first load after a period of no use may take 30–60 seconds to wake up. Paid plans ($7/month) stay awake permanently.
- **Database is shared:** Each Render URL points to one Neon database — one team's data. To give a second coach their own independent instance, repeat both steps with a fresh Neon project and a new Render service.
- **No login required:** The app has no user accounts. Anyone with the URL can use it — treat the URL as the password for now.
- **Data persists:** Data lives in Neon and survives Render redeploys, restarts, and sleep cycles.
