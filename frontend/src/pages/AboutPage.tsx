import type { AppConfig } from '../types'
import type { UiText } from '../i18n'

interface AboutPageProps {
  config: AppConfig | null
  t: UiText
}

const AboutPage = ({ config, t }: AboutPageProps) => {
  const email = config?.about.contact_email ?? 'support@example.com'

  return (
    <section className="stack-lg">
      <section className="card">
        <p>{t.aboutDescription}</p>
      </section>

      <section className="card stat-grid">
        <article>
          <p className="label">{t.aboutVersion}</p>
          <p className="h1">{config?.about.version ?? '0.1.0'}</p>
        </article>
        <article>
          <p className="label">{t.aboutStatus}</p>
          <p className="h1">{t.aboutStatusValue}</p>
        </article>
      </section>

      <section className="card">
        <p className="label">{t.aboutContact}</p>
        <p>
          {t.aboutWrite} <a href={`mailto:${email}`}>{email}</a>
        </p>
      </section>
    </section>
  )
}

export default AboutPage
