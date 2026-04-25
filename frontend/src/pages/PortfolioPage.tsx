import { useMemo, useState } from 'react'
import { getStoredAuthSession } from '../auth'
import type { AppConfig, Asset } from '../types'
import type { Lang, UiText } from '../i18n'
import { getAssetLabel } from '../i18n'
import { toast } from 'react-toastify'

interface PortfolioPageProps {
  config: AppConfig | null
  portfolio: {
    assets: Asset[]
    loading: boolean
    fetchPortfolio: () => Promise<void>
    addAsset: (asset: Omit<Asset, 'id' | 'created_at'>) => Promise<boolean>
    deleteAsset: (assetId: string) => Promise<boolean>
    updateManualCurrentPrice: (assetId: string, manualCurrentPrice: number | null) => Promise<boolean>
  }
  t: UiText
  lang: Lang
}

const DEFAULT_ASSET_TYPES = ['ОВДП', 'Корпоративні облігації', 'Акції (ETF)', 'Криптовалюта', 'Нерухомість', 'Фонди нерухомості (Inzhur, REITs)', 'Земля', 'Готівка', 'Депозит']
const DEFAULT_CURRENCIES = ['UAH', 'USD', 'EUR']
const MS_IN_DAY = 24 * 60 * 60 * 1000
const XIRR_MIN_HOLD_DAYS = 365

const isFiniteNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)

const PortfolioPage = ({ portfolio, config, t, lang }: PortfolioPageProps) => {
  const [formExpanded, setFormExpanded] = useState(false)
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)
  const [editingManualPriceAssetId, setEditingManualPriceAssetId] = useState<string | null>(null)
  const [manualPriceDraft, setManualPriceDraft] = useState('')
  const [totalDisplayCurrency, setTotalDisplayCurrency] = useState<'UAH' | 'USD' | 'EUR'>('UAH')
  const locale = lang === 'uk' ? 'uk-UA' : 'en-US'
  const today = new Date().toISOString().slice(0, 10)
  const assetTypes = config?.asset_types?.length ? config.asset_types : DEFAULT_ASSET_TYPES
  const currencies = config?.currencies?.length ? config.currencies : DEFAULT_CURRENCIES

  const [form, setForm] = useState({
    asset_type: assetTypes[0],
    amount: '',
    currency: currencies[0],
    purchase_price: '',
    purchase_date: today,
    notes: '',
    ticker: '',
    isin: '',
    maturity_date: '',
    yield_percent: '',
  })

  const showYield = useMemo(() => ['ОВДП', 'Корпоративні облігації', 'Депозит', 'Земля', 'Фонди нерухомості (Inzhur, REITs)'].includes(form.asset_type), [form.asset_type])
  const showTicker = useMemo(() => ['Акції (ETF)', 'Криптовалюта', 'Фонди нерухомості (Inzhur, REITs)'].includes(form.asset_type), [form.asset_type])
  const showIsin = useMemo(() => ['ОВДП', 'Корпоративні облігації'].includes(form.asset_type), [form.asset_type])
  const cashLike = useMemo(() => ['Готівка', 'Депозит'].includes(form.asset_type), [form.asset_type])

  const getAssetPurchasePriceByDisplayCurrency = (asset: Asset): number | null => {
    if (totalDisplayCurrency === 'UAH') {
      return isFiniteNumber(asset.purchase_price_uah) ? asset.purchase_price_uah : null
    }
    if (totalDisplayCurrency === 'USD') {
      return isFiniteNumber(asset.purchase_price_usd) ? asset.purchase_price_usd : null
    }
    return isFiniteNumber(asset.purchase_price_eur) ? asset.purchase_price_eur : null
  }

  const getAssetCurrentPriceByDisplayCurrency = (asset: Asset): number | null => {
    if (totalDisplayCurrency === 'UAH') {
      return isFiniteNumber(asset.current_price_uah) ? asset.current_price_uah : null
    }
    if (totalDisplayCurrency === 'USD') {
      return isFiniteNumber(asset.current_price_usd) ? asset.current_price_usd : null
    }
    return isFiniteNumber(asset.current_price_eur) ? asset.current_price_eur : null
  }

  const getAssetCurrentValueByDisplayCurrency = (asset: Asset): number | null => {
    if (totalDisplayCurrency === 'UAH') {
      return isFiniteNumber(asset.current_value_uah) ? asset.current_value_uah : null
    }
    if (totalDisplayCurrency === 'USD') {
      return isFiniteNumber(asset.current_value_usd) ? asset.current_value_usd : null
    }
    return isFiniteNumber(asset.current_value_eur) ? asset.current_value_eur : null
  }

  const getAssetInvestedValueByDisplayCurrency = (asset: Asset): number | null => {
    if (totalDisplayCurrency === 'UAH') {
      return isFiniteNumber(asset.invested_value_uah) ? asset.invested_value_uah : null
    }
    if (totalDisplayCurrency === 'USD') {
      return isFiniteNumber(asset.invested_value_usd) ? asset.invested_value_usd : null
    }
    return isFiniteNumber(asset.invested_value_eur) ? asset.invested_value_eur : null
  }

  const getAssetPnlValueByDisplayCurrency = (asset: Asset): number | null => {
    if (totalDisplayCurrency === 'UAH') {
      return isFiniteNumber(asset.pnl_value_uah) ? asset.pnl_value_uah : null
    }
    if (totalDisplayCurrency === 'USD') {
      return isFiniteNumber(asset.pnl_value_usd) ? asset.pnl_value_usd : null
    }
    return isFiniteNumber(asset.pnl_value_eur) ? asset.pnl_value_eur : null
  }

  const getAssetPnlPercentByDisplayCurrency = (asset: Asset): number | null => {
    if (totalDisplayCurrency === 'UAH') {
      return isFiniteNumber(asset.pnl_percent_uah) ? asset.pnl_percent_uah : null
    }
    if (totalDisplayCurrency === 'USD') {
      return isFiniteNumber(asset.pnl_percent_usd) ? asset.pnl_percent_usd : null
    }
    return isFiniteNumber(asset.pnl_percent_eur) ? asset.pnl_percent_eur : null
  }

  const getAssetCurrentValueNative = (asset: Asset): number | null => {
    if (isFiniteNumber(asset.current_value_original_currency)) {
      return asset.current_value_original_currency
    }
    if (isFiniteNumber(asset.current_value)) {
      return asset.current_value
    }
    return null
  }

  const getAssetPurchaseValueNative = (asset: Asset): number | null => {
    if (!isFiniteNumber(asset.amount) || !isFiniteNumber(asset.purchase_price)) {
      return null
    }
    return asset.amount * asset.purchase_price
  }

  const getHoldingDays = (purchaseDate: string | undefined): number | null => {
    if (!purchaseDate) {
      return null
    }
    const purchaseTimestamp = new Date(purchaseDate).getTime()
    if (!Number.isFinite(purchaseTimestamp)) {
      return null
    }
    const elapsedMs = Date.now() - purchaseTimestamp
    if (elapsedMs <= 0) {
      return null
    }
    return elapsedMs / MS_IN_DAY
  }

  const getAssetXirrPercent = (asset: Asset): number | null => {
    const holdingDays = getHoldingDays(asset.purchase_date)
    if (!isFiniteNumber(holdingDays) || holdingDays < XIRR_MIN_HOLD_DAYS) {
      return null
    }
    const purchaseValue = getAssetInvestedValueByDisplayCurrency(asset)
    const currentValue = getAssetCurrentValueByDisplayCurrency(asset)
    if (!isFiniteNumber(purchaseValue) || !isFiniteNumber(currentValue) || purchaseValue <= 0 || currentValue <= 0) {
      return null
    }
    return (Math.pow(currentValue / purchaseValue, 365 / holdingDays) - 1) * 100
  }

  const totalCurrentValue = useMemo(() => {
    const values = portfolio.assets
      .map((asset) => getAssetCurrentValueByDisplayCurrency(asset))
      .filter((value): value is number => isFiniteNumber(value))

    if (values.length === 0) {
      return null
    }
    return values.reduce((sum, value) => sum + value, 0)
  }, [portfolio.assets, totalDisplayCurrency])

  const formatNumber = (value: number, maximumFractionDigits: number = 2) => (
    new Intl.NumberFormat(locale, {
      maximumFractionDigits,
      minimumFractionDigits: 0,
    }).format(value)
  )

  const formatCurrency = (value: number | null | undefined, currency?: string) => {
    if (!isFiniteNumber(value)) {
      return '—'
    }
    if (currency) {
      try {
        return new Intl.NumberFormat(locale, {
          style: 'currency',
          currency,
          currencyDisplay: 'narrowSymbol',
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        }).format(value)
      } catch {
        return `${formatNumber(value)} ${currency}`
      }
    }
    return formatNumber(value)
  }

  const formatPercent = (value: number | null | undefined) => {
    if (!isFiniteNumber(value)) {
      return '—'
    }
    const absolute = new Intl.NumberFormat(locale, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(Math.abs(value))
    if (value > 0) {
      return `+${absolute}%`
    }
    if (value < 0) {
      return `-${absolute}%`
    }
    return `${absolute}%`
  }

  const formatAnnualizedPercent = (value: number | null | undefined) => {
    if (!isFiniteNumber(value)) {
      return '—'
    }
    const absolute = new Intl.NumberFormat(locale, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(Math.abs(value))
    const suffix = lang === 'uk' ? '%/рік' : '%/yr'
    if (value > 0) {
      return `+${absolute}${suffix}`
    }
    if (value < 0) {
      return `-${absolute}${suffix}`
    }
    return `${absolute}${suffix}`
  }

  const formatPnlAbsoluteAndPercent = (
    absoluteValue: number | null | undefined,
    percentValue: number | null | undefined,
    currency: string | null | undefined,
  ) => {
    if (!isFiniteNumber(absoluteValue)) {
      return '—'
    }
    const sign = absoluteValue > 0 ? '+' : absoluteValue < 0 ? '-' : ''
    const absoluteText = formatCurrency(Math.abs(absoluteValue), currency || undefined)
    const percentText = formatPercent(percentValue)
    if (percentText === '—') {
      return `${sign ? `${sign} ` : ''}${absoluteText}`
    }
    return `${sign ? `${sign} ` : ''}${absoluteText} (${percentText})`
  }

  const shouldShowNativeSubvalue = (asset: Asset) => (
    (asset.currency || '').toUpperCase() !== totalDisplayCurrency
  )

  const getPnlClassName = (value: number | null | undefined) => {
    if (!isFiniteNumber(value) || value === 0) {
      return 'pnl-neutral'
    }
    return value > 0 ? 'pnl-positive' : 'pnl-negative'
  }

  const startManualPriceEdit = (asset: Asset) => {
    setEditingManualPriceAssetId(asset.id)
    if (isFiniteNumber(asset.manual_current_price)) {
      setManualPriceDraft(String(asset.manual_current_price))
      return
    }
    setManualPriceDraft('')
  }

  const cancelManualPriceEdit = () => {
    setEditingManualPriceAssetId(null)
    setManualPriceDraft('')
  }

  const saveManualPriceEdit = async (asset: Asset) => {
    const normalized = manualPriceDraft.trim()
    if (!normalized) {
      const success = await portfolio.updateManualCurrentPrice(asset.id, null)
      if (success) {
        cancelManualPriceEdit()
      }
      return
    }

    const parsed = Number(normalized)
    if (!Number.isFinite(parsed) || parsed < 0) {
      toast.error(t.portfolioManualPriceInvalid)
      return
    }

    const success = await portfolio.updateManualCurrentPrice(asset.id, parsed)
    if (success) {
      cancelManualPriceEdit()
    }
  }

  const updateForm = (field: string, value: string) => {
    setForm((previous) => ({ ...previous, [field]: value }))
  }

  const adjustNumberField = (field: string, delta: number, step: number = 1, min: number = 0) => {
    const currentValue = Number.parseFloat(form[field as keyof typeof form] || '0')
    const current = Number.isFinite(currentValue) ? currentValue : 0
    const next = Math.max(min, current + delta * step)
    const formatted = Number.isInteger(next) ? String(next) : String(Number(next.toFixed(4)))
    updateForm(field, formatted)
  }

  const submitAsset = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!form.purchase_date || form.purchase_date > today) {
      toast.error(t.portfolioDateFutureError)
      return
    }
    if (form.maturity_date && form.maturity_date < form.purchase_date) {
      toast.error(t.portfolioMaturityBeforeBuyError)
      return
    }

    const payload: Omit<Asset, 'id' | 'created_at'> = {
      user_id: getStoredAuthSession()?.userId ?? '',
      asset_type: form.asset_type,
      amount: Number(form.amount),
      currency: form.currency,
      purchase_price: cashLike ? 1 : Number(form.purchase_price),
      purchase_date: form.purchase_date,
      notes: form.notes || undefined,
      ticker: form.ticker || undefined,
      isin: form.isin || undefined,
      maturity_date: form.maturity_date || undefined,
      yield_percent: form.yield_percent ? Number(form.yield_percent) : undefined,
    }

    const success = await portfolio.addAsset(payload)
    if (!success) {
      return
    }
    setForm({
      asset_type: assetTypes[0],
      amount: '',
      currency: currencies[0],
      purchase_price: '',
      purchase_date: today,
      notes: '',
      ticker: '',
      isin: '',
      maturity_date: '',
      yield_percent: '',
    })
  }

  const requestDeleteAsset = (id: string) => {
    setPendingDeleteId((current) => (current === id ? null : id))
  }

  const confirmDeleteAsset = async (id: string) => {
    await portfolio.deleteAsset(id)
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
          {formExpanded ? '▼' : '▶'} {t.portfolioAdd}
        </button>

        {formExpanded ? (
          <form className="form-grid" onSubmit={submitAsset}>
            <label>
              <span className="label">{t.portfolioAssetType}</span>
              <div className="select-shell">
                <select value={form.asset_type} onChange={(event) => updateForm('asset_type', event.target.value)}>
                  {assetTypes.map((item) => (
                    <option key={item} value={item}>{getAssetLabel(item, lang)}</option>
                  ))}
                </select>
                <span className="select-arrow" aria-hidden="true">⌄</span>
              </div>
            </label>

            <label>
              <span className="label">{t.portfolioCurrency}</span>
              <div className="select-shell">
                <select value={form.currency} onChange={(event) => updateForm('currency', event.target.value)}>
                  {currencies.map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </select>
                <span className="select-arrow" aria-hidden="true">⌄</span>
              </div>
            </label>

            <label>
              <span className="label">{cashLike ? t.portfolioSum : t.portfolioQuantity}</span>
              <div className="stepper">
                <input required type="number" min="0" step="any" value={form.amount} onChange={(event) => updateForm('amount', event.target.value)} />
                <div className="stepper-controls">
                  <button type="button" className="stepper-button" onClick={() => adjustNumberField('amount', 1, 1, 0)} aria-label="Increase amount">+</button>
                  <button type="button" className="stepper-button" onClick={() => adjustNumberField('amount', -1, 1, 0)} aria-label="Decrease amount">-</button>
                </div>
              </div>
            </label>

            {!cashLike ? (
              <label>
                <span className="label">{t.portfolioPricePerUnit}</span>
                <div className="stepper">
                  <input type="number" min="0" step="any" value={form.purchase_price} onChange={(event) => updateForm('purchase_price', event.target.value)} />
                  <div className="stepper-controls">
                    <button type="button" className="stepper-button" onClick={() => adjustNumberField('purchase_price', 1, 1, 0)} aria-label="Increase price">+</button>
                    <button type="button" className="stepper-button" onClick={() => adjustNumberField('purchase_price', -1, 1, 0)} aria-label="Decrease price">-</button>
                  </div>
                </div>
              </label>
            ) : null}

            <label>
              <span className="label">{t.portfolioDate}</span>
              <input type="date" max={today} value={form.purchase_date} onChange={(event) => updateForm('purchase_date', event.target.value)} />
            </label>

            <label>
              <span className="label">{t.portfolioComment}</span>
              <input type="text" value={form.notes} onChange={(event) => updateForm('notes', event.target.value)} />
            </label>

            {showYield ? (
              <label>
                <span className="label">{t.portfolioYield}</span>
                <div className="stepper">
                  <input type="number" min="0" step="any" value={form.yield_percent} onChange={(event) => updateForm('yield_percent', event.target.value)} />
                  <div className="stepper-controls">
                    <button type="button" className="stepper-button" onClick={() => adjustNumberField('yield_percent', 1, 0.5, 0)} aria-label="Increase yield">+</button>
                    <button type="button" className="stepper-button" onClick={() => adjustNumberField('yield_percent', -1, 0.5, 0)} aria-label="Decrease yield">-</button>
                  </div>
                </div>
              </label>
            ) : null}

            {showTicker ? (
              <label>
                <span className="label">{t.portfolioTicker}</span>
                <input type="text" value={form.ticker} onChange={(event) => updateForm('ticker', event.target.value)} />
              </label>
            ) : null}

            {showIsin ? (
              <label>
                <span className="label">{t.portfolioIsin}</span>
                <input type="text" value={form.isin} onChange={(event) => updateForm('isin', event.target.value)} />
              </label>
            ) : null}

            {showIsin ? (
              <label>
                <span className="label">{t.portfolioMaturity}</span>
                <input type="date" value={form.maturity_date} onChange={(event) => updateForm('maturity_date', event.target.value)} />
              </label>
            ) : null}

            <div>
              <button className="button-primary" type="submit" disabled={portfolio.loading}>{t.portfolioAdd}</button>
            </div>
          </form>
        ) : null}
      </section>

      <section className="portfolio-list">
        <section className="card portfolio-summary">
          <div className="portfolio-summary-top">
            <p className="label">{t.portfolioTotalCurrentValue}</p>
            <div className="total-currency-toggle" role="group" aria-label={t.portfolioTotalCurrentValue}>
              <button
                className={`button-quiet total-currency-toggle-btn ${totalDisplayCurrency === 'UAH' ? 'active' : ''}`}
                type="button"
                onClick={() => setTotalDisplayCurrency('UAH')}
              >
                {t.portfolioTotalToggleUah}
              </button>
              <button
                className={`button-quiet total-currency-toggle-btn ${totalDisplayCurrency === 'USD' ? 'active' : ''}`}
                type="button"
                onClick={() => setTotalDisplayCurrency('USD')}
              >
                {t.portfolioTotalToggleUsd}
              </button>
              <button
                className={`button-quiet total-currency-toggle-btn ${totalDisplayCurrency === 'EUR' ? 'active' : ''}`}
                type="button"
                onClick={() => setTotalDisplayCurrency('EUR')}
              >
                {t.portfolioTotalToggleEur}
              </button>
            </div>
          </div>
          <p className="portfolio-summary-value">
            {totalCurrentValue === null
              ? '—'
              : formatCurrency(totalCurrentValue, totalDisplayCurrency)}
          </p>
          <p className="muted portfolio-valuation-note">{t.portfolioXiprNote}</p>
        </section>

        {portfolio.assets.length === 0 ? <p className="muted">{t.portfolioEmpty}</p> : null}

        {portfolio.assets.length > 0 ? (
          <div className="portfolio-grid portfolio-grid-header">
            <p>{t.portfolioAssetType}</p>
            <p>{t.portfolioAmount}</p>
            <p>{t.portfolioPrice}</p>
            <p>{t.portfolioCurrentPrice}</p>
            <p>{t.portfolioCurrentValue}</p>
            <p>
              {t.portfolioPnlXipr}
              <span className="table-column-hint" title={t.portfolioXirrTooltip} aria-label={t.portfolioXirrTooltip}>
                ⓘ
              </span>
            </p>
            <p>{t.portfolioDate}</p>
            <p>{t.portfolioComment}</p>
          </div>
        ) : null}

        {portfolio.assets.map((asset) => {
          const purchasePriceByToggle = getAssetPurchasePriceByDisplayCurrency(asset)
          const currentPriceByToggle = getAssetCurrentPriceByDisplayCurrency(asset)
          const currentValueByToggle = getAssetCurrentValueByDisplayCurrency(asset)
          const pnlValueByToggle = getAssetPnlValueByDisplayCurrency(asset)
          const pnlPercentByToggle = getAssetPnlPercentByDisplayCurrency(asset)
          const purchaseValueNative = getAssetPurchaseValueNative(asset)
          const currentValueNative = getAssetCurrentValueNative(asset)
          const pnlAbsoluteNative = (
            isFiniteNumber(currentValueNative) && isFiniteNumber(purchaseValueNative)
              ? currentValueNative - purchaseValueNative
              : null
          )
          const xirrPercent = getAssetXirrPercent(asset)
          const pnlDisplayGlobal = formatPnlAbsoluteAndPercent(
            pnlValueByToggle,
            pnlPercentByToggle,
            totalDisplayCurrency,
          )
          const pnlDisplayNative = formatPnlAbsoluteAndPercent(
            pnlAbsoluteNative,
            asset.pnl_percent,
            asset.currency || undefined,
          )
          const metricForColor = (
            isFiniteNumber(xirrPercent)
              ? xirrPercent
              : isFiniteNumber(pnlPercentByToggle)
                ? pnlPercentByToggle
                : pnlValueByToggle
          )
          const pnlClassName = getPnlClassName(metricForColor)
          const hasNativeSubvalue = shouldShowNativeSubvalue(asset)
          const hasNativePnlContext = hasNativeSubvalue && pnlDisplayNative !== '—'

          return (
            <article key={asset.id} className="portfolio-grid asset-row">
              <div className="portfolio-cell">
                <p className="asset-title">{getAssetLabel(asset.asset_type, lang)}</p>
                <p className="muted">{asset.ticker || asset.isin || '—'}</p>
              </div>
              <div className="portfolio-cell">
                {['Готівка', 'Депозит'].includes(asset.asset_type) ? (
                  <p>{asset.amount} {asset.currency}</p>
                ) : (
                  <p>{asset.amount}</p>
                )}
              </div>
              <div className="portfolio-cell">
                {['Готівка', 'Депозит'].includes(asset.asset_type) ? (
                  <p>—</p>
                ) : (
                  <>
                    <p>{formatCurrency(purchasePriceByToggle, totalDisplayCurrency)}</p>
                    {hasNativeSubvalue ? (
                      <p className="muted portfolio-native-subvalue">{formatCurrency(asset.purchase_price, asset.currency)}</p>
                    ) : null}
                  </>
                )}
              </div>
              <div className="portfolio-cell">
                <p>{formatCurrency(currentPriceByToggle, totalDisplayCurrency)}</p>
                {hasNativeSubvalue ? (
                  <p className="muted portfolio-native-subvalue">{formatCurrency(asset.current_price, asset.currency)}</p>
                ) : null}
                {isFiniteNumber(asset.manual_current_price) ? (
                  <p className="muted manual-price-hint">{t.portfolioManualLabel}</p>
                ) : null}

                {editingManualPriceAssetId === asset.id ? (
                  <section className="manual-price-editor">
                    <input
                      type="number"
                      min="0"
                      step="any"
                      value={manualPriceDraft}
                      onChange={(event) => setManualPriceDraft(event.target.value)}
                    />
                    <div className="inline-confirm-actions">
                      <button className="button-quiet" type="button" onClick={cancelManualPriceEdit}>
                        {t.cancel}
                      </button>
                      <button className="button-primary" type="button" onClick={() => saveManualPriceEdit(asset)} disabled={portfolio.loading}>
                        {t.confirm}
                      </button>
                    </div>
                  </section>
                ) : (
                  <div className="manual-price-actions">
                    <button className="button-quiet manual-price-trigger" type="button" onClick={() => startManualPriceEdit(asset)}>
                      {isFiniteNumber(asset.manual_current_price) ? t.portfolioManualEdit : t.portfolioManualSet}
                    </button>
                    {isFiniteNumber(asset.manual_current_price) ? (
                      <button
                        className="button-quiet manual-price-trigger"
                        type="button"
                        onClick={() => portfolio.updateManualCurrentPrice(asset.id, null)}
                        disabled={portfolio.loading}
                      >
                        {t.portfolioManualClear}
                      </button>
                    ) : null}
                  </div>
                )}
              </div>
              <div className="portfolio-cell">
                <p>{formatCurrency(currentValueByToggle, totalDisplayCurrency)}</p>
                {hasNativeSubvalue ? (
                  <p className="muted portfolio-native-subvalue">{formatCurrency(currentValueNative, asset.currency)}</p>
                ) : null}
              </div>
              <div className="portfolio-cell">
                {isFiniteNumber(xirrPercent) ? (
                  <>
                    <p className={pnlClassName}>{t.portfolioXiprLabel}: {formatAnnualizedPercent(xirrPercent)}</p>
                    <p className={`pnl-subline ${pnlClassName}`}>{pnlDisplayGlobal}</p>
                    {hasNativePnlContext ? (
                      <p className="muted portfolio-native-subvalue">{pnlDisplayNative}</p>
                    ) : null}
                  </>
                ) : (
                  <>
                    <p className={pnlClassName}>{pnlDisplayGlobal}</p>
                    {hasNativePnlContext ? (
                      <p className="muted portfolio-native-subvalue">{pnlDisplayNative}</p>
                    ) : null}
                  </>
                )}
              </div>
              <div className="portfolio-cell">
                <p className="muted">{t.portfolioBuy}: {asset.purchase_date?.slice(0, 10)}</p>
                <p className="muted">{t.portfolioMaturityShort}: {asset.maturity_date?.slice(0, 10) || '—'}</p>
              </div>
              <div className="portfolio-cell portfolio-meta">
                <p className="muted">{asset.notes || '—'}</p>
                {(asset.yield_percent ?? 0) > 0 ? <p className="muted">{t.portfolioYieldShort}: {asset.yield_percent}%</p> : null}
                <button className="button-quiet portfolio-delete" type="button" onClick={() => requestDeleteAsset(asset.id)}>{t.delete}</button>
                {pendingDeleteId === asset.id ? (
                  <section className="inline-confirm">
                    <p className="muted">{t.confirmDeleteAsset}</p>
                    <div className="inline-confirm-actions">
                      <button className="button-quiet" type="button" onClick={() => setPendingDeleteId(null)}>{t.cancel}</button>
                      <button className="button-primary" type="button" onClick={() => confirmDeleteAsset(asset.id)} disabled={portfolio.loading}>{t.confirm}</button>
                    </div>
                  </section>
                ) : null}
              </div>
            </article>
          )
        })}
      </section>
    </section>
  )
}

export default PortfolioPage
