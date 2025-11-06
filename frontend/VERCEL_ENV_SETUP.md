# Vercel Environment Variables Configuration

## Required Environment Variables

Add these environment variables in your Vercel project settings:

### 1. Go to Vercel Dashboard
- Navigate to your project
- Click "Settings" → "Environment Variables"

### 2. Add These Variables

#### API URL (Required)
- **Name**: `NEXT_PUBLIC_API_URL`
- **Value**: `https://alphagex-api.onrender.com`
- **Environment**: Production, Preview, Development

#### WebSocket URL (Required)
- **Name**: `NEXT_PUBLIC_WS_URL`
- **Value**: `wss://alphagex-api.onrender.com`
- **Environment**: Production, Preview, Development

## How to Add:

1. In Vercel Dashboard, go to: **Project Settings → Environment Variables**
2. Click **"Add New"**
3. Enter variable name (e.g., `NEXT_PUBLIC_API_URL`)
4. Enter value (e.g., `https://alphagex-api.onrender.com`)
5. Select environments: **Production**, **Preview**, **Development**
6. Click **"Save"**
7. Repeat for `NEXT_PUBLIC_WS_URL`

## After Adding Variables:

**IMPORTANT**: You must redeploy for the changes to take effect:
1. Go to "Deployments" tab
2. Click "Redeploy" on the latest deployment
3. Uncheck "Use existing Build Cache"
4. Click "Redeploy"

## Verify Connection:

After redeployment, check the browser console (F12) for:
- ✅ API calls to `https://alphagex-api.onrender.com`
- ✅ WebSocket connections to `wss://alphagex-api.onrender.com`
- ❌ No errors about `localhost:8000`

## Expected Results:

Once configured correctly:
- ✅ GEX Profile chart will load
- ✅ Gamma Intelligence will show data
- ✅ Multi-Symbol Scanner will work
- ✅ SPY price in navigation will update
- ✅ All pages will connect to your Render backend
