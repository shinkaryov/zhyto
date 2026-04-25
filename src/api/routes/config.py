"""
Configuration and design-token endpoints.
"""

from fastapi import APIRouter

from src.core import VERSION

router = APIRouter(prefix="/config", tags=["config"])

DESIGN_TOKENS = {
    "version": "alpha",
    "name": "ЖИТО",
    "description": "Private-banking black, champagne letterforms.",
    "colors": {
        "primary": "#E9E3D4",
        "secondary": "#8C8575",
        "tertiary": "#C9A15A",
        "neutral": "#0A0A09",
        "surface": "#131211",
        "on-primary": "#0A0A09",
    },
    "typography": {
        "display": {
            "fontFamily": "Playfair Display",
            "fontSize": "4.5rem",
            "fontWeight": 500,
        },
        "h1": {
            "fontFamily": "Playfair Display",
            "fontSize": "2.5rem",
            "fontWeight": 500,
        },
        "body": {
            "fontFamily": "Inter",
            "fontSize": "0.95rem",
            "lineHeight": 1.65,
        },
        "label": {
            "fontFamily": "Inter",
            "fontSize": "0.72rem",
            "fontWeight": 600,
            "letterSpacing": "0.16em",
        },
    },
    "rounded": {
        "sm": "1px",
        "md": "2px",
        "lg": "3px",
    },
    "spacing": {
        "sm": "8px",
        "md": "16px",
        "lg": "32px",
    },
    "components": {
        "button-primary": {
            "backgroundColor": "{colors.tertiary}",
            "textColor": "{colors.on-primary}",
            "rounded": "{rounded.md}",
            "padding": "12px 20px",
        },
        "card": {
            "backgroundColor": "{colors.surface}",
            "textColor": "{colors.primary}",
            "rounded": "{rounded.lg}",
            "padding": "24px",
        },
    },
}

ASSET_TYPES = [
    "ОВДП",
    "Корпоративні облігації",
    "Акції (ETF)",
    "Криптовалюта",
    "Нерухомість",
    "Фонди нерухомості (Inzhur, REITs)",
    "Земля",
    "Готівка",
    "Депозит",
]

CURRENCIES = ["UAH", "USD", "EUR"]

HOME_CONTENT = {
    "title": "Ласкаво просимо до ЖИТО",
    "subtitle": "Ваш персональний фінансовий асистент на базі штучного інтелекту.",
    "features": [
        {
            "title": "Управління портфелем",
            "text": "Відстежуйте свої інвестиції: ОВДП, нерухомість, акції та крипту в одному дашборді.",
        },
        {
            "title": "Розумний AI-чат",
            "text": "Ставте складні питання про податки, ризики та стратегію з цитованими джерелами.",
        },
        {
            "title": "Інвестиційні нотатки",
            "text": "Фіксуйте цілі та стратегію — асистент враховує цей контекст у відповідях.",
        },
        {
            "title": "Приватність та безпека",
            "text": "Ваші фінансові дані обробляються конфіденційно для персональних консультацій.",
        },
    ],
}

ABOUT_CONTENT = {
    "description": (
        "ЖИТО — ваш інтелектуальний партнер у світі українських інвестицій. "
        "Додаток допомагає структурувати інформацію та приймати обґрунтовані рішення."
    ),
    "version": VERSION,
    "status": "Закрите бета-тестування",
    "contact_email": "shinkaryovae@gmail.com",
}


@router.get("/colors")
async def get_design_tokens():
    """Return frontend design tokens."""
    return DESIGN_TOKENS


@router.get("/app")
async def get_app_config():
    """Return app-level frontend config formerly embedded in Streamlit."""
    return {
        "asset_types": ASSET_TYPES,
        "currencies": CURRENCIES,
        "home": HOME_CONTENT,
        "about": ABOUT_CONTENT,
    }
