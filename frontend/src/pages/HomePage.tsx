import type { UiText } from '../i18n'

interface HomePageProps {
  t: UiText
}

const HomePage = ({ t }: HomePageProps) => {
  const features = [
    { title: t.homeFeature1Title, text: t.homeFeature1Text },
    { title: t.homeFeature2Title, text: t.homeFeature2Text },
    { title: t.homeFeature3Title, text: t.homeFeature3Text },
    { title: t.homeFeature4Title, text: t.homeFeature4Text },
  ]

  return (
    <section className="stack-lg">
      <div className="feature-grid">
        {features.map((feature, index) => (
          <article key={feature.title} className={`card reveal delayed-${(index % 3) + 1}`}>
            <p className="label">{String(index + 1).padStart(2, '0')}</p>
            <h2 className="h1">{feature.title}</h2>
            <p>{feature.text}</p>
          </article>
        ))}
      </div>
    </section>
  )
}

export default HomePage
