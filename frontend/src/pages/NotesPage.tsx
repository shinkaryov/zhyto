import { useState } from 'react'
import type { Note } from '../types'
import type { Lang, UiText } from '../i18n'

interface NotesPageProps {
  notes: {
    notes: Note[]
    loading: boolean
    fetchNotes: () => Promise<void>
    addNote: (content: string) => Promise<boolean>
    deleteNote: (id: string) => Promise<boolean>
  }
  t: UiText
  lang: Lang
}

const NotesPage = ({ notes, t, lang }: NotesPageProps) => {
  const [formExpanded, setFormExpanded] = useState(false)
  const [content, setContent] = useState('')
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)

  const addNote = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!content.trim()) {
      return
    }

    const success = await notes.addNote(content.trim())
    if (success) {
      setContent('')
    }
  }

  const requestDeleteNote = (id: string) => {
    setPendingDeleteId((current) => (current === id ? null : id))
  }

  const confirmDeleteNote = async (id: string) => {
    await notes.deleteNote(id)
    setPendingDeleteId(null)
  }

  return (
    <section className="stack-lg">
      <section className="card stack-md">
        <button
          className="button-quiet collapse-trigger"
          type="button"
          onClick={() => setFormExpanded((current) => !current)}
          aria-expanded={formExpanded}
        >
          {formExpanded ? '▼' : '▶'} {t.notesAdd}
        </button>

        {formExpanded ? (
          <form className="stack-md" onSubmit={addNote}>
            <label>
              <span className="label">{t.notesNew}</span>
              <textarea value={content} onChange={(event) => setContent(event.target.value)} rows={5} placeholder={t.notesPlaceholder} />
            </label>
            <div>
              <button className="button-primary" type="submit" disabled={!content.trim() || notes.loading}>{t.notesSave}</button>
            </div>
          </form>
        ) : null}
      </section>

      <section className="stack-md notes-list">
        {notes.notes.length === 0 ? <p className="muted">{t.notesEmpty}</p> : null}
        {notes.notes.map((note) => (
          <article key={note.id} className="note-row">
            <p>{note.content}</p>
            <div className="note-meta">
              <p className="muted">{new Date(note.created_at).toLocaleDateString(lang === 'uk' ? 'uk-UA' : 'en-US')}</p>
              <button className="button-quiet" type="button" onClick={() => requestDeleteNote(note.id)}>{t.delete}</button>
            </div>
            {pendingDeleteId === note.id ? (
              <section className="inline-confirm">
                <p className="muted">{t.confirmDeleteNote}</p>
                <div className="inline-confirm-actions">
                  <button className="button-quiet" type="button" onClick={() => setPendingDeleteId(null)}>{t.cancel}</button>
                  <button className="button-primary" type="button" onClick={() => confirmDeleteNote(note.id)} disabled={notes.loading}>{t.confirm}</button>
                </div>
              </section>
            ) : null}
          </article>
        ))}
      </section>
    </section>
  )
}

export default NotesPage
