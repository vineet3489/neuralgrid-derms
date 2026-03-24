import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Zap, Eye, EyeOff, AlertCircle, ChevronDown } from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { api } from '../api/client'
import type { Deployment } from '../types'

export default function LoginPage() {
  const navigate = useNavigate()
  const { token, setToken, setUser, setDeployments, setDeployment, currentDeployment } =
    useAuthStore()

  const [email, setEmail] = useState('admin@neuralgrid.com')
  const [password, setPassword] = useState('NeuralGrid2026!')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [deployments, setLocalDeployments] = useState<Deployment[]>([])
  const [selectedDep, setSelectedDep] = useState(currentDeployment || 'ssen')

  // Redirect if already logged in
  useEffect(() => {
    if (token) navigate('/dashboard', { replace: true })
  }, [token, navigate])

  // Load deployments on mount
  useEffect(() => {
    api
      .deployments()
      .then((r) => {
        const deps: Deployment[] = r.data
        setLocalDeployments(deps)
        setDeployments(deps)
        if (deps.length && !deps.find((d) => d.slug === selectedDep)) {
          setSelectedDep(deps[0].slug)
        }
      })
      .catch(() => {
        // Use fallback deployments if API not reachable
        const fallback: Deployment[] = [
          {
            id: 'dep-ssen-001',
            slug: 'ssen',
            name: 'SSEN — Scotland & Northern Isles',
            country: 'UK',
            currency_code: 'GBP',
            timezone: 'Europe/London',
            regulatory_framework: 'ENA-CPP-2024',
            settlement_cycle: 'HALF_HOURLY',
          },
          {
            id: 'dep-puvvnl-001',
            slug: 'puvvnl',
            name: 'PUVVNL — Varanasi Division',
            country: 'India',
            currency_code: 'INR',
            timezone: 'Asia/Kolkata',
            regulatory_framework: 'UPERC-DR-2025',
            settlement_cycle: 'FIFTEEN_MIN',
          },
        ]
        setLocalDeployments(fallback)
        setDeployments(fallback)
      })
  }, [])

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email || !password) {
      setError('Please enter email and password.')
      return
    }
    setLoading(true)
    setError('')
    try {
      setDeployment(selectedDep)
      const res = await api.login(email, password)
      const { access_token, user } = res.data
      setToken(access_token)
      if (user) setUser(user)
      navigate('/dashboard', { replace: true })
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Login failed. Check your credentials.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  const selectedDepData = deployments.find((d) => d.slug === selectedDep)

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      {/* Background grid */}
      <div
        className="fixed inset-0 opacity-5"
        style={{
          backgroundImage:
            'linear-gradient(#4f46e5 1px, transparent 1px), linear-gradient(90deg, #4f46e5 1px, transparent 1px)',
          backgroundSize: '60px 60px',
        }}
      />

      <div className="relative w-full max-w-md">
        {/* Card */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 shadow-2xl">
          {/* Logo */}
          <div className="flex flex-col items-center mb-8">
            <div className="w-14 h-14 bg-indigo-600 rounded-2xl flex items-center justify-center mb-4 shadow-lg shadow-indigo-900/50">
              <Zap className="w-7 h-7 text-white" />
            </div>
            <h1 className="text-2xl font-bold text-white">Neural Grid DERMS</h1>
            <p className="text-sm text-gray-400 mt-1">L&T Digital Energy Solutions</p>
            <div className="mt-2 flex items-center gap-2">
              <div className="h-px w-12 bg-gradient-to-r from-transparent to-indigo-600/50" />
              <span className="text-xs text-indigo-400 font-medium">Distributed Energy Resource Management</span>
              <div className="h-px w-12 bg-gradient-to-l from-transparent to-indigo-600/50" />
            </div>
          </div>

          {/* Form */}
          <form onSubmit={handleLogin} className="space-y-4">
            {/* Deployment selector */}
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">
                Deployment
              </label>
              <div className="relative">
                <select
                  value={selectedDep}
                  onChange={(e) => setSelectedDep(e.target.value)}
                  className="select w-full appearance-none pr-8"
                >
                  {deployments.map((d) => (
                    <option key={d.slug} value={d.slug}>
                      {d.name}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
              </div>
              {selectedDepData && (
                <div className="mt-1.5 flex items-center gap-2 text-xs text-gray-500">
                  <span className="bg-gray-800 px-2 py-0.5 rounded text-gray-400">
                    {selectedDepData.regulatory_framework}
                  </span>
                  <span>{selectedDepData.country}</span>
                  <span>{selectedDepData.currency_code}</span>
                </div>
              )}
            </div>

            {/* Email */}
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">
                Email Address
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input w-full"
                placeholder="admin@neuralgrid.com"
                autoComplete="email"
                required
              />
            </div>

            {/* Password */}
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">
                Password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="input w-full pr-10"
                  placeholder="••••••••••"
                  autoComplete="current-password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-200"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Error message */}
            {error && (
              <div className="flex items-start gap-2 bg-red-900/30 border border-red-800/50 rounded-lg p-3 text-sm text-red-400">
                <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full flex items-center justify-center gap-2 py-3 text-base mt-2"
            >
              {loading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Signing in...
                </>
              ) : (
                'Sign In'
              )}
            </button>
          </form>

          {/* Demo credentials */}
          <div className="mt-5 p-3 bg-gray-800/50 border border-gray-700/50 rounded-lg">
            <div className="text-xs font-medium text-gray-400 mb-2">Demo Credentials</div>
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-500">Email:</span>
                <span className="font-mono text-gray-300">admin@neuralgrid.com</span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-500">Password:</span>
                <span className="font-mono text-gray-300">NeuralGrid2026!</span>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="text-center mt-4 text-xs text-gray-600">
          © 2026 L&T Digital Energy Solutions · Neural Grid DERMS v1.0
        </div>
      </div>
    </div>
  )
}
