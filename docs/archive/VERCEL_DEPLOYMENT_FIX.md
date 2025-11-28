# Vercel 404 Deployment Fix

## Problem
You were seeing: `404: NOT_FOUND` with error ID like `cle1::crfrl-1762444890114-b93a175687ab` when visiting https://alphagex.com/

This is a **Vercel deployment configuration issue**, not a Next.js routing issue.

## Root Cause
Your Next.js app is in the `frontend/` subdirectory, but Vercel was trying to deploy from the root directory and couldn't find the app.

## Solution

### Option 1: Use the Root-Level vercel.json (RECOMMENDED)
I've added a `vercel.json` at the root level that tells Vercel how to build your monorepo.

**Steps:**
1. ✅ The root `vercel.json` has been committed to your branch
2. Go to https://vercel.com and log into your project
3. **Redeploy** the branch: `claude/fix-404-not-found-011CUru2gfSPJ4rxoYj4KavB`
4. Wait for the build to complete
5. Visit https://alphagex.com/ - it should work!

### Option 2: Configure Root Directory in Vercel Dashboard (Alternative)
If Option 1 doesn't work, configure Vercel to deploy from the frontend directory:

1. Go to https://vercel.com/dashboard
2. Select your **AlphaGEX** project
3. Go to **Settings** → **General**
4. Find **Root Directory** setting
5. Set it to: `frontend`
6. Click **Save**
7. Go to **Deployments** and redeploy

## What Was Changed

### New File: `/vercel.json` (root level)
```json
{
  "buildCommand": "cd frontend && npm run build",
  "outputDirectory": "frontend/.next",
  "devCommand": "cd frontend && npm run dev",
  "installCommand": "cd frontend && npm install",
  "framework": "nextjs"
}
```

This tells Vercel:
- Change into the `frontend/` directory before building
- Install npm dependencies in `frontend/`
- Build the Next.js app from `frontend/`
- Use `frontend/.next` as the output directory

## Verifying the Fix

After redeploying, you should see:
- ✅ https://alphagex.com/ loads the dashboard
- ✅ All routes work properly
- ✅ No more `cle1::...` error IDs
- ✅ Custom error pages appear if you visit invalid routes

## Troubleshooting

### If you still see 404:
1. **Check build logs** in Vercel dashboard:
   - Look for "Build Command" running: `cd frontend && npm run build`
   - Ensure no npm install errors
   - Verify build completes successfully

2. **Check environment variables**:
   - Go to Vercel Settings → Environment Variables
   - Add `NEXT_PUBLIC_API_URL` if needed
   - Add `NEXT_PUBLIC_WS_URL` if needed

3. **Force a fresh deploy**:
   - In Vercel, go to Deployments
   - Click the three dots on the latest deployment
   - Select "Redeploy"
   - Check "Use existing Build Cache" is **UNCHECKED**

4. **Check Vercel Function Logs**:
   - If you see errors, check the logs in Vercel dashboard
   - Look for any missing dependencies or build failures

## Branch Information
- **Branch**: `claude/fix-404-not-found-011CUru2gfSPJ4rxoYj4KavB`
- **Commits**:
  - `424bd2d` - Added custom error pages
  - `6fd95cf` - Added root-level vercel.json

## Next Steps
1. Merge this branch to `main` once verified
2. Ensure `main` branch auto-deploys to production
3. Set up Vercel Preview deployments for future PRs

## Notes
- The `frontend/vercel.json` file is now redundant (you can delete it later)
- The root `vercel.json` handles all deployment configuration
- Make sure both frontend and backend environment variables are set in Vercel
