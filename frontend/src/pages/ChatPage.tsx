import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import type { UiText } from '../i18n'
import type { PageType } from '../constants'
import type { PendingTransactionDraft } from '../types'

interface ChatPageProps {
  chat: {
    messages: Array<{ role: 'user' | 'assistant'; content: string; sources?: Array<{ index: number; channel: string; url: string; date: string }> }>
    loading: boolean
    savingSummary: boolean
    sendMessage: (message: string) => Promise<unknown>
    finalizeChat: () => Promise<unknown>
    restartChat: () => void
    confirmTransactionDraft: (messageIndex: number) => Promise<boolean>
    cancelTransactionDraft: (messageIndex: number) => void
  }
  hasContext: boolean
  t: UiText
  onNavigate: (page: PageType) => void
}

const INTERNAL_CHAT_LINKS: Record<string, PageType> = {
  '/notes': 'notes',
  '/portfolio': 'portfolio',
}

const normalizeInternalPath = (href: string): string => {
  const normalized = href.split('#')[0].split('?')[0]
  if (normalized.length > 1 && normalized.endsWith('/')) {
    return normalized.slice(0, -1)
  }
  return normalized
}

const ChatPage = ({ chat, hasContext, t, onNavigate }: ChatPageProps) => {
  const [input, setInput] = useState('')
  const [expandedSources, setExpandedSources] = useState<Record<string, boolean>>({})
  const [pendingInlineConfirm, setPendingInlineConfirm] = useState<'restart' | 'finalize' | null>(null)
  const hasUserMessages = chat.messages.some((message) => message.role === 'user')

  useEffect(() => {
    if (!pendingInlineConfirm) {
      return
    }
    const timeoutId = window.setTimeout(() => {
      setPendingInlineConfirm(null)
    }, 3000)
    return () => {
      window.clearTimeout(timeoutId)
    }
  }, [pendingInlineConfirm])

  useEffect(() => {
    if (!pendingInlineConfirm) {
      return
    }

    const handleOutsideClick = (event: MouseEvent) => {
      const target = event.target
      if (!(target instanceof Element)) {
        setPendingInlineConfirm(null)
        return
      }
      if (!target.closest('[data-inline-confirm-action]')) {
        setPendingInlineConfirm(null)
      }
    }

    window.addEventListener('mousedown', handleOutsideClick)
    return () => {
      window.removeEventListener('mousedown', handleOutsideClick)
    }
  }, [pendingInlineConfirm])

  const handleSendMessage = async () => {
    const messageToSend = input.trim()
    if (!messageToSend || chat.loading) {
      return
    }

    setInput('')
    await chat.sendMessage(messageToSend)
  }

  const handleFinishChat = async () => {
    if (chat.loading || chat.savingSummary || !hasUserMessages) {
      return
    }
    if (pendingInlineConfirm !== 'finalize') {
      setPendingInlineConfirm('finalize')
      return
    }
    setPendingInlineConfirm(null)
    await chat.finalizeChat()
  }

  const handleRestartChat = () => {
    if (chat.loading || chat.savingSummary || !chat.messages.length) {
      return
    }
    if (pendingInlineConfirm !== 'restart') {
      setPendingInlineConfirm('restart')
      return
    }
    setPendingInlineConfirm(null)
    chat.restartChat()
  }

  const toggleSources = (messageKey: string) => {
    setExpandedSources((previous) => ({
      ...previous,
      [messageKey]: !previous[messageKey],
    }))
  }

  const markdownComponents: Components = {
    a: ({ href, children, ...props }) => {
      const linkHref = typeof href === 'string' ? href : ''
      const normalizedPath = linkHref.startsWith('/') ? normalizeInternalPath(linkHref) : ''
      const mappedPage = normalizedPath ? INTERNAL_CHAT_LINKS[normalizedPath] : undefined
      const isInternalRoute = !!mappedPage

      return (
        <a
          {...props}
          href={linkHref || '#'}
          className={`chat-inline-link ${props.className ?? ''}`.trim()}
          onClick={(event) => {
            if (isInternalRoute && mappedPage) {
              event.preventDefault()
              onNavigate(mappedPage)
              return
            }
            props.onClick?.(event)
          }}
          target={isInternalRoute ? undefined : '_blank'}
          rel={isInternalRoute ? undefined : 'noreferrer'}
        >
          {children}
        </a>
      )
    },
  }

  const renderDraftSummaryValue = (value: string | number | undefined) => {
    if (value === null || value === undefined || value === '') {
      return '—'
    }
    return String(value)
  }

  const renderDraftCard = (
    draft: PendingTransactionDraft,
    draftStatus: 'pending' | 'submitting' | 'added' | 'cancelled' | 'failed' | undefined,
    messageIndex: number,
  ) => {
    const isSubmitting = draftStatus === 'submitting'
    const isAdded = draftStatus === 'added'
    const isCancelled = draftStatus === 'cancelled'
    const isFailed = draftStatus === 'failed'
    const isLocked = isSubmitting || isAdded || isCancelled

    return (
      <section className="chat-draft-card">
        <p className="label">Чернетка транзакції</p>
        <div className="chat-draft-grid">
          <p><span className="muted">Актив:</span> {renderDraftSummaryValue(draft.asset_type)}</p>
          <p><span className="muted">Кількість:</span> {renderDraftSummaryValue(draft.amount)}</p>
          <p><span className="muted">Валюта:</span> {renderDraftSummaryValue(draft.currency)}</p>
          <p><span className="muted">Тикер:</span> {renderDraftSummaryValue(draft.ticker)}</p>
          <p><span className="muted">Ціна за одиницю:</span> {renderDraftSummaryValue(draft.purchase_price)}</p>
          <p><span className="muted">Загальна сума:</span> {renderDraftSummaryValue(draft.total_value)}</p>
          <p><span className="muted">Дата:</span> {renderDraftSummaryValue(draft.purchase_date)}</p>
        </div>
        {isAdded ? <p className="chat-draft-status-success">Додано успішно</p> : null}
        {isCancelled ? <p className="muted">Додавання скасовано</p> : null}
        {isFailed ? <p className="chat-draft-status-error">Не вдалося додати актив. Перевірте деталі.</p> : null}
        {!isAdded && !isCancelled ? (
          <div className="chat-draft-actions">
            <button
              type="button"
              className="button-primary chat-draft-confirm"
              onClick={() => chat.confirmTransactionDraft(messageIndex)}
              disabled={isLocked}
            >
              {isSubmitting ? 'Збереження...' : 'Підтвердити'}
            </button>
            <button
              type="button"
              className="button-quiet chat-draft-cancel"
              onClick={() => chat.cancelTransactionDraft(messageIndex)}
              disabled={isLocked}
            >
              Скасувати
            </button>
          </div>
        ) : null}
      </section>
    )
  }

  return (
    <section className="stack-lg">
      <header className="card">
        <h1 className="h1">{t.chatTitle}</h1>
        {!hasContext ? <p className="muted">{t.chatNoContext}</p> : null}
      </header>

      <section className="chat-window">
        {chat.messages.map((message, idx) => (
          <article key={`${message.role}-${idx}`} className={`message ${message.role}`}>
            <p className="label">{message.role === 'user' ? t.chatYou : t.chatAssistant}</p>
            <ReactMarkdown components={markdownComponents}>{message.content}</ReactMarkdown>
            {message.pending_transaction_draft ? renderDraftCard(message.pending_transaction_draft, message.draft_status, idx) : null}
            {message.sources && message.sources.length > 0 ? (
              <>
                <button
                  type="button"
                  className="button-quiet sources-toggle"
                  onClick={() => toggleSources(`${message.role}-${idx}`)}
                >
                  {expandedSources[`${message.role}-${idx}`] ? `▼ ${t.chatHideSources}` : `▶ ${t.chatShowSources}`}
                </button>
                {expandedSources[`${message.role}-${idx}`] ? (
                  <div className="sources">
                    {message.sources.map((source) => (
                      <p key={`${source.index}-${source.url}`}>
                        [{source.index}] <a href={source.url} target="_blank" rel="noreferrer">{source.channel}</a> ({source.date})
                      </p>
                    ))}
                  </div>
                ) : null}
              </>
            ) : null}
          </article>
        ))}

        {chat.loading ? <p className="muted">{t.chatGenerating}</p> : null}
      </section>

      <section className="card composer">
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
              event.preventDefault()
              handleSendMessage()
            }
          }}
          rows={4}
          placeholder={t.chatPlaceholder}
          aria-label="Chat input"
        />
        <div className="chat-composer-actions">
          <button type="button" className="button-primary chat-action-btn chat-send-btn" onClick={handleSendMessage} disabled={!input.trim() || chat.loading}>
            {t.chatSend}
          </button>
          <button
            type="button"
            className="button-quiet chat-action-btn chat-finalize-btn"
            onClick={handleRestartChat}
            data-inline-confirm-action="restart"
            disabled={!chat.messages.length || chat.loading || chat.savingSummary}
          >
            {pendingInlineConfirm === 'restart' ? t.chatConfirmInline : t.chatRestart}
          </button>
          <button
            type="button"
            className="button-quiet chat-action-btn chat-finalize-btn"
            onClick={handleFinishChat}
            data-inline-confirm-action="finalize"
            disabled={!hasUserMessages || chat.loading || chat.savingSummary}
          >
            {pendingInlineConfirm === 'finalize'
              ? t.chatConfirmInline
              : (chat.savingSummary ? t.chatSavingSummary : t.chatFinishSave)}
          </button>
        </div>
      </section>
    </section>
  )
}

export default ChatPage
