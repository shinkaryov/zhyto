import React from 'react'

interface NavbarProps {
  toggleSidebar: () => void
}

const Navbar: React.FC<NavbarProps> = ({ toggleSidebar }) => {
  return (
    <nav className="bg-surface border-b border-secondary px-lg py-md flex items-center justify-between">
      <div className="flex items-center gap-md">
        <button
          onClick={toggleSidebar}
          className="p-sm hover:bg-neutral rounded-md transition-colors"
          title="Toggle sidebar"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
        <h1 className="font-display text-2xl text-primary">Ukraine Invest Assistant</h1>
      </div>
      <div className="text-secondary text-sm">v0.1.0</div>
    </nav>
  )
}

export default Navbar

