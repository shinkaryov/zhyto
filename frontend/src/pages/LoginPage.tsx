import { useEffect, useState, type FormEvent } from 'react'
import { toast } from 'react-toastify'
import type { UiText } from '../i18n'
import type { SecretQuestion } from '../types'

interface LoginPageProps {
  auth: {
    loading: boolean
    login: (email: string, password: string) => Promise<boolean>
    register: (
      email: string,
      password: string,
      confirmPassword: string,
      secretQuestionId: string,
      secretAnswer: string,
    ) => Promise<boolean>
    fetchSecretQuestions: () => Promise<SecretQuestion[]>
    resetPassword: (
      email: string,
      secretQuestionId: string,
      secretAnswer: string,
      newPassword: string,
      confirmPassword: string,
    ) => Promise<boolean>
  }
  t: UiText
}

const LoginPage = ({ auth, t }: LoginPageProps) => {
  const [mode, setMode] = useState<'login' | 'register' | 'reset'>('login')
  const [secretQuestions, setSecretQuestions] = useState<SecretQuestion[]>([])
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [secretQuestionId, setSecretQuestionId] = useState('')
  const [secretAnswer, setSecretAnswer] = useState('')

  useEffect(() => {
    const loadQuestions = async () => {
      const questions = await auth.fetchSecretQuestions()
      setSecretQuestions(questions)
      if (questions.length > 0) {
        setSecretQuestionId((previous) => previous || questions[0].id)
      }
    }
    loadQuestions()
  }, [])

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!email.trim()) {
      return
    }
    if (mode === 'register') {
      if (!password) {
        return
      }
      if (password !== confirmPassword) {
        toast.error(t.authPasswordsMismatch)
        return
      }
      await auth.register(email.trim(), password, confirmPassword, secretQuestionId, secretAnswer)
      return
    }
    if (mode === 'reset') {
      if (!password) {
        return
      }
      if (password !== confirmPassword) {
        toast.error(t.authPasswordsMismatch)
        return
      }
      await auth.resetPassword(email.trim(), secretQuestionId, secretAnswer, password, confirmPassword)
      return
    }
    await auth.login(email.trim(), password)
  }

  const isReset = mode === 'reset'
  const isRegister = mode === 'register'
  const requiresSecretQuestion = isRegister || isReset

  return (
    <section className="stack-lg">
      <header className="card">
        <h1 className="h1">{t.authLoginTitle}</h1>
        <p className="muted">
          {isRegister ? t.authRegisterSubtitle : (isReset ? t.authResetSubtitle : t.authLoginSubtitle)}
        </p>
      </header>

      <form className="card stack-md" onSubmit={handleSubmit}>
        <div className="nav-tabs">
          <button
            type="button"
            className={`nav-tab ${mode === 'login' ? 'active' : ''}`}
            onClick={() => setMode('login')}
          >
            {t.authModeLogin}
          </button>
          <button
            type="button"
            className={`nav-tab ${mode === 'register' ? 'active' : ''}`}
            onClick={() => setMode('register')}
          >
            {t.authModeRegister}
          </button>
          <button
            type="button"
            className={`nav-tab ${mode === 'reset' ? 'active' : ''}`}
            onClick={() => setMode('reset')}
          >
            {t.authModeReset}
          </button>
        </div>

        <label>
          <span className="label">{t.authEmail}</span>
          <input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="email@example.com"
            required
          />
        </label>

        {mode !== 'reset' ? (
          <label>
            <span className="label">{t.authPassword}</span>
            <input
              type="password"
              autoComplete={isRegister ? 'new-password' : 'current-password'}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
        ) : null}

        {isReset ? (
          <label>
            <span className="label">{t.authNewPassword}</span>
            <input
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
        ) : null}

        {(isRegister || isReset) ? (
          <label>
            <span className="label">{t.authConfirmPassword}</span>
            <input
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              required
            />
          </label>
        ) : null}

        {requiresSecretQuestion ? (
          <>
            <label>
              <span className="label">{t.authSecretQuestion}</span>
              <select
                value={secretQuestionId}
                onChange={(event) => setSecretQuestionId(event.target.value)}
                required
              >
                {secretQuestions.map((question) => (
                  <option key={question.id} value={question.id}>
                    {question.question}
                  </option>
                ))}
              </select>
            </label>

            <label>
              <span className="label">{t.authSecretAnswer}</span>
              <input
                type="text"
                value={secretAnswer}
                onChange={(event) => setSecretAnswer(event.target.value)}
                required
              />
            </label>

            <p className="muted">{t.authResetBetaNote}</p>
          </>
        ) : null}

        <button
          type="submit"
          className="button-primary"
          disabled={
            auth.loading
            || !email.trim()
            || !password
            || ((isRegister || isReset) && !confirmPassword)
            || (requiresSecretQuestion && (!secretQuestionId || !secretAnswer.trim()))
          }
        >
          {auth.loading ? `${isRegister ? t.authRegister : (isReset ? t.authReset : t.authLogin)}...` : (
            isRegister ? t.authRegister : (isReset ? t.authReset : t.authLogin)
          )}
        </button>
      </form>
    </section>
  )
}

export default LoginPage
