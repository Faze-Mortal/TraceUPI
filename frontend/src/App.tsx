import { useState } from 'react'
import { Navbar } from './components/Navbar'
import { LandingPage } from './components/LandingPage'
import { DashboardWorkbench } from './components/DashboardWorkbench'
import './App.css'

export function App() {
  const [currentView, setCurrentView] = useState<'landing' | 'dashboard'>('landing')

  return (
    <div className="app-layout">
      <Navbar
        currentView={currentView}
        onNavigate={(view) => {
          setCurrentView(view)
          window.scrollTo({ top: 0, behavior: 'smooth' })
        }}
      />

      {currentView === 'landing' ? (
        <LandingPage
          onOpenDashboard={() => {
            setCurrentView('dashboard')
            window.scrollTo({ top: 0, behavior: 'smooth' })
          }}
        />
      ) : (
        <DashboardWorkbench
          onBackToOverview={() => {
            setCurrentView('landing')
            window.scrollTo({ top: 0, behavior: 'smooth' })
          }}
        />
      )}
    </div>
  )
}

export default App
