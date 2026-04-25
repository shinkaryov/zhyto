import React from 'react'

type PageType = 'home' | 'chat' | 'portfolio' | 'notes' | 'about'

interface SidebarProps {
  currentPage: PageType
  setCurrentPage: (page: PageType) => void
  isOpen: boolean
  toggleSidebar: () => void
}

const Sidebar: React.FC<SidebarProps> = ({ currentPage, setCurrentPage, isOpen }) => {
  const pages: { id: PageType; label: string; icon: string }[] = [
    { id: 'home', label: 'Огляд / Overview', icon: '🏠' },
    { id: 'chat', label: 'Радник / Advisor', icon: '💬' },
    { id: 'portfolio', label: 'Портфель / Portfolio', icon: '📊' },
    { id: 'notes', label: 'Нотатки / Notes', icon: '📝' },
    { id: 'about', label: 'Про застосунок / About', icon: 'ℹ️' },
  ]

  if (!isOpen) return null

  return (
    <aside className="w-64 bg-surface border-r border-secondary p-md flex flex-col gap-lg overflow-auto">
      <div>
        <h2 className="font-display text-xl text-primary mb-lg">Навігація / Navigation</h2>
        <nav className="flex flex-col gap-sm">
          {pages.map(page => (
            <button
              key={page.id}
              onClick={() => setCurrentPage(page.id)}
              className={`w-full text-left px-md py-sm rounded-md transition-colors ${
                currentPage === page.id
                  ? 'bg-tertiary text-surface'
                  : 'text-primary hover:bg-neutral'
              }`}
            >
              <span className="mr-md">{page.icon}</span>
              {page.label}
            </button>
          ))}
        </nav>
      </div>
    </aside>
  )
}

export default Sidebar
