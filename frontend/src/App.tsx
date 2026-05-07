import { useState, useCallback, useEffect, useRef } from 'react'
import JarvisFinalUI from './components/JarvisFinalUI'
import JarvisDashboard from './components/JarvisDashboard'
import { useJarvisSocket } from './hooks/useJarvisSocket'
import { useAutonomy } from './hooks/useAutonomy'
import './App.css'

export default function App() {
  const { data: jarvisData, connState } = useJarvisSocket()
  const autonomyData = useAutonomy()
  return (
    <div className="app-shell">
      <JarvisFinalUI />
      <JarvisDashboard />
    </div>
  )
}

