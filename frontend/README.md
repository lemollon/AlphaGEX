# AlphaGEX React Frontend

Professional options intelligence platform built with Next.js, TypeScript, and Tailwind CSS.

## 🚀 Quick Start

### Prerequisites
- Node.js 18+ installed
- Backend API running (see `../backend/README.md`)

### Installation

```bash
# Install dependencies
npm install

# Copy environment file
cp .env.local.example .env.local

# Edit .env.local with your API URLs
# For local development:
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000

# For production:
# NEXT_PUBLIC_API_URL=https://alphagex-api.onrender.com
# NEXT_PUBLIC_WS_URL=wss://alphagex-api.onrender.com
```

### Development

```bash
# Start development server
npm run dev

# Open http://localhost:3000
```

### Build for Production

```bash
# Build optimized production bundle
npm run build

# Start production server
npm start
```

## 📁 Project Structure

```
frontend/
├── src/
│   ├── app/                  # Next.js 14 app directory
│   │   ├── layout.tsx       # Root layout
│   │   ├── page.tsx         # Dashboard (home page)
│   │   ├── gex/             # GEX Analysis page
│   │   ├── gamma/           # Gamma Intelligence page
│   │   ├── ai/              # AI Copilot page
│   │   └── trader/          # Autonomous Trader page
│   ├── components/          # Reusable components
│   │   ├── Navigation.tsx   # Top navigation bar
│   │   ├── StatusCard.tsx   # Metric display cards
│   │   └── ...
│   ├── lib/                 # Utilities
│   │   └── api.ts           # API client (axios)
│   └── hooks/               # Custom React hooks
│       └── useWebSocket.ts  # WebSocket connection
├── public/                  # Static assets
├── tailwind.config.ts       # Tailwind configuration
├── next.config.js           # Next.js configuration
└── package.json             # Dependencies
```

## 🎨 Design System

### Colors
- **Background:** Deep navy (#0a0e1a), Card (#141824)
- **Accent:** Blue (#3b82f6)
- **Success:** Green (#10b981) - Long positions, profits
- **Danger:** Red (#ef4444) - Short positions, losses
- **Warning:** Amber (#f59e0b) - Alerts, flip point

### Typography
- **Font:** Inter (sans-serif), JetBrains Mono (numbers)
- **Sizes:** Display (48px), Heading (30px), Body (16px)

### Components
- Cards with hover effects
- Smooth transitions (200ms)
- Real-time data updates
- Loading skeletons

## 🔌 API Integration

### REST API
```typescript
import { apiClient } from '@/lib/api'

// Fetch GEX data
const response = await apiClient.getGEX('SPY')
console.log(response.data)
```

### WebSocket
```typescript
import { useWebSocket } from '@/hooks/useWebSocket'

function MyComponent() {
  const { data, isConnected } = useWebSocket('SPY')

  // data updates automatically every 30 seconds
  return <div>{data?.spot_price}</div>
}
```

## 📊 Features

### Implemented (v1.0)
- ✅ Dashboard with status cards
- ✅ Real-time GEX data display
- ✅ Active positions tracking
- ✅ WebSocket live updates
- ✅ Responsive navigation
- ✅ Dark mode design

### Coming Next
- 🔄 TradingView charts integration
- 🔄 GEX Analysis page with deep dive
- 🔄 Gamma Intelligence (3 views)
- 🔄 AI Copilot chat interface
- 🔄 Autonomous Trader dashboard

## 🚀 Deployment

### Vercel (Recommended)
```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
vercel

# Set environment variables in Vercel dashboard:
# NEXT_PUBLIC_API_URL=https://alphagex-api.onrender.com
# NEXT_PUBLIC_WS_URL=wss://alphagex-api.onrender.com
```

### Docker
```bash
# Build image
docker build -t alphagex-frontend .

# Run container
docker run -p 3000:3000 alphagex-frontend
```

## 🛠️ Tech Stack

- **Framework:** Next.js 14 (App Router)
- **Language:** TypeScript
- **Styling:** Tailwind CSS
- **Charts:** Lightweight Charts (TradingView)
- **UI Components:** Radix UI
- **Icons:** Lucide React
- **HTTP Client:** Axios
- **WebSocket:** Native WebSocket API

## 📝 Development Notes

### Adding a New Page
1. Create `src/app/newpage/page.tsx`
2. Add route to `Navigation.tsx`
3. Create API methods in `src/lib/api.ts` if needed

### Styling Guidelines
- Use Tailwind utility classes
- Follow dark mode color scheme
- Add hover states for interactive elements
- Use custom classes from `globals.css` for common patterns

### Performance
- Pages are server-rendered by default
- Client components use 'use client' directive
- Lazy load heavy components
- Optimize images with Next.js Image component

## 🐛 Troubleshooting

### "Failed to fetch" errors
- Ensure backend API is running
- Check `NEXT_PUBLIC_API_URL` in `.env.local`
- Verify CORS is configured on backend

### WebSocket not connecting
- Check `NEXT_PUBLIC_WS_URL` in `.env.local`
- Ensure WebSocket endpoint is accessible
- Check browser console for errors

### Styles not applying
- Restart dev server after changing Tailwind config
- Clear `.next` folder: `rm -rf .next`
- Check Tailwind class names are correct

## 📚 Resources

- [Next.js Documentation](https://nextjs.org/docs)
- [Tailwind CSS](https://tailwindcss.com/docs)
- [TradingView Lightweight Charts](https://tradingview.github.io/lightweight-charts/)
- [Radix UI](https://www.radix-ui.com/)

---

**Built with ❤️ for professional options traders**
