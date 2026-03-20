import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User, Deployment } from '../types'

interface AuthState {
  token: string | null
  user: User | null
  currentDeployment: string
  deployments: Deployment[]
  setToken: (token: string) => void
  setUser: (user: User) => void
  setDeployment: (slug: string) => void
  setDeployments: (deployments: Deployment[]) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      currentDeployment: 'ssen',
      deployments: [],
      setToken: (token) => set({ token }),
      setUser: (user) => set({ user }),
      setDeployment: (slug) => set({ currentDeployment: slug }),
      setDeployments: (deployments) => set({ deployments }),
      logout: () => set({ token: null, user: null }),
    }),
    {
      name: 'neuralgrid-auth',
      partialize: (s) => ({
        token: s.token,
        currentDeployment: s.currentDeployment,
      }),
    }
  )
)
