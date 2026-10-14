# Deploy the dashboard on Vercel

The dashboard is one static page (index.html) with demo data plus two sample PDF reports.
It contains NO keys or passwords, so it is safe to put online.

## Fastest way (no software needed, about 5 minutes)
1. Go to https://github.com/new and sign in.
2. Repository name: inbox-insights-dashboard. Choose Public or Private, then click "Create repository".
3. Click the link "uploading an existing file".
4. Open this `dashboard` folder on your laptop. Select everything INSIDE it
   (index.html, the reports folder, this file) and drag it into the GitHub page.
5. Click "Commit changes".
6. Go to https://vercel.com/signup, choose "Hobby", then "Continue with GitHub", and allow access.
7. Click "Add New..." then "Project". Next to inbox-insights-dashboard, click "Import".
8. Framework Preset: "Other". Leave everything else as it is. Click "Deploy".
9. Wait about 30 seconds, then click "Continue to Dashboard" and "Visit". Your link looks like
   https://inbox-insights-dashboard.vercel.app

## If your whole project is already on GitHub
1. Put this `dashboard` folder inside your project folder (next to main.py).
2. In GitHub Desktop, commit, then click "Push origin".
3. In Vercel, use Add New, then Project, then Import your project repository.
4. IMPORTANT: next to "Root Directory", click "Edit" and choose `dashboard`. Framework Preset: Other.
5. Click Deploy.

## Changing the page later
Edit index.html, upload it again (or commit and push). Vercel redeploys by itself in about 30 seconds.
