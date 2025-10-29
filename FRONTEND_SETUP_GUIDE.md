# AlphaGEX Frontend Setup Guide

## 🚀 Initialize Next.js Frontend

Since we can't run `npm` commands in this environment, **run these commands on your local machine:**

### Step 1: Create Next.js App

```bash
# Navigate to AlphaGEX directory
cd /path/to/AlphaGEX

# Create Next.js app with TypeScript and Tailwind
npx create-next-app@latest frontend --typescript --tailwind --app --no-src-dir --import-alias "@/*"

# Options to select when prompted:
# ✔ Would you like to use TypeScript? … Yes
# ✔ Would you like to use ESLint? … Yes
# ✔ Would you like to use Tailwind CSS? … Yes
# ✔ Would you like to use `src/` directory? … No
# ✔ Would you like to use App Router? … Yes
# ✔ Would you like to customize the default import alias? … Yes (@/*)
```

### Step 2: Install Dependencies

```bash
cd frontend

# UI Components
npm install @radix-ui/react-slot @radix-ui/react-dialog @radix-ui/react-dropdown-menu
npm install @radix-ui/react-tabs @radix-ui/react-toast @radix-ui/react-tooltip
npm install class-variance-authority clsx tailwind-merge
npm install lucide-react  # Icons

# Charts
npm install recharts
npm install lightweight-charts  # TradingView charts (optional)

# State Management & Data Fetching
npm install zustand
npm install @tanstack/react-query
npm install axios

# WebSocket
npm install socket.io-client

# Forms & Validation
npm install react-hook-form
npm install zod @hookform/resolvers

# Utilities
npm install date-fns
npm install numeral
npm install @types/numeral -D

# Development Tools
npm install -D @types/node
```

### Step 3: Initialize shadcn/ui

```bash
# Initialize shadcn/ui
npx shadcn-ui@latest init

# Options to select:
# ✔ Which style would you like to use? › Default
# ✔ Which color would you like to use as base color? › Slate
# ✔ Would you like to use CSS variables for colors? › Yes

# Add initial components
npx shadcn-ui@latest add button
npx shadcn-ui@latest add card
npx shadcn-ui@latest add input
npx shadcn-ui@latest add label
npx shadcn-ui@latest add tabs
npx shadcn-ui@latest add toast
npx shadcn-ui@latest add dialog
npx shadcn-ui@latest add dropdown-menu
npx shadcn-ui@latest add tooltip
```

## 📁 Project Structure

After initialization, your structure should look like:

```
frontend/
├── app/
│   ├── layout.tsx           # Root layout
│   ├── page.tsx             # Home page
│   ├── globals.css          # Global styles
│   ├── dashboard/
│   │   └── page.tsx
│   ├── gex-analysis/
│   │   └── page.tsx
│   └── ... (more pages)
├── components/
│   ├── ui/                  # shadcn components
│   ├── layout/
│   │   ├── Header.tsx
│   │   ├── Sidebar.tsx
│   │   └── Navigation.tsx
│   ├── dashboard/
│   │   ├── StatusBox.tsx
│   │   └── MetricsCard.tsx
│   └── ...
├── lib/
│   ├── api.ts               # API client
│   ├── websocket.ts         # WebSocket client
│   └── utils.ts
├── hooks/
│   ├── useMarketData.ts
│   └── useWebSocket.ts
├── store/
│   └── marketStore.ts       # Zustand store
├── types/
│   └── index.ts
├── public/
├── tailwind.config.ts
├── tsconfig.json
├── next.config.js
├── package.json
└── .env.local
```

## ⚙️ Configuration Files

### 1. Update `tailwind.config.ts`

```typescript
import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: ["class"],
  content: [
    './pages/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './app/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // AlphaGEX Brand Colors
        primary: {
          blue: '#00D4FF',
          green: '#00FF88',
          red: '#FF4444',
          yellow: '#FFB800',
          purple: '#8A2BE2',
        },
        bg: {
          dark: '#0a0e17',
          card: '#141821',
          hover: '#1a1f2e',
        },
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}

export default config
```

### 2. Create `.env.local`

```bash
# API Configuration
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000

# Environment
NEXT_PUBLIC_ENVIRONMENT=development
```

### 3. Update `next.config.js`

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  images: {
    domains: ['alphagex-api.onrender.com'],
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: process.env.NEXT_PUBLIC_API_URL + '/:path*',
      },
    ]
  },
}

module.exports = nextConfig
```

## 🎨 Initial Files to Create

### 1. API Client (`lib/api.ts`)

```typescript
import axios from 'axios';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// GEX Data
export const getGexData = async (symbol: string) => {
  const { data } = await api.get(`/api/gex/${symbol}`);
  return data;
};

// Gamma Intelligence
export const getGammaIntelligence = async (symbol: string, vix?: number) => {
  const { data } = await api.get(`/api/gamma/${symbol}/intelligence`, {
    params: { vix },
  });
  return data;
};

// AI Copilot
export const analyzeMarket = async (payload: {
  symbol: string;
  query: string;
  market_data?: any;
  gamma_intel?: any;
}) => {
  const { data } = await api.post('/api/ai/analyze', payload);
  return data;
};
```

### 2. WebSocket Hook (`hooks/useWebSocket.ts`)

```typescript
import { useEffect, useState } from 'react';

export function useWebSocket(symbol: string) {
  const [data, setData] = useState(null);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';
    const ws = new WebSocket(`${wsUrl}/ws/market-data?symbol=${symbol}`);

    ws.onopen = () => {
      console.log('WebSocket connected');
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      const update = JSON.parse(event.data);
      setData(update.data);
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setIsConnected(false);
    };

    return () => ws.close();
  }, [symbol]);

  return { data, isConnected };
}
```

### 3. Root Layout (`app/layout.tsx`)

```typescript
import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'AlphaGEX - Options Intelligence Platform',
  description: 'Professional Gamma Exposure Analysis and Trading Intelligence',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body className={inter.className}>
        <div className="min-h-screen bg-bg-dark text-white">
          {children}
        </div>
      </body>
    </html>
  )
}
```

### 4. Home Page (`app/page.tsx`)

```typescript
export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24">
      <div className="text-center">
        <h1 className="text-6xl font-bold mb-4 bg-gradient-to-r from-primary-blue to-primary-green bg-clip-text text-transparent">
          AlphaGEX
        </h1>
        <p className="text-xl text-gray-400 mb-8">
          Professional Options Intelligence Platform
        </p>
        <a
          href="/dashboard"
          className="px-6 py-3 bg-primary-blue text-white rounded-lg hover:bg-blue-600 transition"
        >
          Go to Dashboard
        </a>
      </div>
    </main>
  )
}
```

## 🚀 Run Development Server

```bash
cd frontend
npm run dev
```

Visit: http://localhost:3000

## 📦 Production Build

```bash
npm run build
npm start
```

## 🎯 Next Steps

Once frontend is set up:

1. **Test API connection** - Ensure frontend can reach backend at localhost:8000
2. **Build StatusBox component** - Create the 5 status boxes
3. **Build Dashboard page** - Main landing page with metrics
4. **Integrate WebSocket** - Real-time data updates
5. **Build GEX Analysis page** - Critical page with all gamma logic

## 🐛 Troubleshooting

### CORS Errors
- Make sure backend is running (python backend/main.py)
- Check backend ALLOWED_ORIGINS includes http://localhost:3000
- Clear browser cache

### WebSocket Connection Failed
- Verify backend WebSocket endpoint is running
- Check browser console for errors
- Ensure no firewall blocking WebSocket connections

### Type Errors
- Make sure all types are defined in `types/index.ts`
- Run `npm run type-check` to find type issues

## 📚 Resources

- [Next.js Docs](https://nextjs.org/docs)
- [Tailwind CSS Docs](https://tailwindcss.com/docs)
- [shadcn/ui Docs](https://ui.shadcn.com/)
- [React Query Docs](https://tanstack.com/query/latest)
- [Zustand Docs](https://docs.pmnd.rs/zustand)

---

**Ready to build the most professional trading platform! 🚀**
