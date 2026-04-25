import { useEffect, useMemo, useState } from 'react'
import { ToastContainer } from 'react-toastify'
import 'react-toastify/dist/ReactToastify.css'
import { PageType, pageFromPathname, pathnameForPage } from './constants'
import { useAppConfig, useAuth, useChat, useNotes, usePortfolio } from './hooks'
import HomePage from './pages/HomePage'
import ChatPage from './pages/ChatPage'
import PortfolioPage from './pages/PortfolioPage'
import NotesPage from './pages/NotesPage'
import AboutPage from './pages/AboutPage'
import LoginPage from './pages/LoginPage'
import { Lang, UI_TEXT, defaultLang, getStoredLang, setStoredLang } from './i18n'
import logo_full from './logos/logo_full.png'


const App = () => {
  const [currentPage, setCurrentPage] = useState<PageType>(() => (
    typeof window === 'undefined' ? 'home' : pageFromPathname(window.location.pathname)
  ))
  const [lang, setLang] = useState<Lang>(defaultLang)
  const auth = useAuth()
  const { config, loading: configLoading } = useAppConfig()
  const portfolio = usePortfolio()
  const notes = useNotes()
  const chat = useChat()

  useEffect(() => {
    const initialLang = getStoredLang()
    setLang(initialLang)
    document.documentElement.lang = initialLang
  }, [])

  useEffect(() => {
    setStoredLang(lang)
    document.documentElement.lang = lang
  }, [lang])

  useEffect(() => {
    const syncPageFromLocation = () => {
      setCurrentPage(pageFromPathname(window.location.pathname))
    }

    syncPageFromLocation()
    window.addEventListener('popstate', syncPageFromLocation)
    return () => {
      window.removeEventListener('popstate', syncPageFromLocation)
    }
  }, [])

  useEffect(() => {
    const targetPath = pathnameForPage(currentPage)
    if (window.location.pathname === targetPath) {
      return
    }
    window.history.replaceState({}, '', targetPath)
  }, [currentPage])

  useEffect(() => {
    if (auth.isAuthenticated) {
      return
    }
    if (window.location.pathname !== '/') {
      window.history.replaceState({}, '', '/')
    }
    if (currentPage !== 'home') {
      setCurrentPage('home')
    }
  }, [auth.isAuthenticated, currentPage])

  useEffect(() => {
    if (!auth.isAuthenticated) {
      return
    }
    portfolio.fetchPortfolio()
    notes.fetchNotes()
  }, [auth.isAuthenticated])

  const t = UI_TEXT[lang]

  const navItems = useMemo(
    () => [
      { id: 'home' as PageType, label: t.navHome },
      { id: 'chat' as PageType, label: t.navChat },
      { id: 'portfolio' as PageType, label: t.navPortfolio },
      { id: 'notes' as PageType, label: t.navNotes },
      { id: 'about' as PageType, label: t.navAbout },
    ],
    [t],
  )

  const renderPage = () => {
    if (!auth.isAuthenticated) {
      return <LoginPage auth={auth} t={t} />
    }

    switch (currentPage) {
      case 'home':
        return <HomePage t={t} />
      case 'chat':
        return (
          <ChatPage
            chat={chat}
            hasContext={portfolio.assets.length > 0 || notes.notes.length > 0}
            t={t}
            onNavigate={handleNavigate}
          />
        )
      case 'portfolio':
        return <PortfolioPage portfolio={portfolio} config={config} t={t} lang={lang} />
      case 'notes':
        return <NotesPage notes={notes} t={t} lang={lang} />
      case 'about':
        return <AboutPage config={config} t={t} />
      default:
        return <HomePage t={t} />
    }
  }

  const handleNavigate = (page: PageType) => {
    const targetPath = pathnameForPage(page)
    if (window.location.pathname !== targetPath) {
      window.history.pushState({}, '', targetPath)
    }
    setCurrentPage(page)
  }

  return (
    <div className="app-shell">
      <header className="topbar reveal">
        <div className="brand-wrap">
          <img src={logo_full} alt="ЖИТО logo" className="top-logo" />
        </div>

        {auth.isAuthenticated ? (
          <nav className="nav-tabs nav-tabs-center">
            {navItems.map((item) => (
              <button
                key={item.id}
                className={`nav-tab nav-tab-main ${currentPage === item.id ? 'active' : ''}`}
                onClick={() => handleNavigate(item.id)}
                type="button"
              >
                {item.label}
              </button>
            ))}
          </nav>
        ) : <div />}

        <div className="lang-switch" role="group" aria-label="Language switch">
          {auth.isAuthenticated ? (
            <button type="button" className="button-quiet" onClick={auth.logout}>
              {t.authLogout}
            </button>
          ) : null}
          <button type="button" className={`nav-tab lang-tab ${lang === 'en' ? 'active' : ''}`} onClick={() => setLang('en')}>
            EN
          </button>
          <button type="button" className={`nav-tab lang-tab ${lang === 'uk' ? 'active' : ''}`} onClick={() => setLang('uk')}>
            UA
          </button>
        </div>
      </header>

      <main className="page-wrap reveal delayed">
        {configLoading && !config ? <section className="card">{t.loading}</section> : renderPage()}
      </main>

      <ToastContainer position="bottom-right" autoClose={3000} theme="dark" />
    </div>
  )
}

export default App
