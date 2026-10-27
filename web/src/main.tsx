import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { Layout, RouteError } from './components/Layout'
import './index.css'
import { PeriodProvider } from './lib/period'
import { CalendarPage } from './pages/Calendar'
import { CoachPage } from './pages/Coach'
import { DashboardPage } from './pages/Dashboard'
import { InstrumentDetailPage } from './pages/InstrumentDetail'
import { InstrumentsPage } from './pages/Instruments'
import { SettingsPage } from './pages/Settings'
import { TradeDetailPage } from './pages/TradeDetail'
import { TradesPage } from './pages/Trades'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 10_000, refetchOnWindowFocus: true, retry: 1 } },
})

const router = createBrowserRouter([
  {
    element: <Layout />,
    errorElement: (
      <Layout>
        <RouteError />
      </Layout>
    ),
    children: [
      { path: '/', element: <DashboardPage /> },
      { path: '/calendar', element: <CalendarPage /> },
      { path: '/trades', element: <TradesPage /> },
      { path: '/trades/:id', element: <TradeDetailPage /> },
      { path: '/instruments', element: <InstrumentsPage /> },
      { path: '/instruments/:symbol', element: <InstrumentDetailPage /> },
      { path: '/coach', element: <CoachPage /> },
      { path: '/coach/:id', element: <CoachPage /> },
      { path: '/settings', element: <SettingsPage /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <PeriodProvider>
        <RouterProvider router={router} />
      </PeriodProvider>
    </QueryClientProvider>
  </StrictMode>,
)
