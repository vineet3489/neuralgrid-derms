import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User, Deployment } from '../types'

interface AuthState {
  token: string | null
  user: User | null
  currentDeployment: string
  deployments: Deployment[]
  _hasHydrated: boolean          // ← guards against hydration race on page load
  setToken: (token: string) => void
  setUser: (user: User) => void
  setDeployment: (slug: string) => void
  setDeployments: (deployments: Deployment[]) => void
  setHasHydrated: (v: boolean) => void
  logout: () => void
}

// Fallback deployments so the UI always has something to show
const FALLBACK_DEPLOYMENTS: Deployment[] = [
  {
    id: 'dep-ssen-001',
    slug: 'ssen',
    name: 'SSEN South Scotland',
    country: 'GB',
    currency_code: 'GBP',
    timezone: 'Europe/London',
    regulatory_framework: 'ENA-CPP-2024 / RIIO-ED2',
    settlement_cycle: 'WEEKLY',
  },
  {
    id: 'dep-puvvnl-001',
    slug: 'puvvnl',
    name: 'PUVVNL Varanasi',
    country: 'IN',
    currency_code: 'INR',
    timezone: 'Asia/Kolkata',
    regulatory_framework: 'UPERC-DR-2025',
    settlement_cycle: 'MONTHLY',
  },
]

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      currentDeployment: 'ssen',
      deployments: FALLBACK_DEPLOYMENTS,
      _hasHydrated: false,
      setToken: (token) => set({ token }),
      setUser: (user) => set({ user }),
      setDeployment: (slug) => set({ currentDeployment: slug }),
      setDeployments: (deployments) =>
        set({ deployments: deployments.length > 0 ? deployments : FALLBACK_DEPLOYMENTS }),
      setHasHydrated: (v) => set({ _hasHydrated: v }),
      logout: () => set({ token: null, user: null }),
    }),
    {
      name: 'neuralgrid-auth',
      // Persist token + deployment choice + user across page refreshes
      partialize: (s) => ({
        token: s.token,
        currentDeployment: s.currentDeployment,
        user: s.user,
        deployments: s.deployments,
      }),
      // Called once localStorage has been read — set the hydrated flag
      onRehydrateStorage: () => (state) => {
        if (state) state._hasHydrated = true
      },
    }
  )
)
