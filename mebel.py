# -*- coding: utf-8 -*-
"""
mebel.py — «Кухни Островский»: сайт + админка (CMS) на Supabase + AI-помощник.

Как это работает
----------------
1. page.html  — это ШАБЛОН (разметка + CSS + JS). В нём стоят подстановки
   вида {{hero.title_em}} и циклы {{#each works.items}} ... {{/each}}.
2. Контент лежит в Supabase (таблица site_content, строка id=1, колонка data jsonb).
3. При запросе "/" сервер читает page.html, подставляет данные из Supabase
   и отдаёт готовый HTML. Поэтому правки в админке видны на сайте сразу.
4. Картинки с VK проксируются через /img?u=... (кэш + подмена Referer).
5. Загрузка файлов из админки идёт в Supabase Storage (публичный бакет),
   если Storage недоступен — файл сохраняется как data-URL.

Админка: /admin  (логин/пароль — переменные ADMIN_LOGIN и ADMIN_PASSWORD)

Переменные окружения (RelaxDev → Environment)
---------------------------------------------
PORT, DOMAIN, ADMIN_LOGIN, ADMIN_PASSWORD,
SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY, SUPABASE_BUCKET, SUPABASE_TABLE,
YANDEX_API_KEY, FOLDER_ID, GIGACHAT_AUTH_KEY, AI_PROVIDER (yandex|gigachat|auto)
"""

import base64
import gzip
import hashlib
import hmac
import html as _html
import io
import json
import os
import re
import secrets
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

# ============================================================
#  КОНФИГ
# ============================================================
PORT = int(os.environ.get("PORT", "8080"))
DOMAIN = os.environ.get("DOMAIN", "https://кухниостровский.рф").rstrip("/")
ROOT = os.path.dirname(os.path.abspath(__file__))

SUPABASE_URL = (os.environ.get("SUPABASE_URL") or "https://hliafkrpvmntpctmqwfu.supabase.co").rstrip("/")
SUPABASE_ANON = os.environ.get("SUPABASE_ANON_KEY") or (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhsaWFma3Jwdm1udHBjdG1xd2Z1Iiwicm9sZSI6ImFub24i"
    "LCJpYXQiOjE3OTEyMDQ1NzYsImV4cCI6MjEwNjc4MDU3Nn0.yi57-Ty1iIfhnEh80_zvifhX1W_JX2qCl7QrARuJ2ns")
SUPABASE_SERVICE = os.environ.get("SUPABASE_SERVICE_KEY") or (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhsaWFma3Jwdm1udHBjdG1xd2Z1Iiwicm9sZSI6InNlcnZpY2Vfcm9s"
    "ZSIsImlhdCI6MTc5MTIwNDU3NiwiZXhwIjoyMTA2NzgwNTc2fQ.Yr4z9vx6kF9ZINNNUjUn43GYi-A2BmBfg8uyrOtmDWo")
BUCKET = os.environ.get("SUPABASE_BUCKET", "site-images")
DATA_TABLE = os.environ.get("SUPABASE_TABLE", "site_content")

ADMIN_LOGIN_ENV = os.environ.get("ADMIN_LOGIN", "кухниост")
ADMIN_PASSWORD_ENV = os.environ.get("ADMIN_PASSWORD", "романкух")

YANDEX_API_KEY = os.environ.get("YANDEX_API_KEY", "")
FOLDER_ID = os.environ.get("FOLDER_ID", "")
GIGACHAT_AUTH_KEY = os.environ.get("GIGACHAT_AUTH_KEY", "")
AI_PROVIDER = (os.environ.get("AI_PROVIDER", "auto") or "auto").lower()

SESSION_TTL = 31536000
MAX_UPLOAD = 8 * 1024 * 1024
DATA_ROW_ID = 1
CACHE_TTL = 15
IMG_TTL = 604800
IMG_FAIL_TTL = 600
IMG_TIMEOUT = int(os.environ.get("IMG_TIMEOUT", "8"))
# IMG_PROXY=0 — отдавать картинки напрямую с VK (если на хостинге нет корневых сертификатов)
IMG_PROXY = (os.environ.get("IMG_PROXY", "1") or "1").lower() not in ("0", "false", "no", "off")
HTTP_TIMEOUT = 12

# Favicon, вшитый прямо в файл: работает без интернета, без Pillow и без внешних ссылок
FAVICON_ICO_B64 = "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"
FAVICON_PNG180_B64 = "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9qce94Qnjtf3DZaGUVAwlcRELY2asgkwPwUpMzHMBYqKf0NTo6nZV4c45wCaFno8S/ia6Y9g7qq0djoGcexu+eaeXUcc9dbffeu+22599rN+6bYDG/3hikgzO/FADR7z2Mfs2LF65llnnXzq90xHI+c0sQ9AatNf3vm7b33LVZ+96uUvf+nPP+s5j3rUf3vJSy78xte+1F9eEbH0QfHe+6ra2H/LeG3v5v69owN7127b2zTj9bUDjTTldth42jfccONFF1703d/93S97+cummwcMX5m+1d3QNynzAEOmrT4u2F3pZgEE8x1GPu5U42iaogUAI0NAZjysBENRxldmmsnD4XxvZXVlaceRaDZPvffJ73rXO/fs2fP8X37edDrtD/pA01r6RH7pw3/1sbW1tcc/9ifRjHTPjfJrhjuO+LdPf+rNb37L+c867/se/ODJ5v5Xv/rXl5eXX3nxq5yvnPd2W4ZzzleVd86np1dV3vcHw6V+rw/nUuyMnK7VldUrPv43n7/6qt954xt3Hb27ntbMQkyDwaDX682Ur7OFyWy24cqPaKu+D7ensEIglwaQQ20cuSlqlprNaAqk5hPP+VvF3IpM8k9EXE8ne/Z8czqdsK/WDqyd/v0/9LZLLvnHK//x3Kc+de9t+5zvhWvTNE1vafUTn/i7Rz/qka973W+fe+459/2e75lsbnBuoACQ3mBww9evO++88x56xhnnnf+cyfpaPRkff9J9fuO1r7nssste99rXVoPl0EAOozMH1tZu/ubNKa3LpePmaHNtba2t/Me8tr526969z//VX7n/aaeNDuz3VRXygH379u0/sH8rvzpzujwLpWftkC2BIirvWJq0aeo7cKD+Fa94xZ3nOaZAYzvSWzCdsFWHidvSbwj6fNPxiJkf9vCH7dq5g4B6Mj7p3qeefv/73nDTnt3HHHPSKfeWehrKFuf9xvra17/x9Z8999xnPvOZUtfKHdJz9b3BZ//93yeT6Qte8KtHHX1MM51WlW/G4++63/12H33Urbfd9n2nnz5cGoay0zk32lg/6eSTf+gHH2Kt2DneXFs7/vjjf/AhD2ZzHMxuY3PzR3/0v577tHOnow2X+nVMtLa29oDTTn/AA05DU7eq0C200jELCTJjJrjEmsUahK6ri3va2TnfO5SNt2ayKfUkLTLYBqCDSujNeM7WzYgzkVVV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"
FAVICON_PNG32_B64 = "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAEFklEQVR42rVWTW8bVRS99743M45j54NEEImoaioWkUiFaGCVCrFBVAgWIJb8A34SQkhdItaVWCBRigQsEKQUgUpIQ4FSJ82XE0/n4917WIydD9cOjkSv5LFmnn3P3HfPPecxAHqaIfSU46kD+DPWQOi7Z+b/DQBAf7ozkgM0BJvPaHJR5KcLICfiRE79BWARFneOCgCUZXH9049/uftz5CMYwOREOo/TV1965c2lxb3tljhPBDMYoCHMLiw9t/DiwDr6AcxMRNbu3f3i5ueN8SYAYgbBiTvsHB4ctLXIyqzjnAfICGYIZfHg1+9n5l/wUTJqD0IISVLz3psBBGYScd575xyziPPivJoxwAJxHsww620k/zcAM6upmsGMmABmMjMDgQhV9L4N3Z7gHHOAipREfXsK4PQj9PiFIfmHAHD3wkzELMJMzMzMxEQAgZirxapcYjnfHKjp4yxlYVWtdsCJHKadvMhhaqFkIjOomZqaGrHDiADVcM1Oz157/VocxWYmzsWRZ+IiFBfnL9am556Jx1kEQEUBMyMWcW4kADNzzm21tm58dqM5MbG/t7+ysvLhB+/sbv7jo7gsi93WfWYnUYSyqJpgqsZMQwZ28Balafrb72tTk1O7e7sXLl7Y39vZ3dl0LiKCMIPYRbEVGTEDZBaM3TBFGNwcEVdLkjiOkziJorgnNgIiBYzIQEZs1aydJVJDKgBMVQ2mqqraGG/o5KSLYsCIiFicj7TIK8YCZuBhQjtUTQ1QVTMlwuof23/efxhH0Yl94O4QMJuqj6K3Lps/DwAfjamIfPTJ9a9v3Wo0mmpaJYaBpZoSLsuy0Wi+9sbbtbH6k3I3ZA5CgME7750Xkeb4+PTUZKPZNNWqHz1Co0s87+lcc/Ds3BwxtTZb7f39drudpunm5tbjLOsCHH9YnKSd9OUrV5rNiYFEGmA4lR5+dfPL7779JoSwuLhYlsX6+r0kSVRVRHqiRMxcGd+7772/cOnSQFt7AgDQMoOpr9V7JLZRzgYWSmYi7ne3PgCErAMNIBKRVqu1evv28vLyZquVpun8/PM/3blzeWnp0aNtwJrNiTzPNzY2rl69WqslTJX8ETvv4/pRLXL6LQIsVNLo47goy/X1e/VGM8vzg8PD6ZmZtbV156OHrdZffz8Iqj/8uFrRzDnfy8jQUstscAVW5lpmFceZpSyLLMsqrtTrdVUNIRBRkiQA8jwviqJerzvnvPeVVRwxxY81umJ+EgAaQt45+TsRqdqY59lOe7d7Szw7PeOcY2Yz6xrcCSthFj/WGNxkLTILOfVe58ioYJaXRS8HJ0nSx+xjAJiLx6R3ABhEUw0wBYGAYwhmYe5qEZGZVUunrBLEzOwjF9VGOniNFqfdmGmkU8V5gs9Ua/oXI1+PfOCUKloAAAAASUVORK5CYII="
_fav_bytes = {}


def _b64_bytes(s):
    if not s:
        return None
    if s not in _fav_bytes:
        try:
            _fav_bytes[s] = base64.b64decode(s)
        except Exception:
            _fav_bytes[s] = None
    return _fav_bytes[s]


FAVICON_URL = "https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/logo/logo-512.jpg"

# ============================================================
#  АНИМАЦИИ (вставляются в page.html, если их там ещё нет)
# ============================================================
# ============================================================
#  ДЕФОЛТНЫЙ КОНТЕНТ (актуальная версия сайта; БД перекрывает эти значения)
# ============================================================
# <<<DEFAULT_DATA_START>>>
DEFAULT_DATA = {'seo': {'favicon_url': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/logo/logo-512.jpg', 'title': 'Кухни Островский — кухни на заказ в Ростове, Батайске и Азове | Мебель под ключ',
         'keywords': 'кухни на заказ Ростов-на-Дону, кухни на заказ Ростов, кухни Ростов, кухни Батайск, кухни на заказ Батайск, кухни Азов, кухни на заказ Азов, кухонный гарнитур Ростов, мебель на заказ Ростов, корпусная мебель Ростов, шкафы на заказ Ростов, гардеробные на заказ Ростов, прихожие на заказ Ростов, кухонный гарнитур Батайск, мебель на заказ Батайск, корпусная мебель Батайск, шкафы на заказ Батайск, гардеробные Батайск, прихожие Батайск, кухонный гарнитур Азов, мебель на заказ Азов, корпусная мебель Азов, шкафы на заказ Азов, гардеробные Азов, прихожие Азов, кухня по индивидуальным размерам Ростов, кухня по проекту Ростов, угловая кухня Ростов, прямая кухня Ростов, П-образная кухня Ростов, кухня с островом Ростов, современная кухня Ростов, классическая кухня Ростов, кухни Ростовская область, мебель на заказ Ростовская область',
         'og_image': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/logo/logo-512.jpg',
         'description': 'Кухни на заказ в Ростове-на-Дону, Батайске и Азове от мастерской «Кухни Островский». Бесплатный замер и '
                        '3D-проект, собственное производство, монтаж под ключ. ☎ +7 (950) 846-53-97',
         'og_title': 'Кухни Островский — кухни на заказ в Ростове, Батайске и Азове',
         'og_description': 'Кухни и корпусная мебель под ключ. Бесплатный замер и 3D-проект, собственное производство, монтаж. ☎ +7 '
                           '(950) 846-53-97',
         'domain': 'https://кухниостровский.рф',
         'canonical': 'https://кухниостровский.рф/',
         'robots_meta': 'index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1',
         'geo_region': 'RU-ROS',
         'geo_placename': 'Ростов-на-Дону',
         'geo_lat': '47.2357',
         'geo_lon': '39.7015',
         'yandex_verification': 'f7e96d07aee79bf3',
         'google_verification': 'dNSAELu64Y7aK5sjz_zpmhoz6YKn2PIZ03UKPwrgnCI',
         'metrika_id': '',
         'robots': '',
         'extra_urls': []},
 'code': {'head': '', 'body': ''},
 'lead_form': {'enabled': True, 'title': 'Оставить заявку', 'subtitle': 'Оставьте номер — свяжемся и обсудим задачу.', 'button': 'Оставить заявку'},
 'sections': {'stats': True, 'about': True, 'consult': True, 'works': True, 'reviews': True,
              'services': True, 'process': True, 'guarantees': True, 'cities': True, 'cta': True,
              'contacts': True, 'footer': True, 'cookie': True},
 'design': {'bg': '#0e0c09',
            'gold': '#d4af6a',
            'gold_soft': '#eccfa0',
            'gold_deep': '#a37c3f',
            'text': '#f5efe3',
            'muted': '#b9ad9a',
            'fonts_url': 'https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,500&family=Manrope:wght@300;400;500;600;700;800&display=swap',
            'custom_css': '', 'radius': '24px', 'container': '1180px'},
 'brand': {'vk': 'https://vk.com/mebel.ostrovsky',
           'sub': 'Ростов · Батайск · Азов',
           'name': 'Кухни Островский',
           'phone': '+7 (950) 846-53-97',
           'logo_url': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/logo/logo-256.jpg',
           'telegram': 'https://t.me/fanny161',
           'phone_raw': '+79508465397'},
 'nav': {'items': [{'label': 'Специалист', 'href': '#about'},
                   {'label': 'Работы', 'href': '#works'},
                   {'label': 'Отзывы', 'href': '#reviews'},
                   {'label': 'Услуги', 'href': '#services'},
                   {'label': 'Как работаем', 'href': '#process'},
                   {'label': 'Города', 'href': '#cities'},
                   {'label': 'Контакты', 'href': '#contacts'}],
         'cta_label': 'Позвонить специалисту',
         'cta_href': 'tel:+79508465397'},
 'hero': {'bg': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/works/w01.jpg',
          'sub': 'Проектируем и изготавливаем кухни, шкафы, гардеробные и другую корпусную мебель в Ростове, Батайске и Азове — по '
                 'вашему проекту, от замера до монтажа.',
          'btn1': 'Получить консультацию',
          'btn2': 'Смотреть работы',
          'eyebrow': 'Мебель и кухни на заказ',
          'title_em': 'создаёт настроение',
          'title_before': 'Мебель, которая ',
          'btn1_href': '#consult',
          'btn2_href': '#works',
          'watermark': 'Мебель',
          'scroll_cue': 'Листайте'},
 'stats': {'bg': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/works/w02.jpg',
           'items': [{'prefix': '', 'num': '10', 'suffix': '+', 'decimal': '', 'label': 'лет опыта'},
                     {'prefix': '', 'num': '5', 'suffix': '', 'decimal': '1', 'label': 'средняя оценка клиентов'},
                     {'prefix': '', 'num': '9', 'suffix': '/10', 'decimal': '', 'label': 'клиентов по рекомендации'},
                     {'prefix': '', 'num': '100', 'suffix': '%', 'decimal': '', 'label': 'полный цикл под ключ'}]},
 'about': {'bg': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/bg/about.jpg',
           'name': 'Роман Островский',
           'role': 'Руководитель мебельной мастерской Островского',
           'photo': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/about/roman.jpg',
           'title': 'Кухни и мебель под ключ — с заботой о деталях',
           'kicker': 'О руководителе',
           'features': ['Кухни, шкафы, гардеробные и прихожие',
                        'Честный расчёт — без навязывания лишнего',
                        'Аккуратность, пунктуальность, сопровождение',
                        'Гарантия качества'],
           'card_text': 'С командой изготавливаем кухни и корпусную мебель по индивидуальным проектам — с учётом ваших идей, размеров '
                        'и задач.',
           'text': 'Мы помогаем с планировкой и подбором материалов, предлагаем решения даже для сложных задач — когда другие разводят '
                   'руками. Ведём вас от консультации и замера до сборки и установки.'},
 'consult': {'bg': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/bg/consult.jpg',
             'text': 'Позвоните или напишите нам в Telegram или MAX — расскажем про кухни и мебель, всё обсудим и договоримся о '
                     'бесплатном замере.',
             'title': 'Консультация',
             'kicker': 'Бесплатно',
             'phone': '+7 (950) 846-53-97',
             'phone_raw': '+79508465397'},
 'works': {'bg': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/bg/works.jpg',
           'items': [{'alt': 'Кухня на заказ в Ростове',
                      'url': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/works/w01.jpg'},
                     {'alt': 'Кухня на заказ в Батайске',
                      'url': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/works/w02.jpg'},
                     {'alt': 'Кухня на заказ в Азове',
                      'url': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/works/w03.jpg'},
                     {'alt': 'Мебель на заказ в Ростове',
                      'url': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/works/w04.jpg'},
                     {'alt': 'Шкаф-купе на заказ',
                      'url': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/works/w05.jpg'},
                     {'alt': 'Мебель на заказ в Батайске',
                      'url': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/works/w06.jpg'},
                     {'alt': 'Кухня на заказ',
                      'url': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/works/w07.jpg'},
                     {'alt': 'Мебель на заказ',
                      'url': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/works/w08.jpg'},
                     {'alt': 'Кухня на заказ в Батайске',
                      'url': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/works/w09.jpg'},
                     {'alt': 'Мебель на заказ',
                      'url': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/works/w10.jpg'},
                     {'alt': 'Кухня на заказ',
                      'url': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/works/w11.jpg'},
                     {'alt': 'Кухня на заказ',
                      'url': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/works/w12.jpg'},
                     {'alt': 'Кухня на заказ',
                      'url': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/works/w13.jpg'}],
           'title': 'Кухни и мебель, которые мы сделали',
           'kicker': 'Наши работы',
           'subtitle': 'Нажмите на фото, чтобы рассмотреть в большом размере.',
           'hint': 'Листайте',
           'watermark': 'Работы',
           'more_text': 'Больше работ — в сообществе',
           'more_label': 'ВКонтакте',
           'more_href': 'https://vk.com/mebel.ostrovsky'},
 'reviews': {'bg': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/bg/reviews.jpg',
             'items': [{'sub': 'Кухня на заказ',
                        'name': 'Виктория Брандикова',
                        'text': 'Заказывали у Романа кухню, всё прошло на высшем уровне, начиная от замеров, до установки! Мы очень '
                                'рады, что обратились именно к нему (нашли в объявлении и нам крупно повезло), Роман супер '
                                'профессионал своего дела!!! Кухня у нас маленькая, не стандартная, сверху выступы, вся на трубах, '
                                'расположение мойки и кухонной плиты не удобное и вытяжку мы хотели, но нам некуда было её '
                                'устанавливать (как мы думали), но Роман всё разрешил, практично разместил технику (в том числе и '
                                'вытяжку), переставил мойку, установил подсветку сделал кухню функциональной светлой, практичной и '
                                'современной. Кухня была готова в короткие сроки, установкой очень довольны, всё под ключ с установкой '
                                'техники и подключением, всё быстро, качественно, и чисто! Мы не ожидали такого результата, просто не '
                                'верится, что у нас теперь удобная, вместительная, современная кухня, о такой даже и не мечтали, даже '
                                'несмотря на то, что кухня бюджетная. За мебелью теперь только к Роману!!! Однозначно всем буду '
                                'рекомендовать!!!',
                        'stars': 5,
                        'video': '',
                        'avatar': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/reviews/ava-01.jpg'},
                       {'sub': 'Кухня и гардеробная',
                        'name': 'Виктория Маренко',
                        'text': 'И вновь мы обратились к Роману! Понадобилась кухня. Кухня на самом деле очень удобная! Как и хотелось '
                                'она светлая, но не маркая. Как всегда учтены все пожелания и воплощены в жизнь! Очень трудно нам '
                                'дался выбор цветов, но Роман спокойно вынес все наши метания, выполнил работу достойно, внимательно и '
                                'аккуратно! Однозначно советую обращаться к нему. Гардеробную так же заказывали у Романа, и она '
                                'идеальна! Ответственный подход, качество, внимательность и чистота исполнения - его качества, которые '
                                'для нас важны.',
                        'stars': 5,
                        'video': '',
                        'avatar': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/reviews/ava-02.jpg'},
                       {'sub': 'Шкаф, тумбы, прихожая',
                        'name': 'Любовь Петелько',
                        'text': 'Всем здравствуйте. Я заказала у Романа шкаф купе в спальню. Когда Роман приехал, я не совсем понимала '
                                'что я хочу, пообщавшись с ним, получила много советов и рекомендаций по составу и цвету шкафа. В '
                                'итоге решила в комплект заказать сразу тумбы, гарнитур под телевизор, и прихожую. Установили все '
                                'раньше обещанного срока. Я очень довольна и всем рекомендую. Роман специалист своего дела. Скоро буду '
                                'заказывать зону хранения балкона и самое главное кухню мечты. Спасибо!',
                        'stars': 5,
                        'video': '',
                        'avatar': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/reviews/ava-03.jpg'},
                       {'sub': 'Шкаф и стенка',
                        'name': 'Дмитрий Юшенко',
                        'text': 'Заказывали у Романа шкаф и стенку в спальню. Работа вышла отличной, подсказал несколько удачных '
                                'решений наших хотелок. Все супер! Спасибо!',
                        'stars': 5,
                        'video': '',
                        'avatar': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/reviews/ava-04.jpg'},
                       {'sub': 'Кухня на заказ',
                        'name': 'Екатерина Умнягина',
                        'text': 'Заказывали у Романа кухню, всё очень понравилось! Подбирали всё до мелочей, и Рома всё исполнил, как '
                                'мы хотели, за это мы ему очень благодарны. Всё сделано идеально, спрятали то, что не должно быть '
                                'видно, и получилось очень красиво. Спасибо, Рома, за эту крутую современную кухню!!!',
                        'stars': 5,
                        'video': '',
                        'avatar': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/reviews/ava-05.jpg'},
                       {'sub': 'Два шкафа, гардеробная',
                        'name': 'Анастасия Зайцева',
                        'text': 'Заказывали у Романа два шкафа. Во время замеров у нас не было определённой идеи, как сделать '
                                'вместительный шкаф в нашу небольшую спальню, ещё и с несущей колонной. Роман подкинул прекрасную '
                                'идею, в итоге получился не просто шкаф, а целая угловая гардеробная, я была в восторге! Большой выбор '
                                'цветов и текстур. Работа выполнена в оговорённый срок и качественно. Большое спасибо за эстетичное '
                                'воплощение нашей мечты!',
                        'stars': 5,
                        'video': '',
                        'avatar': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/reviews/ava-06.jpg'},
                       {'sub': 'Видеоотзыв · Кухня на заказ',
                        'name': 'Александр Карташев',
                        'text': '«Прям гордость квартиры! За приемлемую цену получили отличную кухню: выступ стояка закрыли пеналом, а '
                                'в ножку барного стола встроили розетки».',
                        'stars': 5,
                        'video': 'https://vk.ru/video_ext.php?oid=-212015374&id=456239019&hash=6abf300a7c2518d4',
                        'avatar': ''}],
             'title': 'Что говорят наши клиенты',
             'kicker': 'Отзывы',
             'subtitle': 'Реальные отзывы о нашей работе. Листайте влево-вправо.',
             'hint': 'Листайте',
             'watermark': 'Отзывы',
             'video_poster': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/bg/reviews.jpg',
             'more_text': 'Больше отзывов — в нашем сообществе',
             'more_label': 'ВКонтакте',
             'more_href': 'https://vk.com/mebel.ostrovsky'},
 'services': {'bg': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/bg/services.jpg',
              'items': [{'icon': 'M3 9h18M3 9v10a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1V9M3 9l2-4h14l2 4M8 9v2M12 9v2M16 9v2',
                         'text': 'Проектируем кухню точно под ваш размер, стиль и привычки — от классики до минимализма.',
                         'title': 'Кухни на заказ'},
                        {'icon': 'M3 3h18v18H3zM3 8h18M8 8v13M16 8v13',
                         'text': 'Шкафы-купе, гардеробные, тумбы и комоды — встроенные и отдельно стоящие.',
                         'title': 'Шкафы и гардеробные'},
                        {'icon': 'M12 3v18M3 12h18M5 5l14 14M19 5L5 19',
                         'text': 'Прихожие, стенки, гарнитуры под ТВ — аккуратно впишем в ваш интерьер.',
                         'title': 'Прихожие и стенки'},
                        {'icon': 'M14 6l4 4M5 19l7-7M17 3l4 4-4 4-1-1-1 1-4-4 1-1-1-1 4-4z',
                         'text': 'Профессиональная установка, аккуратная сборка и подключение техники.',
                         'title': 'Сборка и монтаж'},
                        {'icon': 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 3v18M3 12h18',
                         'text': 'Выезжаем на замер, делаем планировку и 3D-проект — бесплатно.',
                         'title': 'Замер и проект'},
                        {'icon': 'M3 12a9 9 0 1 0 9-9M3 12h6M3 12l4-4M3 12l4 4',
                         'text': 'Освежим фасады и фурнитуру существующей кухни — дешевле, чем новая.',
                         'title': 'Обновление мебели'}],
              'title': 'Услуги',
              'kicker': 'Что мы делаем',
              'subtitle': 'Индивидуальный подход к каждому проекту и полный цикл производства.',
              'watermark': 'Услуги'},
 'process': {'bg': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/bg/process.jpg',
             'items': [{'n': '01', 'text': 'Вы звоните или пишете — обговариваем задачу и пожелания.', 'title': 'Обращение'},
                       {'n': '02', 'text': 'Выезжаем, снимаем размеры и обсуждаем планировку. Бесплатно.', 'title': 'Замер'},
                       {'n': '03', 'text': 'Готовим 3D-проект и подбираем материалы с фурнитурой.', 'title': 'Проект'},
                       {'n': '04', 'text': 'Фиксируем стоимость и условия, подписываем договор.', 'title': 'Договор'},
                       {'n': '05', 'text': 'Изготавливаем мебель на собственном производстве.', 'title': 'Производство'},
                       {'n': '06', 'text': 'Привозим, собираем и устанавливаем. Сдаём с гарантией.', 'title': 'Доставка и монтаж'}],
             'title': 'Путь от идеи до готовой мебели',
             'kicker': 'Как мы работаем'},
 'guarantees': {'bg': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/bg/guarantees.jpg',
                'items': [{'icon': 'M12 3l7 3v6c0 4.4-3 7.6-7 9-4-1.4-7-4.6-7-9V6l7-3zM9 12l2 2 4-4',
                           'text': 'Отвечаем за свою работу и сопровождаем после установки.',
                           'title': 'Гарантия качества'},
                          {'icon': 'M4 20h16M6 20V8l6-4 6 4v12M9 11h6M9 15h6M10 11v8M14 11v8',
                           'text': 'Без навязывания лишнего и скрытых доплат.',
                           'title': 'Честный расчёт'},
                          {'icon': 'M3 21V9l9-5 9 5v12M3 21h18M9 21v-6h6v6M12 9v2',
                           'text': 'Без посредников — контролируем качество на каждом этапе.',
                           'title': 'Собственное производство'},
                          {'icon': 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM4 21c0-4 3.6-6 8-6s8 2 8 6',
                           'text': 'Вы всегда на связи со специалистом — от замера до монтажа.',
                           'title': 'Личное сопровождение'}],
                'title': 'Гарантии и преимущества',
                'kicker': 'Почему мы'},
 'cities': {'bg': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/bg/cities.jpg',
            'items': [{'name': 'Ростов-на-Дону', 'text': 'Выезд на замер, проектирование, производство и монтаж мебели под ключ.'},
                      {'name': 'Батайск', 'text': 'Кухни и корпусная мебель с бесплатным замером и 3D-проектом.'},
                      {'name': 'Азов', 'text': 'Индивидуальные проекты, доставка, сборка и установка с гарантией.'}],
            'title': 'Три города — один стандарт качества',
            'kicker': 'Где работаем',
            'subtitle': 'Бесплатный замер и проект в каждом из городов.'},
 'cta': {'bg': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/bg/reviews.jpg',
         'text': 'Позвоните нам — бесплатно проконсультируем, посчитаем и запишем на замер.',
         'title': 'Готовы обсудить вашу мебель?',
         'button': '📞 Позвонить специалисту'},
 'contacts': {'bg': 'https://hliafkrpvmntpctmqwfu.supabase.co/storage/v1/object/public/site-images/works/w12.jpg',
              'title': 'Создадим мебель, о которой вы мечтали',
              'kicker': 'Контакты',
              'regions': 'Ростов-на-Дону, Батайск, Азов',
              'subtitle': 'Позвоните или напишите — ответим быстро и подскажем по всем вопросам.',
              'call_label': 'Свяжитесь с нами удобным способом',
              'call_number': '+7 (950) 846-53-97',
              'call_hint': 'Бесплатная консультация и запись на замер.\nЗвоните или пишите в любой мессенджер.',
              'lines': [{'label': 'Регион работы',
                         'value': 'Ростов-на-Дону, Батайск, Азов',
                         'href': '',
                         'icon': 'M12 3v18M3 12h18M5.6 5.6l12.8 12.8M18.4 5.6L5.6 18.4'
                                 '0 0 0 5z'},
                        {'label': 'Сайт в VK',
                         'value': 'mebel.ostrovsky',
                         'href': 'https://vk.com/mebel.ostrovsky',
                         'icon': 'M4 20h16M6 20V8l6-4 6 4v12'
                                 '1.8.9 4.6 3.6 5.4 8.4h-3.4c-.6-2.5-2.4-4.4-4.3-4.9V19H14z'},
                        {'label': 'Telegram / MAX',
                         'value': 'по номеру +7 (950) 846-53-97',
                         'href': 'https://t.me/fanny161',
                         'icon': '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-6 8-6s8 2 8 6"/>'
                                 '6.4c.4-.3-.1-.5-.6-.2L6.7 13.4l-4.6-1.4c-1-.3-1-1 .2-1.5l18-6.9c.8-.3 1.6.2 1.6 1z'},
                        {'label': 'Сообщения VK',
                         'value': 'личные сообщения сообщества',
                         'href': 'https://vk.com/mebel.ostrovsky',
                         'icon': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/>'}],
              'buttons': [{'label': 'Позвонить',
                           'href': 'tel:+79508465397',
                           'cls': 'c-call',
                           'external': False,
                           'icon': 'M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 '
                                   '0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 2 .7 2.9a2 2 0 0 1-.4 2.1L8.1 10a16 16 0 0 0 6 6l1.3-1.3a2 2 '
                                   '0 0 1 2.1-.4c.9.3 1.9.6 2.9.7a2 2 0 0 1 1.6 2z'},
                          {'label': 'Написать в Telegram',
                           'href': 'https://t.me/fanny161',
                           'cls': 'c-tg',
                           'external': True,
                           'icon': 'M21.9 4.6L18.8 19c-.2 1-.8 1.3-1.7.8l-4.7-3.5-2.3 2.2c-.3.3-.5.5-1 .5l.4-4.8L18 '
                                   '6.4c.4-.3-.1-.5-.6-.2L6.7 13.4l-4.6-1.4c-1-.3-1-1 .2-1.5l18-6.9c.8-.3 1.6.2 1.6 1z'},
                          {'label': 'Написать в MAX',
                           'href': 'tel:+79508465397',
                           'cls': 'c-max',
                           'external': False,
                           'icon': 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z'}]},
 'footer': {'line': 'Кухни и корпусная мебель на заказ — Ростов, Батайск, Азов',
            'copyright': 'Кухни Островский. Все права защищены.',
            'socials': [{'label': 'Позвонить',
                         'href': 'tel:+79508465397',
                         'icon': 'M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 '
                                 '0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 2 .7 2.9a2 2 0 0 1-.4 2.1L8.1 10a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 '
                                 '1 2.1-.4c.9.3 1.9.6 2.9.7a2 2 0 0 1 1.6 2z'},
                        {'label': 'Telegram',
                         'href': 'https://t.me/fanny161',
                         'icon': 'M21.9 4.6L18.8 19c-.2 1-.8 1.3-1.7.8l-4.7-3.5-2.3 2.2c-.3.3-.5.5-1 .5l.4-4.8L18 '
                                 '6.4c.4-.3-.1-.5-.6-.2L6.7 13.4l-4.6-1.4c-1-.3-1-1 .2-1.5l18-6.9c.8-.3 1.6.2 1.6 1z'},
                        {'label': 'ВКонтакте',
                         'href': 'https://vk.com/mebel.ostrovsky',
                         'icon': 'M14 19c-6 0-9.5-4.5-9.7-12h3c.1 5 2.5 8 4.3 8.8V7h3v5c1.8-.2 3.6-2.6 4.2-5h3c-.6 3.4-2.8 5.8-4.6 6.6 '
                                 '1.8.9 4.6 3.6 5.4 8.4h-3.4c-.6-2.5-2.4-4.4-4.3-4.9V19H14z'},
                        {'label': 'MAX', 'href': 'tel:+79508465397', 'icon': 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z'}]},
 'cookie': {'text': 'Мы используем файлы cookie для корректной работы сайта и улучшения сервиса.',
            'link_label': 'Политика конфиденциальности',
            'link_href': '#',
            'button': 'Принять'},
 'page404': {'title': 'Такой страницы нет',
             'text': 'Возможно, ссылка устарела или адрес введён с ошибкой. Вернитесь на главную — там вас ждут наши работы, отзывы и '
                     'контакты.',
             'button': 'На главную'}}
# <<<DEFAULT_DATA_END>>>

PAGE = r"""<!DOCTYPE html>
<html lang="ru" class="js" data-build="2026-10-06-v9">
<head>
<meta charset="UTF-8">
<script>/* шим: если браузер не умеет IntersectionObserver, показываем блоки сразу (без «мёртвых» скрытых секций) */
window.IntersectionObserver=window.IntersectionObserver||function(cb){return{observe:function(el){try{cb([{isIntersecting:true,target:el}],this);}catch(e){}},unobserve:function(){},disconnect:function(){}};};
</script>
<!-- Кухни Островский · сборка 2026-10-06-v9: анимации, аватарка и favicon из Supabase, защита сохранения (rev), история версий -->
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{seo.title}}</title>
<meta name="description" content="{{seo.description}}">
{{#if seo.keywords}}<meta name="keywords" content="{{seo.keywords}}">{{/if}}
<meta name="robots" content="{{seo.robots_meta}}">
<meta name="geo.region" content="{{seo.geo_region}}">
<meta name="geo.placename" content="{{seo.geo_placename}}">
<meta name="geo.position" content="{{seo.geo_lat}};{{seo.geo_lon}}">
<meta name="ICBM" content="{{seo.geo_lat}}, {{seo.geo_lon}}">
<meta name="theme-color" content="{{design.bg}}">
<meta name="msapplication-TileColor" content="{{design.bg}}">
{{#if seo.canonical}}<link rel="canonical" href="{{seo.canonical}}">
<link rel="alternate" hreflang="ru" href="{{seo.canonical}}">
<link rel="alternate" hreflang="x-default" href="{{seo.canonical}}">{{/if}}
{{#if seo.yandex_verification}}<meta name="yandex-verification" content="{{seo.yandex_verification}}">{{/if}}
{{#if seo.google_verification}}<meta name="google-site-verification" content="{{seo.google_verification}}">{{/if}}
<link rel="shortcut icon" href="/favicon.ico">
<link rel="icon" type="image/x-icon" href="/favicon.ico">
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
<link rel="icon" type="image/jpeg" sizes="any" href="{{favicon}}">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<link rel="apple-touch-icon" sizes="any" href="{{favicon}}">
<meta name="msapplication-TileImage" content="/apple-touch-icon.png">
<link rel="manifest" href="/manifest.webmanifest">
<meta property="og:type" content="website">
<meta property="og:locale" content="ru_RU">
<meta property="og:site_name" content="{{brand.name}}">
<meta property="og:title" content="{{seo.og_title}}">
<meta property="og:description" content="{{seo.og_description}}">
<meta property="og:image" content="{{seo.og_image}}">
{{#if seo.canonical}}<meta property="og:url" content="{{seo.canonical}}">{{/if}}
<meta property="og:image:alt" content="{{seo.og_title}}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{{seo.og_title}}">
<meta name="twitter:description" content="{{seo.og_description}}">
<meta name="twitter:image" content="{{seo.og_image}}">
<script type="application/ld+json">
[
{
  "@context": "https://schema.org",
  "@type": ["LocalBusiness", "HomeAndConstructionBusiness"],
  "@id": "{{seo.canonical|json}}#business",
  "name": "{{brand.name|json}}",
  "alternateName": "{{seo.og_title|json}}",
  "url": "{{seo.canonical|json}}",
  "logo": "{{brand.logo_url|json}}",
  "image": "{{seo.og_image|json}}",
  "description": "{{seo.description|json}}",
  "telephone": "{{brand.phone_raw|json}}",
  "priceRange": "₽₽",
  "currenciesAccepted": "RUB",
  "address": {"@type": "PostalAddress", "addressLocality": "{{seo.geo_placename|json}}", "addressRegion": "Ростовская область", "addressCountry": "RU"},
  "geo": {"@type": "GeoCoordinates", "latitude": {{seo.geo_lat|json}}, "longitude": {{seo.geo_lon|json}}},
  "areaServed": [{{#each cities.items}}{"@type": "City", "name": "{{this.name|json}}"}{{#unless @last}},{{/unless}}{{/each}}],
  "sameAs": ["{{brand.vk|json}}"{{#if brand.telegram}}, "{{brand.telegram|json}}"{{/if}}],
  "contactPoint": {"@type": "ContactPoint", "telephone": "{{brand.phone_raw|json}}", "contactType": "customer service", "availableLanguage": "Russian"}
},
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "@id": "{{seo.canonical|json}}#org",
  "name": "{{brand.name|json}}",
  "url": "{{seo.canonical|json}}",
  "logo": "{{brand.logo_url|json}}",
  "sameAs": ["{{brand.vk|json}}"{{#if brand.telegram}}, "{{brand.telegram|json}}"{{/if}}],
  "contactPoint": {"@type": "ContactPoint", "telephone": "{{brand.phone_raw|json}}", "contactType": "customer service", "availableLanguage": "Russian"}
},
{
  "@context": "https://schema.org",
  "@type": "ContactPage",
  "@id": "{{seo.canonical|json}}#contacts",
  "url": "{{seo.canonical|json}}#contacts",
  "name": "Контакты — {{brand.name|json}}",
  "inLanguage": "ru-RU",
  "mainEntity": {"@id": "{{seo.canonical|json}}#business"}
},
{
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  "itemListElement": [
    {"@type": "ListItem", "position": 1, "name": "Главная", "item": "{{seo.canonical|json}}"}
  ]
},
{
  "@context": "https://schema.org",
  "@type": "WebSite",
  "@id": "{{seo.canonical|json}}#website",
  "url": "{{seo.canonical|json}}",
  "name": "{{brand.name|json}}",
  "inLanguage": "ru-RU",
  "potentialAction": {
    "@type": "SearchAction",
    "target": {"@type": "EntryPoint", "urlTemplate": "{{seo.canonical|json}}?q={search_term_string}"},
    "query-input": "required name=search_term_string"
  }
}
]
</script>
{{#if img_origin}}<link rel="preconnect" href="{{img_origin}}" crossorigin>
<link rel="dns-prefetch" href="{{img_origin}}">{{/if}}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{{design.fonts_url}}" rel="stylesheet">
{{#if hero.bg}}<link rel="preload" as="image" fetchpriority="high" href="{{{hero.bg}}}">{{/if}}
<style>
:root{
  --bg:#0e0c09;
  --gold:#d4af6a;
  --gold-soft:#eccfa0;
  --gold-deep:#a37c3f;
  --text:#f5efe3;
  --muted:#b9ad9a;
  --line:rgba(212,175,106,.14);
  --line-strong:rgba(236,207,160,.38);
  --r-lg:24px;--r-md:16px;--r-sm:12px;
  --shadow-lg:0 34px 80px rgba(0,0,0,.5);
  --shadow-md:0 18px 46px rgba(0,0,0,.36);
  --shadow-gold:0 16px 42px rgba(212,175,106,.26);
  --serif:'Cormorant Garamond',Georgia,serif;
  --sans:'Manrope',system-ui,sans-serif;
}
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth;overflow-x:hidden}
section{scroll-margin-top:92px}
body{font-family:var(--sans);color:var(--text);line-height:1.72;-webkit-font-smoothing:antialiased;overflow-x:hidden;position:relative;min-height:100vh}
body::before{content:"";position:fixed;inset:0;z-index:-2;background:
radial-gradient(1200px 700px at 85% -10%,rgba(212,175,106,.16),transparent 60%),
radial-gradient(1000px 640px at -10% 30%,rgba(212,175,106,.09),transparent 55%),
radial-gradient(1400px 900px at 50% 120%,rgba(163,124,63,.14),transparent 60%),
linear-gradient(180deg,#12100b,#0c0a07 45%,#100d09)}
body::after{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;background:
linear-gradient(115deg,transparent 30%,rgba(236,207,160,.028) 50%,transparent 70%),
radial-gradient(900px 600px at 50% 0%,rgba(0,0,0,0),rgba(0,0,0,.28))}
.orb{position:fixed;border-radius:50%;pointer-events:none;z-index:-1;will-change:transform}
.orb-1{width:560px;height:560px;left:-180px;top:10%;background:radial-gradient(circle,rgba(212,175,106,.13),transparent 65%);animation:orbFloat 18s ease-in-out infinite alternate}
.orb-2{width:480px;height:480px;right:-160px;top:40%;background:radial-gradient(circle,rgba(163,124,63,.12),transparent 65%);animation:orbFloat 24s ease-in-out infinite alternate-reverse}
.orb-3{width:640px;height:640px;left:28%;bottom:-240px;background:radial-gradient(circle,rgba(212,175,106,.08),transparent 65%);animation:orbFloat 30s ease-in-out infinite alternate}
@keyframes orbFloat{from{transform:translateY(-36px)}to{transform:translateY(44px)}}
.grain{position:fixed;inset:0;z-index:2147480000;pointer-events:none;opacity:.03;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.6'/%3E%3C/svg%3E")}
::selection{background:rgba(212,175,106,.32);color:#fff}
h1,h2,h3{font-family:var(--serif);overflow-wrap:break-word;word-break:break-word;letter-spacing:.3px}
img{max-width:100%;display:block}
a{text-decoration:none;color:inherit}
ul{list-style:none}
button{font-family:inherit;cursor:pointer}
.wrap{width:100%;max-width:1180px;margin:0 auto;padding:0 20px}
.progress{position:fixed;top:0;left:0;height:3px;z-index:300;background:linear-gradient(90deg,var(--gold-deep),var(--gold-soft),var(--gold));width:0%;box-shadow:0 0 14px rgba(236,207,160,.7);will-change:width}
#cursorGlow{position:fixed;left:0;top:0;width:340px;height:340px;border-radius:50%;pointer-events:none;z-index:55;background:radial-gradient(circle,rgba(212,175,106,.09),transparent 66%);mix-blend-mode:screen;will-change:transform;display:none}
@media(hover:hover) and (pointer:fine){#cursorGlow{display:block}}
header{position:fixed;top:0;left:0;right:0;z-index:200;background:rgba(14,12,9,.55);backdrop-filter:blur(18px) saturate(150%);-webkit-backdrop-filter:blur(18px) saturate(150%);transition:background .45s,box-shadow .45s}
header.solid{background:rgba(14,12,9,.92);box-shadow:0 12px 44px rgba(0,0,0,.45),inset 0 -1px 0 var(--line)}
.nav{display:flex;align-items:center;justify-content:space-between;height:78px;gap:12px}
.logo{display:flex;align-items:center;gap:13px;min-width:0;max-width:100%;cursor:pointer;transition:opacity .3s}
.logo:hover{opacity:.86}
.brand-ava-w{position:relative;flex-shrink:0;display:inline-flex}
.brand-ava-w::before{content:"";position:absolute;inset:-5px;border-radius:50%;border:1px solid rgba(236,207,160,.5);opacity:.7;animation:ringPulse 3.6s ease-in-out infinite}
@keyframes ringPulse{0%,100%{transform:scale(.94);opacity:.35}50%{transform:scale(1.08);opacity:.75}}
.brand-ava{width:46px;height:46px;border-radius:50%;object-fit:cover;border:1.5px solid rgba(236,207,160,.65);box-shadow:0 0 0 5px rgba(212,175,106,.1),0 0 24px rgba(212,175,106,.4);position:relative;z-index:1}
.logo .brand-txt{display:flex;flex-direction:column;min-width:0;line-height:1.15}
.logo .brand-txt .name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-family:var(--serif);font-size:26px;font-weight:600;color:#fff;line-height:1.05;background:linear-gradient(120deg,#fff,var(--gold-soft));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:.3px}
.logo .brand-txt .sub{color:var(--gold-soft);font-size:11px;font-weight:600;letter-spacing:2px;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:62vw;margin-top:3px;opacity:.85}
.menu{position:fixed;top:0;height:78px;right:max(20px,calc((100vw - 1220px)/2));display:flex;gap:24px;align-items:center;z-index:201}
.menu a{position:relative;color:rgba(255,255,255,.8);font-size:13px;font-weight:600;letter-spacing:.5px;transition:.3s;padding:6px 0;white-space:nowrap}
.menu a::after{content:"";position:absolute;left:0;bottom:0;width:100%;height:1.5px;background:linear-gradient(90deg,var(--gold-soft),var(--gold));transform:scaleX(0);transform-origin:left;transition:transform .4s cubic-bezier(.22,.61,.36,1);border-radius:2px}
.menu a:hover{color:#fff}
.menu a:hover::after{transform:scaleX(1)}
.menu a.active{color:var(--gold-soft)}
.menu a.active::after{transform:scaleX(1)}
.sheet-handle{display:none}
.menu-call{display:none}
.burger{display:none;background:none;border:none;cursor:pointer;width:44px;height:44px;position:relative;z-index:210;flex-shrink:0}
.burger span{position:absolute;left:7px;right:7px;height:2px;background:#fff;transition:.3s;border-radius:2px}
.burger span:nth-child(1){top:13px}
.burger span:nth-child(2){top:21px}
.burger span:nth-child(3){top:29px}
.burger.open span:nth-child(1){top:21px;transform:rotate(45deg)}
.burger.open span:nth-child(2){opacity:0}
.burger.open span:nth-child(3){top:21px;transform:rotate(-45deg)}
.scrim{position:fixed;inset:0;background:rgba(0,0,0,.5);opacity:0;visibility:hidden;transition:.35s;z-index:195;backdrop-filter:blur(3px)}
.scrim.show{opacity:1;visibility:visible}
[data-watermark]{position:relative}
[data-watermark]::before{content:attr(data-watermark);position:absolute;top:4%;right:2%;font-family:var(--serif);font-size:clamp(110px,16vw,230px);line-height:1;font-weight:600;color:transparent;-webkit-text-stroke:1px rgba(212,175,106,.07);white-space:nowrap;pointer-events:none;user-select:none;z-index:0}
[data-watermark] .wrap{position:relative;z-index:1}
.panel{position:relative;min-height:100vh;display:flex;align-items:center;padding:150px 0;overflow:hidden}
.panel .bg{position:absolute;inset:-14% 0;z-index:0;background-size:cover;background-position:center;will-change:transform;transform:translateZ(0)}
.panel .bg::after{content:"";position:absolute;inset:0;background:linear-gradient(to right,rgba(10,8,6,.94) 22%,rgba(10,8,6,.6) 58%,rgba(10,8,6,.75))}
.panel--hero .bg::before{content:"";position:absolute;inset:-8%;background-image:inherit;background-size:cover;background-position:center;animation:kenburns 22s ease-in-out infinite alternate;will-change:transform}
@keyframes kenburns{from{transform:scale(1)}to{transform:scale(1.1)}}
.panel--hero .bg::after{z-index:1}
.panel .content{position:relative;z-index:2;width:100%;will-change:transform;transform:translateZ(0)}
.panel--center .content{text-align:center}
.panel--center .bg::after{background:linear-gradient(180deg,rgba(10,8,6,.86),rgba(10,8,6,.62))}
.panel--dark .bg::after{background:linear-gradient(180deg,rgba(10,8,6,.9),rgba(10,8,6,.7))}
.panel + .panel{margin-top:16px}
.eyebrow{display:inline-flex;align-items:center;gap:12px;color:var(--gold-soft);letter-spacing:5px;text-transform:uppercase;font-size:12px;font-weight:600;margin-bottom:20px}
.eyebrow::before{content:"";width:42px;height:1px;background:linear-gradient(90deg,transparent,var(--gold))}
.eyebrow::after{content:"";width:42px;height:1px;background:linear-gradient(90deg,var(--gold),transparent)}
h1{font-size:clamp(34px,6vw,76px);font-weight:500;line-height:1.08;color:#fff;letter-spacing:.4px;text-shadow:0 5px 30px rgba(0,0,0,.5);overflow-wrap:break-word;word-break:break-word;max-width:100%}
h1 em{font-style:italic}
.sub{color:rgba(245,239,227,.9);font-size:clamp(16px,1.8vw,19.5px);font-weight:300;margin:24px 0 34px;max-width:580px;text-shadow:0 2px 16px rgba(0,0,0,.55);letter-spacing:.3px}
.btn-row{display:flex;gap:16px;flex-wrap:wrap}
.btn{position:relative;overflow:hidden;display:inline-flex;align-items:center;justify-content:center;gap:10px;min-height:48px;padding:15px 30px;font-size:13px;font-weight:700;letter-spacing:1.3px;text-transform:uppercase;transition:transform .4s cubic-bezier(.22,.61,.36,1),box-shadow .4s,filter .4s,background .4s,color .4s;cursor:pointer;border-radius:13px;border:none}
.btn-solid{background:linear-gradient(135deg,var(--gold-soft),var(--gold) 55%,var(--gold-deep));color:#17120b;box-shadow:var(--shadow-gold);animation:btnGlow 3.6s ease-in-out infinite}
@keyframes btnGlow{0%,100%{box-shadow:0 16px 42px rgba(212,175,106,.26)}50%{box-shadow:0 24px 62px rgba(236,207,160,.5)}}
.btn-solid:hover{transform:translateY(-4px);box-shadow:0 26px 60px rgba(212,175,106,.45)}
.btn-line{border:1px solid rgba(255,255,255,.4);color:#fff;background:rgba(255,255,255,.04)}
.btn-line:hover{background:rgba(255,255,255,.12);color:#fff;transform:translateY(-4px);box-shadow:0 20px 50px rgba(0,0,0,.35)}
.btn::after{content:"";position:absolute;top:0;left:-130%;width:55%;height:100%;background:linear-gradient(120deg,transparent,rgba(255,255,255,.4),transparent);transform:skewX(-20deg);transition:left .7s ease}
.btn:hover::after{left:145%}
.shimmer{background:linear-gradient(90deg,var(--gold-soft),#fff 35%,var(--gold-soft) 70%);background-size:220% auto;-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;animation:shimmerMove 3.4s linear infinite}
@keyframes shimmerMove{0%{background-position:0% center}100%{background-position:-220% center}}
h1 em.shimmer{-webkit-text-fill-color:transparent}
.cta h2.shimmer{-webkit-text-fill-color:transparent}
.scroll-cue{position:absolute;bottom:26px;left:50%;transform:translateX(-50%);z-index:5;color:rgba(255,255,255,.75);font-size:11px;letter-spacing:4px;text-transform:uppercase;text-align:center;animation:fadeInUp 1s ease .8s both}
.scroll-cue .line{width:1px;height:46px;background:linear-gradient(180deg,var(--gold-soft),transparent);margin:10px auto 0;animation:drip 2.4s infinite}
@keyframes drip{0%{transform:scaleY(0);transform-origin:top}50%{transform:scaleY(1);transform-origin:top}51%{transform-origin:bottom}100%{transform:scaleY(0);transform-origin:bottom}}
@keyframes fadeInUp{from{opacity:0;transform:translate(-50%,10px)}to{opacity:1;transform:translate(-50%,0)}}
.sec-head{max-width:740px;margin:0 auto 52px;text-align:center}
.sec-head .kicker{color:var(--gold-soft);letter-spacing:5px;text-transform:uppercase;font-size:11px;font-weight:600}
.sec-head h2{position:relative;font-size:clamp(30px,4.4vw,48px);font-weight:500;margin:16px 0 14px;line-height:1.14;color:#faf3e6;text-shadow:0 4px 22px rgba(0,0,0,.45),0 0 40px rgba(212,175,106,.14);letter-spacing:.3px}
.sec-head h2::before,.sec-head h2::after{content:"";position:absolute;top:50%;width:56px;height:1px;background:linear-gradient(90deg,transparent,var(--gold));transform:translateY(-50%);opacity:.7}
.sec-head h2::before{right:calc(100% + 26px)}
.sec-head h2::after{left:calc(100% + 26px)}
.sec-head p{color:var(--muted);font-size:15.5px;max-width:620px;margin:0 auto;letter-spacing:.2px}
h2.k{position:relative;font-size:clamp(32px,4.6vw,48px);color:#faf3e6;font-weight:500;margin:16px 0 14px;text-align:center;text-shadow:0 4px 22px rgba(0,0,0,.45),0 0 40px rgba(212,175,106,.14);letter-spacing:.3px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:24px;text-align:center}
.stat{padding:32px 16px;border-radius:var(--r-md);background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.07);transition:transform .45s,border-color .45s,box-shadow .45s}
.stat:hover{transform:translateY(-6px);border-color:rgba(236,207,160,.3);box-shadow:0 22px 54px rgba(0,0,0,.42),0 0 34px rgba(212,175,106,.05)}
.stat .num{font-family:var(--serif);font-size:58px;font-weight:500;line-height:1;background:linear-gradient(160deg,var(--gold-soft),var(--gold) 60%,var(--gold-deep));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;filter:drop-shadow(0 5px 16px rgba(212,175,106,.35))}
.stat .lbl{color:var(--muted);font-size:13.5px;margin-top:12px;letter-spacing:.3px}
.about{display:grid;grid-template-columns:1fr 1.1fr;gap:64px;align-items:center}
.about-card{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.07);padding:48px 40px;text-align:center;border-radius:var(--r-lg);box-shadow:var(--shadow-md);position:relative;overflow:hidden}
.about-card::before{content:"";position:absolute;top:0;left:20%;right:20%;height:1px;background:linear-gradient(90deg,transparent,var(--gold-soft),transparent);opacity:.6}
.avatar{width:130px;height:130px;border-radius:50%;margin:0 auto 22px;overflow:hidden;border:1.5px solid rgba(236,207,160,.65);box-shadow:0 0 0 7px rgba(212,175,106,.12),0 16px 40px rgba(0,0,0,.5);position:relative}
.avatar img{width:100%;height:100%;object-fit:cover}
.avatar::after{content:"";position:absolute;inset:0;border-radius:50%;box-shadow:inset 0 0 0 3px rgba(236,207,160,.4)}
.about-card h3{font-size:29px;color:#fff;letter-spacing:.3px}
.about-card .role{color:var(--gold-soft);font-size:13px;margin-top:5px;letter-spacing:.7px}
.about-card .sep{width:52px;height:1px;background:linear-gradient(90deg,transparent,var(--gold),transparent);margin:22px auto}
.about-card p{color:var(--muted);font-size:14.5px;line-height:1.76}
.about-body .kicker{color:var(--gold-soft);letter-spacing:5px;text-transform:uppercase;font-size:11px;font-weight:600}
.about-body h2{font-size:clamp(30px,3.6vw,44px);font-weight:500;margin:16px 0 22px;line-height:1.14;color:#faf3e6;text-shadow:0 4px 22px rgba(0,0,0,.45);letter-spacing:.3px}
.about-body p{color:var(--muted);font-size:15.5px;margin-bottom:26px;letter-spacing:.2px}
.features{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.features li{position:relative;padding-left:36px;color:var(--text);font-size:14.5px;overflow-wrap:break-word;transition:transform .3s;letter-spacing:.2px}
.features li:hover{transform:translateX(5px)}
.features li::before{content:"";position:absolute;left:0;top:4px;width:18px;height:18px;border:1.5px solid rgba(212,175,106,.6);border-radius:50%;background:rgba(212,175,106,.08)}
.features li::after{content:"✓";position:absolute;left:4px;top:4px;font-size:11px;color:var(--gold-soft);font-weight:800}
.consult .phone{display:inline-block;font-family:var(--sans);font-weight:800;font-size:clamp(30px,4.4vw,52px);letter-spacing:1px;margin-top:12px;white-space:nowrap;background:linear-gradient(120deg,var(--gold-soft),var(--gold));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;filter:drop-shadow(0 7px 22px rgba(212,175,106,.35))}
.consult p{color:var(--muted);font-size:15.5px;margin:30px auto 0;max-width:630px;line-height:1.82;overflow-wrap:break-word;letter-spacing:.2px}
.carousel{position:relative;max-width:1120px;margin:0 auto}
.car-track{display:flex;gap:20px;overflow-x:auto;scroll-snap-type:x mandatory;-webkit-overflow-scrolling:touch;overscroll-behavior-x:contain;touch-action:pan-x;padding:12px 8px 24px;scrollbar-width:none}
.car-track::-webkit-scrollbar{display:none}
.car-nav{position:absolute;top:38%;transform:translateY(-50%);width:48px;height:48px;border-radius:50%;background:rgba(14,12,9,.68);border:1px solid rgba(236,207,160,.35);color:var(--gold-soft);font-size:21px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:transform .4s,border-color .4s,background .4s;z-index:5;box-shadow:var(--shadow-md)}
.car-nav:hover{background:linear-gradient(135deg,var(--gold-soft),var(--gold));color:#17120b;transform:translateY(-50%) scale(1.08)}
.car-prev{left:-16px}.car-next{right:-16px}
.car-dots{display:flex;justify-content:center;gap:10px;margin-top:12px;flex-wrap:wrap}
.car-dot{width:8px;height:8px;min-width:8px;border-radius:99px;background:rgba(255,255,255,.2);cursor:pointer;transition:width .35s,background .35s,transform .35s;border:none;padding:0}
.car-dot:hover{background:rgba(236,207,160,.55)}
.car-dot.active{width:26px;background:linear-gradient(135deg,var(--gold-soft),var(--gold));box-shadow:0 0 12px rgba(236,207,160,.6)}
.swipe-hint{display:flex;align-items:center;justify-content:center;gap:8px;color:var(--muted);font-size:12px;letter-spacing:1.5px;text-transform:uppercase;margin-top:10px;animation:hintPulse 1.8s ease-in-out infinite}
.swipe-hint::after{content:"→";display:inline-block;animation:hintArrow 1.4s ease-in-out infinite}
@keyframes hintArrow{0%,100%{transform:translateX(0);opacity:.5}50%{transform:translateX(7px);opacity:1}}
@keyframes hintPulse{0%,100%{opacity:.55}50%{opacity:1}}
.car-slide{flex:0 0 auto;width:min(78vw,440px);scroll-snap-align:center;border-radius:var(--r-lg);overflow:hidden;border:1px solid rgba(255,255,255,.08);background:rgba(14,12,9,.55);cursor:zoom-in;transition:transform .5s cubic-bezier(.22,.61,.36,1),box-shadow .5s,border-color .5s;box-shadow:var(--shadow-md);position:relative}
.car-slide::before{content:"";position:absolute;inset:0;z-index:1;background:linear-gradient(100deg,rgba(255,255,255,.02),rgba(255,255,255,.07),rgba(255,255,255,.02));background-size:200% 100%;animation:shim 1.4s infinite}
@keyframes shim{0%{background-position:120% 0}100%{background-position:-120% 0}}
.car-slide:hover{transform:translateY(-8px);border-color:rgba(236,207,160,.3);box-shadow:var(--shadow-lg)}
.car-slide img{width:100%;height:300px;object-fit:cover;display:block;position:relative;z-index:2}
.car-slide:hover img{transform:scale(1.07)}
.rev-track{align-items:flex-start}
.rev-card{scroll-snap-align:center;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.07);border-radius:var(--r-lg);padding:24px 26px;width:min(82vw,520px);flex:0 0 auto;display:flex;flex-direction:column;box-shadow:var(--shadow-md);position:relative;overflow:hidden;transition:transform .5s,box-shadow .5s,border-color .5s}
.rev-card:hover{transform:translateY(-8px);border-color:rgba(236,207,160,.28);box-shadow:var(--shadow-lg)}
.rev-card::before{content:"";position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--gold-soft),transparent);opacity:.75}
.rev-head{display:flex;align-items:center;gap:14px;margin-bottom:14px;flex-wrap:wrap}
.rev-ava{width:50px;height:50px;border-radius:50%;object-fit:cover;border:1.5px solid rgba(236,207,160,.6);box-shadow:0 0 0 4px rgba(212,175,106,.1),0 0 14px rgba(212,175,106,.32);flex-shrink:0}
.rev-name{color:#fff;font-weight:700;font-size:14.5px}
.rev-sub{color:var(--muted);font-size:11px;margin-top:2px}
.rev-stars{color:var(--gold-soft);letter-spacing:3px;font-size:14px;margin-left:auto;white-space:nowrap;text-shadow:0 0 14px rgba(236,207,160,.45)}
.rev-text{color:#ece2cd;font-size:13.5px;line-height:1.66;font-weight:300;text-align:left;overflow-wrap:break-word;word-break:break-word;letter-spacing:.1px}
.rev-video{margin-top:14px;border-radius:var(--r-md);overflow:hidden;border:1px solid rgba(255,255,255,.08);box-shadow:var(--shadow-md)}
.video-box{position:relative;width:100%;height:260px;background-size:cover;background-position:center;cursor:pointer;display:flex;align-items:center;justify-content:center;background-color:#0b0907}
.video-box::after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(10,8,6,.12),rgba(10,8,6,.34));transition:.3s}
.video-box:hover::after{background:linear-gradient(180deg,rgba(10,8,6,.02),rgba(10,8,6,.2))}
.vb-play{position:relative;z-index:2;width:64px;height:64px;border-radius:50%;border:1px solid rgba(236,207,160,.7);background:rgba(14,12,9,.55);color:var(--gold-soft);display:flex;align-items:center;justify-content:center;cursor:pointer;transition:transform .35s,background .35s;box-shadow:0 0 0 8px rgba(212,175,106,.14),0 0 30px rgba(212,175,106,.4);animation:playPulse 2.4s ease-in-out infinite}
@keyframes playPulse{0%,100%{box-shadow:0 0 0 8px rgba(212,175,106,.14),0 0 30px rgba(212,175,106,.4)}50%{box-shadow:0 0 0 14px rgba(212,175,106,.08),0 0 44px rgba(212,175,106,.6)}}
.video-box:hover .vb-play{transform:scale(1.1);background:linear-gradient(135deg,var(--gold-soft),var(--gold));color:#17120b}
.vb-play svg{width:22px;height:22px;fill:currentColor;margin-left:3px}
.video-box iframe{position:absolute;inset:0;width:100%;height:100%;border:0}
.svc-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:22px}
.svc{position:relative;background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.07);padding:38px 30px;transition:transform .5s cubic-bezier(.22,.61,.36,1),box-shadow .5s,border-color .5s;border-radius:var(--r-lg);overflow-wrap:break-word;overflow:hidden}
.svc::before{content:"";position:absolute;top:0;left:22%;right:22%;height:1px;background:linear-gradient(90deg,transparent,var(--gold-soft),transparent);opacity:0;transition:.5s}
.svc:hover{transform:translateY(-8px);background:rgba(255,255,255,.05);box-shadow:var(--shadow-lg);border-color:rgba(236,207,160,.26)}
.svc:hover::before{opacity:.7}
.svc svg{width:34px;height:34px;stroke:var(--gold-soft);fill:none;stroke-width:1.4;margin-bottom:20px;transition:transform .55s cubic-bezier(.22,.61,.36,1)}
.svc:hover svg{transform:scale(1.12) rotate(-4deg)}
.svc h3{font-size:23px;color:#fff;margin-bottom:9px;letter-spacing:.3px}
.svc p{color:var(--muted);font-size:14px;line-height:1.7;letter-spacing:.1px}
.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:22px}
.step{position:relative;padding:34px 26px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.07);border-radius:var(--r-lg);transition:transform .45s cubic-bezier(.22,.61,.36,1),box-shadow .45s,border-color .45s;overflow-wrap:break-word;overflow:hidden}
.step:hover{transform:translateY(-7px);border-color:rgba(236,207,160,.28);box-shadow:var(--shadow-md)}
.step .n{font-family:var(--serif);font-size:54px;line-height:1;background:linear-gradient(160deg,var(--gold-soft),var(--gold-deep));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;transition:transform .45s}
.step:hover .n{transform:scale(1.1)}
.step h3{font-size:22px;color:#fff;margin:14px 0 8px;letter-spacing:.3px}
.step p{color:var(--muted);font-size:14px;line-height:1.7;letter-spacing:.1px}
.guar-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:22px}
.guar{position:relative;background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.07);padding:38px 26px;text-align:center;transition:transform .45s,box-shadow .45s,border-color .45s;border-radius:var(--r-lg);overflow-wrap:break-word;overflow:hidden}
.guar::before{content:"";position:absolute;top:0;left:25%;right:25%;height:1px;background:linear-gradient(90deg,transparent,var(--gold-soft),transparent);opacity:0;transition:.45s}
.guar:hover{transform:translateY(-8px);box-shadow:var(--shadow-lg);border-color:rgba(236,207,160,.26)}
.guar:hover::before{opacity:.7}
.guar .ico{width:54px;height:54px;margin:0 auto 18px;border:1px solid rgba(236,207,160,.35);border-radius:50%;display:flex;align-items:center;justify-content:center;color:var(--gold-soft);background:radial-gradient(circle at 30% 30%,rgba(236,207,160,.16),rgba(212,175,106,.03));box-shadow:0 0 22px rgba(212,175,106,.16);transition:transform .45s}
.guar:hover .ico{transform:scale(1.12) rotate(6deg)}
.guar .ico svg{width:23px;height:23px;stroke:currentColor;fill:none;stroke-width:1.5}
.guar h3{font-size:18px;color:#fff;margin-bottom:8px;letter-spacing:.2px}
.guar p{color:var(--muted);font-size:13px;line-height:1.7;letter-spacing:.1px}
.city-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:22px}
.city{position:relative;padding:38px 28px;border-radius:var(--r-lg);background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.07);text-align:center;transition:transform .45s,box-shadow .45s,border-color .45s;overflow:hidden}
.city::before{content:"";position:absolute;top:0;left:25%;right:25%;height:1px;background:linear-gradient(90deg,transparent,var(--gold-soft),transparent);opacity:0;transition:.45s}
.city:hover{transform:translateY(-7px);box-shadow:var(--shadow-lg);border-color:rgba(236,207,160,.26)}
.city:hover::before{opacity:.7}
.city .city-name{font-family:var(--serif);font-size:28px;color:#fff;font-weight:500;letter-spacing:.4px}
.city .city-line{width:42px;height:1px;background:linear-gradient(90deg,transparent,var(--gold),transparent);margin:14px auto}
.city p{color:var(--muted);font-size:14px;line-height:1.68;letter-spacing:.1px}
.contact-grid{display:grid;grid-template-columns:1fr 1fr;gap:56px;align-items:start}
.contact-info h2{font-size:clamp(30px,4.1vw,46px);color:#faf3e6;margin:16px 0 14px;line-height:1.12;text-shadow:0 4px 22px rgba(0,0,0,.45);letter-spacing:.3px}
.contact-info .kicker{color:var(--gold-soft);letter-spacing:5px;text-transform:uppercase;font-size:11px;font-weight:600}
.contact-info>p{color:var(--muted);font-size:15.5px;margin-bottom:32px;letter-spacing:.2px}
.c-line{display:flex;align-items:flex-start;gap:20px;margin-bottom:24px;transition:transform .4s}
.c-line:hover{transform:translateX(6px)}
.c-ico{width:44px;height:44px;border:1px solid rgba(236,207,160,.35);border-radius:50%;display:flex;align-items:center;justify-content:center;color:var(--gold-soft);background:radial-gradient(circle at 30% 30%,rgba(236,207,160,.15),rgba(212,175,106,.02));flex-shrink:0;box-shadow:0 0 18px rgba(212,175,106,.14);transition:transform .45s}
.c-line:hover .c-ico{transform:scale(1.1)}
.c-ico svg{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:1.5}
.c-line .lab{font-size:10.5px;letter-spacing:2.5px;text-transform:uppercase;color:var(--muted);margin-bottom:4px}
.c-line .val{font-size:18px;font-weight:600;color:var(--text);overflow-wrap:break-word;word-break:break-word;letter-spacing:.2px}
.c-line a.val:hover{color:var(--gold-soft)}
.call-block{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.07);padding:46px 36px;text-align:center;border-radius:var(--r-lg);box-shadow:var(--shadow-md);position:relative;overflow:hidden}
.call-block::before{content:"";position:absolute;top:0;left:20%;right:20%;height:1px;background:linear-gradient(90deg,transparent,var(--gold-soft),transparent);opacity:.6}
.call-block .cb-lab{font-size:12px;letter-spacing:4px;text-transform:uppercase;color:var(--gold-soft)}
.call-block .cb-num{display:block;font-family:var(--sans);font-weight:800;font-size:clamp(27px,3.6vw,44px);color:#fff;margin:14px 0 18px;white-space:nowrap;transition:color .3s,text-shadow .3s;text-shadow:0 5px 22px rgba(0,0,0,.42);letter-spacing:.4px}
.call-block .cb-num:hover{color:var(--gold-soft);text-shadow:0 0 30px rgba(236,207,160,.5)}
.call-block .cb-hint{color:var(--muted);font-size:14px;line-height:1.82;overflow-wrap:break-word;letter-spacing:.1px}
.contact-actions{display:flex;flex-direction:column;gap:12px;margin-top:24px}
.c-action{display:flex;align-items:center;justify-content:center;gap:11px;width:100%;min-height:52px;padding:15px 18px;border-radius:var(--r-sm);font-weight:700;font-size:14.5px;letter-spacing:.4px;transition:transform .4s,background .4s,filter .4s,box-shadow .4s;color:#fff}
.c-action svg{width:19px;height:19px;fill:none;stroke:currentColor;stroke-width:1.8}
.c-action.c-call{background:linear-gradient(135deg,var(--gold-soft),var(--gold));color:#17120b;box-shadow:var(--shadow-gold)}
.c-action.c-call:hover{filter:brightness(1.08);transform:translateY(-4px);box-shadow:0 22px 50px rgba(212,175,106,.42)}
.c-action.c-tg{background:rgba(64,169,242,.12);border:1px solid rgba(64,169,242,.38);color:#8fd0ff}
.c-action.c-tg:hover{background:rgba(64,169,242,.24);transform:translateY(-4px)}
.c-action.c-max{background:rgba(177,88,252,.12);border:1px solid rgba(177,88,252,.38);color:#e0b8ff}
.c-action.c-max:hover{background:rgba(177,88,252,.24);transform:translateY(-4px)}
.cta{text-align:center;padding:110px 0;position:relative}
.cta h2{font-size:clamp(32px,4.6vw,52px);color:#faf3e6;font-weight:500;margin-bottom:16px;text-shadow:0 5px 26px rgba(0,0,0,.45);letter-spacing:.3px}
.cta p{color:var(--muted);font-size:16.5px;max-width:630px;margin:0 auto 34px;overflow-wrap:break-word;letter-spacing:.2px}
footer{position:relative;background:linear-gradient(180deg,rgba(14,12,9,.4),rgba(10,8,6,.97));color:var(--muted);padding:52px 20px 60px;text-align:center;font-size:13px;border-top:1px solid rgba(255,255,255,.06)}
footer::before{content:"";position:absolute;top:-1px;left:50%;transform:translateX(-50%);width:min(420px,72%);height:1px;background:linear-gradient(90deg,transparent,var(--gold),transparent)}
footer .flogo{font-family:var(--serif);font-size:28px;color:#fff;margin-bottom:8px;line-height:1.3;letter-spacing:.3px}
footer .flogo span{color:var(--gold-soft);font-size:13px;font-family:var(--sans);font-weight:500;letter-spacing:1px}
.social-row{display:flex;justify-content:center;gap:14px;margin:22px 0 18px;flex-wrap:wrap}
.soc{display:inline-flex;align-items:center;justify-content:center;width:46px;height:46px;min-width:46px;min-height:46px;border-radius:50%;border:1px solid rgba(236,207,160,.32);color:var(--gold-soft);background:rgba(212,175,106,.06);transition:transform .35s,background .35s,box-shadow .35s}
.soc svg{width:19px;height:19px;stroke:currentColor;fill:none;stroke-width:1.6}
.soc:hover{background:linear-gradient(135deg,var(--gold-soft),var(--gold));color:#17120b;transform:translateY(-4px);box-shadow:var(--shadow-gold)}
.cookie-bar{position:fixed;bottom:16px;left:50%;transform:translate(-50%,140%);z-index:400;background:rgba(14,12,9,.93);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);border:1px solid rgba(255,255,255,.08);border-radius:var(--r-md);padding:16px 20px;display:flex;align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap;box-shadow:var(--shadow-lg);width:min(680px,calc(100vw - 32px));transition:transform .6s cubic-bezier(.22,.61,.36,1)}
.cookie-bar.show{transform:translate(-50%,0)}
.cookie-bar p{color:var(--muted);font-size:13px;max-width:720px;line-height:1.5}
.cookie-bar .btn{flex-shrink:0;padding:12px 26px}
.lightbox{position:fixed;inset:0;z-index:3000;background:rgba(8,6,4,.96);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);display:none;align-items:center;justify-content:center;flex-direction:column;gap:14px}
.lightbox.open{display:flex;animation:lbFade .3s ease}
@keyframes lbFade{from{opacity:0}to{opacity:1}}
.lb-stage{position:relative;width:100%;max-width:1180px;height:calc(100vh - 130px);display:flex;align-items:center;justify-content:center;overflow:hidden;touch-action:none}
.lb-stage img{max-width:94%;max-height:100%;border-radius:var(--r-lg);border:1px solid rgba(236,207,160,.55);box-shadow:0 26px 90px rgba(0,0,0,.8);cursor:grab;transition:transform .18s ease-out;will-change:transform;user-select:none;-webkit-user-drag:none}
.lb-stage img:active{cursor:grabbing}
.lb-bar{display:flex;align-items:center;justify-content:center;gap:20px}
.lb-count{color:var(--muted);font-size:13px;min-width:70px;text-align:center}
.lb-close{position:absolute;top:18px;right:24px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);color:#fff;font-size:28px;cursor:pointer;z-index:5;line-height:1;width:48px;height:48px;min-width:48px;min-height:48px;border-radius:50%;display:flex;align-items:center;justify-content:center;transition:transform .3s,background .3s}
.lb-close:hover{transform:rotate(90deg);background:rgba(236,207,160,.18)}
.lb-nav{width:50px;height:50px;min-width:50px;min-height:50px;border-radius:50%;background:rgba(14,12,9,.6);border:1px solid rgba(236,207,160,.5);color:var(--gold-soft);font-size:24px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:background .3s,transform .3s}
.lb-nav:hover{background:linear-gradient(135deg,var(--gold-soft),var(--gold));color:#17120b;transform:scale(1.06)}
.js .reveal{opacity:0;transform:translateY(26px);filter:blur(10px);transition:opacity .8s ease,transform .8s cubic-bezier(.22,.61,.36,1),filter .8s ease}
.js .reveal.in{opacity:1;transform:none;filter:none}
.stats .reveal:nth-child(1){transition-delay:.05s}.stats .reveal:nth-child(2){transition-delay:.15s}.stats .reveal:nth-child(3){transition-delay:.25s}.stats .reveal:nth-child(4){transition-delay:.35s}
.steps .reveal:nth-child(2){transition-delay:.08s}.steps .reveal:nth-child(3){transition-delay:.16s}.steps .reveal:nth-child(4){transition-delay:.24s}.steps .reveal:nth-child(5){transition-delay:.32s}.steps .reveal:nth-child(6){transition-delay:.4s}
.svc-grid .reveal:nth-child(2){transition-delay:.08s}.svc-grid .reveal:nth-child(3){transition-delay:.16s}.svc-grid .reveal:nth-child(4){transition-delay:.24s}.svc-grid .reveal:nth-child(5){transition-delay:.32s}.svc-grid .reveal:nth-child(6){transition-delay:.4s}
.guar-grid .reveal:nth-child(2){transition-delay:.08s}.guar-grid .reveal:nth-child(3){transition-delay:.16s}.guar-grid .reveal:nth-child(4){transition-delay:.24s}
.city-grid .reveal:nth-child(2){transition-delay:.12s}.city-grid .reveal:nth-child(3){transition-delay:.24s}
@supports (content-visibility:auto){.panel{content-visibility:auto;contain-intrinsic-size:auto 820px}}
@media(max-width:1180px){.menu{right:max(16px,calc((100vw - 1080px)/2));gap:20px}}
@media(max-width:1024px){.stats{grid-template-columns:repeat(2,1fr);gap:30px}.svc-grid{grid-template-columns:repeat(2,1fr)}.guar-grid{grid-template-columns:repeat(2,1fr)}.city-grid{grid-template-columns:repeat(3,1fr)}.panel{padding:132px 0}}
@media(max-width:860px){.menu{position:fixed;top:auto;left:0;right:0;bottom:0;width:100%;max-height:82vh;background:linear-gradient(180deg,#16130e,#0b0907);flex-direction:column;justify-content:flex-start;gap:4px;padding:12px 24px calc(22px + env(safe-area-inset-bottom));transform:translateY(105%);transition:transform .45s cubic-bezier(.22,.61,.36,1);z-index:205;opacity:1;visibility:visible;box-shadow:0 -22px 54px rgba(0,0,0,.55);border-radius:26px 26px 0 0;overflow-y:auto;height:auto;border-top:1px solid rgba(236,207,160,.2)}.menu.open{transform:none}.sheet-handle{display:flex;justify-content:center;padding:4px 0 8px}.sheet-handle span{width:42px;height:4px;border-radius:99px;background:rgba(236,207,160,.35)}.menu a{font-size:19px;font-family:var(--serif);color:#fff;border-bottom:1px solid rgba(236,207,160,.12);padding:13px 6px;display:flex;align-items:center;min-height:48px}.menu a::after{display:none}.menu a:hover{color:var(--gold-soft)}.menu a.active{color:var(--gold-soft)}.menu-call{display:block;margin-top:10px;padding-top:10px;border-top:1px solid rgba(236,207,160,.14)}.menu-call a{display:flex;align-items:center;justify-content:center;gap:10px;width:100%;min-height:52px;background:linear-gradient(135deg,var(--gold-soft),var(--gold));color:#17120b;font-family:var(--sans);font-size:14.5px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;border:none;border-radius:var(--r-sm);padding:15px 18px;box-shadow:var(--shadow-gold)}.burger{display:block}.scrim{display:block}.about{grid-template-columns:1fr;gap:36px}.features{grid-template-columns:1fr}.steps{grid-template-columns:1fr;gap:20px}.contact-grid{grid-template-columns:1fr;gap:36px}.city-grid{grid-template-columns:1fr}.panel{padding:116px 0}.car-nav{display:none}.rev-card{width:86vw}.video-box{height:230px}}
@media(max-width:768px){.stats{grid-template-columns:1fr 1fr}.guar-grid{grid-template-columns:1fr 1fr}.svc-grid{grid-template-columns:1fr}.steps{grid-template-columns:1fr}.panel{padding:104px 0 60px}}
@media(max-width:520px){.logo .brand-ava{width:40px;height:40px}.logo .brand-txt .name{font-size:20px}.logo .brand-txt .sub{font-size:9.5px;max-width:54vw;letter-spacing:1.2px}.nav{height:64px}.panel{min-height:auto;padding:96px 0 56px}h1{font-size:31px}.sub{font-size:15px;margin:18px 0 26px}.btn-row{width:100%}.btn{width:100%;text-align:center;padding:14px 20px;font-size:12px}.stat .num{font-size:44px}.sec-head{margin-bottom:38px}.sec-head h2::before,.sec-head h2::after{display:none}.scroll-cue{display:none}.car-slide{width:84vw}.car-slide img{height:205px}.rev-card{width:92vw;padding:17px}.rev-head{gap:10px}.rev-ava{width:44px;height:44px}.rev-name{font-size:13.5px}.rev-sub{font-size:10px}.rev-stars{font-size:12.5px;display:block;margin:6px 0 0}.rev-text{font-size:12.5px;line-height:1.56}.video-box{height:190px}.consult .phone{font-size:25px}.call-block .cb-num{font-size:22px}.menu{padding:10px 20px calc(18px + env(safe-area-inset-bottom))}.lb-nav{width:44px;height:44px;min-width:44px;min-height:44px;font-size:22px}.lb-close{width:44px;height:44px;min-width:44px;min-height:44px}.cookie-bar{bottom:10px;padding:14px 16px}.city{padding:28px 22px}.contact-info>p{margin-bottom:24px}}
@media(max-width:380px){.car-slide{width:88vw}.car-slide img{height:190px}.rev-card{width:94vw;padding:14px}.rev-text{font-size:12px}.video-box{height:170px}.btn{font-size:11px}}

</style>
<style id="designVars">
:root{--bg:{{design.bg}};--gold:{{design.gold}};--gold-soft:{{design.gold_soft}};--gold-deep:{{design.gold_deep}};--text:{{design.text}};--muted:{{design.muted}};--r-lg:{{design.radius}};--r-md:{{design.radius}};--r-sm:{{design.radius}}}
.wrap{max-width:{{design.container}}}
body::before{background:radial-gradient(1200px 700px at 85% -10%,rgba(212,175,106,.16),transparent 60%),radial-gradient(1000px 640px at -10% 30%,rgba(212,175,106,.09),transparent 55%),radial-gradient(1400px 900px at 50% 120%,rgba(163,124,63,.14),transparent 60%),linear-gradient(180deg,#12100b,{{design.bg}} 45%,#100d09)}
header{background:{{design.bg}}8c}
header.solid{background:{{design.bg}}eb}
</style>
<style id="cmsExtras">
.empty{color:var(--muted);font-size:15px;text-align:center;max-width:560px;margin:0 auto;padding:28px;border:1px dashed rgba(236,207,160,.25);border-radius:var(--r-lg)}
.section-note{color:var(--muted);margin-top:24px;text-align:center;font-size:13.5px}
.section-note a{color:var(--gold-soft);font-weight:600}
</style>
<style id="beautyCSS">
/* ====== Анимации и оформление (CMS) ====== */
@keyframes rvUp{from{opacity:0;transform:translateY(36px);filter:blur(12px)}to{opacity:1;transform:none;filter:none}}
@keyframes rvR{from{opacity:0;transform:translateX(42px)}to{opacity:1;transform:none}}
@keyframes rvZ{from{opacity:0;transform:scale(.9)}to{opacity:1;transform:scale(1)}}
@keyframes floatY{0%,100%{transform:translateY(0)}50%{transform:translateY(-9px)}}
@keyframes sweepX{0%{background-position:160% 0}100%{background-position:-160% 0}}
@keyframes shineMove{0%{transform:translateX(-160%) skewX(-18deg)}100%{transform:translateX(320%) skewX(-18deg)}}
@keyframes rippleGo{to{transform:scale(3.4);opacity:0}}
@keyframes pulseGold{0%,100%{box-shadow:0 16px 42px rgba(212,175,106,.26)}50%{box-shadow:0 22px 58px rgba(236,207,160,.5),0 0 34px rgba(212,175,106,.32)}}
@keyframes numGlow{0%,100%{filter:drop-shadow(0 5px 16px rgba(212,175,106,.35))}50%{filter:drop-shadow(0 10px 30px rgba(236,207,160,.62))}}
@keyframes driftGlow{0%,100%{opacity:.35}50%{opacity:.9}}
@keyframes wordUp{0%{opacity:0;transform:translate3d(0,24px,0) scale(.97)}55%{opacity:1}100%{opacity:1;transform:none}}
@keyframes lineGrow{from{transform:scaleX(0);opacity:0}to{transform:scaleX(1);opacity:.75}}

/* появление по скроллу */
.js .rv{opacity:0;transform:translateY(36px);filter:blur(12px);transition:opacity .95s cubic-bezier(.22,.61,.36,1),transform .95s cubic-bezier(.22,.61,.36,1),filter .95s cubic-bezier(.22,.61,.36,1)}
.js .rv.rv-right{transform:translateX(42px)}
.js .rv.rv-zoom{transform:scale(.92)}
.js .rv.in{opacity:1;transform:none;filter:none}

/* карточки: подъём, свечение, бегущий блик (исправляет перебитый hover у .reveal) */
.svc,.step,.guar,.city,.rev-card,.about-card,.call-block,.stat{position:relative;transition:transform .55s cubic-bezier(.22,.61,.36,1),box-shadow .55s,border-color .55s,background .55s}
.js .svc.reveal.in:hover,.js .step.reveal.in:hover,.js .guar.reveal.in:hover,.js .city.reveal.in:hover,
.js .rev-card.reveal.in:hover,.js .stat.reveal.in:hover,.js .about-card.reveal.in:hover,.js .call-block.reveal.in:hover,
.svc:hover,.step:hover,.guar:hover,.city:hover,.rev-card:hover,.about-card:hover,.call-block:hover,.stat:hover{transform:translateY(-10px);border-color:rgba(236,207,160,.36);box-shadow:0 32px 74px rgba(0,0,0,.55),0 0 46px rgba(212,175,106,.16)}
.svc::after,.step::after,.guar::after,.city::after,.rev-card::after,.stat::after,.about-card::after,.call-block::after{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;opacity:0;background:linear-gradient(115deg,transparent 34%,rgba(236,207,160,.12) 50%,transparent 66%);background-size:260% 100%;background-position:160% 0;transition:opacity .45s}
.svc:hover::after,.step:hover::after,.guar:hover::after,.city:hover::after,.rev-card:hover::after,.stat:hover::after,.about-card:hover::after,.call-block:hover::after{opacity:1;animation:sweepX 1.7s ease-in-out}
.svc svg,.guar .ico,.c-ico,.step .n{animation:floatY 5.2s ease-in-out infinite}
.svc:nth-child(2n) svg,.guar:nth-child(2n) .ico,.c-line:nth-child(2n) .c-ico,.step:nth-child(2n) .n{animation-delay:-1.4s}
.svc:nth-child(3n) svg,.guar:nth-child(3n) .ico,.c-line:nth-child(3n) .c-ico,.step:nth-child(3n) .n{animation-delay:-2.7s}
.c-line:hover .c-ico{animation-play-state:paused}

/* заголовки секций: золотые линии «прорастают» */
.sec-head h2::before,.sec-head h2::after{transform:translateY(-50%) scaleX(0);opacity:0;transition:transform .95s cubic-bezier(.22,.61,.36,1),opacity .7s}
.sec-head.in h2::before,.sec-head.in h2::after{transform:translateY(-50%) scaleX(1);opacity:.75}
.sec-head h2{text-shadow:0 6px 26px rgba(0,0,0,.5),0 0 46px rgba(212,175,106,.18)}

/* кнопки: блик, отклик, свечение */
.btn{transition:transform .42s cubic-bezier(.22,.61,.36,1),box-shadow .42s,filter .42s,background .42s,color .42s}
.btn:hover{transform:translateY(-4px) scale(1.02)}
.btn:active{transform:translateY(-1px) scale(.985)}
.btn-solid{overflow:hidden}
.btn-solid::before{content:"";position:absolute;top:0;left:-40%;width:45%;height:100%;background:linear-gradient(90deg,transparent,rgba(255,255,255,.6),transparent);animation:shineMove 3.9s ease-in-out infinite;pointer-events:none;z-index:1}
.btn-solid:hover::before{animation-duration:1.3s}
.btn-line{overflow:hidden}
.btn-line::before{content:"";position:absolute;inset:0;background:linear-gradient(120deg,rgba(236,207,160,.18),transparent 55%);opacity:0;transition:opacity .45s}
.btn-line:hover::before{opacity:1}
.c-action,.soc,.car-dot,.lb-nav,.menu a,.svc,.step,.guar,.city,.rev-card,.stat,.c-line,.btn{position:relative;overflow:hidden}
.ripple-el{position:absolute;border-radius:50%;pointer-events:none;z-index:4;background:radial-gradient(circle,rgba(255,255,255,.55),rgba(255,255,255,0) 70%);transform:scale(0);animation:rippleGo .8s cubic-bezier(.2,.6,.3,1) forwards}
.btn-solid>.ripple-el,.c-action.c-call>.ripple-el,.soc>.ripple-el,.car-dot.active>.ripple-el{background:radial-gradient(circle,rgba(23,18,11,.38),rgba(23,18,11,0) 70%)}
.c-action:hover{transform:translateY(-4px) scale(1.015)}
.soc:hover{transform:translateY(-5px) rotate(6deg) scale(1.06)}
.car-dot:hover{transform:scale(1.3)}
.car-nav{transition:background .35s,transform .35s,box-shadow .35s}
.car-nav:hover{transform:translateY(-50%) scale(1.12)}
.lb-nav:hover{transform:scale(1.12)}
.lb-close:hover{transform:rotate(90deg) scale(1.06)}
.lb-close{overflow:hidden}
.c-line:hover{transform:translateX(8px)}

/* подчёркивание «прорастает» у ссылок */
.c-line a.val,.section-note a,footer a,.cookie-bar a{background-image:linear-gradient(90deg,var(--gold-soft),var(--gold));background-repeat:no-repeat;background-size:0 1px;background-position:0 100%;transition:background-size .45s,color .3s}
.c-line a.val:hover,.section-note a:hover,footer a:hover,.cookie-bar a:hover{background-size:100% 1px;color:var(--gold-soft)}

/* главный экран, цифры, подсказки */
#heroTitle{text-shadow:0 8px 42px rgba(0,0,0,.62),0 0 80px rgba(212,175,106,.16)}
#heroTitle.split .w{display:inline-block;opacity:0;animation:wordUp .72s cubic-bezier(.22,1,.36,1) forwards}
#heroTitle.split-done .w{opacity:1!important;animation:none!important}
.stat .num{animation:numGlow 3.6s ease-in-out infinite}
.stat:hover .num{transform:scale(1.06)}
.swipe-hint,.scroll-cue{animation:hintPulse 2s ease-in-out infinite}
.about-card .avatar{animation:floatY 6s ease-in-out infinite}
.empty{animation:driftGlow 3s ease-in-out infinite}
.city .city-name{background:linear-gradient(120deg,#fff 18%,var(--gold-soft) 55%,#fff 92%);background-size:220% auto;-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;animation:sweepX 7s linear infinite}
.call-block .cb-num{background:linear-gradient(120deg,#fff 8%,var(--gold-soft) 55%,#fff 95%);background-size:230% auto;-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;animation:sweepX 7.5s linear infinite}
.cookie-bar .btn{animation:pulseGold 3.4s ease-in-out infinite}
.cookie-bar.show{animation:rvUp .6s cubic-bezier(.22,.61,.36,1)}
.lightbox.open .lb-stage img{animation:rvZ .5s cubic-bezier(.22,.61,.36,1)}
.menu.open li{animation:rvR .5s cubic-bezier(.22,.61,.36,1) both}
.menu.open li:nth-child(1){animation-delay:.02s}.menu.open li:nth-child(2){animation-delay:.06s}.menu.open li:nth-child(3){animation-delay:.1s}
.menu.open li:nth-child(4){animation-delay:.14s}.menu.open li:nth-child(5){animation-delay:.18s}.menu.open li:nth-child(6){animation-delay:.22s}
.menu.open li:nth-child(7){animation-delay:.26s}.menu.open li:nth-child(8){animation-delay:.3s}.menu.open li:nth-child(9){animation-delay:.34s}
/* ====== усиленные анимации ====== */
@keyframes h2sweep{0%{background-position:180% 0}100%{background-position:-180% 0}}
@keyframes starShine{0%{background-position:190% 0}100%{background-position:-190% 0}}
@keyframes logoPop{0%{opacity:0;transform:scale(.72) translateY(-10px)}60%{opacity:1;transform:scale(1.07)}100%{opacity:1;transform:none}}
@keyframes headerDown{from{transform:translateY(-104%)}to{transform:none}}
@keyframes sparkFly{0%{transform:translate(0,0) scale(1);opacity:1}100%{transform:translate(var(--dx),var(--dy)) scale(.15);opacity:0}}
@keyframes slideIn{from{opacity:0;transform:translateY(34px) scale(.96)}to{opacity:1;transform:none}}
@keyframes navGlow{0%,100%{box-shadow:0 0 0 0 rgba(212,175,106,0)}50%{box-shadow:0 0 18px 2px rgba(212,175,106,.35)}}
header{animation:headerDown .75s cubic-bezier(.22,.61,.36,1) both}
.brand-ava-w{animation:logoPop .95s cubic-bezier(.34,1.56,.64,1) .1s both}
.brand-ava-w::before{animation:ringPulse 3.6s ease-in-out infinite,ringSpin 14s linear infinite}
.eyebrow,.sec-head .kicker,.about-body .kicker,.contact-info .kicker,.consult .kicker,.carousel .kicker{background:linear-gradient(90deg,rgba(236,207,160,.85),#fff 50%,rgba(236,207,160,.85));background-size:220% auto;-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;animation:h2sweep 5.5s linear infinite}
.sec-head h2,.about-body h2,.contact-info h2,h2.k{background-image:linear-gradient(100deg,#faf3e6 0%,#faf3e6 36%,#eccfa0 50%,#faf3e6 64%,#faf3e6 100%);background-size:230% auto;-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;animation:h2sweep 8s linear infinite}
.cta h2.shimmer,h1 em.shimmer{background-image:linear-gradient(90deg,#eccfa0,#fff 35%,#eccfa0 70%,#eccfa0 100%);background-size:220% auto;-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;animation:h2sweep 4.5s linear infinite}
.rev-stars{background:linear-gradient(90deg,var(--gold-soft),#fff 50%,var(--gold-soft));background-size:200% auto;-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;animation:starShine 3.4s linear infinite}
[data-watermark]::before{animation:driftGlow 7s ease-in-out infinite}
.menu a:hover{transform:translateY(-2px);text-shadow:0 0 16px rgba(236,207,160,.55)}
.menu a.active{animation:navGlow 3.4s ease-in-out infinite;border-radius:8px}
.car-slide.pop,.rev-card.pop{animation:slideIn .85s cubic-bezier(.22,.61,.36,1) both}
.spark{position:fixed;width:7px;height:7px;border-radius:50%;pointer-events:none;z-index:9998;background:radial-gradient(circle,#fff,rgba(236,207,160,.95) 40%,transparent 72%);box-shadow:0 0 12px rgba(236,207,160,.95);animation:sparkFly .75s cubic-bezier(.2,.6,.3,1) forwards}
.cta .btn-solid,.cookie-bar .btn{animation:pulseGold 3.2s ease-in-out infinite}
.footer,.flogo{animation:none}
footer .flogo{background:linear-gradient(100deg,#fff 20%,var(--gold-soft) 55%,#fff 90%);background-size:220% auto;-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;animation:h2sweep 7s linear infinite}
.svc h3,.step h3,.guar h3{transition:text-shadow .4s}
.svc:hover h3,.step:hover h3,.guar:hover h3{text-shadow:0 0 22px rgba(236,207,160,.5)}
/* ====== плавность и полировка ====== */
@keyframes bodyIn{from{opacity:0}to{opacity:1}}
body{animation:bodyIn .9s ease both}
.js .rv{transition:opacity 1.15s cubic-bezier(.16,1,.3,1),transform 1.15s cubic-bezier(.16,1,.3,1),filter 1.15s cubic-bezier(.16,1,.3,1)}
.js .reveal{transition:opacity 1.15s cubic-bezier(.16,1,.3,1),transform 1.15s cubic-bezier(.16,1,.3,1),filter 1.15s cubic-bezier(.16,1,.3,1)}
.rev-ava-w{position:relative;display:inline-flex;width:50px;height:50px;flex-shrink:0}
.rev-ava-w::after{content:"";position:absolute;inset:-4px;border-radius:50%;border:1px solid rgba(236,207,160,.35);opacity:.55;animation:ringPulse 4s ease-in-out infinite}
.rev-ava-txt{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;border-radius:50%;border:1.5px solid rgba(236,207,160,.6);background:linear-gradient(135deg,rgba(212,175,106,.3),rgba(14,12,9,.92));color:var(--gold-soft);font-family:var(--serif);font-size:23px;font-weight:600;box-shadow:0 0 0 4px rgba(212,175,106,.1),0 0 16px rgba(212,175,106,.3)}
.rev-ava{position:absolute;inset:0;z-index:1}
.rev-photo{margin-top:14px;border-radius:var(--r-md);overflow:hidden;border:1px solid rgba(255,255,255,.08);box-shadow:var(--shadow-md)}
.rev-photo img{width:100%;height:180px;object-fit:cover;transition:transform .8s cubic-bezier(.16,1,.3,1)}
.rev-photo:hover img{transform:scale(1.07)}
.img-fade{opacity:0}
.img-ready{opacity:1;transition:opacity 1s cubic-bezier(.16,1,.3,1)}
.img-failed{background:linear-gradient(135deg,rgba(212,175,106,.16),rgba(14,12,9,.9));display:flex;align-items:center;justify-content:center;min-height:120px}
.img-failed::after{content:attr(data-alt);color:var(--muted);font-size:13px;text-align:center;padding:18px;font-family:var(--sans)}
.car-slide{transition:transform .7s cubic-bezier(.16,1,.3,1),box-shadow .7s,border-color .7s}
.svc,.step,.guar,.city,.rev-card,.about-card,.call-block,.stat{transition:transform .7s cubic-bezier(.16,1,.3,1),box-shadow .7s,border-color .7s,background .7s}
.btn{transition:transform .55s cubic-bezier(.16,1,.3,1),box-shadow .55s,filter .55s,background .55s,color .55s}
.c-action,.soc,.car-dot,.car-nav,.lb-nav,.lb-close,.menu a{transition:transform .5s cubic-bezier(.16,1,.3,1),background .5s,color .5s,box-shadow .5s,border-color .5s}
.stat::before{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;opacity:0;background:radial-gradient(circle at 50% -10%,rgba(236,207,160,.16),transparent 62%);transition:opacity .7s}
.stat:hover::before{opacity:1}
.city::after{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;opacity:0;background:radial-gradient(circle at 50% 120%,rgba(212,175,106,.18),transparent 62%);transition:opacity .7s}
.city:hover::after{opacity:1}
.panel--dark .bg::before{content:"";position:absolute;inset:0;pointer-events:none;background:radial-gradient(900px 420px at 50% -12%,rgba(212,175,106,.13),transparent 70%)}
.about-card .avatar,.call-block{transition:transform .8s cubic-bezier(.16,1,.3,1),box-shadow .8s,border-color .8s}
.about-card:hover .avatar{transform:translateY(-6px) scale(1.03)}
.sec-head h2,.about-body h2,.contact-info h2,h2.k{transition:letter-spacing .8s cubic-bezier(.16,1,.3,1)}
.sec-head.in h2{letter-spacing:.6px}
.car-track{scroll-behavior:smooth}
.car-slide img,.rev-photo img,.avatar img{transition:transform .9s cubic-bezier(.16,1,.3,1),opacity 1s cubic-bezier(.16,1,.3,1)}
.svc svg,.guar .ico,.c-ico{transition:transform .7s cubic-bezier(.16,1,.3,1),filter .7s,box-shadow .7s}
/* ====== финальные штрихи плавности ====== */
a{transition:color .45s cubic-bezier(.16,1,.3,1),opacity .45s cubic-bezier(.16,1,.3,1)}
img{transition:opacity 1s cubic-bezier(.16,1,.3,1),transform .95s cubic-bezier(.16,1,.3,1)}
.car-nav{animation:navGlow 3.8s ease-in-out infinite}
.gold-divider i{transition:transform 1.1s cubic-bezier(.16,1,.3,1),opacity 1.1s}
.soc,.c-action,.car-dot,.lb-nav,.lb-close{will-change:transform}
.panel .content{transition:transform .6s cubic-bezier(.16,1,.3,1)}
.swipe-hint,.scroll-cue{transition:opacity .6s ease}
.rev-head{transition:gap .5s cubic-bezier(.16,1,.3,1)}
.rev-card:hover .rev-head{gap:18px}
.step:hover .n,.stat:hover .num{transition:transform .8s cubic-bezier(.16,1,.3,1)}
.svc:hover h3,.step:hover h3,.guar:hover h3,.city:hover .city-name{color:#fff}
/* ====== стрелки карусели по бокам ====== */
.carousel{position:relative}
.car-nav{position:absolute;top:50%;left:-18px;transform:translateY(-50%);overflow:hidden;width:54px;height:54px;border-radius:50%;background:rgba(18,15,11,.72);-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);border:1px solid rgba(236,207,160,.3);color:var(--gold-soft);font-size:20px;line-height:1;display:flex;align-items:center;justify-content:center;box-shadow:0 16px 36px rgba(0,0,0,.5);z-index:6;transition:background .45s cubic-bezier(.16,1,.3,1),color .45s,border-color .45s,transform .45s cubic-bezier(.16,1,.3,1),opacity .45s}
.car-next{left:auto;right:-18px}
.car-nav:hover{background:var(--gold);border-color:var(--gold);color:#17120b;transform:translateY(-50%) scale(1.07)}
.car-nav:active{transform:translateY(-50%) scale(.94)}
.car-nav.is-off{opacity:.28;pointer-events:none}
.car-track{scroll-padding:0 8px}
@media(max-width:1200px){.car-nav{left:-8px}.car-next{left:auto;right:-8px}}
@media(max-width:860px){.car-nav{display:flex;left:0;width:44px;height:44px;font-size:17px}.car-next{left:auto;right:0}.car-track{padding-left:6px;padding-right:6px}}
@media(max-width:520px){.car-nav{width:38px;height:38px;font-size:15px;background:rgba(18,15,11,.82)}.rev-track,.car-track{padding-left:2px;padding-right:2px}}

/* ====== сдержанные, «не-иишные» кнопки ====== */
.btn{border-radius:11px;letter-spacing:1px;font-size:12.5px;font-weight:700;padding:15px 28px;min-height:48px;text-transform:uppercase;animation:none;transition:transform .5s cubic-bezier(.16,1,.3,1),box-shadow .5s,background .5s,border-color .5s,color .5s}
.btn-solid{background:linear-gradient(180deg,#e7d2a7 0%,#d4af6a 62%,#c09a53 100%);color:#1b1509;box-shadow:0 10px 26px rgba(0,0,0,.34),inset 0 1px 0 rgba(255,255,255,.34);animation:none}
.btn-solid:hover{transform:translateY(-2px);box-shadow:0 16px 34px rgba(0,0,0,.42),inset 0 1px 0 rgba(255,255,255,.42);filter:none}
.btn-solid:active{transform:translateY(0);box-shadow:0 6px 16px rgba(0,0,0,.34),inset 0 1px 0 rgba(255,255,255,.3)}
.btn-solid::before{display:none}
.btn-line{border:1px solid rgba(236,207,160,.32);background:rgba(255,255,255,.025);color:#fff}
.btn-line:hover{background:rgba(236,207,160,.1);border-color:rgba(236,207,160,.55);transform:translateY(-2px);box-shadow:0 12px 30px rgba(0,0,0,.34)}
.btn::after{background:linear-gradient(120deg,transparent,rgba(255,255,255,.22),transparent)}
.c-action{border-radius:11px;letter-spacing:.3px;font-weight:700}
.c-action.c-call{background:linear-gradient(180deg,#e7d2a7,#d4af6a 62%,#c09a53);color:#1b1509;box-shadow:0 10px 26px rgba(0,0,0,.3),inset 0 1px 0 rgba(255,255,255,.3)}
.c-action.c-call:hover{filter:none;transform:translateY(-2px);box-shadow:0 16px 34px rgba(0,0,0,.4)}
.c-action.c-tg{background:rgba(64,169,242,.09);border:1px solid rgba(64,169,242,.3)}
.c-action.c-tg:hover{background:rgba(64,169,242,.17);transform:translateY(-2px)}
.c-action.c-max{background:rgba(177,88,252,.09);border:1px solid rgba(177,88,252,.3)}
.c-action.c-max:hover{background:rgba(177,88,252,.17);transform:translateY(-2px)}
.cta .btn-solid,.cookie-bar .btn{animation:none}
.menu a.active{animation:none;color:var(--gold-soft)}
.stat .num{animation:none;filter:drop-shadow(0 6px 18px rgba(212,175,106,.28))}
.stat:hover .num{filter:drop-shadow(0 8px 24px rgba(236,207,160,.45))}
.empty,.swipe-hint,.scroll-cue,.car-nav{animation:none}
.brand-ava-w::before{animation:ringPulse 5s ease-in-out infinite}
.rev-ava-w::after{animation:ringPulse 5.5s ease-in-out infinite}
.soc{background:rgba(255,255,255,.03)}
.soc:hover{background:var(--gold);color:#17120b;transform:translateY(-3px);box-shadow:0 12px 28px rgba(0,0,0,.35)}
.car-dot{background:rgba(255,255,255,.18)}
.car-dot.active{background:var(--gold);box-shadow:none}

/* ====== меньше «картона»: глубина вместо рамок ====== */
.svc,.step,.guar,.city,.rev-card,.about-card,.call-block,.stat{border-color:rgba(255,255,255,.055);background:linear-gradient(180deg,rgba(255,255,255,.05),rgba(255,255,255,.018));box-shadow:inset 0 1px 0 rgba(255,255,255,.05),0 22px 48px -26px rgba(0,0,0,.75)}
.svc:hover,.step:hover,.guar:hover,.city:hover,.rev-card:hover,.about-card:hover,.call-block:hover,.stat:hover{background:linear-gradient(180deg,rgba(255,255,255,.065),rgba(255,255,255,.025));box-shadow:inset 0 1px 0 rgba(255,255,255,.07),0 30px 62px -24px rgba(0,0,0,.8),0 0 42px rgba(212,175,106,.1)}
.svc::before,.guar::before,.city::before,.step::before{background:linear-gradient(90deg,transparent,rgba(236,207,160,.55),transparent)}
.sec-head p,.about-body p,.city p,.svc p,.step p,.guar p{color:#bdb2a0}
h2.k,.sec-head h2,.about-body h2,.contact-info h2{text-shadow:0 4px 20px rgba(0,0,0,.5)}
.panel .bg::after{background:linear-gradient(to right,rgba(10,8,6,.93) 18%,rgba(10,8,6,.62) 58%,rgba(10,8,6,.8))}

/* ====== полная адаптация ====== */
*{min-width:0}
html,body{max-width:100%;overflow-x:hidden}
img,svg,video,iframe{max-width:100%}
.wrap{padding:0 clamp(14px,3.4vw,20px)}
@media(min-width:1600px){.wrap{max-width:1260px}.menu{right:max(24px,calc((100vw - 1300px)/2))}}
@media(max-width:1200px){.car-slide img{height:280px}}
@media(max-width:1024px){
 .about{gap:44px}.contact-grid{gap:40px}.panel{padding:126px 0}
 .stats{gap:20px}.svc-grid,.steps{gap:18px}.guar-grid,.city-grid{gap:18px}
}
@media(max-width:900px){
 .svc-grid{grid-template-columns:1fr 1fr}.guar-grid{grid-template-columns:1fr 1fr}
 .city-grid{grid-template-columns:1fr 1fr}.car-slide{width:min(74vw,420px)}
}
@media(max-width:860px){
 .about-card{padding:38px 26px}.call-block{padding:38px 24px}
 .rev-card{width:88vw}.car-slide{width:80vw}
 .panel{padding:112px 0}
 .sec-head{margin-bottom:40px}
 .menu.open li a{padding:12px 6px}
}
@media(max-width:640px){
 .stats{grid-template-columns:1fr 1fr;gap:14px}.stat{padding:24px 12px}
 .svc-grid,.steps,.guar-grid,.city-grid{grid-template-columns:1fr}
 .features{grid-template-columns:1fr}
 .panel{padding:96px 0 64px}
 h1{font-size:clamp(28px,8.4vw,40px)}
 .sub{font-size:15px;margin:16px 0 24px}
 .btn{padding:14px 20px;font-size:12px}
 .btn-row{gap:10px}
 .car-slide{width:84vw}.car-slide img{height:230px}
 .rev-card{width:90vw;padding:18px}.rev-text{font-size:13px}
 .video-box{height:210px}
 .consult .phone{font-size:clamp(24px,7.4vw,32px)}
 .call-block .cb-num{font-size:clamp(20px,6.4vw,26px)}
 .city{padding:30px 22px}.stat .num{font-size:42px}
  .cookie-bar{flex-direction:column;align-items:stretch;gap:12px;bottom:calc(10px + env(safe-area-inset-bottom))}
 .cookie-bar .btn{width:100%}
 .lb-stage{height:calc(100vh - 132px)}.lb-stage img{max-width:96%;border-radius:16px}
 .lb-bar{gap:14px}
}
@media(max-width:420px){
 .wrap{padding:0 14px}
 .logo .brand-txt .name{font-size:19px}.logo .brand-txt .sub{font-size:9px;letter-spacing:1.1px}
 .brand-ava{width:40px;height:40px}
 .stats{grid-template-columns:1fr 1fr;gap:12px}
 .car-slide{width:88vw}.car-slide img{height:200px}
 .rev-card{width:92vw;padding:15px}.rev-head{gap:10px}
 .rev-ava-w{width:44px;height:44px}.rev-ava-txt{font-size:20px}
 .video-box{height:180px}
 .city .city-name{font-size:24px}
 .step{padding:26px 20px}.svc{padding:28px 22px}.guar{padding:28px 20px}
 .menu{padding:10px 18px calc(16px + env(safe-area-inset-bottom))}
 .menu a{font-size:17px;padding:11px 6px}
 .footer{padding:40px 16px 48px}
}
@media(max-width:340px){
 .car-slide{width:90vw}.car-slide img{height:180px}
 h1{font-size:26px}.btn{font-size:11px;letter-spacing:.6px}
 .stat .num{font-size:36px}
}
@media(orientation:landscape) and (max-height:560px){
 .panel{min-height:auto;padding:96px 0 56px}
 .menu{max-height:88vh}
 .lb-stage{height:calc(100vh - 96px)}
}
@media(hover:none){
 .svc,.step,.guar,.city,.rev-card,.stat,.about-card,.call-block{transform:none!important}
 .btn,.c-action,.soc,.car-dot,.car-nav,.lb-nav,.lb-close{min-height:44px}
 .car-nav{display:flex}
 .menu a{min-height:48px}
}
@media print{
 .menu,header,.cookie-bar,.car-nav,#goldParticles,#cursorGlow,.grain,.orb{display:none!important}
 body{background:#fff;color:#000}
}
/* Мягкий режим при «уменьшенном движении» в системе: анимации не выключаются полностью,
   а становятся спокойными (только прозрачность + короткие переходы). */
/* ====== изящные кнопки (без «кирпича») ====== */
.btn{font-family:var(--sans);font-size:11.5px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;
 padding:13px 30px;min-height:46px;border-radius:9px;border:1px solid transparent;
 transition:transform .5s cubic-bezier(.16,1,.3,1),background .45s,border-color .45s,color .45s,box-shadow .45s}
.btn-solid{background:linear-gradient(180deg,#ecd9b2 0%,#d8b473 55%,#c69f5a 100%);color:#151006;
 border-color:rgba(255,255,255,.16);box-shadow:inset 0 1px 0 rgba(255,255,255,.45),0 6px 18px -8px rgba(0,0,0,.7)}
.btn-solid:hover{background:linear-gradient(180deg,#f3e2c0 0%,#e0bd7f 55%,#cfa763 100%);transform:translateY(-1px);
 box-shadow:inset 0 1px 0 rgba(255,255,255,.5),0 10px 24px -10px rgba(0,0,0,.75)}
.btn-solid:active{transform:translateY(0);box-shadow:inset 0 1px 0 rgba(255,255,255,.4),0 4px 12px -6px rgba(0,0,0,.7)}
.btn-line{border-color:rgba(236,207,160,.28);background:transparent;color:#f3e9d8}
.btn-line:hover{border-color:rgba(236,207,160,.6);background:rgba(236,207,160,.07);color:#fff;transform:translateY(-1px);box-shadow:none}
.btn::after{display:none}
.btn .ripple-el{opacity:.5}
.c-action{border-radius:9px;font-size:13.5px;font-weight:600;letter-spacing:.02em;border:1px solid transparent}
.c-action.c-call{background:linear-gradient(180deg,#ecd9b2,#d8b473 55%,#c69f5a);color:#151006;border-color:rgba(255,255,255,.16);box-shadow:inset 0 1px 0 rgba(255,255,255,.42),0 6px 18px -10px rgba(0,0,0,.7)}
.c-action.c-call:hover{transform:translateY(-1px);filter:none;box-shadow:inset 0 1px 0 rgba(255,255,255,.5),0 10px 24px -10px rgba(0,0,0,.75)}
.c-action.c-tg{background:rgba(64,169,242,.07);border-color:rgba(64,169,242,.26)}
.c-action.c-tg:hover{background:rgba(64,169,242,.14);transform:translateY(-1px)}
.c-action.c-max{background:rgba(177,88,252,.07);border-color:rgba(177,88,252,.26)}
.c-action.c-max:hover{background:rgba(177,88,252,.14);transform:translateY(-1px)}
.cookie-bar .btn{padding:12px 26px;min-height:42px}

/* ====== золотые разделители (везде) ====== */
.gold-divider{position:relative;display:flex;align-items:center;justify-content:center;gap:16px;padding:26px 0}
.gold-divider i{position:relative;overflow:hidden;display:inline-block;width:clamp(70px,13vw,150px);height:1px;
 background:linear-gradient(90deg,transparent,rgba(212,175,106,.7));opacity:1}
.gold-divider i:last-child{background:linear-gradient(90deg,rgba(212,175,106,.7),transparent)}
.gold-divider i::after{content:"";position:absolute;top:0;left:-35%;width:35%;height:100%;
 background:linear-gradient(90deg,transparent,rgba(255,246,230,.95),transparent);animation:divShine 5.5s ease-in-out infinite}
.gold-divider i:last-child::after{left:auto;right:-35%;animation-direction:reverse}
.gold-divider b{width:8px;height:8px;transform:rotate(45deg);background:linear-gradient(135deg,#f2e0ba,#c69f5a);
 box-shadow:0 0 14px rgba(236,207,160,.45);animation:divPulse 4s ease-in-out infinite}
@keyframes divShine{0%{transform:translateX(0);opacity:0}18%{opacity:.9}82%{opacity:.9}100%{transform:translateX(420%);opacity:0}}
@keyframes divPulse{0%,100%{opacity:.7;transform:rotate(45deg) scale(1)}50%{opacity:1;transform:rotate(45deg) scale(1.22)}}
.js .gold-divider.rv{opacity:0;transform:translateY(10px);transition:opacity .9s cubic-bezier(.16,1,.3,1),transform .9s cubic-bezier(.16,1,.3,1)}
.js .gold-divider.rv.in{opacity:1;transform:none}

/* ====== производительность: только transform/opacity, без blur и тяжёлых теней ====== */
.js .reveal,.js .rv{filter:none!important;will-change:transform,opacity}
.js .reveal.in,.js .rv.in{will-change:auto}
.svc,.step,.guar,.city,.rev-card,.about-card,.call-block,.stat,
.car-slide,.rev-photo img,.svc svg,.guar .ico,.c-ico,.stat .num,.btn,.c-action,.soc,.car-dot,.car-nav,.lb-nav,.lb-close,
.c-line,.features li,.gold-divider,.sec-head h2,.menu a,.soc svg,.car-slide img{transition-property:transform,opacity,border-color,background-color,color}
.svc,.step,.guar,.city,.rev-card,.about-card,.call-block,.stat{box-shadow:inset 0 1px 0 rgba(255,255,255,.05),0 18px 40px -26px rgba(0,0,0,.8)}
.svc:hover,.step:hover,.guar:hover,.city:hover,.rev-card:hover,.about-card:hover,.call-block:hover,.stat:hover{
 transform:translateY(-8px);box-shadow:inset 0 1px 0 rgba(255,255,255,.06),0 22px 44px -24px rgba(0,0,0,.85)}
.car-slide{box-shadow:0 14px 30px -20px rgba(0,0,0,.85)}
.car-slide:hover{box-shadow:0 22px 44px -22px rgba(0,0,0,.9)}


/* ====== анимации всегда включены; выключить можно только ?anim=0 ====== */
html.no-anim *,html.no-anim *::before,html.no-anim *::after{animation:none!important;transition-duration:.2s!important}
html.no-anim .js .rv,html.no-anim .js .reveal{opacity:1!important;transform:none!important}
html.no-anim .spark{display:none}

/* ====== компактный разделитель и мягкие стыки секций ====== */
.panel + .panel{margin-top:0}
.gold-divider{position:relative;z-index:3;display:flex;align-items:center;justify-content:center;gap:9px;
 height:1px;padding:0;margin:0;overflow:visible;pointer-events:none}
.gold-divider i{width:clamp(34px,5.6vw,78px);height:1px;opacity:.85}
.gold-divider b{width:5px;height:5px;box-shadow:0 0 10px rgba(236,207,160,.5)}
@media(max-width:640px){.gold-divider i{width:clamp(26px,9vw,54px)}}
.panel::before,.panel::after{content:"";position:absolute;left:0;right:0;pointer-events:none;z-index:1;height:clamp(46px,7vw,96px)}
.panel::before{top:0;background:linear-gradient(180deg,rgba(12,10,7,.92),rgba(12,10,7,0))}
.panel::after{bottom:0;background:linear-gradient(0deg,rgba(12,10,7,.92),rgba(12,10,7,0))}
.panel--hero::before{height:clamp(70px,11vw,150px);background:linear-gradient(180deg,rgba(10,8,6,.88),rgba(10,8,6,0))}
.panel .bg::after{background:linear-gradient(to right,rgba(10,8,6,.9) 18%,rgba(10,8,6,.56) 58%,rgba(10,8,6,.74))}
/* ====== кнопки: спокойный премиум (без «иишности», кирпича и картона) ====== */
.btn{font-family:var(--sans);font-size:11px;font-weight:500;letter-spacing:.09em;text-transform:uppercase;
 padding:13px 26px;min-height:44px;border-radius:6px;border:1px solid transparent;background:none;
 transition:background .45s cubic-bezier(.16,1,.3,1),border-color .45s,color .45s,transform .45s cubic-bezier(.16,1,.3,1),box-shadow .45s}
.btn-solid{background:linear-gradient(180deg,#d8b677 0%,#c9a260 100%);color:#14100a;border-color:rgba(255,255,255,.14);
 box-shadow:inset 0 1px 0 rgba(255,255,255,.3),0 8px 20px -14px rgba(0,0,0,.8)}
.btn-solid:hover{background:linear-gradient(180deg,#e0bf82 0%,#d0aa68 100%);transform:translateY(-1px);
 box-shadow:inset 0 1px 0 rgba(255,255,255,.36),0 12px 26px -16px rgba(0,0,0,.85)}
.btn-solid:active{transform:translateY(0);background:linear-gradient(180deg,#cfa96a,#c19b58)}
.btn-line{background:rgba(255,255,255,.015);border-color:rgba(236,207,160,.22);color:#e9dfca}
.btn-line:hover{border-color:rgba(236,207,160,.46);background:rgba(236,207,160,.055);color:#fff;transform:translateY(-1px);box-shadow:none}
.btn-line:active{transform:translateY(0)}
.btn::after{display:none}
.btn .ripple-el{opacity:.35}
.c-action{font-size:13px;font-weight:500;letter-spacing:.02em;border-radius:6px;border:1px solid transparent}
.c-action.c-call{background:linear-gradient(180deg,#d8b677,#c9a260);color:#14100a;border-color:rgba(255,255,255,.14);
 box-shadow:inset 0 1px 0 rgba(255,255,255,.28),0 8px 20px -14px rgba(0,0,0,.8)}
.c-action.c-call:hover{background:linear-gradient(180deg,#e0bf82,#d0aa68);transform:translateY(-1px);filter:none;box-shadow:inset 0 1px 0 rgba(255,255,255,.34),0 12px 26px -16px rgba(0,0,0,.85)}
.c-action.c-tg{background:rgba(64,169,242,.06);border-color:rgba(64,169,242,.22);color:#9ccdf5}
.c-action.c-tg:hover{background:rgba(64,169,242,.12);border-color:rgba(64,169,242,.34);transform:translateY(-1px)}
.c-action.c-max{background:rgba(177,88,252,.06);border-color:rgba(177,88,252,.22);color:#d3b0f7}
.c-action.c-max:hover{background:rgba(177,88,252,.12);border-color:rgba(177,88,252,.34);transform:translateY(-1px)}
.cookie-bar .btn{padding:11px 22px;min-height:40px}
.btn-row{gap:14px}
@media(max-width:520px){.btn{font-size:10.5px;letter-spacing:.06em;padding:13px 18px}}
</style>
<style id="customCss">{{{design.custom_css}}}</style>
{{#if seo.metrika_id}}<script>(function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};m[i].l=1*new Date();for(var j=0;j<document.scripts.length;j++){if(document.scripts[j].src===r){return}}k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)})(window,document,'script','https://mc.yandex.ru/metrika/tag.js','ym');ym({{seo.metrika_id}},'init',{clickmap:true,trackLinks:true,accurateTrackBounce:true,webvisor:true});</script><noscript><div><img src="https://mc.yandex.ru/watch/{{seo.metrika_id}}" style="position:absolute;left:-9999px" alt=""></div></noscript>{{/if}}
{{{code.head}}}
</head>
<body>

<div class="progress" id="progress"></div>
<div class="grain" aria-hidden="true"></div>
<div class="orb orb-1" aria-hidden="true"></div>
<div class="orb orb-2" aria-hidden="true"></div>
<div class="orb orb-3" aria-hidden="true"></div>

<header id="header">
  <div class="wrap nav">
    <a href="#top" class="logo" id="logo">
      <span class="brand-ava-w">
        <img class="brand-ava" src="{{brand.logo_url}}" width="46" height="46" alt="{{brand.name}}{{#if brand.sub}} — {{brand.sub}}{{/if}}">
      </span>
      <span class="brand-txt"><span class="name">{{brand.name}}</span><span class="sub">{{brand.sub}}</span></span>
    </a>
    <button class="burger" id="burger" aria-label="Меню"><span></span><span></span><span></span></button>
  </div>
</header>
<ul class="menu" id="menu">
  <li class="sheet-handle"><span></span></li>
  {{#each nav.items}}<li><a href="{{this.href}}">{{this.label}}</a></li>
  {{/each}}{{#if nav.cta_label}}<li class="menu-call"><a href="{{nav.cta_href}}"><svg viewBox="0 0 24 24" style="width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:2"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 2 .7 2.9a2 2 0 0 1-.4 2.1L8.1 10a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.9.6 2.9.7a2 2 0 0 1 1.6 2z"/></svg>{{nav.cta_label}}</a></li>{{/if}}
</ul>
<div class="scrim" id="scrim"></div>

<section class="panel panel--hero" id="top"{{#if hero.watermark}} data-watermark="{{hero.watermark}}"{{/if}}>
  <div class="bg" style="background-image:url('{{{hero.bg}}}')"></div>
  <div class="wrap"><div class="content">
    <span class="eyebrow">{{hero.eyebrow}}</span>
    <h1 id="heroTitle">{{hero.title_before}}{{#if hero.title_em}} <em class="shimmer">{{hero.title_em}}</em>{{/if}}</h1>
    <p class="sub">{{hero.sub|nl2br}}</p>
    <div class="btn-row">
      {{#if hero.btn1}}<a href="{{hero.btn1_href}}" class="btn btn-solid">{{hero.btn1}}</a>{{/if}}
      {{#if hero.btn2}}<a href="{{hero.btn2_href}}" class="btn btn-line">{{hero.btn2}}</a>{{/if}}
    </div>
  </div></div>
  {{#if hero.scroll_cue}}<div class="scroll-cue">{{hero.scroll_cue}}<div class="line"></div></div>{{/if}}
</section>

<div class="gold-divider"><i></i><b></b><i></i></div>

{{#if stats.items}}
{{#if sections.stats}}<section class="panel panel--dark">
  <div class="bg" style="background-image:url('{{{stats.bg}}}')"></div>
  <div class="wrap"><div class="content">
    <div class="stats">
      {{#each stats.items}}<div class="stat reveal"><div class="num" data-count="{{this.num}}"{{#if this.decimal}} data-decimal="{{this.decimal}}"{{/if}}{{#if this.suffix}} data-suffix="{{this.suffix}}"{{/if}}{{#if this.prefix}} data-prefix="{{this.prefix}}"{{/if}}>{{this.prefix}}0</div><div class="lbl">{{this.label}}</div></div>
      {{/each}}
    </div>
  </div></div>
</section>{{/if}}
<div class="gold-divider"><i></i><b></b><i></i></div>
{{/if}}

{{#if sections.about}}<section class="panel" id="about">
  <div class="bg" style="background-image:url('{{{about.bg}}}')"></div>
  <div class="wrap"><div class="content">
    <div class="about">
      <div class="about-card reveal">
        <div class="avatar"><img src="{{about.photo}}" width="130" height="130" loading="lazy" decoding="async" alt="{{about.name}}{{#if about.role}} — {{about.role}}{{/if}}"></div>
        <h3>{{about.name}}</h3>
        <div class="role">{{about.role}}</div>
        <div class="sep"></div>
        <p>{{{about.card_text|html}}}</p>
      </div>
      <div class="about-body reveal">
        <div class="kicker">{{about.kicker}}</div>
        <h2>{{about.title}}</h2>
        <p>{{{about.text|html}}}</p>
        {{#if about.features}}<ul class="features">
          {{#each about.features}}<li>{{this}}</li>
          {{/each}}
        </ul>{{/if}}
      </div>
    </div>
  </div></div>
</section>{{/if}}

<div class="gold-divider"><i></i><b></b><i></i></div>

{{#if sections.consult}}<section class="panel panel--center panel--dark" id="consult">
  <div class="bg" style="background-image:url('{{{consult.bg}}}')"></div>
  <div class="wrap"><div class="content consult">
    <span class="kicker reveal" style="color:var(--gold-soft);letter-spacing:6px;text-transform:uppercase;font-size:12px;font-weight:600">{{consult.kicker}}</span>
    <h2 class="k reveal">{{consult.title}}</h2>
    <a href="tel:{{consult.phone_raw}}" class="phone reveal">{{consult.phone}}</a>
    <p class="reveal">{{{consult.text|html}}}</p>
  </div></div>
</section>{{/if}}

<div class="gold-divider"><i></i><b></b><i></i></div>

{{#if sections.works}}<section class="panel panel--center panel--dark" id="works"{{#if works.watermark}} data-watermark="{{works.watermark}}"{{/if}}>
  <div class="bg" style="background-image:url('{{{works.bg}}}')"></div>
  <div class="wrap"><div class="content">
    <div class="sec-head reveal">
      <div class="kicker">{{works.kicker}}</div>
      <h2>{{works.title}}</h2>
      <p>{{works.subtitle}}</p>
    </div>
    {{#if works.items}}
    <div class="carousel reveal">
      <button class="car-nav car-prev" id="carPrev" aria-label="Назад">❮</button>
      <div class="car-track" id="carTrack">
        {{#each works.items}}<div class="car-slide"><img loading="lazy" decoding="async" src="{{this.url}}" alt="{{this.alt}}"></div>
        {{/each}}
      </div>
      <button class="car-nav car-next" id="carNext" aria-label="Вперёд">❯</button>
      <div class="car-dots" id="carDots"></div>
      <div class="swipe-hint">{{works.hint}}</div>
    </div>
    {{else}}<p class="empty">Фотографии работ скоро появятся. Позвоните — покажем портфолио лично.</p>{{/if}}
    {{#if works.more_label}}<p class="section-note">{{works.more_text}} <a href="{{works.more_href}}" target="_blank" rel="noopener">{{works.more_label}}</a></p>{{/if}}
  </div></div>
</section>{{/if}}

<div class="lightbox" id="lightbox">
  <button class="lb-close" id="lbClose" aria-label="Закрыть">×</button>
  <div class="lb-stage" id="lbStage">
    <img id="lbImg" alt="Работа">
  </div>
  <div class="lb-bar">
    <button class="lb-nav lb-prev" id="lbPrev" aria-label="Назад">❮</button>
    <div class="lb-count" id="lbCount"></div>
    <button class="lb-nav lb-next" id="lbNext" aria-label="Вперёд">❯</button>
  </div>
</div>

<div class="gold-divider"><i></i><b></b><i></i></div>

{{#if sections.reviews}}<section class="panel panel--center" id="reviews"{{#if reviews.watermark}} data-watermark="{{reviews.watermark}}"{{/if}}>
  <div class="bg" style="background-image:url('{{{reviews.bg}}}')"></div>
  <div class="wrap"><div class="content">
    <div class="sec-head reveal">
      <div class="kicker">{{reviews.kicker}}</div>
      <h2>{{reviews.title}}</h2>
      <p>{{reviews.subtitle}}</p>
    </div>
    {{#if reviews.items}}
    <div class="carousel reveal">
      <button class="car-nav car-prev" id="revPrev" aria-label="Назад">❮</button>
      <div class="car-track rev-track" id="revTrack">
        {{#each reviews.items}}<div class="rev-card">
          <div class="rev-head">
            <span class="rev-ava-w"><span class="rev-ava-txt" aria-hidden="true">{{this.initial}}</span>{{#if this.avatar}}<img class="rev-ava" loading="lazy" decoding="async" width="50" height="50" src="{{this.avatar}}" alt="Отзыв: {{this.name}}">{{/if}}</span>
            <div><div class="rev-name">{{this.name}}</div><div class="rev-sub">{{this.sub}}</div></div>
            {{#if this.stars}}<div class="rev-stars">{{this.stars|stars}}</div>{{/if}}
          </div>
          {{#if this.video}}<div class="rev-video">
            <div class="video-box" data-src="{{this.video}}" style="background-image:url('{{{this.poster}}}{{#unless this.poster}}{{{reviews.video_poster}}}{{/unless}}')" role="button" aria-label="Смотреть видеоотзыв {{this.name}}">
              <span class="vb-play"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></span>
            </div>
          </div>{{/if}}
          <p class="rev-text">{{this.text|nl2br}}</p>
          {{#if this.photo}}<div class="rev-photo"><img loading="lazy" decoding="async" src="{{this.photo}}" alt="Фото к отзыву {{this.name}}"></div>{{/if}}
        </div>
        {{/each}}
      </div>
      <button class="car-nav car-next" id="revNext" aria-label="Вперёд">❯</button>
      <div class="car-dots" id="revDots"></div>
      <div class="swipe-hint">{{reviews.hint}}</div>
    </div>
    {{else}}<p class="empty">Отзывы появятся здесь совсем скоро. Хотите стать первым — позвоните нам.</p>{{/if}}
    {{#if reviews.more_label}}<p class="section-note">{{reviews.more_text}} <a href="{{reviews.more_href}}" target="_blank" rel="noopener">{{reviews.more_label}}</a></p>{{/if}}
  </div></div>
</section>{{/if}}

<div class="gold-divider"><i></i><b></b><i></i></div>

{{#if services.items}}
{{#if sections.services}}<section class="panel panel--dark" id="services"{{#if services.watermark}} data-watermark="{{services.watermark}}"{{/if}}>
  <div class="bg" style="background-image:url('{{{services.bg}}}')"></div>
  <div class="wrap"><div class="content">
    <div class="sec-head reveal">
      <div class="kicker">{{services.kicker}}</div>
      <h2>{{services.title}}</h2>
      <p>{{services.subtitle}}</p>
    </div>
    <div class="svc-grid">
      {{#each services.items}}<div class="svc reveal">{{{this.icon_svg}}}<h3>{{this.title}}</h3><p>{{this.text}}</p></div>
      {{/each}}
    </div>
  </div></div>
</section>{{/if}}
<div class="gold-divider"><i></i><b></b><i></i></div>
{{/if}}

{{#if process.items}}
{{#if sections.process}}<section class="panel" id="process">
  <div class="bg" style="background-image:url('{{{process.bg}}}')"></div>
  <div class="wrap"><div class="content">
    <div class="sec-head reveal">
      <div class="kicker">{{process.kicker}}</div>
      <h2>{{process.title}}</h2>
    </div>
    <div class="steps">
      {{#each process.items}}<div class="step reveal"><div class="n">{{this.n}}</div><h3>{{this.title}}</h3><p>{{this.text}}</p></div>
      {{/each}}
    </div>
  </div></div>
</section>{{/if}}
<div class="gold-divider"><i></i><b></b><i></i></div>
{{/if}}

{{#if guarantees.items}}
{{#if sections.guarantees}}<section class="panel panel--dark">
  <div class="bg" style="background-image:url('{{{guarantees.bg}}}')"></div>
  <div class="wrap"><div class="content">
    <div class="sec-head reveal">
      <div class="kicker">{{guarantees.kicker}}</div>
      <h2>{{guarantees.title}}</h2>
    </div>
    <div class="guar-grid">
      {{#each guarantees.items}}<div class="guar reveal"><div class="ico">{{{this.icon_svg}}}</div><h3>{{this.title}}</h3><p>{{this.text}}</p></div>
      {{/each}}
    </div>
  </div></div>
</section>{{/if}}
<div class="gold-divider"><i></i><b></b><i></i></div>
{{/if}}

{{#if cities.items}}
{{#if sections.cities}}<section class="panel panel--center panel--dark" id="cities">
  <div class="bg" style="background-image:url('{{{cities.bg}}}')"></div>
  <div class="wrap"><div class="content">
    <div class="sec-head reveal">
      <div class="kicker">{{cities.kicker}}</div>
      <h2>{{cities.title}}</h2>
      <p>{{cities.subtitle}}</p>
    </div>
    <div class="city-grid">
      {{#each cities.items}}<div class="city reveal"><div class="city-name">{{this.name}}</div><div class="city-line"></div><p>{{this.text}}</p></div>
      {{/each}}
    </div>
  </div></div>
</section>{{/if}}
<div class="gold-divider"><i></i><b></b><i></i></div>
{{/if}}

{{#if sections.cta}}<section class="panel panel--center panel--dark">
  <div class="bg" style="background-image:url('{{{cta.bg}}}')"></div>
  <div class="wrap"><div class="content cta">
    <h2 class="reveal shimmer">{{cta.title}}</h2>
    <p class="reveal">{{{cta.text|html}}}</p>
    <a href="tel:{{cta.phone_raw}}" class="btn btn-solid reveal">{{cta.button}}</a>
  </div></div>
</section>{{/if}}

<div class="gold-divider"><i></i><b></b><i></i></div>

{{#if sections.contacts}}<section class="panel panel--dark" id="contacts">
  <div class="bg" style="background-image:url('{{{contacts.bg}}}')"></div>
  <div class="wrap"><div class="content">
    <div class="contact-grid">
      <div class="contact-info reveal">
        <div class="kicker">{{contacts.kicker}}</div>
        <h2>{{contacts.title}}</h2>
        <p>{{contacts.subtitle}}</p>
        {{#each contacts.lines}}<div class="c-line"><div class="c-ico">{{{this.icon_svg}}}</div><div><div class="lab">{{this.label}}</div>{{#if this.href}}<a class="val" href="{{this.href}}"{{#if this.external}} target="_blank" rel="noopener"{{/if}}>{{this.value}}</a>{{else}}<div class="val">{{this.value}}</div>{{/if}}</div></div>
        {{/each}}
      </div>
      <div class="reveal">
        <div class="call-block">
          <div class="cb-lab">{{contacts.call_label}}</div>
          <a class="cb-num" href="tel:{{brand.phone_raw}}">{{contacts.call_number}}</a>
          <div class="cb-hint">{{{contacts.call_hint|html}}}</div>
          <div class="contact-actions">
            {{#each contacts.buttons}}<a class="c-action {{this.cls}}" href="{{this.href}}"{{#if this.external}} target="_blank" rel="noopener"{{/if}}>{{{this.icon_svg}}}{{this.label}}</a>
            {{/each}}
          </div>
        </div>
      </div>
    </div>
  </div></div>
</section>{{/if}}

{{#if sections.footer}}<footer>
  <div class="flogo">{{brand.name}}<span> · {{brand.sub}}</span></div>
  {{#if footer.socials}}<div class="social-row">
    {{#each footer.socials}}<a class="soc" href="{{this.href}}" title="{{this.label}}">{{{this.icon_svg}}}</a>
    {{/each}}
  </div>{{/if}}
  <p>{{footer.line}}</p>
  <p style="margin-top:8px">© <span id="year">{{year}}</span> {{footer.copyright}}</p>
</footer>{{/if}}

{{#if sections.cookie}}<div class="cookie-bar" id="cookieBar">
  <p>{{cookie.text}}{{#if cookie.link_href}} <a href="{{cookie.link_href}}" style="color:var(--gold-soft)">{{cookie.link_label}}</a>.{{/if}}</p>
  <button class="btn btn-solid" id="cookieOk">{{cookie.button}}</button>
</div>

<script>
(function(){
const reduced=false;
const fine=true;
const progress=document.getElementById('progress');
const header=document.getElementById('header');
const burger=document.getElementById('burger'),menu=document.getElementById('menu'),scrim=document.getElementById('scrim');
let ticking=false,menuOpen=false;
function onScroll(){if(ticking)return;ticking=true;requestAnimationFrame(()=>{
  const h=document.documentElement;
  const sc=h.scrollHeight>h.clientHeight?h.scrollTop/(h.scrollHeight-h.clientHeight):0;
  if(progress)progress.style.width=(sc*100)+'%';
  if(header)header.classList.toggle('solid',h.scrollTop>40);
  let current='';
  ['about','works','reviews','services','process','cities','contacts'].forEach(id=>{const el=document.getElementById(id);if(el&&el.getBoundingClientRect().top<=120)current=id;});
  if(menu)menu.querySelectorAll('a[href^="#"]').forEach(a=>a.classList.toggle('active',a.getAttribute('href')==='#'+current));
  ticking=false;
});}
window.addEventListener('scroll',onScroll,{passive:true});onScroll();
const logo=document.getElementById('logo');
if(logo)logo.addEventListener('click',e=>{e.preventDefault();window.scrollTo({top:0,behavior:'smooth'});});
function closeMenu(){if(!burger||!menu||!scrim)return;burger.classList.remove('open');menu.classList.remove('open');scrim.classList.remove('show');menuOpen=false;}
function openMenu(){burger.classList.add('open');menu.classList.add('open');scrim.classList.add('show');menuOpen=true;}
if(burger)burger.addEventListener('click',()=>{if(menuOpen)closeMenu();else openMenu();});
if(scrim)scrim.addEventListener('click',closeMenu);
if(menu)menu.querySelectorAll('a').forEach(a=>a.addEventListener('click',closeMenu));
document.querySelectorAll('a[href^="#"]').forEach(a=>{
  a.addEventListener('click',function(e){
    const id=a.getAttribute('href');
    if(!id||id.length<2)return;
    const t=document.querySelector(id);
    if(!t)return;
    e.preventDefault();t.scrollIntoView({behavior:reduced?'auto':'smooth',block:'start'});
  });
});
if(fine&&!reduced){
  /* параллакс без замеров на каждом кадре: позиции считаем заранее (дешёво и без лагов) */
  let items=[],vh=innerHeight;
  function measure(){
    vh=innerHeight;
    items=[];
    document.querySelectorAll('.panel .bg').forEach(function(bg){
      const p=bg.parentElement;let top=0,el=p;
      while(el){top+=el.offsetTop;el=el.offsetParent;}
      items.push({el:bg,top:top,h:p.offsetHeight,k:-0.22});
    });
    document.querySelectorAll('.panel .content').forEach(function(cn){
      const p=cn.parentElement;let top=0,el=p;
      while(el){top+=el.offsetTop;el=el.offsetParent;}
      items.push({el:cn,top:top,h:p.offsetHeight,k:-0.05});
    });
  }
  let pT=false;
  function parallax(){
    if(pT)return;pT=true;
    requestAnimationFrame(function(){
      const sy=window.scrollY||pageYOffset;
      for(let i=0;i<items.length;i++){
        const it=items[i];
        const c=(it.top+it.h/2)-(sy+vh/2);
        if(Math.abs(c)>vh*2.2)continue;
        it.el.style.transform='translate3d(0,'+(c*it.k).toFixed(1)+'px,0)';
      }
      pT=false;
    });
  }
  measure();parallax();
  window.addEventListener('scroll',parallax,{passive:true});
  let rz;window.addEventListener('resize',function(){clearTimeout(rz);rz=setTimeout(function(){measure();parallax();},300);});
  window.addEventListener('load',function(){setTimeout(function(){measure();parallax();},400);});
}
function animateCount(el){
  const target=parseFloat(el.dataset.count)||0;
  const dec=parseInt(el.dataset.decimal||'0',10);
  const suffix=el.dataset.suffix||'',prefix=el.dataset.prefix||'';
  const dur=1200,start=performance.now();
  function tick(t){let p=Math.min((t-start)/dur,1);p=1-Math.pow(1-p,3);const val=(target*p).toFixed(dec);el.textContent=prefix+(dec?val:Math.round(target*p))+suffix;if(p<1)requestAnimationFrame(tick);}
  requestAnimationFrame(tick);
}
const counters=document.querySelectorAll('.stat .num');
if('IntersectionObserver' in window){
  const statIO=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting){animateCount(e.target);statIO.unobserve(e.target);}});},{threshold:.5});
  counters.forEach(el=>statIO.observe(el));
  const io=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target);}});},{threshold:.12});
  document.querySelectorAll('.reveal').forEach(el=>io.observe(el));
}else{
  counters.forEach(animateCount);
  document.querySelectorAll('.reveal').forEach(el=>el.classList.add('in'));
}
function initCarousel(trackId,prevId,nextId,dotsId){
  const track=document.getElementById(trackId);
  if(!track)return;
  const prev=document.getElementById(prevId),next=document.getElementById(nextId),dotsBox=document.getElementById(dotsId);
  const items=[...track.children];
  if(!items.length){if(prev)prev.style.display='none';if(next)next.style.display='none';return;}
  if(dotsBox){
    dotsBox.innerHTML='';
    items.forEach((_,i)=>{
      const d=document.createElement('button');
      d.className='car-dot'+(i===0?' active':'');
      d.setAttribute('aria-label','Слайд '+(i+1));
      d.addEventListener('click',()=>items[i].scrollIntoView({behavior:reduced?'auto':'smooth',inline:'center',block:'nearest'}));
      dotsBox.appendChild(d);
    });
  }
  const dots=dotsBox?[...dotsBox.children]:[];
  const step=()=>items[0].offsetWidth+20;
  let sTick=false;
  track.addEventListener('scroll',()=>{if(sTick)return;sTick=true;requestAnimationFrame(()=>{const idx=Math.round(track.scrollLeft/step());dots.forEach((d,i)=>d.classList.toggle('active',i===idx));sTick=false;});},{passive:true});
  if(prev)prev.addEventListener('click',()=>track.scrollBy({left:-step(),behavior:reduced?'auto':'smooth'}));
  if(next)next.addEventListener('click',()=>track.scrollBy({left:step(),behavior:reduced?'auto':'smooth'}));
}
initCarousel('carTrack','carPrev','carNext','carDots');
initCarousel('revTrack','revPrev','revNext','revDots');
if(fine&&!reduced){
  document.querySelectorAll('.car-slide').forEach(slide=>{const img=slide.querySelector('img');slide.addEventListener('mousemove',e=>{const r=slide.getBoundingClientRect();const dx=(e.clientX-r.left)/r.width-.5;const dy=(e.clientY-r.top)/r.height-.5;img.style.transform='scale(1.07) translate('+(dx*8)+'px,'+(dy*8)+'px)';});slide.addEventListener('mouseleave',()=>{img.style.transform='';});});
}
const lightbox=document.getElementById('lightbox'),lbStage=document.getElementById('lbStage'),lbImg=document.getElementById('lbImg'),lbCount=document.getElementById('lbCount');
const lbItems=[...document.querySelectorAll('#carTrack .car-slide img')];
let lbIdx=0,scale=1,tx=0,ty=0,startX=0,startY=0,startDist=0,startScale=1,moved=false;
function lbApply(){lbImg.style.transform='translate('+tx+'px,'+ty+'px) scale('+scale+')';}
function lbReset(){scale=1;tx=0;ty=0;lbApply();lbImg.style.transition='transform .25s ease';setTimeout(()=>{lbImg.style.transition='transform .18s ease-out';},260);}
function openLb(i){if(!lbItems.length)return;lbIdx=(i+lbItems.length)%lbItems.length;lbImg.src=lbItems[lbIdx].src;lbImg.alt=lbItems[lbIdx].alt;if(lbCount)lbCount.textContent=(lbIdx+1)+' / '+lbItems.length;lbReset();if(lightbox){lightbox.classList.add('open');document.body.style.overflow='hidden';}}
function closeLb(){if(!lightbox)return;lightbox.classList.remove('open');document.body.style.overflow='';}
function lbStep(d){openLb(lbIdx+d);}
lbItems.forEach((img,i)=>img.addEventListener('click',()=>openLb(i)));
const lbCloseBtn=document.getElementById('lbClose'),lbPrevBtn=document.getElementById('lbPrev'),lbNextBtn=document.getElementById('lbNext');
if(lbCloseBtn)lbCloseBtn.addEventListener('click',closeLb);
if(lbPrevBtn)lbPrevBtn.addEventListener('click',e=>{e.stopPropagation();lbStep(-1);});
if(lbNextBtn)lbNextBtn.addEventListener('click',e=>{e.stopPropagation();lbStep(1);});
if(lightbox)lightbox.addEventListener('click',e=>{if(e.target===lightbox)closeLb();});
document.addEventListener('keydown',e=>{if(lightbox&&lightbox.classList.contains('open')){if(e.key==='Escape')closeLb();if(e.key==='ArrowLeft')lbStep(-1);if(e.key==='ArrowRight')lbStep(1);}});
if(lbStage){
  let lastTap=0;
  lbStage.addEventListener('touchstart',e=>{
    if(e.touches.length===2){startDist=Math.hypot(e.touches[0].clientX-e.touches[1].clientX,e.touches[0].clientY-e.touches[1].clientY);startScale=scale;moved=true;}
    else if(e.touches.length===1){startX=e.touches[0].clientX;startY=e.touches[0].clientY;moved=false;}
    const now=Date.now();
    if(now-lastTap<280){if(scale>1){lbReset();}else{scale=2;tx=0;ty=0;lbApply();}lastTap=0;}else{lastTap=now;}
  },{passive:true});
  lbStage.addEventListener('touchmove',e=>{
    if(e.touches.length===2){e.preventDefault();const d=Math.hypot(e.touches[0].clientX-e.touches[1].clientX,e.touches[0].clientY-e.touches[1].clientY);scale=Math.min(4,Math.max(1,startScale*d/startDist));tx=0;ty=0;lbApply();}
    else if(e.touches.length===1&&scale>1){const dx=e.touches[0].clientX-startX,dy=e.touches[0].clientY-startY;tx+=dx;ty+=dy;startX=e.touches[0].clientX;startY=e.touches[0].clientY;lbApply();}
  },{passive:false});
  lbStage.addEventListener('touchend',e=>{
    if(e.touches.length===0&&scale===1&&!moved){const dx=e.changedTouches[0].clientX-startX;if(Math.abs(dx)>60)lbStep(dx<0?1:-1);}
    if(e.touches.length===0&&scale<1)scale=1;
  },{passive:true});
}
document.querySelectorAll('.video-box').forEach(box=>{
  box.addEventListener('click',()=>{
    if(box.querySelector('iframe'))return;
    const iframe=document.createElement('iframe');
    iframe.src=box.dataset.src;
    iframe.setAttribute('allow','autoplay; encrypted-media; fullscreen; picture-in-picture');
    iframe.setAttribute('allowfullscreen','1');
    iframe.title='Видеоотзыв';
    box.innerHTML='';
    box.appendChild(iframe);
  });
});
/* cookie: помним и в localStorage, и в cookie; если браузер всё запрещает — не надоедаем */
const cookieBar=document.getElementById('cookieBar'),cookieOk=document.getElementById('cookieOk');
function ckAccepted(){
  try{if(localStorage.getItem('cookiesAccepted')==='1')return true;}catch(e){}
  return document.cookie.indexOf('cookiesAccepted=1')>=0;
}
function ckStore(){
  try{localStorage.setItem('cookiesAccepted','1');}catch(e){}
  try{document.cookie='cookiesAccepted=1; max-age=31536000; path=/; SameSite=Lax';}catch(e){}
}
function ckWorks(){
  try{localStorage.setItem('__ck','1');localStorage.removeItem('__ck');return true;}catch(e){return false;}
}
try{
  if(cookieBar&&cookieOk&&!ckAccepted()&&ckWorks()){
    setTimeout(function(){cookieBar.classList.add('show');},900);
    cookieOk.addEventListener('click',function(){
      ckStore();
      cookieBar.classList.remove('show');
      setTimeout(function(){if(cookieBar.parentNode)cookieBar.parentNode.removeChild(cookieBar);},700);
    });
  }else if(cookieBar&&cookieBar.parentNode){
    cookieBar.parentNode.removeChild(cookieBar);
  }
}catch(e){}
const y=document.getElementById('year');if(y)y.textContent=new Date().getFullYear();
})();
</script>
<script id="beautyScript">
(function(){
  var OFF=/[?&]anim=0/.test(location.search);
  if(OFF)d.documentElement.classList.add('no-anim');
  var reduced=false;                     /* анимации включены всегда */
  var fine=true;
  var d=document;
  function all(sel,root){return Array.prototype.slice.call((root||d).querySelectorAll(sel));}

  /* 1. Заголовок героя — появление по словам */
  var h1=d.getElementById('heroTitle');
  if(h1&&!reduced){
    var texts=[];
    (function collect(n){for(var i=0;i<n.childNodes.length;i++){var c=n.childNodes[i];
      if(c.nodeType===3&&c.nodeValue.trim())texts.push(c);else if(c.nodeType===1)collect(c);}})(h1);
    var idx=0;
    texts.forEach(function(txt){
      var parts=txt.nodeValue.split(/(\s+)/),frag=d.createDocumentFragment();
      parts.forEach(function(p){
        if(!p)return;
        if(/^\s+$/.test(p)){frag.appendChild(d.createTextNode(p));return;}
        var sp=d.createElement('span');sp.className='w';sp.textContent=p;
        sp.style.animationDelay=(0.04+idx*0.05).toFixed(2)+'s';idx++;
        frag.appendChild(sp);
      });
      txt.parentNode.replaceChild(frag,txt);
    });
    if(idx)h1.classList.add('split');
    setTimeout(function(){h1.classList.add('split-done');},1800);
  }
  /* плавное появление первого экрана */
  if(!reduced){
    ['.panel--hero .eyebrow','.panel--hero .sub','.panel--hero .btn-row','.panel--hero .scroll-cue'].forEach(function(sel,i){
      all(sel).forEach(function(el){
        el.style.opacity='0';el.style.transform='translate3d(0,18px,0)';
        el.style.transition='opacity .8s cubic-bezier(.22,1,.36,1) '+(0.1+i*0.1)+'s,transform .8s cubic-bezier(.22,1,.36,1) '+(0.1+i*0.1)+'s';
        setTimeout(function(){el.style.opacity='1';el.style.transform='none';},40);
      });
    });
  }

  /* 2. Появление блоков по скроллу (у .reveal уже своё — его не трогаем) */
  var RV='.c-line,.features li,.gold-divider,.section-note,.swipe-hint,.lb-bar,.eyebrow,.sub,.btn-row,.scroll-cue,.rev-text,.svc p,.step p,.guar p,.city p,.stat .lbl,footer .flogo,footer .social-row,footer p,.cookie-bar';
  var rvEls=all(RV).filter(function(el){return !el.classList.contains('reveal')&&!el.closest('#heroTitle');});
  if(reduced||!('IntersectionObserver' in window)){rvEls.forEach(function(el){el.classList.add('rv','in')});}
  else{
    rvEls.forEach(function(el,i){el.classList.add('rv');el.style.transitionDelay=((i%6)*70)+'ms';});
    var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target);}});},{threshold:.12,rootMargin:'0px 0px -40px 0px'});
    rvEls.forEach(function(el){io.observe(el)});
  }
  /* ступенчатая задержка карточек в сетках */
  all('.svc-grid,.steps,.guar-grid,.city-grid,.stats,.features').forEach(function(grid){
    all(':scope > *',grid).forEach(function(el,i){ if(!el.style.transitionDelay) el.style.transitionDelay=(Math.min(i,6)*80)+'ms'; });
  });

  /* 3. Волна от клика на всех кнопках и ссылках */
  d.addEventListener('click',function(e){
    if(reduced)return;
    var t=e.target.closest('.btn,.c-action,.soc,.car-dot,.car-nav,.lb-nav,.lb-close,.menu a,.svc,.step,.guar,.city,.rev-card,.stat,.c-line');
    if(!t||t.tagName==='A'&&t.getAttribute('href')&&t.getAttribute('href').length<1)return;
    var r=t.getBoundingClientRect(),size=Math.max(r.width,r.height);
    if(!size)return;
    var sp=d.createElement('span');sp.className='ripple-el';
    sp.style.width=sp.style.height=size+'px';
    sp.style.left=(e.clientX-r.left-size/2)+'px';
    sp.style.top=(e.clientY-r.top-size/2)+'px';
    if(getComputedStyle(t).position==='static')t.style.position='relative';
    t.appendChild(sp);
    setTimeout(function(){if(sp.parentNode)sp.parentNode.removeChild(sp);},840);
  },{passive:true});


  /* 6. Лёгкий наклон карточек под курсором + магнитные кнопки */
  if(fine&&!reduced){
    all('.svc,.step,.guar,.city,.rev-card,.about-card,.call-block,.stat').forEach(function(card){
      card.addEventListener('mouseenter',function(){card.style.transitionDuration='.18s';});
      card.addEventListener('mousemove',function(e){
        var r=card.getBoundingClientRect();
        var px=(e.clientX-r.left)/r.width-.5,py=(e.clientY-r.top)/r.height-.5;
        card.style.transform='perspective(900px) translateY(-10px) rotateX('+(-py*4.5).toFixed(2)+'deg) rotateY('+(px*5.5).toFixed(2)+'deg)';
      });
      card.addEventListener('mouseleave',function(){card.style.transform='';card.style.transitionDuration='';});
    });
    all('.btn-solid,.c-action.c-call').forEach(function(btn){
      btn.addEventListener('mousemove',function(e){
        var r=btn.getBoundingClientRect();
        var dx=(e.clientX-r.left-r.width/2)/r.width,dy=(e.clientY-r.top-r.height/2)/r.height;
        btn.style.transform='translate('+(dx*6).toFixed(1)+'px,'+(dy*6-3).toFixed(1)+'px) scale(1.02)';
      });
      btn.addEventListener('mouseleave',function(){btn.style.transform='';});
    });
    /* орбы реагируют на курсор */
    var orbs=all('.orb');
    if(orbs.length){
      var ox=0,oy=0,ox2=0,oy2=0;
      window.addEventListener('mousemove',function(e){ox=(e.clientX/innerWidth-.5);oy=(e.clientY/innerHeight-.5);},{passive:true});
      (function loop(){
        ox2+=(ox-ox2)*.05;oy2+=(oy-oy2)*.05;
        orbs.forEach(function(o,i){o.style.marginLeft=(ox2*(18+i*12)).toFixed(1)+'px';o.style.marginTop=(oy2*(14+i*10)).toFixed(1)+'px';});
        requestAnimationFrame(loop);
      })();
    }
  }

  /* 9. Плавное появление фото + аккуратная заглушка, если фото не открылось */
  all('img').forEach(function(im){
    if(im.classList.contains('rev-ava')||im.classList.contains('brand-ava')||im.closest('#lbStage'))return;
    if(!reduced){im.classList.add('img-fade');}
    function ready(){im.classList.remove('img-fade');im.classList.add('img-ready');}
    function failed(){
      if(im.classList.contains('rev-ava')){im.parentNode&&im.parentNode.removeChild(im);return;}
      im.style.display='none';
      var p=im.parentNode;
      if(p&&!p.classList.contains('img-failed')){p.classList.add('img-failed');p.setAttribute('data-alt',im.getAttribute('alt')||'Фото');}
    }
    if(im.complete){ if(im.naturalWidth>0){ready();}else{failed();} }
    im.addEventListener('load',ready);
    im.addEventListener('error',failed);
  });
  setTimeout(function(){all('img.img-fade').forEach(function(im){im.classList.remove('img-fade');im.classList.add('img-ready');});},4000);

  /* 10. Стрелки карусели: показываем «неактивной» на краях */
  all('.car-track').forEach(function(track){
    var box=track.closest('.carousel');
    if(!box)return;
    var prev=box.querySelector('.car-nav.car-prev'),next=box.querySelector('.car-nav.car-next');
    if(!prev||!next)return;
    function upd(){
      var max=track.scrollWidth-track.clientWidth-2;
      prev.classList.toggle('is-off',track.scrollLeft<=2);
      next.classList.toggle('is-off',track.scrollLeft>=max);
    }
    track.addEventListener('scroll',function(){requestAnimationFrame(upd);},{passive:true});
    window.addEventListener('resize',upd);
    setTimeout(upd,300);setTimeout(upd,1500);
  });

  /* 11. Страховка: если блок в поле зрения, но так и не показался — показываем */
  function forceVisible(){
    all('.rv:not(.in),.reveal:not(.in)').forEach(function(el){
      var r=el.getBoundingClientRect();
      if(r.top<window.innerHeight*0.95&&r.bottom>0){el.classList.add('in');}
    });
  }
  setTimeout(forceVisible,2500);
  window.addEventListener('load',function(){setTimeout(forceVisible,600);});

  /* 7. Искры от клика */
  d.addEventListener('click',function(e){
    if(reduced&&!FORCE)return;
    for(var i=0;i<7;i++){
      var sp3=d.createElement('span');sp3.className='spark';
      var ang=(Math.PI*2*i)/7+Math.random()*.6,dist=26+Math.random()*34;
      sp3.style.left=(e.clientX-3)+'px';sp3.style.top=(e.clientY-3)+'px';
      sp3.style.setProperty('--dx',(Math.cos(ang)*dist).toFixed(1)+'px');
      sp3.style.setProperty('--dy',(Math.sin(ang)*dist).toFixed(1)+'px');
      sp3.style.animationDelay=(i*0.012).toFixed(3)+'s';
      d.body.appendChild(sp3);
      (function(el){setTimeout(function(){if(el.parentNode)el.parentNode.removeChild(el);},900);})(sp3);
    }
  },{passive:true});

  /* 8. Каскад слайдов карусели при появлении */
  if('IntersectionObserver' in window&&!reduced){
    all('#carTrack,#revTrack').forEach(function(track){
      var kids=Array.prototype.slice.call(track.children);
      var io2=new IntersectionObserver(function(es){
        es.forEach(function(en){
          if(!en.isIntersecting)return;
          kids.forEach(function(k,i){
            var el=k.querySelector('.car-slide')||k;
            el.classList.add('pop');
            el.style.animationDelay=(Math.min(i,9)*70)+'ms';
          });
          io2.unobserve(en.target);
        });
      },{threshold:.15});
      io2.observe(track);
    });
  }
  console.log('%cКухни Островский · сборка 2026-10-06-v9 · анимации включены'+(reduced?' (у вас в системе отключена анимация — принудительно: добавьте ?anim=1 к адресу)':''),'color:#d4af6a');
})();
</script>
{{{code.body}}}
</body>
</html>
"""


# ============================================================
#  ШАБЛОНИЗАТОР  {{path}}  {{{path|raw}}}  {{#each list}}  {{#if x}} {{else}}
# ============================================================
#  важно: {{{...}}} и {{...}} разбираются раздельно, иначе тег перед "}"
#  (например в JSON-LD: "longitude": {{geo_lon}}}) съедал бы лишнюю скобку
_TAG_RE = re.compile(r"\{\{\{(.*?)\}\}\}|\{\{(.*?)\}\}", re.S)


def _tag_expr(m):
    """Возвращает (выражение, is_raw) для совпадения _TAG_RE."""
    raw = m.group(1)
    if raw is not None:
        return raw.strip(), True
    return (m.group(2) or "").strip(), False


def _escape(s):
    return _html.escape(s, quote=True)


def _stringify(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return ("%f" % v).rstrip("0").rstrip(".")
    if isinstance(v, int):
        return str(v)
    if isinstance(v, (dict, list, tuple)):
        return ""
    return str(v)


def _truthy(v):
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, (list, tuple, dict)):
        return len(v) > 0
    s = str(v).strip()
    return s != "" and s.lower() not in ("0", "false", "none", "null", "нет")


def _lookup(ctx, path):
    path = (path or "").strip()
    if not path:
        return ""
    if path == "this":
        return ctx.get("this", "")
    if path.startswith("this."):
        cur = ctx.get("this")
        rest = path[5:]
    elif path.startswith("@"):
        return ctx.get(path, "")
    else:
        cur = ctx
        rest = path
    for part in rest.split("."):
        if part == "":
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, (list, tuple)):
            if part.lstrip("-").isdigit():
                i = int(part)
                cur = cur[i] if -len(cur) <= i < len(cur) else None
            else:
                return ""
        else:
            return ""
        if cur is None:
            return ""
    return cur


def _nl2br(value, escape=True):
    s = _stringify(value).replace("\r\n", "\n")
    if escape:
        s = _escape(s)
    return s.replace("\n", "<br>")


def _apply_filter(name, value):
    name = (name or "").strip()
    if name == "nl2br":
        return _nl2br(value, True)
    if name == "html":                      # доверенный HTML из админки (можно <b>, <br>)
        return _nl2br(value, False)
    if name == "stars":
        try:
            n = int(float(str(value).strip()))
        except Exception:
            return _escape(_stringify(value))
        n = max(0, min(5, n))
        return "\u2605" * n + "\u2606" * (5 - n)
    if name == "json":
        return json.dumps(_stringify(value), ensure_ascii=False)[1:-1]
    if name == "up":
        return _escape(_stringify(value).upper())
    return _escape(_stringify(value))


def _extract_block(tpl, pos):
    """Возвращает (тело, else-ветка, новая_позиция) для блока #each/#if/#unless."""
    depth = 0
    main, alt = [], []
    cur = main
    seen_else = False
    p = pos
    while True:
        m = _TAG_RE.search(tpl, p)
        if not m:
            cur.append(tpl[p:])
            return "".join(main), ("".join(alt) if seen_else else ""), len(tpl)
        expr, _raw = _tag_expr(m)
        cur.append(tpl[p:m.start()])
        p = m.end()
        if expr.startswith("#each ") or expr.startswith("#if ") or expr.startswith("#unless "):
            depth += 1
            cur.append(m.group(0))
        elif expr in ("/each", "/if", "/unless"):
            if depth == 0:
                return "".join(main), ("".join(alt) if seen_else else ""), p
            depth -= 1
            cur.append(m.group(0))
        elif expr == "else" and depth == 0 and not seen_else:
            seen_else = True
            cur = alt
        else:
            cur.append(m.group(0))


def render(tpl, ctx):
    out = []
    pos = 0
    while True:
        m = _TAG_RE.search(tpl, pos)
        if not m:
            out.append(tpl[pos:])
            break
        out.append(tpl[pos:m.start()])
        token = m.group(0)
        expr, is_raw = _tag_expr(m)
        pos = m.end()

        if expr.startswith("#each "):
            body, _alt, pos = _extract_block(tpl, pos)
            val = _lookup(ctx, expr[6:])
            if isinstance(val, dict):
                val = [val]
            if isinstance(val, (list, tuple)):
                total = len(val)
                for i, item in enumerate(val):
                    sub = dict(ctx)
                    sub["this"] = item
                    sub["@index"] = i + 1
                    sub["@first"] = (i == 0)
                    sub["@last"] = (i == total - 1)
                    out.append(render(body, sub))
        elif expr.startswith("#if ") or expr.startswith("#unless "):
            neg = expr.startswith("#unless ")
            body, alt, pos = _extract_block(tpl, pos)
            cond = _truthy(_lookup(ctx, expr.split(" ", 1)[1]))
            if neg:
                cond = not cond
            out.append(render(body if cond else alt, ctx))
        elif expr.startswith("#"):
            _b, _a, pos = _extract_block(tpl, pos)
        elif expr.startswith(("/", "else", "!")):
            continue
        else:
            name, _, filt = expr.partition("|")
            val = _lookup(ctx, name)
            if is_raw or filt.strip() == "raw":
                out.append(_stringify(val))
            else:
                out.append(_apply_filter(filt, val))
    return "".join(out)


# ============================================================
#  РАБОТА С ДАННЫМИ
# ============================================================
def _json_clone(obj):
    return json.loads(json.dumps(obj, ensure_ascii=False))


def _merge_deep(base, over):
    if not isinstance(base, dict) or not isinstance(over, dict):
        return _json_clone(over)
    res = dict(base)
    for k, v in over.items():
        if k in res and isinstance(res[k], dict) and isinstance(v, dict):
            res[k] = _merge_deep(res[k], v)
        else:
            res[k] = _json_clone(v)
    return res


def _migrate(raw):
    """Приводит старые ключи из БД к новой схеме (не теряя контент)."""
    if not isinstance(raw, dict):
        return {}
    d = _json_clone(raw)

    about = d.get("about")
    if isinstance(about, dict):
        if "body" in about and "card_text" not in about:
            about["card_text"] = about.pop("text", "")
            about["text"] = about.pop("body", "")
        about.pop("body", None)

    hero = d.get("hero")
    if isinstance(hero, dict):
        if hero.get("eyebrow", "").strip() == "Мебель и кухни на заказ1":
            hero["eyebrow"] = "Мебель и кухни на заказ"
        hero.setdefault("btn1_href", "#consult")
        hero.setdefault("btn2_href", "#works")

    contacts = d.get("contacts")
    if isinstance(contacts, dict) and "lines" not in contacts:
        lines = _json_clone(DEFAULT_DATA.get("contacts", {}).get("lines") or [])
        if lines and contacts.get("regions"):
            lines[0]["value"] = contacts["regions"]
        if lines:
            contacts["lines"] = lines

    if "stats" in d and isinstance(d["stats"], dict):
        d["stats"].setdefault("items", _json_clone(DEFAULT_DATA.get("stats", {}).get("items") or []))

    return d


def _icon_markup(value):
    """Иконка может быть: только path (M3 9h18...), внутренностями svg (<circle/><path/>)
    или готовым <svg>. Возвращаем готовую разметку <svg>…</svg>."""
    v = str(value or "").strip()
    if not v:
        return ""
    if "<svg" in v:
        return v
    if "<" in v:
        return '<svg viewBox="0 0 24 24" aria-hidden="true">' + v + '</svg>'
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="' + _escape(v) + '"/></svg>'


def _normalize_context(data):
    """Готовит данные к рендеру: иконки, год, домен."""
    ctx = _json_clone(data)

    def fix_icons(items):
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict):
                    it["icon_svg"] = _icon_markup(it.get("icon"))

    fix_icons((ctx.get("services") or {}).get("items"))
    fix_icons((ctx.get("guarantees") or {}).get("items"))
    contacts = ctx.get("contacts") or {}
    fix_icons(contacts.get("lines"))
    fix_icons(contacts.get("buttons"))
    fix_icons((ctx.get("footer") or {}).get("socials"))
    for r in ((ctx.get("reviews") or {}).get("items") or []):
        if isinstance(r, dict):
            nm = str(r.get("name") or "").strip()
            r["initial"] = (nm[:1] or "О").upper()
    origin = ""
    try:
        u = str(((ctx.get("brand") or {}).get("logo_url")) or ((ctx.get("seo") or {}).get("favicon_url")) or "")
        if u.startswith("http"):
            pr = urllib.parse.urlparse(u)
            origin = "{}://{}".format(pr.scheme, pr.netloc)
    except Exception:
        origin = ""
    ctx["img_origin"] = origin
    ctx["year"] = str(date.today().year)
    ctx["domain"] = _domain(ctx)
    ctx["favicon"] = favicon_source(ctx)
    return ctx


def _domain(data=None):
    dom = DOMAIN
    if isinstance(data, dict):
        seo = data.get("seo") or {}
        dom = (seo.get("domain") or "").strip() or DOMAIN
    dom = dom.rstrip("/")
    if "//" not in dom:
        dom = "https://" + dom
    scheme, _, host = dom.partition("://")
    return scheme + "://" + _punycode(host)


def _host(data=None):
    return _domain(data).split("://", 1)[-1]


def _punycode(host):
    try:
        return host.encode("idna").decode("ascii")
    except Exception:
        return host


# ============================================================
#  SUPABASE (REST + Storage, на стандартной библиотеке)
# ============================================================
def _http(method, url, payload=None, headers=None, timeout=HTTP_TIMEOUT, raw_body=None):
    data = raw_body
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            try:
                return r.status, json.loads(body.decode("utf-8")) if body else None, body
            except Exception:
                return r.status, None, body
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body.decode("utf-8")), body
        except Exception:
            return e.code, None, body
    except Exception as e:
        return 0, None, str(e).encode("utf-8")


def _sb_headers():
    key = SUPABASE_SERVICE or SUPABASE_ANON
    return {"apikey": key, "Authorization": "Bearer " + key}


def _fetch_from_supabase(timeout=8):
    """Возвращает (data|None, ok). ok=False — сеть/ошибка, кэш не трогаем."""
    if not SUPABASE_URL:
        return None, False
    url = "{}/rest/v1/{}?id=eq.{}&select=data".format(SUPABASE_URL, DATA_TABLE, DATA_ROW_ID)
    keys = [k for k in (SUPABASE_SERVICE, SUPABASE_ANON) if k]
    for i, key in enumerate(keys):
        st, js, body = _http("GET", url, headers={"apikey": key, "Authorization": "Bearer " + key}, timeout=timeout)
        if st == 200 and isinstance(js, list):
            if js and isinstance(js[0].get("data"), dict) and js[0]["data"]:
                return js[0]["data"], True
            return None, True
        print("[sb] read({}): HTTP {} {}".format("service" if i == 0 else "anon", st, (body or b"")[:200]), flush=True)
    return None, False


def _save_to_supabase(data):
    if not SUPABASE_URL:
        return False
    key = SUPABASE_SERVICE or SUPABASE_ANON
    if not key:
        return False
    url = "{}/rest/v1/{}".format(SUPABASE_URL, DATA_TABLE)
    headers = {"apikey": key, "Authorization": "Bearer " + key,
               "Prefer": "resolution=merge-duplicates,return=minimal"}
    st, js, body = _http("POST", url, payload=[{"id": DATA_ROW_ID, "data": data}], headers=headers, timeout=25)
    if 200 <= st < 300:
        print("[save] OK: записано в Supabase ({} КБ)".format(len(json.dumps(data, ensure_ascii=False)) // 1024), flush=True)
        return True
    print("[save] FAIL: HTTP {} {}".format(st, (body or b"")[:300]), flush=True)
    return False


BACKUP_BUCKET = os.environ.get("SUPABASE_BACKUP_BUCKET", "site-backups")
_bucket_state = {"checked": {}, "ok": {}}
_bucket_lock = threading.Lock()


def _bucket_ensure(name=None, public=True):
    name = name or BUCKET
    with _bucket_lock:
        if _bucket_state["checked"].get(name):
            return _bucket_state["ok"].get(name, False)
        _bucket_state["checked"][name] = True
        if not (SUPABASE_URL and SUPABASE_SERVICE):
            return False
        base = SUPABASE_URL + "/storage/v1/bucket"
        st, js, body = _http("GET", base + "/" + name, headers=_sb_headers())
        if st == 200:
            _bucket_state["ok"][name] = True
            return True
        st, js, body = _http("POST", base, payload={"id": name, "name": name, "public": bool(public)},
                             headers=_sb_headers())
        _bucket_state["ok"][name] = st in (200, 201)
        print("[storage] создать бакет {}: HTTP {} {}".format(name, st, (body or b"")[:200]), flush=True)
        return _bucket_state["ok"][name]


def _storage_put(bucket, name, blob, mime="application/json", upsert=True):
    if not _bucket_ensure(bucket, public=False):
        return None
    url = "{}/storage/v1/object/{}/{}".format(SUPABASE_URL, bucket, name)
    headers = _sb_headers()
    headers.update({"Content-Type": mime, "x-upsert": "true" if upsert else "false"})
    st, js, body = _http("POST", url, headers=headers, raw_body=blob, timeout=45)
    if 200 <= st < 300:
        return name
    print("[storage] put {}: HTTP {} {}".format(name, st, (body or b"")[:200]), flush=True)
    return None


def _storage_get(bucket, name):
    url = "{}/storage/v1/object/{}/{}".format(SUPABASE_URL, bucket, name)
    st, js, body = _http("GET", url, headers=_sb_headers(), timeout=30)
    return body if st == 200 else None


def _storage_list_bucket(bucket, limit=200):
    if not _bucket_ensure(bucket, public=False):
        return []
    url = "{}/storage/v1/object/list/{}".format(SUPABASE_URL, bucket)
    payload = {"prefix": "", "limit": limit, "offset": 0, "sortBy": {"column": "name", "order": "desc"}}
    st, js, body = _http("POST", url, payload=payload, headers=_sb_headers(), timeout=20)
    if st == 200 and isinstance(js, list):
        return [it for it in js if isinstance(it, dict) and it.get("id") and it.get("name")]
    return []


def _storage_delete(bucket, names):
    if not names:
        return False
    url = "{}/storage/v1/object/{}".format(SUPABASE_URL, bucket)
    st, js, body = _http("DELETE", url, payload={"prefixes": list(names)}, headers=_sb_headers(), timeout=20)
    return 200 <= st < 300


def _storage_public_url(name):
    return "{}/storage/v1/object/public/{}/{}".format(SUPABASE_URL, BUCKET, name)


def _storage_upload(filename, blob, mime):
    if not _bucket_ensure():
        return None
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".avif", ".ico"):
        ext = {"image/png": ".png", "image/webp": ".webp", "image/gif": ".gif", "image/svg+xml": ".svg"}.get(mime, ".jpg")
    name = "{}-{}{}".format(date.today().isoformat(), secrets.token_hex(6), ext)
    url = "{}/storage/v1/object/{}/{}".format(SUPABASE_URL, BUCKET, name)
    headers = _sb_headers()
    headers.update({"Content-Type": mime, "x-upsert": "true", "Cache-Control": "max-age=31536000"})
    st, js, body = _http("POST", url, headers=headers, raw_body=blob, timeout=45)
    if 200 <= st < 300:
        return _storage_public_url(name)
    print("[storage] upload: HTTP {} {}".format(st, (body or b"")[:200]), flush=True)
    return None


def _storage_list(limit=120):
    if not _bucket_ensure():
        return []
    url = "{}/storage/v1/object/list/{}".format(SUPABASE_URL, BUCKET)
    payload = {"prefix": "", "limit": limit, "offset": 0, "sortBy": {"column": "created_at", "order": "desc"}}
    st, js, body = _http("POST", url, payload=payload, headers=_sb_headers(), timeout=20)
    if st == 200 and isinstance(js, list):
        out = []
        for it in js:
            if not isinstance(it, dict):
                continue
            nm = it.get("name")
            if nm and it.get("id"):          # пропускаем папки
                out.append({"name": nm, "url": _storage_public_url(nm)})
        return out
    return []


# ============================================================
#  ЗАЯВКИ С САЙТА + ЖУРНАЛ
# ============================================================
LEADS_FILE = "leads.json"
AUDIT_FILE = "audit.json"
_leads_lock = threading.Lock()
_audit_lock = threading.Lock()


def _private_json_get(filename, default):
    try:
        blob = _storage_get(BACKUP_BUCKET, filename)
        if not blob:
            return _json_clone(default)
        obj = json.loads(blob.decode("utf-8"))
        return obj
    except Exception as e:
        print("[private-json] read {}: {}".format(filename, e), flush=True)
        return _json_clone(default)


def _private_json_put(filename, obj):
    try:
        blob = json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8")
        return bool(_storage_put(BACKUP_BUCKET, filename, blob, "application/json", upsert=True))
    except Exception as e:
        print("[private-json] write {}: {}".format(filename, e), flush=True)
        return False


def _load_leads():
    obj = _private_json_get(LEADS_FILE, [])
    return obj if isinstance(obj, list) else []


def _save_leads(items):
    return _private_json_put(LEADS_FILE, items[-500:])


def _add_lead(name, phone, message, page, ip=""):
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    ip_hash = hashlib.sha256((ip + "::" + (_session_secret().hex()[:16])).encode("utf-8")).hexdigest()[:16] if ip else ""
    item = {
        "id": uuid.uuid4().hex[:12], "at": now, "name": name[:120],
        "phone": phone[:80], "message": message[:1000], "page": page[:300],
        "ip_hash": ip_hash, "read": False,
    }
    with _leads_lock:
        items = _load_leads()
        items.insert(0, item)
        ok = _save_leads(items)
    return item if ok else None


def _get_leads():
    with _leads_lock:
        return _load_leads()


def _mark_lead(lead_id=None, read=True):
    changed = False
    with _leads_lock:
        items = _load_leads()
        for it in items:
            if lead_id is None or str(it.get("id")) == str(lead_id):
                if bool(it.get("read")) != bool(read):
                    it["read"] = bool(read)
                    changed = True
                if lead_id is not None:
                    break
        if changed:
            _save_leads(items)
    return changed


def _audit(action, who="", details=""):
    item = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "action": str(action)[:80],
            "who": str(who)[:100], "details": str(details)[:500]}
    with _audit_lock:
        items = _private_json_get(AUDIT_FILE, [])
        if not isinstance(items, list):
            items = []
        items.insert(0, item)
        _private_json_put(AUDIT_FILE, items[:300])


def _get_audit():
    with _audit_lock:
        items = _private_json_get(AUDIT_FILE, [])
    return items if isinstance(items, list) else []


# ============================================================
#  AI (YandexGPT / GigaChat)
# ============================================================
def _ai_yandex(system, user, max_tokens=700):
    if not (YANDEX_API_KEY and FOLDER_ID):
        return None, "нет YANDEX_API_KEY / FOLDER_ID"
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    payload = {
        "modelUri": "gpt://{}/yandexgpt-lite/latest".format(FOLDER_ID),
        "completionOptions": {"stream": False, "temperature": 0.55, "maxTokens": str(int(max_tokens))},
        "messages": [{"role": "system", "text": system}, {"role": "user", "text": user}],
    }
    st, js, body = _http("POST", url, payload=payload,
                         headers={"Authorization": "Api-Key " + YANDEX_API_KEY}, timeout=60)
    if st == 200 and isinstance(js, dict):
        try:
            return js["result"]["alternatives"][0]["message"]["text"], None
        except Exception:
            return None, "неожиданный ответ YandexGPT"
    return None, "YandexGPT HTTP {}: {}".format(st, (body or b"")[:200])


_gc = {"token": "", "exp": 0.0}
_gc_lock = threading.Lock()


def _gigachat_token():
    with _gc_lock:
        if _gc["token"] and _gc["exp"] > time.time() + 60:
            return _gc["token"], None
        if not GIGACHAT_AUTH_KEY:
            return None, "нет GIGACHAT_AUTH_KEY"
        req = urllib.request.Request("https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                                     data=b"scope=GIGACHAT_API_PERS", method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        req.add_header("Accept", "application/json")
        req.add_header("RqUID", str(uuid.uuid4()))
        req.add_header("Authorization", "Basic " + GIGACHAT_AUTH_KEY)
        ctx = ssl._create_unverified_context()   # у Сбера собственный корневой сертификат
        try:
            with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
                js = json.loads(r.read().decode("utf-8"))
            tok = js.get("access_token")
            if not tok:
                return None, "GigaChat: нет access_token"
            _gc["token"] = tok
            exp = js.get("expires_at")
            _gc["exp"] = (float(exp) / 1000.0) if exp else (time.time() + 1500)
            return tok, None
        except urllib.error.HTTPError as e:
            return None, "GigaChat oauth HTTP {}: {}".format(e.code, e.read()[:200])
        except Exception as e:
            return None, "GigaChat oauth: {}".format(e)


def _ai_gigachat(system, user, max_tokens=700):
    tok, err = _gigachat_token()
    if not tok:
        return None, err
    url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
    payload = {"model": "GigaChat", "temperature": 0.6, "max_tokens": int(max_tokens),
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header("Authorization", "Bearer " + tok)
    try:
        with urllib.request.urlopen(req, timeout=60, context=ssl._create_unverified_context()) as r:
            js = json.loads(r.read().decode("utf-8"))
        return js["choices"][0]["message"]["content"], None
    except urllib.error.HTTPError as e:
        return None, "GigaChat HTTP {}: {}".format(e.code, e.read()[:200])
    except Exception as e:
        return None, "GigaChat: {}".format(e)


def _ai_generate(system, user, max_tokens=700):
    order = ["yandex", "gigachat"] if AI_PROVIDER == "auto" else [AI_PROVIDER]
    errors = []
    for p in order:
        if p == "yandex":
            text, err = _ai_yandex(system, user, max_tokens)
        elif p == "gigachat":
            text, err = _ai_gigachat(system, user, max_tokens)
        else:
            continue
        if text:
            return _clean_ai(text), p, None
        if err:
            errors.append(err)
    return None, None, "; ".join(errors) or "AI не настроен (нет ключей)"


def _clean_ai(text):
    t = (text or "").strip()
    t = re.sub(r"^(?:вариант\s*\d+\s*[:.\-]\s*)", "", t, flags=re.I)
    t = re.sub(r"^\*\*(.+?)\*\*$", r"\1", t)
    t = t.strip().strip('"').strip("«»").strip()
    t = re.sub(r"^(?:Title|Заголовок|Description|Описание|Keywords|Ключевые слова|Текст)\s*[:：]\s*", "", t, flags=re.I)
    return t.replace("**", "").strip()


def _ai_ask(data, task, path, value):
    brand = data.get("brand") or {}
    cities = ", ".join([c.get("name", "") for c in ((data.get("cities") or {}).get("items") or []) if isinstance(c, dict)])
    services = ", ".join([s.get("title", "") for s in ((data.get("services") or {}).get("items") or []) if isinstance(s, dict)])
    seo = data.get("seo") or {}
    base = ("Компания: {}. Города: {}. Услуги: {}. Телефон: {}. Сайт: {}."
            .format(brand.get("name", "Кухни Островский"), cities or "Ростов-на-Дону, Батайск, Азов",
                    services or "кухни и корпусная мебель на заказ",
                    brand.get("phone", ""), seo.get("domain") or DOMAIN))
    system = ("Ты опытный русскоязычный копирайтер и SEO-специалист для локального бизнеса "
              "(мебель на заказ). Пиши живым, конкретным языком, без воды, без markdown, "
              "без кавычек вокруг ответа, без слова «Вариант». Отвечай ТОЛЬКО готовым текстом.")
    user = base + "\nБез emoji. Не выдумывай цены, сроки и проценты.\n\n"
    if task == "seo_title":
        user += "Составь SEO Title (title страницы) до 65 символов: название компании + услуга + 2 города + выгода. Верни одну строку."
    elif task == "seo_description":
        user += ("Составь meta description до 160 символов: что делаем, где, выгода (бесплатный замер и проект), "
                 "телефон в конце. Верни одну строку.")
    elif task == "seo_keywords":
        user += "Составь 12-15 ключевых фраз через запятую (поисковые запросы по кухням и мебели на заказ в этих городах)."
    elif task == "hero_sub":
        user += "Напиши подзаголовок на главном экране: 1-2 предложения, до 220 символов, про кухни и корпусную мебель под ключ."
    elif task == "about_text":
        user += "Напиши блок «о нас» (3-4 предложения, до 400 символов) от лица руководителя мастерской."
    elif task == "service_text":
        user += "Опиши услугу одним предложением до 130 символов. Название услуги: " + (value or "")
    elif task == "city_text":
        user += "Напиши одно предложение до 120 символов про работу в городе: " + (value or "")
    elif task == "cta_text":
        user += "Напиши короткий призыв к действию (1-2 предложения, до 180 символов) с приглашением позвонить."
    elif task == "watermark":
        user += "Придумай ОДНО короткое слово (до 10 символов) для фоновой надписи секции сайта на тему: " + (value or "мебель")
    elif task == "shorten":
        user += "Сократи текст до 1-2 предложений, сохранив смысл и ключевые слова:\n" + (value or "")
    elif task == "expand":
        user += "Дополни и улучши текст (до 3 предложений), сохранив смысл:\n" + (value or "")
    else:
        user += "Улучши текст: убери ошибки и воду, сделай живее, сохрани смысл и длину:\n" + (value or "")
    return system, user


# ============================================================
#  КЭШ ДАННЫХ, СЕССИИ
# ============================================================
_data_lock = threading.Lock()
_data_cache = None
_cache_ts = 0.0
_db_state = {"read": None, "write": None}

_auth_lock = threading.Lock()
_sessions = {}
_login_fails = {}


def _session_secret():
    """Ключ подписи сессии: не меняется между перезапусками/деплоями,
    поэтому вход в админку сохраняется на устройстве."""
    raw = "mebel-cms::{}::{}::{}".format(ADMIN_LOGIN_ENV, ADMIN_PASSWORD_ENV, (SUPABASE_SERVICE or "")[:32])
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _new_session():
    """Сессия без хранения на сервере: подписанная метка со сроком годности."""
    exp = int(time.time()) + SESSION_TTL
    payload = "{}|{}".format(int(time.time()), exp)
    sig = hmac.new(_session_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=") + "." + sig


def _check_session(token):
    if not token or "." not in token:
        return False
    body, _, sig = token.rpartition(".")
    try:
        payload = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode("utf-8")
    except Exception:
        return False
    good = hmac.new(_session_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(good, sig):
        return False
    try:
        exp = int(payload.split("|")[1])
    except Exception:
        return False
    return exp > time.time()


def _drop_session(token):
    """Подписанную метку на сервере не храним — выход просто стирает cookie."""
    if token:
        with _auth_lock:
            _sessions.pop(token, None)


def _login_blocked(ip):
    with _auth_lock:
        rec = _login_fails.get(ip)
        if not rec:
            return False
        cnt, until = rec
        if until and until < time.time():
            _login_fails.pop(ip, None)
            return False
        return cnt >= 8


def _login_note(ip, ok):
    with _auth_lock:
        if ok:
            _login_fails.pop(ip, None)
            return
        cnt, _ = _login_fails.get(ip, (0, 0))
        _login_fails[ip] = (cnt + 1, time.time() + 600)


def load_fresh():
    """Читает БД синхронно. Если БД недоступна — последний кэш или дефолты."""
    global _data_cache, _cache_ts
    raw, ok = _fetch_from_supabase()
    _db_state["read"] = ok
    with _data_lock:
        if not ok:
            if _data_cache is not None:
                _cache_ts = time.time()
                print("[load] БД недоступна — отдаю кэш", flush=True)
                return _data_cache
            _data_cache = _json_clone(DEFAULT_DATA)
            _cache_ts = time.time()
            print("[load] БД недоступна — дефолтный контент", flush=True)
            return _data_cache
        if raw is None:
            data = _json_clone(DEFAULT_DATA)
            print("[load] строка в БД пустая — дефолтный контент", flush=True)
        else:
            data = _merge_deep(DEFAULT_DATA, _migrate(raw))
            print("[load] из БД: {} разделов".format(len(raw)), flush=True)
        _data_cache = data
        _cache_ts = time.time()
        _bump_data_sig()
    return data


_refresh_lock = threading.Lock()
_refreshing = [False]


def _bg_refresh():
    try:
        load_fresh()
    except Exception as e:
        print("[load] фон-обновление: {}".format(e), flush=True)
    finally:
        _refreshing[0] = False


def load_data():
    """Отдаёт кэш МГНОВЕННО; если он устарел — обновляет в фоне (страница не ждёт Supabase)."""
    global _cache_ts
    with _data_lock:
        cached = _data_cache
        fresh = cached is not None and (time.time() - _cache_ts < CACHE_TTL)
    if cached is None:
        return load_fresh()
    if not fresh and not _refreshing[0]:
        with _refresh_lock:
            if not _refreshing[0]:
                _refreshing[0] = True
                threading.Thread(target=_bg_refresh, daemon=True).start()
    return cached


def save_data(data):
    global _data_cache, _cache_ts
    ok = _save_to_supabase(data)
    _db_state["write"] = ok
    if ok:
        with _data_lock:
            _data_cache = _merge_deep(DEFAULT_DATA, _migrate(data))
            _cache_ts = time.time()
    return ok


def _meta_of(data):
    m = data.get("_meta") if isinstance(data, dict) else None
    if not isinstance(m, dict):
        m = {}
    try:
        rev = int(m.get("rev") or 0)
    except Exception:
        rev = 0
    return {"rev": rev, "at": str(m.get("at") or ""), "by": str(m.get("by") or "")}


def _backup_save(data, rev, keep=40):
    """Копия текущего содержимого в приватный бакет перед перезаписью."""
    try:
        name = "rev-{:05d}-{}.json".format(int(rev), time.strftime("%Y-%m-%d_%H-%M-%S"))
        blob = json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")
        saved = _storage_put(BACKUP_BUCKET, name, blob, "application/json")
        items = _storage_list_bucket(BACKUP_BUCKET, 200)
        if len(items) > keep:
            old = [it["name"] for it in items[keep:]]
            if old:
                _storage_delete(BACKUP_BUCKET, old)
        return saved
    except Exception as e:
        print("[backup] {}".format(e), flush=True)
        return None


def save_versioned(data, client_rev=None, force=False, who=""):
    """Сохранение с защитой от перезаписи чужого снимка (другая вкладка/устройство)."""
    global _data_cache, _cache_ts
    current = load_fresh()
    cur_rev = _meta_of(current)["rev"]
    try:
        client_rev = cur_rev if client_rev is None else int(client_rev)
    except Exception:
        client_rev = cur_rev
    if not force and client_rev != cur_rev:
        return {"ok": False, "conflict": True, "server_rev": cur_rev, "client_rev": client_rev,
                "server_at": _meta_of(current)["at"],
                "message": "База уже обновлена (rev {}), у вас снимок rev {}.".format(cur_rev, client_rev)}
    backup = _backup_save(current, cur_rev)
    new = _json_clone(data)
    new.pop("_meta", None)
    new["_meta"] = {"rev": cur_rev + 1, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "by": who[:60]}
    ok = _save_to_supabase(new)
    _db_state["write"] = ok
    if not ok:
        return {"ok": False, "error": "запись в Supabase не прошла (проверьте SUPABASE_SERVICE_KEY на хостинге)"}
    _audit("Сохранение контента", who, "rev {} → {}".format(cur_rev, cur_rev + 1))
    verified = False
    check, ok_read = _fetch_from_supabase(timeout=10)
    if ok_read and isinstance(check, dict):
        stored = _merge_deep(DEFAULT_DATA, _migrate(check))
        verified = (_meta_of(check)["rev"] == cur_rev + 1)
    else:
        stored = new
    with _data_lock:
        _data_cache = stored
        _cache_ts = time.time()
        _bump_data_sig()
    return {"ok": True, "rev": cur_rev + 1, "verified": bool(verified), "backup": backup}


# ============================================================
#  ПРОКСИ VK-КАРТИНОК
# ============================================================
_img_cache = {}
_img_fail = {}
_img_lock = threading.Lock()
_VK_RE = re.compile(r'https://(?:sun\d+-\d+\.)?vkuserphoto\.ru/[^\s"\'\)<>]+')
_PROT_RE = re.compile(r"\x00PROT(\d+)\x00")


def _fetch_image(url):
    now = time.time()
    with _img_lock:
        c = _img_cache.get(url)
        if c and now - c[1] < IMG_TTL:
            return c[0], c[2]
        f = _img_fail.get(url)
        if f and now - f < IMG_FAIL_TTL:
            return None, None
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
            "Referer": "https://vk.com/",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        })
        with urllib.request.urlopen(req, timeout=IMG_TIMEOUT) as resp:
            data = resp.read()
            ct = resp.headers.get("Content-Type", "image/jpeg")
        if data:
            with _img_lock:
                if len(_img_cache) > 400:
                    _img_cache.clear()
                _img_cache[url] = (data, now, ct)
            return data, ct
    except Exception as e:
        print("[img] {} -> {}".format(url[:60], e), flush=True)
    with _img_lock:
        if len(_img_fail) > 500:
            _img_fail.clear()
        _img_fail[url] = now
    return None, None


def _img_proxy_url(url):
    return "/img?u=" + base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii").rstrip("=")


def _proxify_urls(html):
    """Меняем прямые ссылки VK на /img?u=... (кроме og:image и JSON-LD)."""
    if not IMG_PROXY:
        return html
    stash = []

    def keep(m):
        stash.append(m.group(0))
        return "\x00PROT%d\x00" % (len(stash) - 1)

    html = re.sub(r'<script type="application/ld\+json">.*?</script>', keep, html, flags=re.S)
    html = re.sub(r'<meta property="og:image"[^>]*>', keep, html)
    html = _VK_RE.sub(lambda m: _img_proxy_url(m.group(0)), html)
    if stash:
        html = _PROT_RE.sub(lambda m: stash[int(m.group(1))], html)
    return html


# ============================================================
#  СТРАНИЦА, ROBOTS, SITEMAP, 404
# ============================================================
_page_cache = {"mtime": -1.0, "html": ""}
_page_lock = threading.Lock()


def _page_template():
    """Страница сайта лежит в этом файле (PAGE). Если рядом положить page.html
    с шаблонными метками ({{hero.…}}), он будет использован вместо встроенного —
    удобно править разметку отдельным файлом."""
    p = os.path.join(ROOT, "page.html")
    try:
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as f:
                ext = f.read()
            if "{{hero." in ext or "{{seo." in ext:
                return ext
    except Exception as e:
        print("[page] page.html прочитан с ошибкой: {}".format(e), flush=True)
    return PAGE


_render_cache = {"sig": None, "html": ""}
_render_lock = threading.Lock()
_data_sig = [0]


def _bump_data_sig():
    _data_sig[0] += 1


def _inject_site_ui(html, data):
    'Добавляет компактную форму заявки и короткую заставку без изменения page.html.'
    lead = data.get("lead_form") or {}
    if lead.get("enabled", True) and 'id="ostLeadModal"' not in html:
        brand = data.get("brand") or {}
        seo = data.get("seo") or {}
        name = _escape(str(brand.get("name") or "Кухни Островский"))
        logo = _escape(str(seo.get("favicon_url") or brand.get("logo_url") or "/favicon-192x192.png"))
        title = _escape(str(lead.get("title") or "Оставить заявку"))
        subtitle = _escape(str(lead.get("subtitle") or "Оставьте номер — свяжемся и обсудим задачу."))
        button = _escape(str(lead.get("button") or "Оставить заявку"))
        widget = """<style id="ostLeadStyles">
#ostLeadFab{position:fixed;right:22px;bottom:22px;z-index:8990;border:1px solid rgba(236,207,160,.5);background:linear-gradient(135deg,#ecd09c,#c89e58);color:#17120b;border-radius:999px;padding:13px 18px;font:700 13px/1 system-ui;box-shadow:0 16px 40px -18px #000;cursor:pointer;transition:.3s}
#ostLeadFab:hover{transform:translateY(-2px)}
#ostLeadModal{position:fixed;inset:0;z-index:8999;display:none;align-items:center;justify-content:center;padding:18px;background:rgba(8,6,4,.72);backdrop-filter:blur(12px)}
#ostLeadModal.open{display:flex}
.ostLeadCard{width:min(470px,100%);position:relative;border:1px solid rgba(236,207,160,.25);border-radius:24px;background:linear-gradient(160deg,rgba(28,23,17,.98),rgba(12,10,8,.98));box-shadow:0 35px 90px -35px #000;padding:28px}
.ostLeadTop{display:flex;align-items:center;gap:12px;margin-bottom:20px}.ostLeadLogo{width:48px;height:48px;border-radius:15px;object-fit:cover;border:1px solid rgba(236,207,160,.28)}
.ostLeadCard h3{font:600 25px/1.05 Georgia,serif;color:#fff;margin:0}.ostLeadSub{color:#b9ad9a;font:13px/1.55 system-ui;margin:5px 0 0}
.ostLeadClose{position:absolute;right:16px;top:14px;width:34px;height:34px;border:1px solid rgba(255,255,255,.1);border-radius:50%;background:rgba(255,255,255,.04);color:#fff;cursor:pointer}
.ostLeadField{margin:0 0 12px}.ostLeadField label{display:block;color:#eccfa0;font:700 10px/1 system-ui;letter-spacing:1.2px;text-transform:uppercase;margin:0 0 6px}
.ostLeadField input,.ostLeadField textarea{width:100%;border:1px solid rgba(255,255,255,.1);border-radius:12px;background:rgba(0,0,0,.28);color:#fff;padding:12px 13px;font:14px system-ui;outline:none}
.ostLeadField textarea{min-height:82px;resize:vertical}.ostLeadSend{width:100%;border:0;border-radius:12px;padding:13px 16px;background:linear-gradient(135deg,#ecd09c,#c89e58);color:#17120b;font:800 13px system-ui;cursor:pointer;margin-top:4px}
.ostLeadNote{color:#71685c;font:10.5px/1.45 system-ui;text-align:center;margin:9px 2px 0}.ostLeadHp{position:absolute;left:-10000px;width:1px;height:1px;overflow:hidden}
@media(max-width:600px){#ostLeadFab{right:14px;bottom:14px;padding:12px 15px}.ostLeadCard{padding:24px 18px;border-radius:20px}}
</style>
<button id="ostLeadFab" type="button">""" + button + """</button>
<div id="ostLeadModal" aria-hidden="true"><div class="ostLeadCard" role="dialog" aria-modal="true">
<button class="ostLeadClose" id="ostLeadClose" type="button" aria-label="Закрыть">×</button>
<div class="ostLeadTop"><img class="ostLeadLogo" src=""" + logo + """ alt=""" + name + """><div><h3>""" + title + """</h3><p class="ostLeadSub">""" + subtitle + """</p></div></div>
<form id="ostLeadForm" autocomplete="on">
<div class="ostLeadField"><label>Имя</label><input name="name" maxlength="120" placeholder="Как к вам обращаться"></div>
<div class="ostLeadField"><label>Телефон *</label><input name="phone" type="tel" maxlength="80" required placeholder="+7 (___) ___-__-__"></div>
<div class="ostLeadField"><label>Что нужно сделать</label><textarea name="message" maxlength="1000" placeholder="Например: нужна кухня по размерам"></textarea></div>
<div class="ostLeadHp"><input name="website" tabindex="-1" autocomplete="off"></div>
<button class="ostLeadSend" type="submit">Отправить заявку</button><p class="ostLeadNote">Контакт нужен только для связи по заявке.</p>
</form></div></div>
<script>(function(){const f=document.getElementById('ostLeadFab'),m=document.getElementById('ostLeadModal'),c=document.getElementById('ostLeadClose'),form=document.getElementById('ostLeadForm');function o(){m.classList.add('open');m.setAttribute('aria-hidden','false');setTimeout(()=>form&&form.querySelector('input[name=name]')?.focus(),70)}function x(){m.classList.remove('open');m.setAttribute('aria-hidden','true')}f&&f.addEventListener('click',o);c&&c.addEventListener('click',x);m&&m.addEventListener('click',e=>{if(e.target===m)x()});document.addEventListener('keydown',e=>{if(e.key==='Escape')x()});form&&form.addEventListener('submit',async e=>{e.preventDefault();const b=form.querySelector('.ostLeadSend'),fd=new FormData(form),body={name:String(fd.get('name')||'').trim(),phone:String(fd.get('phone')||'').trim(),message:String(fd.get('message')||'').trim(),website:String(fd.get('website')||''),page:location.href};b.disabled=true;b.textContent='Отправляю…';try{const r=await fetch('/api/lead',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),j=await r.json();if(!r.ok||!j.ok)throw Error(j.error||'Ошибка');form.reset();b.textContent='Заявка отправлена ✓';setTimeout(()=>{b.textContent='Отправить заявку';b.disabled=false;x()},850)}catch(err){b.disabled=false;b.textContent='Отправить заявку';alert('Не удалось отправить заявку. Позвоните или напишите напрямую.')}})})();</script>"""
        loader = """<style id="ostLoaderStyles">
#ostSiteLoader{position:fixed;inset:0;z-index:100000;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;background:radial-gradient(circle at 50% 42%,rgba(236,207,160,.16),transparent 27%),radial-gradient(circle at 20% 80%,rgba(163,124,63,.15),transparent 35%),linear-gradient(135deg,#100d09,#070605 58%,#161007);transition:opacity .28s ease,visibility .28s ease}
#ostSiteLoader img{width:76px;height:76px;object-fit:cover;border-radius:22px;border:1px solid rgba(236,207,160,.35);box-shadow:0 0 45px rgba(236,207,160,.18),0 18px 45px -25px #000}
.ostLoaderName{font:600 23px/1 Georgia,serif;letter-spacing:.8px;color:#f8efe0}.ostLoaderLine{width:80px;height:1px;background:linear-gradient(90deg,transparent,#ecd09c,transparent);opacity:.7}
#ostSiteLoader.done{opacity:0;visibility:hidden;pointer-events:none}
html.ost-lite .panel .bg,html.ost-lite .panel .content{transform:none!important}html.ost-lite *,html.ost-lite *::before,html.ost-lite *::after{animation-duration:.001ms!important;animation-iteration-count:1!important;transition-duration:.001ms!important}
</style>"""
        html = html.replace("</head>", loader + "</head>", 1)
        html = html.replace("</body>", widget + '<div id="ostSiteLoader"><img src="' + logo + '" alt=""><div class="ostLoaderName">' + name + '</div><div class="ostLoaderLine"></div></div><script>(function(){try{var c=navigator.connection;if((c&&c.saveData)||navigator.hardwareConcurrency&&navigator.hardwareConcurrency<=4)document.documentElement.classList.add("ost-lite")}catch(e){}var l=document.getElementById("ostSiteLoader");var seen=false;try{seen=sessionStorage.getItem("ostLoaderSeen")==="1"}catch(e){}if(seen){l.remove();return}try{sessionStorage.setItem("ostLoaderSeen","1")}catch(e){}window.addEventListener("load",function(){setTimeout(function(){l.classList.add("done");setTimeout(function(){l.remove()},330)},260)});setTimeout(function(){l.classList.add("done")},1200)})();</script></body>', 1)
    return html


def render_site():
    """Готовый HTML кэшируется до смены данных — страница отдаётся мгновенно."""
    data = load_data()
    with _page_lock:
        mt = _page_cache.get("mtime")
    sig = (_data_sig[0], mt, id(data))
    with _render_lock:
        if _render_cache["sig"] == sig and _render_cache["html"]:
            return _render_cache["html"]
    ctx = _normalize_context(data)
    try:
        html = render(_page_template(), ctx)
    except Exception as e:
        print("[render] ОШИБКА: {}".format(e), flush=True)
        html = _page_template()
    html = _proxify_urls(html)
    html = _inject_site_ui(html, data)
    with _render_lock:
        _render_cache["sig"] = sig
        _render_cache["html"] = html
    return html


def build_robots(data):
    dom, host = _domain(data), _host(data)
    seo = data.get("seo") or {}
    custom = (seo.get("robots") or "").strip()
    if custom:
        return custom.replace("{{domain}}", dom).replace("{{host}}", host) + "\n"
    return ("User-agent: *\n"
            "Allow: /\n"
            "Disallow: /admin\n"
            "Clean-param: utm_source&utm_medium&utm_campaign&utm_term&utm_content&yclid&gclid\n\n"
            "Host: {}\n"
            "Sitemap: {}/sitemap.xml\n").format(host, dom)


def build_sitemap(data):
    dom = _domain(data)
    today = date.today().isoformat()
    seo = data.get("seo") or {}
    works = [w for w in ((data.get("works") or {}).get("items") or []) if isinstance(w, dict) and w.get("url")]
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
             '        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">',
             '  <url>',
             '    <loc>{}</loc>'.format(_escape(dom + "/")),
             '    <lastmod>{}</lastmod>'.format(today),
             '    <changefreq>weekly</changefreq>',
             '    <priority>1.0</priority>']
    brand = (data.get("brand") or {}).get("name") or "Кухни Островский"
    for w in works[:60]:
        url = str(w.get("url") or "")
        if not url.startswith("http"):
            continue
        parts.append('    <image:image><image:loc>{}</image:loc><image:title>{}</image:title></image:image>'.format(
            _escape(url), _escape(str(w.get("alt") or brand))))
    parts.append('  </url>')
    for it in (seo.get("extra_urls") or []):
        if not isinstance(it, dict):
            continue
        loc = (it.get("loc") or "").strip()
        if not loc:
            continue
        if loc.startswith("/"):
            loc = dom + loc
        parts.append("  <url>\n    <loc>{}</loc>\n    <lastmod>{}</lastmod>\n"
                     "    <changefreq>{}</changefreq>\n    <priority>{}</priority>\n  </url>".format(
                         _escape(loc), today, _escape((it.get("changefreq") or "monthly").strip()),
                         _escape((it.get("priority") or "0.6").strip())))
    parts.append('</urlset>')
    return "\n".join(parts) + "\n"


def build_manifest(data):
    brand = data.get("brand") or {}
    design = data.get("design") or {}
    seo = data.get("seo") or {}
    name = brand.get("name", "Кухни Островский")
    return json.dumps({
        "name": seo.get("title") or name,
        "short_name": name,
        "description": seo.get("description") or "",
        "start_url": "/", "display": "standalone",
        "background_color": design.get("bg", "#0e0c09"),
        "theme_color": design.get("bg", "#0e0c09"),
        "lang": "ru-RU",
        "icons": [
            {"src": "/favicon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
            {"src": "/favicon.ico", "sizes": "16x16 32x32 48x48 64x64", "type": "image/x-icon", "purpose": "any"},
            {"src": "/favicon-16x16.png", "sizes": "16x16", "type": "image/png", "purpose": "any"},
            {"src": "/favicon-32x32.png", "sizes": "32x32", "type": "image/png", "purpose": "any"},
            {"src": "/apple-touch-icon.png", "sizes": "180x180", "type": "image/png", "purpose": "any"},
            {"src": "/favicon-192x192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        ],
    }, ensure_ascii=False)


PAGE_404_TPL = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, follow">
<title>404 — %(title)s | %(brand)s</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Manrope',system-ui,sans-serif;background:%(bg)s;color:%(text_color)s;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;text-align:center}
.card{max-width:560px;width:100%%}
.code{font-family:Georgia,serif;font-size:clamp(80px,18vw,160px);line-height:1;background:linear-gradient(135deg,%(gold_soft)s,%(gold)s 55%%,%(gold_deep)s);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;filter:drop-shadow(0 8px 26px rgba(212,175,106,.35))}
h1{font-family:Georgia,serif;font-size:clamp(24px,5vw,34px);color:#fff;margin:14px 0 10px;letter-spacing:.4px}
p{color:%(muted)s;font-size:15px;line-height:1.7;margin-bottom:28px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:10px;padding:15px 30px;border-radius:14px;background:linear-gradient(135deg,%(gold_soft)s,%(gold)s 55%%,%(gold_deep)s);color:#17120b;font-weight:700;font-size:13px;letter-spacing:1.2px;text-transform:uppercase;text-decoration:none;box-shadow:0 18px 44px rgba(212,175,106,.28);transition:.3s}
.btn:hover{transform:translateY(-3px)}
.contacts{margin-top:30px;color:%(muted)s;font-size:13.5px;line-height:1.9}
.contacts a{color:%(gold_soft)s;text-decoration:none}
</style>
</head>
<body>
<div class="card">
  <div class="code">404</div>
  <h1>%(title)s</h1>
  <p>%(text)s</p>
  <a class="btn" href="/">%(button)s</a>
  <div class="contacts">%(contacts)s</div>
</div>{{/if}}
</body>
</html>
"""


def build_404(data):
    p = data.get("page404") or {}
    brand = data.get("brand") or {}
    design = data.get("design") or {}
    rows = []
    if brand.get("phone"):
        rows.append('\u260e <a href="tel:%s">%s</a>' % (_escape(brand.get("phone_raw", "")), _escape(brand["phone"])))
    links = []
    if brand.get("telegram"):
        links.append('<a href="%s" target="_blank" rel="noopener">Telegram</a>' % _escape(brand["telegram"]))
    if brand.get("vk"):
        links.append('<a href="%s" target="_blank" rel="noopener">ВКонтакте</a>' % _escape(brand["vk"]))
    if links:
        rows.append(' \u00b7 '.join(links))
    return PAGE_404_TPL % {
        "title": _escape(p.get("title") or "Такой страницы нет"),
        "text": _escape(p.get("text") or "Возможно, ссылка устарела или адрес введён с ошибкой."),
        "button": _escape(p.get("button") or "На главную"),
        "brand": _escape(brand.get("name") or "Кухни Островский"),
        "bg": _escape(design.get("bg") or "#0e0c09"),
        "text_color": _escape(design.get("text") or "#f5efe3"),
        "muted": _escape(design.get("muted") or "#b9ad9a"),
        "gold": _escape(design.get("gold") or "#d4af6a"),
        "gold_soft": _escape(design.get("gold_soft") or "#eccfa0"),
        "gold_deep": _escape(design.get("gold_deep") or "#a37c3f"),
        "contacts": "<br>".join(rows),
    }


# ============================================================
#  FAVICON
# ============================================================
_fc = {"url": "", "data": None, "ts": 0.0}
_ic = {"ico": None, "png16": None, "png32": None, "png180": None, "png192": None}
_fc_lock = threading.Lock()


def _make_icons(data):
    try:
        from PIL import Image
    except Exception:
        return
    try:
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        buf = io.BytesIO()
        img.save(buf, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
        _ic["ico"] = buf.getvalue()

        def png(size):
            c = img.copy()
            c.thumbnail((size, size))
            b = io.BytesIO()
            c.save(b, format="PNG")
            return b.getvalue()

        _ic["png16"] = png(16)
        _ic["png32"] = png(32)
        _ic["png180"] = png(180)
        _ic["png192"] = png(192)
    except Exception as e:
        print("[favicon] {}".format(e), flush=True)


def favicon_source(data=None):
    """Откуда брать иконку: seo.favicon_url -> brand.logo_url -> FAVICON_URL."""
    d = data if isinstance(data, dict) else None
    if d is None:
        try:
            d = load_data()
        except Exception:
            d = None
    urls = []
    if isinstance(d, dict):
        urls.append(str((d.get("seo") or {}).get("favicon_url") or "").strip())
        urls.append(str((d.get("brand") or {}).get("logo_url") or "").strip())
    urls.append(FAVICON_URL)
    for u in urls:
        if u:
            return u
    return FAVICON_URL


def get_favicon(url=None):
    """Скачивает аватарку и держит её в памяти; при смене URL обновляет."""
    url = url or favicon_source()
    now = time.time()
    with _fc_lock:
        if _fc["data"] is not None and _fc["url"] == url and now - _fc["ts"] < 3600:
            return _fc["data"]
    data, _ct = _fetch_image(url)
    if data:
        with _fc_lock:
            _fc["url"] = url
            _fc["data"] = data
            _fc["ts"] = now
        _make_icons(data)
    return data


def favicon_svg(url=None):
    """SVG-иконка поверх той же аватарки (для современных браузеров)."""
    url = url or favicon_source()
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
            '<defs><clipPath id="r"><rect width="64" height="64" rx="14"/></clipPath></defs>'
            '<image href="' + _escape(url) + '" width="64" height="64" '
            'preserveAspectRatio="xMidYMid slice" clip-path="url(#r)"/></svg>')


# ============================================================
#  СХЕМА АДМИНКИ
# ============================================================
def _svg_icon(_unused=None):
    return {"path": "icon", "label": "Иконка", "type": "textarea", "rows": 2, "mono": True,
            "hint": "Только содержимое атрибута d у <path viewBox=\"0 0 24 24\">. "
                    "Например: M3 9h18M3 9v10a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1V9"}


ADMIN_SCHEMA = [
    {"id": "seo", "group": "SEO и код", "title": "SEO и мета", "hint": "Заголовок и описание страницы, Open Graph, robots, sitemap.",
     "fields": [
         {"path": "seo.title", "label": "Title", "type": "textarea", "rows": 2, "ai": "seo_title"},
         {"path": "seo.description", "label": "Description", "type": "textarea", "rows": 3, "ai": "seo_description"},
         {"path": "seo.keywords", "label": "Keywords", "type": "textarea", "rows": 2, "ai": "seo_keywords"},
         {"path": "seo.domain", "label": "Домен сайта", "type": "text", "hint": "Идёт в canonical, robots, sitemap. Можно кириллицей."},
         {"path": "seo.canonical", "label": "Canonical URL", "type": "text"},
         {"path": "seo.robots_meta", "label": "Мета robots", "type": "text"},
         {"path": "seo.og_title", "label": "OG title", "type": "text"},
         {"path": "seo.og_description", "label": "OG description", "type": "textarea", "rows": 2},
         {"path": "seo.og_image", "label": "OG картинка (превью в соцсетях)", "type": "image"},
         {"path": "seo.favicon_url", "label": "Favicon (иконка вкладки и телефона)", "type": "image", "hint": "Пусто = берётся логотип."},
         {"path": "seo.geo_region", "label": "Регион (geo.region)", "type": "text"},
         {"path": "seo.geo_placename", "label": "Город (geo.placename)", "type": "text"},
         {"path": "seo.geo_lat", "label": "Широта", "type": "text"},
         {"path": "seo.geo_lon", "label": "Долгота", "type": "text"},
         {"path": "seo.yandex_verification", "label": "Яндекс: код подтверждения", "type": "text"},
         {"path": "seo.google_verification", "label": "Google: код подтверждения", "type": "text"},
         {"path": "seo.metrika_id", "label": "Номер счётчика Яндекс.Метрики", "type": "text", "hint": "Если заполнить — счётчик вставится сам."},
         {"path": "seo.robots", "label": "robots.txt (весь файл)", "type": "textarea", "rows": 6, "mono": True,
          "hint": "Пусто = сгенерировать автоматически ({{domain}} и {{host}} подставятся сами)."},
     ],
     "lists": [
         {"path": "seo.extra_urls", "label": "Доп. страницы в sitemap", "titleField": "loc",
          "tpl": {"loc": "/", "changefreq": "monthly", "priority": "0.6"},
          "item": [
              {"path": "loc", "label": "URL (можно /ceny/ или полный)", "type": "text"},
              {"path": "changefreq", "label": "changefreq", "type": "select", "options": ["daily", "weekly", "monthly", "yearly"]},
              {"path": "priority", "label": "priority", "type": "text"},
          ]},
     ]},

    {"id": "code", "group": "SEO и код", "title": "Коды и скрипты",
     "hint": "Коды счётчиков, пикселей, чатов. HTML вставляется как есть.",
     "fields": [
         {"path": "code.head", "label": "Код в head (Метрика, Google, пиксели)", "type": "textarea", "rows": 8, "mono": True},
         {"path": "code.body", "label": "Код перед /body (чаты, виджеты)", "type": "textarea", "rows": 8, "mono": True},
     ]},

    {"id": "sections", "group": "Контент", "title": "Секции сайта",
     "hint": "Можно выключить любую секцию — она исчезнет с сайта и из меню по якорю.",
     "fields": [
         {"path": "sections.stats", "label": "Цифры (10+, 5.0, 9/10)", "type": "check"},
         {"path": "sections.about", "label": "О специалисте", "type": "check"},
         {"path": "sections.consult", "label": "Консультация", "type": "check"},
         {"path": "sections.works", "label": "Работы", "type": "check"},
         {"path": "sections.reviews", "label": "Отзывы", "type": "check"},
         {"path": "sections.services", "label": "Услуги", "type": "check"},
         {"path": "sections.process", "label": "Этапы работы", "type": "check"},
         {"path": "sections.guarantees", "label": "Гарантии", "type": "check"},
         {"path": "sections.cities", "label": "Города", "type": "check"},
         {"path": "sections.cta", "label": "Призыв к действию", "type": "check"},
         {"path": "sections.contacts", "label": "Контакты", "type": "check"},
         {"path": "sections.footer", "label": "Подвал", "type": "check"},
         {"path": "sections.cookie", "label": "Cookie-баннер", "type": "check"},
     ]},

    {"id": "design", "group": "SEO и код", "title": "Дизайн и цвета", "hint": "Цвета, шрифты, скругления и ширина сайта.",
     "fields": [
         {"path": "design.radius", "label": "Скругление карточек", "type": "text", "hint": "Например 24px или 8px."},
         {"path": "design.container", "label": "Ширина контента", "type": "text", "hint": "Например 1180px или 1320px."},
         {"path": "design.bg", "label": "Фон сайта", "type": "color"},
         {"path": "design.gold", "label": "Золотой (основной акцент)", "type": "color"},
         {"path": "design.gold_soft", "label": "Светлое золото", "type": "color"},
         {"path": "design.gold_deep", "label": "Тёмное золото (градиент)", "type": "color"},
         {"path": "design.text", "label": "Основной текст", "type": "color"},
         {"path": "design.muted", "label": "Второстепенный текст", "type": "color"},
         {"path": "design.fonts_url", "label": "Ссылка на шрифты Google", "type": "text", "mono": True},
         {"path": "design.custom_css", "label": "Свой CSS", "type": "textarea", "rows": 8, "mono": True},
     ]},

    {"id": "brand", "group": "Контент", "title": "Бренд и меню", "fields": [
        {"path": "brand.name", "label": "Название", "type": "text"},
        {"path": "brand.sub", "label": "Подпись под названием", "type": "text"},
        {"path": "brand.logo_url", "label": "Логотип / аватар", "type": "image"},
        {"path": "brand.phone", "label": "Телефон (как показывать)", "type": "text"},
        {"path": "brand.phone_raw", "label": "Телефон для ссылок tel:", "type": "text"},
        {"path": "brand.telegram", "label": "Telegram (ссылка)", "type": "text"},
        {"path": "brand.vk", "label": "VK (ссылка)", "type": "text"},
        {"path": "brand.max", "label": "MAX (ссылка или tel:)", "type": "text"},
        {"path": "nav.cta_label", "label": "Кнопка звонка в мобильном меню", "type": "text"},
        {"path": "nav.cta_href", "label": "Кнопка звонка — ссылка", "type": "text"},
     ],
     "lists": [
         {"path": "nav.items", "label": "Пункты меню", "titleField": "label",
          "tpl": {"label": "Новый пункт", "href": "#top"},
          "item": [{"path": "label", "label": "Текст", "type": "text"},
                   {"path": "href", "label": "Ссылка (#якорь)", "type": "text"}]},
     ]},

    {"id": "hero", "group": "Контент", "title": "Главный экран", "fields": [
        {"path": "hero.eyebrow", "label": "Надзаголовок", "type": "text"},
        {"path": "hero.title_before", "label": "Заголовок (начало)", "type": "text"},
        {"path": "hero.title_em", "label": "Заголовок (золотые слова)", "type": "text"},
        {"path": "hero.sub", "label": "Подзаголовок", "type": "textarea", "rows": 3, "ai": "hero_sub"},
        {"path": "hero.btn1", "label": "Кнопка 1 — текст", "type": "text"},
        {"path": "hero.btn1_href", "label": "Кнопка 1 — ссылка", "type": "text"},
        {"path": "hero.btn2", "label": "Кнопка 2 — текст", "type": "text"},
        {"path": "hero.btn2_href", "label": "Кнопка 2 — ссылка", "type": "text"},
        {"path": "hero.scroll_cue", "label": "Подпись «Листайте» внизу", "type": "text"},
        {"path": "hero.watermark", "label": "Фоновая надпись секции", "type": "text", "ai": "watermark"},
        {"path": "hero.bg", "label": "Фон", "type": "image"},
     ]},

    {"id": "stats", "group": "Контент", "title": "Цифры (счётчики)", "fields": [
        {"path": "stats.bg", "label": "Фон", "type": "image"},
     ],
     "lists": [
         {"path": "stats.items", "label": "Цифры", "titleField": "label",
          "tpl": {"prefix": "", "num": "10", "suffix": "+", "decimal": "", "label": "лет опыта"},
          "item": [
              {"path": "num", "label": "Число", "type": "text"},
              {"path": "decimal", "label": "Знаков после запятой (пусто или 1)", "type": "text"},
              {"path": "prefix", "label": "Префикс", "type": "text"},
              {"path": "suffix", "label": "Суффикс (%, +, /10)", "type": "text"},
              {"path": "label", "label": "Подпись", "type": "text"},
          ]},
     ]},

    {"id": "about", "group": "Контент", "title": "О специалисте", "fields": [
        {"path": "about.kicker", "label": "Надзаголовок", "type": "text"},
        {"path": "about.title", "label": "Заголовок", "type": "text"},
        {"path": "about.text", "label": "Текст справа (можно HTML)", "type": "textarea", "rows": 4, "ai": "about_text"},
        {"path": "about.photo", "label": "Фото", "type": "image"},
        {"path": "about.name", "label": "Имя", "type": "text"},
        {"path": "about.role", "label": "Должность", "type": "text"},
        {"path": "about.card_text", "label": "Текст в карточке (можно HTML)", "type": "textarea", "rows": 3, "ai": "improve"},
        {"path": "about.bg", "label": "Фон", "type": "image"},
     ],
     "lists": [
         {"path": "about.features", "label": "Плюсы (галочки)", "titleField": "", "tpl": "Новое преимущество",
          "item": [{"path": "", "label": "", "type": "text", "placeholder": "Например: Гарантия качества"}]},
     ]},

    {"id": "consult", "group": "Контент", "title": "Блок консультации", "fields": [
        {"path": "consult.kicker", "label": "Надзаголовок", "type": "text"},
        {"path": "consult.title", "label": "Заголовок", "type": "text"},
        {"path": "consult.phone", "label": "Телефон (как показывать)", "type": "text"},
        {"path": "consult.phone_raw", "label": "Телефон для tel:", "type": "text"},
        {"path": "consult.text", "label": "Текст (можно HTML)", "type": "textarea", "rows": 3, "ai": "improve"},
        {"path": "consult.bg", "label": "Фон", "type": "image"},
     ]},

    {"id": "works", "group": "Контент", "title": "Работы (фото)", "fields": [
        {"path": "works.kicker", "label": "Надзаголовок", "type": "text"},
        {"path": "works.title", "label": "Заголовок", "type": "text"},
        {"path": "works.subtitle", "label": "Подзаголовок", "type": "textarea", "rows": 2},
        {"path": "works.hint", "label": "Подпись «Листайте»", "type": "text"},
        {"path": "works.watermark", "label": "Фоновая надпись секции", "type": "text", "ai": "watermark"},
        {"path": "works.more_text", "label": "Строка под каруселью", "type": "text"},
        {"path": "works.more_label", "label": "Ссылка — текст", "type": "text"},
        {"path": "works.more_href", "label": "Ссылка — URL", "type": "text"},
        {"path": "works.bg", "label": "Фон", "type": "image"},
     ],
     "lists": [
         {"path": "works.items", "label": "Фотографии работ", "titleField": "alt",
          "tpl": {"url": "", "alt": "Кухня на заказ"},
          "item": [
              {"path": "url", "label": "Картинка", "type": "image"},
              {"path": "alt", "label": "Alt (для SEO)", "type": "text"},
          ]},
     ]},

    {"id": "reviews", "group": "Контент", "title": "Отзывы", "fields": [
        {"path": "reviews.kicker", "label": "Надзаголовок", "type": "text"},
        {"path": "reviews.title", "label": "Заголовок", "type": "text"},
        {"path": "reviews.subtitle", "label": "Подзаголовок", "type": "textarea", "rows": 2},
        {"path": "reviews.hint", "label": "Подпись «Листайте»", "type": "text"},
        {"path": "reviews.watermark", "label": "Фоновая надпись секции", "type": "text", "ai": "watermark"},
        {"path": "reviews.more_text", "label": "Строка под каруселью", "type": "text"},
        {"path": "reviews.more_label", "label": "Ссылка — текст", "type": "text"},
        {"path": "reviews.more_href", "label": "Ссылка — URL", "type": "text"},
        {"path": "reviews.bg", "label": "Фон", "type": "image"},
        {"path": "reviews.video_poster", "label": "Превью для видеоотзывов", "type": "image"},
     ],
     "lists": [
         {"path": "reviews.items", "label": "Отзывы", "titleField": "name",
          "tpl": {"name": "", "sub": "", "stars": 5, "avatar": "", "text": "", "video": "", "poster": "", "photo": ""},
          "item": [
              {"path": "name", "label": "Имя", "type": "text"},
              {"path": "sub", "label": "Что заказывали", "type": "text"},
              {"path": "stars", "label": "Звёзд (1-5)", "type": "text"},
              {"path": "avatar", "label": "Аватар", "type": "image"},
              {"path": "text", "label": "Текст отзыва", "type": "textarea", "rows": 4},
              {"path": "photo", "label": "Фото к отзыву (необязательно)", "type": "image", "hint": "Покажется под текстом отзыва."},
              {"path": "video", "label": "Видео: ссылка для iframe (vk video_ext.php)", "type": "text"},
              {"path": "poster", "label": "Превью видео", "type": "image"},
          ]},
     ]},

    {"id": "services", "group": "Контент", "title": "Услуги", "fields": [
        {"path": "services.kicker", "label": "Надзаголовок", "type": "text"},
        {"path": "services.title", "label": "Заголовок", "type": "text"},
        {"path": "services.subtitle", "label": "Подзаголовок", "type": "textarea", "rows": 2},
        {"path": "services.watermark", "label": "Фоновая надпись секции", "type": "text", "ai": "watermark"},
        {"path": "services.bg", "label": "Фон", "type": "image"},
     ],
     "lists": [
         {"path": "services.items", "label": "Услуги", "titleField": "title",
          "tpl": {"title": "", "text": "", "icon": ""},
          "item": [
              {"path": "title", "label": "Название", "type": "text"},
              {"path": "text", "label": "Описание", "type": "textarea", "rows": 2, "ai": "improve"},
              _svg_icon(),
          ]},
     ]},

    {"id": "process", "group": "Контент", "title": "Этапы работы", "fields": [
        {"path": "process.kicker", "label": "Надзаголовок", "type": "text"},
        {"path": "process.title", "label": "Заголовок", "type": "text"},
        {"path": "process.bg", "label": "Фон", "type": "image"},
     ],
     "lists": [
         {"path": "process.items", "label": "Этапы", "titleField": "title",
          "tpl": {"n": "07", "title": "", "text": ""},
          "item": [
              {"path": "n", "label": "Номер", "type": "text"},
              {"path": "title", "label": "Заголовок", "type": "text"},
              {"path": "text", "label": "Текст", "type": "textarea", "rows": 2},
          ]},
     ]},

    {"id": "guarantees", "group": "Контент", "title": "Гарантии", "fields": [
        {"path": "guarantees.kicker", "label": "Надзаголовок", "type": "text"},
        {"path": "guarantees.title", "label": "Заголовок", "type": "text"},
        {"path": "guarantees.bg", "label": "Фон", "type": "image"},
     ],
     "lists": [
         {"path": "guarantees.items", "label": "Пункты", "titleField": "title",
          "tpl": {"title": "", "text": "", "icon": ""},
          "item": [
              {"path": "title", "label": "Заголовок", "type": "text"},
              {"path": "text", "label": "Текст", "type": "textarea", "rows": 2},
              _svg_icon(),
          ]},
     ]},

    {"id": "cities", "group": "Контент", "title": "Города", "fields": [
        {"path": "cities.kicker", "label": "Надзаголовок", "type": "text"},
        {"path": "cities.title", "label": "Заголовок", "type": "text"},
        {"path": "cities.subtitle", "label": "Подзаголовок", "type": "textarea", "rows": 2},
        {"path": "cities.bg", "label": "Фон", "type": "image"},
     ],
     "lists": [
         {"path": "cities.items", "label": "Города", "titleField": "name",
          "tpl": {"name": "", "text": ""},
          "item": [
              {"path": "name", "label": "Город", "type": "text"},
              {"path": "text", "label": "Текст", "type": "textarea", "rows": 2, "ai": "city_text"},
          ]},
     ]},

    {"id": "cta", "group": "Контент", "title": "Призыв к действию", "fields": [
        {"path": "cta.title", "label": "Заголовок", "type": "text"},
        {"path": "cta.text", "label": "Текст (можно HTML)", "type": "textarea", "rows": 3, "ai": "cta_text"},
        {"path": "cta.button", "label": "Кнопка", "type": "text"},
        {"path": "cta.phone_raw", "label": "Телефон для tel:", "type": "text"},
        {"path": "cta.bg", "label": "Фон", "type": "image"},
     ]},

    {"id": "contacts", "group": "Контент", "title": "Контакты", "fields": [
        {"path": "contacts.kicker", "label": "Надзаголовок", "type": "text"},
        {"path": "contacts.title", "label": "Заголовок", "type": "text"},
        {"path": "contacts.subtitle", "label": "Подзаголовок", "type": "textarea", "rows": 2},
        {"path": "contacts.call_label", "label": "Подпись в карточке звонка", "type": "text"},
        {"path": "contacts.call_number", "label": "Телефон в карточке", "type": "text"},
        {"path": "contacts.call_hint", "label": "Текст под телефоном", "type": "textarea", "rows": 2},
        {"path": "contacts.bg", "label": "Фон", "type": "image"},
     ],
     "lists": [
         {"path": "contacts.lines", "label": "Строки контактов", "titleField": "label",
          "tpl": {"label": "", "value": "", "href": "", "icon": ""},
          "item": [
              {"path": "label", "label": "Подпись", "type": "text"},
              {"path": "value", "label": "Значение", "type": "text"},
              {"path": "href", "label": "Ссылка (если нужна)", "type": "text"},
              _svg_icon(),
          ]},
         {"path": "contacts.buttons", "label": "Кнопки связи", "titleField": "label",
          "tpl": {"label": "", "href": "", "cls": "c-call", "external": False, "icon": ""},
          "item": [
              {"path": "label", "label": "Текст", "type": "text"},
              {"path": "href", "label": "Ссылка", "type": "text"},
              {"path": "cls", "label": "Вид", "type": "select", "options": ["c-call", "c-tg", "c-max"]},
              {"path": "external", "label": "Открывать в новой вкладке", "type": "check"},
              _svg_icon(),
          ]},
     ]},

    {"id": "footer", "group": "Контент", "title": "Подвал", "fields": [
        {"path": "footer.line", "label": "Строка описания", "type": "text"},
        {"path": "footer.copyright", "label": "Копирайт", "type": "text"},
     ],
     "lists": [
         {"path": "footer.socials", "label": "Кнопки соцсетей", "titleField": "label",
          "tpl": {"label": "", "href": "", "icon": ""},
          "item": [
              {"path": "label", "label": "Подпись (title)", "type": "text"},
              {"path": "href", "label": "Ссылка", "type": "text"},
              _svg_icon(),
          ]},
     ]},

    {"id": "cookie", "group": "Контент", "title": "Cookie-баннер", "fields": [
        {"path": "cookie.text", "label": "Текст", "type": "textarea", "rows": 2},
        {"path": "cookie.link_label", "label": "Ссылка на политику — текст", "type": "text"},
        {"path": "cookie.link_href", "label": "Ссылка на политику — URL", "type": "text",
         "hint": "Пусто = ссылка не показывается."},
        {"path": "cookie.button", "label": "Кнопка", "type": "text"},
     ]},

    {"id": "page404", "group": "Контент", "title": "Страница 404", "fields": [
        {"path": "page404.title", "label": "Заголовок", "type": "text"},
        {"path": "page404.text", "label": "Текст", "type": "textarea", "rows": 2},
        {"path": "page404.button", "label": "Кнопка", "type": "text"},
     ]},

    {"id": "lead_settings", "group": "Заявки", "title": "Форма заявки",
     "hint": "Компактная форма на сайте. Новые обращения автоматически появляются в разделе «Заявки».",
     "fields": [
         {"path": "lead_form.enabled", "label": "Показывать форму на сайте", "type": "check", "chkLabel": "включено"},
         {"path": "lead_form.title", "label": "Заголовок формы", "type": "text"},
         {"path": "lead_form.subtitle", "label": "Подзаголовок", "type": "textarea", "rows": 2},
         {"path": "lead_form.button", "label": "Текст плавающей кнопки", "type": "text"},
     ]},

    {"id": "guide", "group": "Помощь", "title": "Инструкция для админов",
     "hint": "Подробный порядок работы с сайтом. Если сомневаетесь — сначала сохраните копию.",
     "fields": [
         {"type": "info", "text": "<b>1. Изменение текста</b>\nОткройте нужный раздел слева → измените поле → нажмите «Сохранить». До сохранения сайт не меняется."},
         {"type": "info", "text": "<b>2. Фото</b>\nВ поле картинки можно вставить ссылку, загрузить файл кнопкой «Файл» или выбрать уже загруженное через «Медиа». Лучше загружать JPG/WebP до 8 МБ."},
         {"type": "info", "text": "<b>3. Списки</b>\nРаботы, услуги, отзывы и этапы добавляются кнопкой «+ Добавить». Стрелки меняют порядок. Удаление просит подтверждение."},
         {"type": "info", "text": "<b>4. Заявки</b>\nВсе обращения с формы сайта находятся в разделе «Заявки». Новые отмечены золотой точкой. Откройте телефон клиента для звонка и после просмотра отметьте заявку прочитанной."},
         {"type": "info", "text": "<b>5. Сохранение</b>\nЕсли снизу появилась панель «Есть несохранённые изменения», нажмите «Сохранить». Перед перезаписью автоматически создаётся резервная копия."},
         {"type": "info", "text": "<b>6. Если что-то испортили</b>\nНе паникуйте. Нажмите «Отменить», если ещё не сохраняли. Если уже сохранили — откройте «История версий», подставьте нужную копию и сохраните её."},
         {"type": "info", "text": "<b>7. SEO</b>\nTitle и Description должны описывать реальные услуги и города. Не вставляйте огромные списки слов в видимый текст сайта — поисковику важнее полезный контент."},
         {"type": "info", "text": "<b>8. Что нельзя выдумывать</b>\nНе добавляйте от себя цены, сроки, гарантию, бесплатные услуги, материалы или города. Если факт неизвестен — сначала спросите Романа."},
         {"type": "info", "text": "<b>9. Проверка сайта</b>\nПосле крупных изменений нажмите «Открыть сайт», проверьте телефон, кнопки, фото и мобильную версию. На телефоне меню и форма должны оставаться удобными."},
         {"type": "info", "text": "<b>10. Правило перед публикацией</b>\nСначала проверить → потом сохранить → потом открыть сайт в новой вкладке → затем ещё раз проверить на телефоне."}
     ]},

    {"id": "tools", "group": "Инструменты", "title": "Инструменты и связь",
     "hint": "Проверка связей, бэкап контента, генерация текстов через AI.",
     "fields": [
         {"type": "buttons", "buttons": [
             {"act": "status", "label": "Проверить связи", "cls": "btn-gold"},
             {"act": "ai-seo", "label": "Сгенерировать SEO через AI", "cls": ""},
             {"act": "export", "label": "Скачать бэкап (JSON)", "cls": ""},
             {"act": "import", "label": "Загрузить бэкап", "cls": ""},
             {"act": "open", "label": "Открыть сайт", "cls": ""},
             {"act": "reload", "label": "Отменить изменения", "cls": "btn-red"},
         ]},
         {"type": "info", "text": "<div id=\"toolsOut\" class=\"info\">Нажмите «Проверить связи», чтобы увидеть состояние базы, хранилища и AI.</div>"},
         {"type": "info", "text": "<b>Как сохраняется контент</b>\nТексты и фото лежат в Supabase, а не в файле mebel.py — поэтому деплой на хостинге их не сбрасывает.\nКаждое сохранение делает резервную копию (вкладка «История версий»).\nЕсли база изменилась из другого окна или с другого устройства — админка предупредит и не даст молча перезаписать."},
     ]},
    {"id": "history", "group": "Инструменты", "title": "История версий",
     "hint": "Резервные копии делаются автоматически при каждом сохранении (последние 40).",
     "fields": [
         {"type": "buttons", "buttons": [{"act": "history", "label": "Обновить список", "cls": "btn-gold"}]},
         {"type": "info", "text": "<div id=\"histOut\">Нажмите «Обновить список».</div>"},
     ]},
]

_SCHEMA_JSON = json.dumps(ADMIN_SCHEMA, ensure_ascii=False)


# ============================================================
#  АДМИНКА (HTML)
# ============================================================
ADMIN_LOGIN_HTML = """<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Вход — Кухни Островский</title><style>
*{margin:0;padding:0;box-sizing:border-box}body{font-family:system-ui;background:linear-gradient(135deg,#0e0c09,#1a1611);color:#f5efe3;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.card{background:rgba(255,255,255,.04);border:1px solid rgba(236,207,160,.2);border-radius:20px;padding:42px 38px;width:100%;max-width:420px}
h1{font-family:Georgia,serif;font-size:28px;color:#fff;margin-bottom:8px;text-align:center}
p.sub{color:#b9ad9a;font-size:13.5px;text-align:center;margin-bottom:28px}
label{display:block;color:#eccfa0;font-size:12px;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:8px;font-weight:600}
input{width:100%;padding:14px 16px;background:rgba(0,0,0,.3);border:1px solid rgba(255,255,255,.12);border-radius:12px;color:#fff;font-size:15px;margin-bottom:18px}
input:focus{outline:none;border-color:#d4af6a}
button{width:100%;padding:15px;background:linear-gradient(135deg,#eccfa0,#d4af6a 55%,#a37c3f);color:#17120b;font-weight:700;border:none;border-radius:12px;cursor:pointer;text-transform:uppercase;letter-spacing:1px;font-family:inherit}
.err{background:rgba(220,60,60,.14);border:1px solid rgba(220,60,60,.4);color:#ff9a9a;padding:12px;border-radius:10px;font-size:13px;margin-bottom:18px;text-align:center}
.hint{margin-top:18px;color:#6f6659;font-size:11.5px;text-align:center;line-height:1.5}
</style></head><body>
<form class="card" method="POST" action="/admin/login">
<h1>Кухни Островский</h1><p class="sub">Панель управления сайтом</p>__ERROR__
<label>Логин</label><input type="text" name="login" required autofocus autocomplete="username">
<label>Пароль</label><input type="password" name="password" required autocomplete="current-password">
<button>Войти</button>
<div class="hint">Логин и пароль задаются переменными ADMIN_LOGIN и ADMIN_PASSWORD на хостинге.</div>
</form></body></html>"""


ADMIN_HTML = r"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Админка — Кухни Островский</title><style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--g:#d4af6a;--gs:#eccfa0;--gd:#a37c3f;--bd:rgba(236,207,160,.14);--mut:#a2988a}
html{scroll-behavior:smooth}
body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:#0c0a07;color:#f3ede2;line-height:1.55;min-height:100vh;overflow-x:hidden}
body::before{content:"";position:fixed;inset:0;z-index:-2;background:radial-gradient(1100px 620px at 88% -14%,rgba(212,175,106,.13),transparent 60%),radial-gradient(900px 560px at -10% 30%,rgba(212,175,106,.07),transparent 58%),radial-gradient(1200px 700px at 50% 120%,rgba(163,124,63,.13),transparent 62%),linear-gradient(180deg,#0e0c08,#0a0806 55%,#0c0a07)}
body::after{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:.45;background-image:radial-gradient(rgba(255,255,255,.04) 1px,transparent 1px);background-size:3px 3px}
@keyframes fadeUp{from{opacity:0;transform:translate3d(0,14px,0)}to{opacity:1;transform:none}}
@keyframes softPulse{0%,100%{box-shadow:0 0 0 0 rgba(236,207,160,.45)}50%{box-shadow:0 0 0 6px rgba(236,207,160,0)}}
@keyframes skel{0%{background-position:-200% 0}100%{background-position:200% 0}}
header{position:sticky;top:0;z-index:30;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;padding:11px 20px;background:rgba(12,10,7,.86);backdrop-filter:blur(14px);border-bottom:1px solid var(--bd)}
.brand{font-family:Georgia,serif;font-size:19px;color:var(--gs);display:flex;align-items:center;gap:11px}
.brand .mark{width:26px;height:26px;border-radius:50%;background:linear-gradient(140deg,#e7d2a7,#c69f5a);box-shadow:inset 0 1px 0 rgba(255,255,255,.45),0 5px 16px -7px rgba(0,0,0,.9);animation:softPulse 5s ease-in-out infinite;flex-shrink:0}
.brand span{font-size:11px;opacity:.6;font-family:system-ui;letter-spacing:1.4px;text-transform:uppercase}
.actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.btn{padding:9px 15px;border-radius:6px;border:1px solid rgba(236,207,160,.18);background:rgba(255,255,255,.03);color:#f3ede2;font-size:13px;font-weight:500;cursor:pointer;text-decoration:none;font-family:inherit;display:inline-flex;align-items:center;gap:6px;transition:background .35s cubic-bezier(.16,1,.3,1),border-color .35s,color .35s,transform .35s cubic-bezier(.16,1,.3,1),box-shadow .35s}
.btn:hover{border-color:rgba(212,175,106,.5);background:rgba(212,175,106,.08);transform:translateY(-1px)}
.btn:active{transform:translateY(0)}
.btn:disabled{opacity:.5;cursor:default;transform:none}
.btn-gold{background:linear-gradient(180deg,#d8b677,#c9a260);color:#14100a;border-color:rgba(255,255,255,.14);box-shadow:inset 0 1px 0 rgba(255,255,255,.3),0 8px 20px -14px rgba(0,0,0,.85)}
.btn-gold:hover{background:linear-gradient(180deg,#e0bf82,#d0aa68);box-shadow:inset 0 1px 0 rgba(255,255,255,.36),0 12px 24px -15px rgba(0,0,0,.9)}
.btn-red{background:rgba(220,70,70,.09);border-color:rgba(220,70,70,.28);color:#ff9d9d}
.btn-red:hover{background:rgba(220,70,70,.16);border-color:rgba(220,70,70,.45)}
.btn.pulse{animation:softPulse 2s ease-in-out infinite}
.layout{display:flex;min-height:calc(100vh - 56px);align-items:flex-start}
nav.side{width:254px;flex-shrink:0;position:sticky;top:56px;max-height:calc(100vh - 56px);overflow-y:auto;padding:12px 0 40px;background:rgba(0,0,0,.26);border-right:1px solid var(--bd);scrollbar-width:thin}
nav.side::-webkit-scrollbar{width:8px}
nav.side::-webkit-scrollbar-thumb{background:rgba(236,207,160,.16);border-radius:4px}
.side-search{position:relative;margin:0 14px 12px;animation:fadeUp .5s cubic-bezier(.16,1,.3,1) both}
.side-search input{width:100%;padding:10px 12px 10px 33px;background:rgba(0,0,0,.4);border:1px solid var(--bd);border-radius:8px;color:#fff;font-size:13px;font-family:inherit;transition:border-color .35s,box-shadow .35s,background .35s}
.side-search input:focus{outline:none;border-color:rgba(212,175,106,.5);box-shadow:0 0 0 3px rgba(212,175,106,.09);background:rgba(0,0,0,.55)}

nav.side a.changed{box-shadow:inset 0 0 0 1px rgba(236,207,160,.18);margin:2px 8px;border-radius:8px;padding-left:18px}
nav.side a.changed:after{content:"ВНИМАНИЕ";font-size:8px;letter-spacing:.7px;color:#ecd09c;opacity:.85;animation:adminAttention 1.8s infinite}
.side-search .ic{position:absolute;left:11px;top:50%;transform:translateY(-50%);color:var(--g);opacity:.75;font-size:14px;pointer-events:none}
nav.side a{position:relative;display:flex;align-items:center;gap:9px;padding:10px 18px;color:var(--mut);font-size:13.5px;cursor:pointer;border-left:2px solid transparent;transition:color .35s,background .35s,padding-left .35s,border-color .35s}
nav.side a:hover{color:#fff;background:rgba(255,255,255,.035);padding-left:22px}
nav.side a.active{color:var(--gs);border-left-color:var(--g);background:linear-gradient(90deg,rgba(212,175,106,.13),transparent)}
nav.side a .cap{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
nav.side a .dot{width:6px;height:6px;border-radius:50%;background:var(--g);opacity:0;transform:scale(.4);transition:opacity .35s,transform .35s;flex-shrink:0}
nav.side a.changed .dot{opacity:1;transform:none;box-shadow:0 0 10px rgba(212,175,106,.85)}
.nav-group{padding:14px 18px 6px;font-size:10.5px;letter-spacing:2px;text-transform:uppercase;color:#6f6659;font-weight:700}
main{flex:1;min-width:0;max-width:1080px;padding:24px clamp(16px,3vw,30px) 150px;animation:fadeUp .5s cubic-bezier(.16,1,.3,1)}
h2{font-family:Georgia,serif;font-size:24px;color:#fff;margin-bottom:6px}
p.hint{color:var(--mut);font-size:13px;margin-bottom:18px}
.field{margin-bottom:15px;animation:fadeUp .5s cubic-bezier(.16,1,.3,1) both;animation-delay:var(--d,0s)}
.field>label{display:flex;align-items:center;gap:8px;color:var(--gs);font-size:11px;letter-spacing:1.2px;text-transform:uppercase;margin-bottom:6px;font-weight:600}
.field input,.field textarea,.field select{width:100%;padding:10px 13px;background:rgba(0,0,0,.38);border:1px solid rgba(255,255,255,.1);border-radius:8px;color:#fff;font-size:14px;font-family:inherit;transition:border-color .35s,box-shadow .35s,background .35s}
.field textarea{resize:vertical;min-height:64px;line-height:1.55}
.field input:focus,.field textarea:focus,.field select:focus{outline:none;border-color:rgba(212,175,106,.55);box-shadow:0 0 0 3px rgba(212,175,106,.09);background:rgba(0,0,0,.5)}
.field .mono{font-family:ui-monospace,Consolas,monospace;font-size:12.5px}
.fhint{color:#6f6659;font-size:11.5px;margin-top:5px}
.img-row{display:flex;gap:6px;align-items:stretch}
.img-row input{flex:1}
.prev{margin-top:8px}.prev img{max-width:190px;border-radius:8px;display:block;border:1px solid rgba(255,255,255,.1);animation:fadeUp .5s cubic-bezier(.16,1,.3,1) both}
.color-row{display:flex;gap:8px;align-items:center}.color-row input[type=color]{width:52px;height:40px;padding:2px;cursor:pointer}
.chk{display:flex;align-items:center;gap:9px;font-size:14px;color:#d8cfbe;cursor:pointer}
.chk input{width:18px;height:18px;accent-color:#d4af6a;cursor:pointer}
.ai{padding:2px 8px;font-size:12px;border-radius:6px;background:rgba(212,175,106,.12);border-color:rgba(212,175,106,.35);color:var(--gs)}
.mini{padding:5px 10px;font-size:12px;border-radius:6px}
.item{background:rgba(255,255,255,.028);border:1px solid rgba(255,255,255,.075);border-radius:11px;padding:15px;margin-bottom:12px;animation:fadeUp .5s cubic-bezier(.16,1,.3,1) both;animation-delay:var(--d,0s);transition:border-color .4s,background .4s,transform .4s cubic-bezier(.16,1,.3,1)}
.item:hover{border-color:rgba(236,207,160,.2);background:rgba(255,255,255,.04)}
.item-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;gap:8px;flex-wrap:wrap}
.item-head strong{color:var(--gs);font-size:13px;word-break:break-word}
.item-tools{display:flex;gap:6px}
.list-head{display:flex;justify-content:space-between;align-items:baseline;margin:24px 0 10px;border-top:1px solid var(--bd);padding-top:14px}
.list-head strong{color:#fff;font-family:Georgia,serif;font-size:17px}
.list-head .muted{color:#6f6659;font-size:12px}
.info{background:rgba(212,175,106,.06);border:1px solid rgba(212,175,106,.2);border-radius:10px;padding:14px 16px;font-size:13px;color:#e0d6c4;margin-bottom:14px;white-space:pre-wrap;animation:fadeUp .5s cubic-bezier(.16,1,.3,1) both}
.info b{color:var(--gs)}
.status{font-size:11.5px;padding:4px 10px;border-radius:6px;display:inline-block;font-weight:600}
.status.ok{background:rgba(80,200,120,.14);color:#7ee0a0;border:1px solid rgba(80,200,120,.35)}
.status.bad{background:rgba(220,60,60,.14);color:#ff9a9a;border:1px solid rgba(220,60,60,.35)}
.status.saving{background:rgba(212,175,106,.18);color:var(--gs);border:1px solid rgba(212,175,106,.45)}
.toast{position:fixed;bottom:22px;left:50%;transform:translate(-50%,150%);background:linear-gradient(180deg,#e0bf82,#cfa968);color:#14100a;padding:12px 22px;border-radius:8px;font-weight:600;font-size:13.5px;z-index:9999;transition:transform .4s cubic-bezier(.16,1,.3,1);max-width:92vw;text-align:center;box-shadow:0 18px 40px -18px rgba(0,0,0,.9)}
.toast.show{transform:translate(-50%,0)}
.toast.err{background:linear-gradient(180deg,#ff9a9a,#e0574a);color:#fff}
.modal{position:fixed;inset:0;background:rgba(6,5,3,.86);display:none;align-items:center;justify-content:center;z-index:9000;padding:18px}
.modal.open{display:flex;animation:fadeUp .35s ease both}
.modal-card{background:#15120d;border:1px solid rgba(236,207,160,.2);border-radius:14px;width:min(920px,100%);max-height:86vh;display:flex;flex-direction:column;box-shadow:0 40px 90px -40px rgba(0,0,0,.95)}
.modal-head{display:flex;justify-content:space-between;align-items:center;padding:14px 18px;border-bottom:1px solid var(--bd)}
.media-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:10px;padding:16px;overflow-y:auto}
.media-grid button{padding:0;border:1px solid rgba(255,255,255,.1);border-radius:9px;overflow:hidden;background:#0b0907;cursor:pointer;transition:transform .4s cubic-bezier(.16,1,.3,1),border-color .4s}
.media-grid button:hover{transform:translateY(-3px);border-color:rgba(212,175,106,.45)}
.media-grid img{width:100%;height:110px;object-fit:cover;display:block}
.media-grid .nm{font-size:10.5px;color:var(--mut);padding:5px;word-break:break-all}
.savebar{position:fixed;left:50%;bottom:-100px;transform:translateX(-50%);display:flex;align-items:center;gap:10px;padding:10px 14px;background:rgba(20,16,11,.94);border:1px solid rgba(236,207,160,.22);border-radius:11px;box-shadow:0 26px 60px -26px rgba(0,0,0,.95);z-index:8000;transition:bottom .5s cubic-bezier(.16,1,.3,1);max-width:94vw;flex-wrap:wrap;justify-content:center}
.savebar.show{bottom:18px}
.savebar .bt{font-size:13px;color:var(--gs)}
.skel{height:16px;border-radius:6px;background:linear-gradient(90deg,rgba(255,255,255,.05),rgba(255,255,255,.12),rgba(255,255,255,.05));background-size:200% 100%;animation:skel 1.3s linear infinite;margin-bottom:12px}
.skel.w40{width:40%}.skel.w70{width:70%}.skel.big{height:42px}
.srctab{color:#6f6659;font-size:11px}
mark.hit{background:rgba(212,175,106,.25);color:#fff;border-radius:3px;padding:0 2px}
@media(max-width:820px){
 .layout{flex-direction:column}
 nav.side{width:100%;max-height:none;position:static;display:flex;flex-wrap:wrap;gap:6px;padding:8px;border-right:none;border-bottom:1px solid var(--bd);overflow:visible}
 nav.side a{white-space:nowrap;border-left:none;border-bottom:2px solid transparent;padding:8px 12px;border-radius:6px;background:rgba(255,255,255,.03)}
 nav.side a:hover{padding-left:12px}
 nav.side a.active{border-left:none;border-bottom-color:var(--g);background:rgba(212,175,106,.12)}
 nav.side a .dot{display:none}
 .side-search{width:100%;margin:0 0 8px;order:-1}
 .nav-group{display:none}
 main{padding:16px 14px 130px;max-width:none}
 .savebar{left:12px;right:12px;transform:none;max-width:none}
 .savebar.show{bottom:12px}
}
<style id="ostAdminUpgrade">
.noticePulse{position:relative;border-color:rgba(236,207,160,.38)!important;box-shadow:0 0 0 1px rgba(236,207,160,.05) inset,0 10px 35px -24px #000}
.noticePulse:after{content:"";position:absolute;right:10px;top:10px;width:7px;height:7px;border-radius:50%;background:#e5bd70;box-shadow:0 0 0 0 rgba(229,189,112,.55);animation:adminAttention 1.8s infinite}
@keyframes adminAttention{0%,65%,100%{box-shadow:0 0 0 0 rgba(229,189,112,0)}35%{box-shadow:0 0 0 7px rgba(229,189,112,.0)}}
.dashboard{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:0 0 22px}
.dash{position:relative;overflow:hidden;border:1px solid rgba(236,207,160,.12);background:linear-gradient(145deg,rgba(255,255,255,.045),rgba(255,255,255,.018));border-radius:16px;padding:16px;box-shadow:0 20px 45px -38px #000}
.dash b{display:block;font:600 25px/1 Georgia,serif;color:#fff}.dash span{display:block;margin-top:5px;color:#8f8577;font-size:11px}
.lead-card,.audit-row{border:1px solid rgba(236,207,160,.12);background:linear-gradient(145deg,rgba(255,255,255,.035),rgba(255,255,255,.018));border-radius:15px;padding:15px;margin-bottom:10px;transition:.25s}
.lead-card.unread{border-color:rgba(236,207,160,.38);box-shadow:0 0 0 1px rgba(236,207,160,.04) inset}
.lead-top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.lead-name{font-weight:700;color:#fff}.lead-date{font-size:11px;color:#756d61}
.lead-phone{display:inline-flex;margin-top:8px;color:#ecd09c;font-weight:700;text-decoration:none}.lead-msg{margin-top:10px;color:#c7bdaf;font-size:13px;white-space:pre-wrap}.lead-actions{display:flex;gap:7px;margin-top:12px;flex-wrap:wrap}
.audit-row{display:grid;grid-template-columns:145px 180px 1fr;gap:12px;color:#c7bdaf;font-size:12px}.audit-row b{color:#ecd09c}
@media(max-width:700px){.dashboard{grid-template-columns:1fr 1fr}.audit-row{grid-template-columns:1fr}.lead-top{display:block}}
@media(max-width:480px){.dashboard{grid-template-columns:1fr}}
</style></head><body>
<header>
<div class="brand"><span class="mark"></span>Кухни Островский<span>CMS</span><span class="status" id="status">Загрузка…</span><span class="status" id="revInfo" style="background:rgba(255,255,255,.05);color:#a2988a;border:1px solid rgba(255,255,255,.08)">rev —</span></div>
<div class="actions">
<a class="btn" href="/" target="_blank" rel="noopener">Открыть сайт</a>
<button class="btn" id="reloadBtn" title="Вернуть данные из базы (отменить изменения)">↻ Отменить</button>
<button class="btn btn-gold" id="saveBtn" title="Ctrl+S — сохранить на сайт">Сохранить</button>
<a class="btn btn-red" href="/admin/logout">Выйти</a>
</div>
</header>
<div class="layout"><nav class="side" id="side"></nav><main id="main"><div class="skel w40 big"></div><div class="skel w70"></div><div class="skel"></div><div class="skel w40"></div></main></div>
<div class="savebar" id="savebar"><span class="bt">Есть несохранённые изменения</span><button class="btn btn-gold" id="barSave">Сохранить</button><button class="btn" id="barUndo">Отменить</button></div>
<div class="toast" id="toast"></div>
<div class="modal" id="modal"><div class="modal-card"><div class="modal-head"><strong>Медиатека (Supabase Storage)</strong><button class="btn mini" id="mClose">Закрыть</button></div><div class="media-grid" id="mediaGrid"></div></div></div>
<input type="file" id="importFile" accept="application/json,.json" hidden>
<script>
document.addEventListener('input',function(e){
  if(e.target&&e.target.id==='search'){
    SEARCH=e.target.value;
    var pos=e.target.selectionStart;
    render();
    var n=q('#search');if(n){n.focus();try{n.setSelectionRange(pos,pos)}catch(x){}}
  }
});
document.addEventListener('keydown',function(e){
  if(e.key==='/'&&!/input|textarea|select/i.test((e.target.tagName||''))){var n=q('#search');if(n){e.preventDefault();n.focus()}}
});
document.addEventListener('click',function(e){
  var b=e.target.closest&&e.target.closest('#barSave,#barUndo');
  if(b){ if(b.id==='barSave')save(); else {var r=q('#reloadBtn');if(r)r.click();} }
});
var SCHEMA=__SCHEMA__, DATA=null, ORIG=null, TAB=(__SCHEMA__[0]||{}).id, dirty=false, mediaTarget=null, REV=0, SERVER_AT='', SEARCH='';

function q(s){return document.querySelector(s)}
function qa(s){return Array.prototype.slice.call(document.querySelectorAll(s))}
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function getPath(o,p){if(!p)return o;return p.split('.').reduce(function(a,k){if(a==null)return undefined;if(Array.isArray(a))return a[parseInt(k,10)];return a[k]},o)}
function setPath(o,p,v){var a=p.split('.'),c=o;for(var i=0;i<a.length-1;i++){var k=a[i],n=a[i+1];if(c[k]==null)c[k]=/^\d+$/.test(n)?[]:{};c=c[k]}c[a[a.length-1]]=v}
function toast(m,bad){var t=q('#toast');t.textContent=m;t.classList.toggle('err',!!bad);t.classList.add('show');clearTimeout(t._h);t._h=setTimeout(function(){t.classList.remove('show')},3000)}
function setStatus(txt,cls){var el=q('#status');el.className='status '+(cls||'ok');el.textContent=txt}
function setDirty(v){dirty=v;document.title=(v?'* ':'')+'Админка — Кухни Островский';var sb=q('#saveBtn');if(sb)sb.classList.toggle('pulse',v);updateBar();var act=q('nav.side a.active');if(act)act.classList.toggle('changed',tabChanged(SCHEMA.filter(function(t){return t.id===TAB})[0]||{}))}
function api(url,opts){return fetch(url,Object.assign({credentials:'same-origin'},opts||{})).then(function(r){if(r.status===401){location.href='/admin/login';throw new Error('Нужно войти')}return r.json()})}
function normColor(v){v=String(v||'').trim();return /^#[0-9a-f]{6}$/i.test(v)?v:'#000000'}

function stagger(html){
  var n=0;
  return html.replace(/class="field"/g,function(){return 'style="--d:'+((n++)*0.018).toFixed(3)+'s" class="field"'})
             .replace(/class="item"/g,function(){return 'style="--d:'+((n++)*0.02).toFixed(3)+'s" class="item"'});
}
function pathDiff(p){
  if(!ORIG)return false;
  var a=getPath(ORIG,p),b=getPath(DATA,p);
  return JSON.stringify(a===undefined?null:a)!==JSON.stringify(b===undefined?null:b);
}
function tabChanged(t){
  if(!ORIG)return false;
  var hit=false;
  (t.fields||[]).forEach(function(f){if(!hit&&f.path&&f.type!=='info'&&f.type!=='buttons'&&pathDiff(f.path))hit=true});
  (t.lists||[]).forEach(function(l){if(!hit&&pathDiff(l.path))hit=true});
  return hit;
}
function searchHTML(){
  var needle=SEARCH.trim().toLowerCase(),hits=[],MAX=90;
  SCHEMA.forEach(function(t){
    (t.fields||[]).forEach(function(f){
      if(hits.length>=MAX||f.type==='info'||f.type==='buttons')return;
      if(((f.label||'')+' '+(f.path||'')+' '+(t.title||'')).toLowerCase().indexOf(needle)>=0)hits.push({f:f,base:'',where:t.title});
    });
    (t.lists||[]).forEach(function(l){
      var arr=getPath(DATA,l.path);
      if(!Array.isArray(arr))return;
      (l.fields||[]).forEach(function(f){
        if(hits.length>=MAX)return;
        if(((f.label||'')+' '+(l.label||'')+' '+(t.title||'')).toLowerCase().indexOf(needle)<0)return;
        arr.forEach(function(it,i){ if(hits.length<MAX)hits.push({f:f,base:l.path+'.'+i,where:t.title+' · '+(i+1)+' · '+(it.title||it.name||'')}); });
      });
    });
  });
  var h='<h2>Поиск: '+esc(SEARCH)+'</h2><p class="hint">Найдено полей: '+hits.length+(hits.length>=MAX?' (показаны первые '+MAX+', уточните запрос)':'')+' · <a href="#" id="clearSearch" style="color:#eccfa0">сбросить поиск</a></p>';
  hits.forEach(function(x){
    var f={};for(var k in x.f)f[k]=x.f[k];
    f.label='<span class="srctab">'+esc(x.where)+'</span> '+esc(f.label||f.path||'');
    h+=fieldHTML(f,x.base,true);
  });
  return h;
}
function renderLeads(){
  q('#main').innerHTML='<h2>Заявки</h2><p class="hint">Новые обращения с формы сайта. Здесь только реальные отправленные заявки — ничего не нужно переносить вручную.</p><div class="dashboard"><div class="dash"><b id="leadTotal">—</b><span>всего заявок</span></div><div class="dash"><b id="leadUnread">—</b><span>новых</span></div><div class="dash"><b>24/7</b><span>форма принимает обращения</span></div></div><div class="actions" style="margin-bottom:16px"><button class="btn btn-gold" id="refreshLeads">Обновить</button><button class="btn" id="readAllLeads">Отметить всё прочитанным</button></div><div id="leadsOut"><div class="skel big"></div><div class="skel"></div></div>';
  q('#refreshLeads').onclick=loadLeads;
  q('#readAllLeads').onclick=function(){api('/admin/api/leads/read',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).then(loadLeads)};
  loadLeads();
}
function loadLeads(){
  var out=q('#leadsOut');if(out)out.innerHTML='<div class="skel big"></div><div class="skel"></div>';
  api('/admin/api/leads').then(function(j){
    var items=Array.isArray(j.items)?j.items:[];
    var total=q('#leadTotal'),un=q('#leadUnread');if(total)total.textContent=items.length;if(un)un.textContent=j.unread||0;
    var badge=q('#leadBadge');if(badge){badge.textContent=j.unread||0;badge.style.display=(j.unread||0)?'inline-flex':'none'}
    if(!items.length){if(out)out.innerHTML='<div class="info"><b>Пока заявок нет.</b><br>Когда посетитель заполнит форму на сайте, обращение появится здесь.</div>';return}
    if(out)out.innerHTML=items.map(function(it){
      var cls=it.read?'':' unread',dt=esc(String(it.at||'').replace('T',' ')),name=esc(it.name||'Без имени'),phone=esc(it.phone||''),msg=esc(it.message||'Без комментария');
      return '<article class="lead-card'+cls+'"><div class="lead-top"><div><div class="lead-name">'+name+'</div><a class="lead-phone" href="tel:'+esc(it.phone||'')+'">'+phone+'</a></div><span class="lead-date">'+dt+'</span></div><div class="lead-msg">'+msg+'</div><div class="lead-actions">'+(it.read?'':'<button class="btn mini" data-lead-read="'+esc(it.id)+'">Прочитано</button>')+'<a class="btn mini btn-gold" href="tel:'+esc(it.phone||'')+'">Позвонить</a></div></article>';
    }).join('');
    qa('[data-lead-read]').forEach(function(b){b.onclick=function(){api('/admin/api/leads/read',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:b.dataset.leadRead})}).then(loadLeads)}});
  }).catch(function(e){if(out)out.innerHTML='<div class="info">'+esc(e.message)+'</div>'});
}
function renderAudit(){
  q('#main').innerHTML='<h2>Журнал действий</h2><p class="hint">Кто и когда сохранял изменения в админке. Последние 300 записей.</p><div class="actions" style="margin-bottom:16px"><button class="btn btn-gold" id="refreshAudit">Обновить журнал</button></div><div id="auditOut"><div class="skel big"></div></div>';
  q('#refreshAudit').onclick=loadAudit;loadAudit();
}
function loadAudit(){
  api('/admin/api/audit').then(function(j){
    var out=q('#auditOut'),items=Array.isArray(j.items)?j.items:[];
    if(!items.length){out.innerHTML='<div class="info">Журнал пока пуст. Первая запись появится после сохранения.</div>';return}
    out.innerHTML=items.map(function(x){return '<div class="audit-row"><b>'+esc(x.at||'')+'</b><span>'+esc(x.action||'')+'</span><span>'+esc(x.who||'администратор')+(x.details?' · '+esc(x.details):'')+'</span></div>'}).join('');
  }).catch(function(e){q('#auditOut').innerHTML='<div class="info">'+esc(e.message)+'</div>'});
}
function refreshLeadBadge(){
  api('/admin/api/leads').then(function(j){var b=q('#leadBadge');if(!b)return;b.textContent=j.unread||0;b.style.display=(j.unread||0)?'inline-flex':'none'}).catch(function(){});
}

function render(){
  var groups={},order=[];
  SCHEMA.forEach(function(t){if(!groups[t.group]){groups[t.group]=[];order.push(t.group)}groups[t.group].push(t)});
  var nav='<div class="side-search"><span class="ic">⌕</span><input id="search" type="search" placeholder="Поиск по всем полям…" value="'+esc(SEARCH)+'"></div>';
  nav+='<div class="nav-group">Рабочее</div><a data-tab="leads" class="'+(TAB==='leads'?'active':'')+'"><span class="dot"></span><span class="cap">Заявки</span><span id="leadBadge" class="status" style="display:none;padding:2px 7px;margin-left:auto;background:rgba(236,207,160,.15);color:#ecd09c;border:1px solid rgba(236,207,160,.25)">0</span></a>';
  nav+='<a data-tab="audit" class="'+(TAB==='audit'?'active':'')+'"><span class="dot"></span><span class="cap">Журнал действий</span></a>';
  order.forEach(function(g){
    nav+='<div class="nav-group">'+esc(g)+'</div>';
    groups[g].forEach(function(t){
      var cls=(t.id===TAB?' active':'')+(tabChanged(t)?' changed':'');
      nav+='<a data-tab="'+t.id+'" class="'+(cls.trim()||'')+'"><span class="dot"></span><span class="cap">'+esc(t.title)+'</span></a>';
    });
  });
  q('#side').innerHTML=nav;
  if(SEARCH.trim()){
    q('#main').innerHTML=stagger(searchHTML());
    bind();
    var cs=q('#clearSearch');
    if(cs)cs.addEventListener('click',function(e){e.preventDefault();SEARCH='';render()});
    updateBar();refreshLeadBadge();
    return;
  }
  if(TAB==='leads'){renderLeads();updateBar();refreshLeadBadge();return}
  if(TAB==='audit'){renderAudit();updateBar();refreshLeadBadge();return}
  var tab=SCHEMA.filter(function(t){return t.id===TAB})[0]||SCHEMA[0];
  var h='<h2>'+esc(tab.title)+'</h2>'+(tab.hint?'<p class="hint">'+tab.hint+'</p>':'');
  (tab.fields||[]).forEach(function(f){h+=fieldHTML(f,'')});
  (tab.lists||[]).forEach(function(l){h+=listHTML(l)});
  q('#main').innerHTML=stagger(h);
  bind();
  var act=q('nav.side a.active');
  if(act&&act.scrollIntoView)try{act.scrollIntoView({block:'nearest'})}catch(e){}
  updateBar();
  window.scrollTo(0,0);
}
function updateBar(){
  var b=q('#savebar');if(b)b.classList.toggle('show',dirty);
  var s2=q('#status');
  if(s2&&dirty&&!s2.classList.contains('saving')){s2.className='status saving';s2.textContent='Есть изменения'}
  var ri=q('#revInfo');if(ri)ri.textContent='rev '+REV+(SERVER_AT?(' · '+SERVER_AT.slice(5,16).replace('T',' ')):'');
}

function aiBtn(p,task){return '<button class="btn mini ai" data-ai="'+task+'" data-ai-path="'+p+'" title="Сгенерировать через AI">AI</button>'}

function fieldHTML(f,base,rawLabel){
  var p=f.path?(base?base+'.'+f.path:f.path):base;
  if(f.type==='info')return '<div class="info">'+(f.text||'')+'</div>';
  var LBL=rawLabel?String(f.label||''):esc(f.label);
  if(f.type==='buttons'){
    var b='<div class="actions" style="margin-bottom:14px">';
    (f.buttons||[]).forEach(function(x){b+='<button class="btn '+(x.cls||'')+'" data-act="'+x.act+'">'+esc(x.label)+'</button>'});
    return b+'</div>';
  }
  var v=getPath(DATA,p),inp;
  if(f.type==='image'){
    return '<div class="field"><label>'+LBL+'</label><div class="img-row">'
      +'<input type="text" data-path="'+p+'" value="'+esc(v)+'" placeholder="https://... или загрузите файл">'
      +'<label class="btn mini" title="Загрузить файл">Файл<input type="file" accept="image/*" data-upload="'+p+'" hidden></label>'
      +'<button class="btn mini" data-media="'+p+'" title="Выбрать из медиатеки">Медиа</button></div>'
      +'<div class="prev" data-prev="'+p+'">'+(v?'<img src="'+esc(v)+'" loading="lazy">':'')+'</div>'
      +(f.hint?'<div class="fhint">'+f.hint+'</div>':'')+'</div>';
  }
  if(f.type==='textarea')inp='<textarea data-path="'+p+'" rows="'+(f.rows||3)+'"'+(f.mono?' class="mono"':'')+' placeholder="'+esc(f.placeholder||'')+'">'+esc(v)+'</textarea>'+(p.endsWith('.icon')?'<div class="fhint">Иконка SVG хранится отдельно. Если поле пустое — на сайте используется аккуратная базовая иконка.</div>':'');
  else if(f.type==='check')inp='<label class="chk"><input type="checkbox" data-path="'+p+'"'+(v?' checked':'')+'> '+(f.chkLabel||'включено')+'</label>';
  else if(f.type==='select')inp='<select data-path="'+p+'">'+(f.options||[]).map(function(o){return '<option value="'+esc(o)+'"'+(String(v)===o?' selected':'')+'>'+esc(o)+'</option>'}).join('')+'</select>';
  else if(f.type==='color')inp='<div class="color-row"><input type="color" data-path="'+p+'" value="'+esc(normColor(v))+'"><input type="text" data-path="'+p+'" value="'+esc(v)+'"></div>';
  else inp='<input type="text" data-path="'+p+'" value="'+esc(v)+'" placeholder="'+esc(f.placeholder||'')+'">';
  return '<div class="field">'+(f.label?'<label>'+f.label+(f.ai?aiBtn(p,f.ai):'')+'</label>':'')+inp+(f.hint?'<div class="fhint">'+f.hint+'</div>':'')+'</div>';
}

function listHTML(l){
  var arr=getPath(DATA,l.path); if(!Array.isArray(arr))arr=[];
  var h='<div class="list-head"><strong>'+esc(l.label)+' ('+arr.length+')</strong><span class="muted">стрелки — порядок</span></div>';
  arr.forEach(function(item,i){
    var t=l.titleField?String(getPath(item,l.titleField)||''):'';
    h+='<div class="item"><div class="item-head"><strong>#'+(i+1)+(t?' · '+esc(t):'')+'</strong><div class="item-tools">'
      +'<button class="btn mini" data-mv="'+l.path+'" data-i="'+i+'" data-d="-1">&#8593;</button>'
      +'<button class="btn mini" data-mv="'+l.path+'" data-i="'+i+'" data-d="1">&#8595;</button>'
      +'<button class="btn btn-red mini" data-del="'+l.path+'" data-i="'+i+'">Удалить</button></div></div>';
    (l.item||[]).forEach(function(f){h+=fieldHTML(f,l.path+'.'+i)});
    h+='</div>';
  });
  var tpl=typeof l.tpl==='string'?l.tpl:JSON.stringify(l.tpl||{});
  h+='<button class="btn" data-add="'+l.path+'" data-tpl="'+esc(tpl)+'">+ Добавить</button>';
  return h;
}

function bind(){
  qa('[data-path]').forEach(function(el){
    el.addEventListener(el.tagName==='SELECT'||el.type==='checkbox'?'change':'input',function(){
      var p=el.dataset.path;
      var val=(el.type==='checkbox')?!!el.checked:el.value;
      setPath(DATA,p,val); setDirty(true);
      qa('[data-path="'+p+'"]').forEach(function(o){if(o!==el){if(o.type==='checkbox')o.checked=!!val;else o.value=val}});
      var pv=q('[data-prev="'+p+'"]'); if(pv)pv.innerHTML=val?'<img src="'+esc(val)+'" loading="lazy">':'';
    });
  });
  qa('[data-upload]').forEach(function(inp){inp.addEventListener('change',function(){upload(inp)})});
  qa('[data-media]').forEach(function(b){b.addEventListener('click',function(){openMedia(b.dataset.media)})});
  qa('[data-ai]').forEach(function(b){b.addEventListener('click',function(){runAI(b)})});
  qa('[data-del]').forEach(function(b){b.addEventListener('click',function(){delItem(b.dataset.del,+b.dataset.i)})});
  qa('[data-mv]').forEach(function(b){b.addEventListener('click',function(){moveItem(b.dataset.mv,+b.dataset.i,+b.dataset.d)})});
  qa('[data-add]').forEach(function(b){b.addEventListener('click',function(){addItem(b.dataset.add,b.dataset.tpl)})});
  qa('[data-act]').forEach(function(b){b.addEventListener('click',function(){doAction(b.dataset.act)})});
}

function addItem(path,tpl){
  var arr=getPath(DATA,path); if(!Array.isArray(arr)){arr=[];setPath(DATA,path,arr)}
  var item; try{item=JSON.parse(tpl)}catch(e){item=tpl}
  arr.push(item); setDirty(true); render();
}
function delItem(path,i){ if(!confirm('Удалить этот элемент?'))return; getPath(DATA,path).splice(i,1); setDirty(true); render(); }
function moveItem(path,i,d){ var arr=getPath(DATA,path),j=i+d; if(j<0||j>=arr.length)return; var x=arr[i];arr[i]=arr[j];arr[j]=x; setDirty(true); render(); }
function refreshField(p,val){ qa('[data-path="'+p+'"]').forEach(function(o){o.value=val}); var pv=q('[data-prev="'+p+'"]'); if(pv)pv.innerHTML=val?'<img src="'+esc(val)+'" loading="lazy">':''; }

function upload(inp){
  var p=inp.dataset.upload,f=inp.files[0];
  if(!f)return;
  if(f.size>8*1024*1024){toast('Файл больше 8 МБ',true);return}
  var fd=new FormData(); fd.append('file',f);
  toast('Загружаю...');
  fetch('/admin/api/upload',{method:'POST',body:fd,credentials:'same-origin'})
    .then(function(r){return r.json()})
    .then(function(j){
      if(j&&j.url){setPath(DATA,p,j.url);setDirty(true);refreshField(p,j.url);toast(j.storage?'Загружено в Supabase Storage':'Загружено (data-URL)')}
      else toast('Не загрузилось: '+((j&&j.error)||'ошибка'),true);
    }).catch(function(e){toast('Ошибка: '+e.message,true)});
  inp.value='';
}

function runAI(b){
  var p=b.dataset.aiPath,task=b.dataset.ai,cur=String(getPath(DATA,p)||'');
  b.disabled=true; var old=b.textContent; b.textContent='...';
  api('/admin/api/ai',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task:task,path:p,value:cur})})
    .then(function(j){
      if(j&&j.text){setPath(DATA,p,j.text);setDirty(true);refreshField(p,j.text);toast('AI ('+j.provider+'): готово')}
      else toast('AI: '+((j&&j.error)||'пустой ответ'),true);
    })
    .catch(function(e){toast('AI ошибка: '+e.message,true)})
    .then(function(){b.disabled=false;b.textContent=old});
}

function openMedia(p){
  mediaTarget=p;
  q('#mediaGrid').innerHTML='<p class="hint" style="padding:16px">Загружаю список...</p>';
  q('#modal').classList.add('open');
  api('/admin/api/media').then(function(j){
    if(!j||!j.items||!j.items.length){q('#mediaGrid').innerHTML='<p class="hint" style="padding:16px">В хранилище пока нет файлов. Загрузите первый кнопкой «Файл».</p>';return}
    q('#mediaGrid').innerHTML=j.items.map(function(it){
      return '<button data-pick="'+esc(it.url)+'"><img src="'+esc(it.url)+'" loading="lazy"><div class="nm">'+esc(it.name)+'</div></button>';
    }).join('');
    qa('[data-pick]').forEach(function(b){b.addEventListener('click',function(){
      setPath(DATA,mediaTarget,b.dataset.pick);setDirty(true);refreshField(mediaTarget,b.dataset.pick);
      q('#modal').classList.remove('open');toast('Картинка выбрана');
    })});
  }).catch(function(e){q('#mediaGrid').innerHTML='<p class="hint" style="padding:16px">Ошибка: '+esc(e.message)+'</p>'});
}

function out(html){var el=q('#toolsOut'); if(el)el.innerHTML=html; else toast('Откройте вкладку «Инструменты»')}

function showStatus(){
  out('Проверяю...');
  api('/admin/api/status').then(function(j){
    function row(ok,txt){return '<div>'+(ok?'[OK]':'[--]')+' '+txt+'</div>'}
    out('<b>Состояние</b>\n'
      +row(j.db_read,'Чтение Supabase: '+(j.db_read?'OK':'ошибка'))
      +row(j.db_write!==false,'Запись Supabase: '+(j.db_write===false?'была ошибка':'OK'))
      +row(j.storage,'Хранилище картинок: '+(j.storage?('бакет '+j.bucket):'недоступно (картинки станут data-URL)'))
      +row(j.ai.yandex||j.ai.gigachat,'AI: '+(j.ai.yandex?'YandexGPT готов':'YandexGPT нет ключа')+', '+(j.ai.gigachat?'GigaChat готов':'GigaChat нет ключа'))
      +'\n<b>Контент</b>\n'
      +'<div>Размер данных: '+Math.round((j.size||0)/1024)+' КБ · работ: '+(j.counts.works||0)+' · отзывов: '+(j.counts.reviews||0)+' · услуг: '+(j.counts.services||0)+'</div>'
      +'<div>Домен: '+esc(j.domain)+' · адресов в sitemap: '+j.sitemap_urls+' · картинок в sitemap: '+j.sitemap_images+'</div>'
      +'\n<b>Версии</b>\n<div>Версия в базе: rev '+(j.rev||0)+(j.at?(' · '+esc(j.at)):'')+' · резервных копий: '+(j.backups||0)+'</div>');
  }).catch(function(e){out('Ошибка проверки: '+esc(e.message))});
}

function aiSeo(){
  var tasks=[['seo.title','seo_title'],['seo.description','seo_description'],['seo.keywords','seo_keywords']];
  out('Генерирую SEO... (10-30 секунд)');
  var i=0,done=[];
  (function next(){
    if(i>=tasks.length){out('<b>SEO обновлён</b>\n'+done.join('\n')+'\n\nНе забудьте нажать «Сохранить».');return}
    var p=tasks[i][0],t=tasks[i][1];
    api('/admin/api/ai',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task:t,path:p,value:String(getPath(DATA,p)||'')})})
      .then(function(j){
        if(j&&j.text){setPath(DATA,p,j.text);setDirty(true);done.push('+ '+p+': '+esc(j.text.slice(0,90)))}
        else done.push('- '+p+': ошибка '+esc((j&&j.error)||''));
      }).catch(function(e){done.push('- '+p+': '+esc(e.message))})
      .then(function(){i++;next()});
  })();
}

function doAction(act){
  if(act==='open'){window.open('/','_blank');return}
  if(act==='reload'){if(!confirm('Отменить несохранённые изменения?'))return;load();return}
  if(act==='export'){location.href='/admin/api/export';return}
  if(act==='import'){q('#importFile').click();return}
  if(act==='status'){showStatus();return}
  if(act==='history'){loadBackups();return}
  if(act==='ai-seo'){aiSeo();return}
}

function save(force){
  if(!DATA){toast('Данные ещё не загрузились',true);return}
  if(!force && dirty && !confirm('Проверили изменения?\n\nПосле сохранения они появятся на сайте.\nЕсли всё верно — нажмите «ОК».'))return;
  setStatus(force?'Перезапись...':'Сохранение...','saving');
  fetch('/admin/api/save',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({data:DATA,rev:REV,force:!!force})})
    .then(function(r){return r.json()})
    .then(function(j){
      if(j&&j.ok){
        REV=j.rev||REV+1; setDirty(false);
        setStatus('Сохранено · rev '+REV,'ok');
        toast(j.verified?('Сохранено и проверено в базе (rev '+REV+')'):('Сохранено (rev '+REV+')'));
      }else if(j&&j.conflict){
        setStatus('Конфликт версий','bad');
        var msg='В базе уже версия rev '+j.server_rev+(j.server_at?(' от '+j.server_at):'')+', а у вас открыт снимок rev '+j.client_rev+'.\n\n'
          +'Такое бывает, если админка открыта в двух вкладках/окнах или на двух устройствах.\n\n'
          +'OK — перезаписать базу тем, что сейчас в этой вкладке.\n'
          +'Отмена — загрузить свежие данные из базы (несохранённые правки этой вкладки пропадут).';
        if(confirm(msg)){save(true);}else{load();}
      }else{
        setStatus('Не сохранилось','bad');
        toast('Ошибка записи: '+((j&&(j.error||j.message))||'проверьте SUPABASE_SERVICE_KEY на хостинге'),true);
      }
    }).catch(function(e){setStatus('Ошибка','bad');toast('Ошибка: '+e.message,true)});
}

function load(){
  api('/admin/api/data').then(function(j){
    if(!j||typeof j!=='object'){throw new Error('пустой ответ')}
    DATA=j; ORIG=JSON.parse(JSON.stringify(j)); REV=(j._meta&&j._meta.rev)||0; SERVER_AT=(j._meta&&j._meta.at)||'';
    setDirty(false);render();setStatus('Готово · rev '+REV,'ok');
  }).catch(function(e){
    setStatus('Ошибка загрузки','bad');
    q('#main').innerHTML='<h2>Не удалось загрузить данные</h2><p class="hint">'+esc(e.message)+'</p><p class="hint">Проверьте SUPABASE_URL и SUPABASE_SERVICE_KEY на хостинге, затем обновите страницу.</p>';
  });
}

/* тихо подтягиваем свежие данные, когда возвращаемся в окно */
function checkRemote(){
  if(dirty)return;
  api('/admin/api/data').then(function(j){
    var r=(j&&j._meta&&j._meta.rev)||0;
    if(r!==REV){
      DATA=j;REV=r;SERVER_AT=(j._meta&&j._meta.at)||'';render();
      setStatus('Обновлено из базы · rev '+REV,'ok');
      toast('Данные обновлены из базы (rev '+REV+')');
    }
  }).catch(function(){});
}
window.addEventListener('focus',checkRemote);
document.addEventListener('visibilitychange',function(){if(!document.hidden)checkRemote();});

/* история версий */
function out2(html){var el=q('#histOut'); if(el)el.innerHTML=html; else toast('Откройте вкладку «История версий»')}
function loadBackups(){
  out2('Загружаю список...');
  api('/admin/api/history').then(function(j){
    if(!j||!j.items||!j.items.length){out2('Резервных копий пока нет — они появятся после первого сохранения.');return}
    var h='<b>Резервные копии: '+j.items.length+'</b>\n';
    j.items.forEach(function(it){
      var dt=String(it.at||'').replace('T',' ').slice(0,19);
      var kb=it.size?(' · '+Math.round(it.size/1024)+' КБ'):'';
      h+='<div style="display:flex;justify-content:space-between;gap:10px;align-items:center;border-bottom:1px solid rgba(236,207,160,.12);padding:6px 0">'
        +'<span>'+esc(it.name)+'<span style="color:#6f6659"> · '+esc(dt)+kb+'</span></span>'
        +'<span><button class="btn mini" data-restore="'+esc(it.name)+'">Подставить</button></span></div>';
    });
    out2(h+'\n«Подставить» загрузит копию в редактор — затем нажмите «Сохранить».');
    qa('[data-restore]').forEach(function(b){b.addEventListener('click',function(){restore(b.dataset.restore)})});
  }).catch(function(e){out2('Ошибка: '+esc(e.message))});
}
function restore(name){
  api('/admin/api/history?name='+encodeURIComponent(name)).then(function(j){
    if(!j||typeof j!=='object'){toast('Копия пустая',true);return}
    if(!confirm('Подставить копию '+name+' в редактор? Несохранённые правки пропадут.'))return;
    DATA=j;REV=(j._meta&&j._meta.rev)||0;setDirty(true);render();
    toast('Копия загружена — нажмите «Сохранить»');
  }).catch(function(e){toast('Ошибка: '+e.message,true)});
}

document.addEventListener('click',function(e){
  var tab=e.target.closest('nav.side a[data-tab]');
  if(tab){TAB=tab.dataset.tab;render();return}
  if(e.target.closest('#saveBtn')){save();return}
  if(e.target.closest('#reloadBtn')){doAction('reload');return}
  if(e.target.closest('#mClose')||e.target.id==='modal'){q('#modal').classList.remove('open');return}
});
q('#importFile').addEventListener('change',function(){
  var f=this.files[0]; if(!f)return;
  var r=new FileReader();
  r.onload=function(){
    try{
      var obj=JSON.parse(r.result);
      if(!obj||typeof obj!=='object')throw new Error('это не объект');
      DATA=obj;setDirty(true);render();toast('Бэкап загружен — нажмите «Сохранить»');
    }catch(err){toast('Не разобрал JSON: '+err.message,true)}
  };
  r.readAsText(f,'utf-8');
  this.value='';
});
document.addEventListener('keydown',function(e){
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){e.preventDefault();save()}
  if(e.key==='Escape')q('#modal').classList.remove('open');
});
window.addEventListener('beforeunload',function(e){if(dirty){e.preventDefault();e.returnValue=''}});
load();
setInterval(refreshLeadBadge,15000);
</script></body></html>"""

ADMIN_HTML = ADMIN_HTML.replace("__SCHEMA__", _SCHEMA_JSON)

STATIC_EXT = {".html", ".htm", ".txt", ".xml", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico",
              ".css", ".js", ".json", ".webmanifest", ".woff", ".woff2", ".pdf", ".mp4"}
STATIC_BLOCK = {"page.html", "mebel.py", "requirements.txt", "Dockerfile", "robots.txt", "sitemap.xml"}
MIME = {".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8", ".txt": "text/plain; charset=utf-8",
        ".xml": "application/xml; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif",
        ".ico": "image/x-icon", ".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8", ".webmanifest": "application/manifest+json; charset=utf-8",
        ".woff": "font/woff", ".woff2": "font/woff2", ".pdf": "application/pdf", ".mp4": "video/mp4"}


# ============================================================
#  HTTP
# ============================================================
def _parse_multipart(body, boundary):
    """Возвращает (имя_файла, данные) первого файла из multipart/form-data."""
    if not body or not boundary:
        return None, None
    for p in body.split(b"--" + boundary):
        if b"Content-Disposition" not in p:
            continue
        head, _, data = p.partition(b"\r\n\r\n")
        if not data:
            continue
        data = data.rstrip(b"\r\n")
        if data.endswith(b"--"):
            data = data[:-2].rstrip(b"\r\n")
        name = ""
        m = re.search(rb'filename="([^"]*)"', head)
        if m:
            name = m.group(1).decode("utf-8", "ignore")
        return name, data
    return None, None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "OstrovskyCMS/2.0"
    _head_only = False

    # ---------- служебное ----------
    def _tok(self):
        raw = self.headers.get("Cookie", "")
        if not raw:
            return None
        try:
            c = SimpleCookie()
            c.load(raw)
            m = c.get("admin_session")
            return m.value if m else None
        except Exception:
            return None

    def _admin(self):
        return _check_session(self._tok())

    def _ip(self):
        fwd = self.headers.get("X-Forwarded-For", "")
        return (fwd.split(",")[0].strip() if fwd else self.client_address[0])

    def _is_https(self):
        return self.headers.get("X-Forwarded-Proto", "").lower() == "https"

    def _send(self, code, body, ctype="text/plain; charset=utf-8", cache="no-cache", gzip_ok=True):
        data = body.encode("utf-8") if isinstance(body, str) else body
        etag = '"' + hashlib.sha256(data).hexdigest()[:20] + '"'
        if code == 200 and self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", cache)
            self.end_headers()
            return
        ae = self.headers.get("Accept-Encoding", "") or ""
        extra = [("X-Content-Type-Options", "nosniff"),
                 ("Referrer-Policy", "strict-origin-when-cross-origin")]
        if self.path.startswith("/admin"):
            extra.append(("X-Robots-Tag", "noindex, nofollow"))
        if gzip_ok and isinstance(body, str) and "gzip" in ae and len(data) > 700:
            buf = io.BytesIO()
            with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6) as gz:
                gz.write(data)
            data = buf.getvalue()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        else:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            if isinstance(body, str):
                self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.send_header("ETag", etag)
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        if not self._head_only:
            try:
                self.wfile.write(data)
            except Exception:
                pass

    def _redir(self, loc, cookie=None):
        self.send_response(302)
        self.send_header("Location", loc)
        self.send_header("Cache-Control", "no-cache")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length", "0") or 0)
        except Exception:
            n = 0
        if n <= 0 or n > MAX_UPLOAD * 4:
            return b""
        return self.rfile.read(n)

    def _cookie(self, token):
        c = "admin_session={}; Path=/; Max-Age={}; HttpOnly; SameSite=Lax".format(token, SESSION_TTL)
        if self._is_https():
            c += "; Secure"
        return c

    # ---------- маршруты ----------
    def do_HEAD(self):
        self._head_only = True
        self.do_GET()

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        # Единый адрес: www -> основной домен. Админка/локальный хост не трогаем.
        host = (self.headers.get("Host") or "").split(":", 1)[0].lower()
        if host.startswith("www.") and path not in ("/admin", "/admin/login"):
            target_host = _host(load_data()).lower()
            if target_host and host[4:] == target_host:
                loc = _domain(load_data()) + (self.path if self.path else "/")
                self._redir(loc)
                return

        if path == "/img":
            self._route_img()
            return
        if path == "/healthz":
            self._send(200, "ok", "text/plain; charset=utf-8")
            return

        if path == "/admin/login":
            self._send(200, ADMIN_LOGIN_HTML.replace("__ERROR__", ""), "text/html; charset=utf-8")
            return
        if path == "/admin/logout":
            _drop_session(self._tok())
            self._redir("/admin/login", "admin_session=; Path=/; Max-Age=0; HttpOnly")
            return
        if path == "/admin/api/data":
            if not self._admin():
                self._json({"error": "no auth"}, 401)
                return
            self._json(load_fresh())
            return
        if path == "/admin/api/export":
            if not self._admin():
                self._json({"error": "no auth"}, 401)
                return
            blob = json.dumps(load_fresh(), ensure_ascii=False, indent=1).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition",
                             'attachment; filename="mebel-backup-{}.json"'.format(date.today().isoformat()))
            self.send_header("Content-Length", str(len(blob)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            if not self._head_only:
                self.wfile.write(blob)
            return
        if path == "/admin/api/media":
            if not self._admin():
                self._json({"error": "no auth"}, 401)
                return
            self._json({"items": _storage_list(), "bucket": BUCKET})
            return
        if path == "/admin/api/leads":
            if not self._admin():
                self._json({"error": "no auth"}, 401)
                return
            items = _get_leads()
            self._json({"items": items, "unread": sum(1 for x in items if not x.get("read"))})
            return
        if path == "/admin/api/audit":
            if not self._admin():
                self._json({"error": "no auth"}, 401)
                return
            self._json({"items": _get_audit()})
            return
        if path == "/admin/api/history":
            if not self._admin():
                self._json({"error": "no auth"}, 401)
                return
            qs = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            name = (qs.get("name") or [""])[0]
            if name:
                if not re.match(r"^[A-Za-z0-9._-]+$", name) or ".." in name:
                    self._json({"error": "плохое имя"}, 400)
                    return
                blob = _storage_get(BACKUP_BUCKET, name)
                if blob is None:
                    self._json({"error": "копия не найдена"}, 404)
                    return
                self._send(200, blob, "application/json; charset=utf-8", "no-cache")
                return
            items = _storage_list_bucket(BACKUP_BUCKET, 200)
            out = []
            for it in items:
                meta = it.get("metadata") if isinstance(it.get("metadata"), dict) else {}
                out.append({"name": it.get("name"), "size": meta.get("size"), "at": it.get("created_at")})
            self._json({"items": out, "bucket": BACKUP_BUCKET})
            return
        if path == "/admin/api/status":
            if not self._admin():
                self._json({"error": "no auth"}, 401)
                return
            self._json(self._status_payload())
            return
        if path == "/admin":
            if not self._admin():
                self._redir("/admin/login")
                return
            self._send(200, ADMIN_HTML, "text/html; charset=utf-8")
            return

        if path in ("/", "/index.html"):
            html = render_site()
            if "cookiesAccepted=1" in (self.headers.get("Cookie") or ""):
                html = re.sub(r'<div class="cookie-bar" id="cookieBar">.*?</div>\s*', "", html, count=1, flags=re.S)
            self._send(200, html, "text/html; charset=utf-8", "no-cache")
            return
        if path == "/robots.txt":
            self._send(200, build_robots(load_data()), "text/plain; charset=utf-8", "public, max-age=3600")
            return
        if path == "/sitemap.xml":
            self._send(200, build_sitemap(load_data()), "application/xml; charset=utf-8", "public, max-age=3600")
            return
        if path == "/manifest.webmanifest":
            self._send(200, build_manifest(load_data()), "application/manifest+json; charset=utf-8", "public, max-age=86400")
            return
        if path in ("/favicon.ico", "/favicon.svg", "/favicon-16x16.png", "/favicon-32x32.png",
                    "/apple-touch-icon.png", "/favicon-192x192.png"):
            self._route_favicon(path)
            return

        if self._serve_static(path):
            return
        self._send(404, build_404(load_data()), "text/html; charset=utf-8")

    def do_POST(self):
        path = self.path.split("?", 1)[0]

        if path == "/api/lead":
            try:
                req = json.loads(self._body().decode("utf-8") or "{}")
            except Exception:
                self._json({"error": "Некорректные данные"}, 400)
                return
            if not isinstance(req, dict):
                self._json({"error": "Некорректные данные"}, 400)
                return
            if str(req.get("website") or "").strip():
                self._json({"ok": True})
                return
            name = re.sub(r"\s+", " ", str(req.get("name") or "").strip())[:120]
            phone = re.sub(r"\s+", " ", str(req.get("phone") or "").strip())[:80]
            message = str(req.get("message") or "").strip()[:1000]
            page = str(req.get("page") or "/").strip()[:300]
            digits = re.sub(r"\D", "", phone)
            if len(digits) < 7:
                self._json({"error": "Укажите номер телефона"}, 400)
                return
            lead = _add_lead(name, phone, message, page, self._ip())
            if not lead:
                self._json({"error": "Хранилище заявок временно недоступно"}, 503)
                return
            self._json({"ok": True, "id": lead["id"]})
            return

        if path == "/admin/login":
            ip = self._ip()
            if _login_blocked(ip):
                self._send(200, ADMIN_LOGIN_HTML.replace("__ERROR__", '<div class="err">Слишком много попыток. Подождите 10 минут.</div>'),
                           "text/html; charset=utf-8")
                return
            p = parse_qs(self._body().decode("utf-8", "ignore"))
            login = (p.get("login") or [""])[0].strip()
            pw = (p.get("password") or [""])[0]
            if (hmac.compare_digest(login.encode("utf-8"), ADMIN_LOGIN_ENV.encode("utf-8"))
                    and hmac.compare_digest(pw.encode("utf-8"), ADMIN_PASSWORD_ENV.encode("utf-8"))):
                _login_note(ip, True)
                self._redir("/admin", self._cookie(_new_session()))
            else:
                _login_note(ip, False)
                self._send(200, ADMIN_LOGIN_HTML.replace("__ERROR__", '<div class="err">Неверный логин или пароль</div>'),
                           "text/html; charset=utf-8")
            return

        if path == "/admin/api/save":
            if not self._admin():
                self._json({"error": "no auth"}, 401)
                return
            try:
                body = json.loads(self._body().decode("utf-8") or "{}")
            except Exception:
                self._json({"error": "bad json"}, 400)
                return
            if not isinstance(body, dict):
                self._json({"error": "not an object"}, 400)
                return
            if isinstance(body.get("data"), dict):
                payload, client_rev, force = body["data"], body.get("rev"), bool(body.get("force"))
            else:                       # старый формат: сразу объект данных
                payload, client_rev, force = body, None, True
            self._json(save_versioned(payload, client_rev, force, self._ip()))
            return

        if path == "/admin/api/leads/read":
            if not self._admin():
                self._json({"error": "no auth"}, 401)
                return
            try:
                req = json.loads(self._body().decode("utf-8") or "{}")
            except Exception:
                req = {}
            lead_id = req.get("id")
            if lead_id is None:
                _mark_lead(None, True)
                self._json({"ok": True})
            else:
                self._json({"ok": _mark_lead(str(lead_id), True)})
            return

        if path == "/admin/api/upload":
            if not self._admin():
                self._json({"error": "no auth"}, 401)
                return
            body = self._body()
            if not body:
                self._json({"error": "пустой файл"}, 400)
                return
            if len(body) > MAX_UPLOAD:
                self._json({"error": "файл больше 8 МБ"}, 413)
                return
            ctype = self.headers.get("Content-Type", "")
            blob, fname = None, "upload"
            if "multipart/form-data" in ctype:
                m = re.search(r"boundary=([^;]+)", ctype)
                if m:
                    fname, blob = _parse_multipart(body, m.group(1).strip().strip('"').encode())
            if not blob:
                blob, fname = body, "upload.jpg"
            mime = "image/jpeg"
            if blob[:8] == b"\x89PNG\r\n\x1a\n":
                mime = "image/png"
            elif blob[:6] in (b"GIF87a", b"GIF89a"):
                mime = "image/gif"
            elif blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
                mime = "image/webp"
            elif blob[:5] == b"<?xml" or blob[:4] == b"<svg":
                mime = "image/svg+xml"
            url = _storage_upload(fname, blob, mime)
            if url:
                self._json({"url": url, "storage": True, "bucket": BUCKET})
            else:
                self._json({"url": "data:{};base64,{}".format(mime, base64.b64encode(blob).decode("ascii")),
                            "storage": False, "warning": "Storage недоступен — картинка сохранена как data-URL"})
            return

        if path == "/admin/api/ai":
            if not self._admin():
                self._json({"error": "no auth"}, 401)
                return
            try:
                req = json.loads(self._body().decode("utf-8") or "{}")
            except Exception:
                req = {}
            task = str(req.get("task") or "improve")
            value = str(req.get("value") or "")
            system, user = _ai_ask(load_data(), task, req.get("path"), value)
            text, provider, err = _ai_generate(system, user, 700)
            if text:
                self._json({"text": text, "provider": provider})
            else:
                self._json({"error": err or "AI недоступен"}, 200)
            return

        self._json({"error": "not found"}, 404)

    # ---------- помощники ----------
    def _route_img(self):
        qs = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
        u = (qs.get("u") or [""])[0]
        if not u:
            self._send(404, "no url")
            return
        try:
            url = base64.urlsafe_b64decode(u + "=" * (-len(u) % 4)).decode("utf-8")
        except Exception:
            self._send(400, "bad")
            return
        host = urllib.parse.urlparse(url).hostname or ""
        if not url.startswith("https://") or not host.endswith("vkuserphoto.ru"):
            self._send(403, "forbidden")
            return
        if not IMG_PROXY:
            self._redir(url)
            return
        blob, ct = _fetch_image(url)
        if blob is None:
            self._redir(url)
            return
        self._send(200, blob, ct, "public, max-age=604800", gzip_ok=False)

    def _route_favicon(self, path):
        """Иконки: сначала пробуем собрать из логотипа, иначе отдаём вшитые в файл."""
        if path == "/favicon.svg":
            self._send(200, favicon_svg(), "image/svg+xml", "public, max-age=86400", gzip_ok=False)
            return
        if path == "/favicon.ico":
            get_favicon()
            blob = _ic["ico"] or _b64_bytes(FAVICON_ICO_B64)
            if blob:
                self._send(200, blob, "image/x-icon", "public, max-age=86400", gzip_ok=False)
            else:
                self._redir(favicon_source())
            return
        key, fb = {"/favicon-16x16.png": ("png16", FAVICON_PNG32_B64),
                   "/favicon-32x32.png": ("png32", FAVICON_PNG32_B64),
                   "/apple-touch-icon.png": ("png180", FAVICON_PNG180_B64),
                   "/favicon-192x192.png": ("png192", FAVICON_PNG180_B64)}[path]
        if _ic.get(key) is None:
            get_favicon()
        blob = _ic.get(key) or _b64_bytes(fb)
        if blob:
            self._send(200, blob, "image/png", "public, max-age=86400", gzip_ok=False)
        else:
            self._redir(favicon_source())

    def _serve_static(self, path):
        rel = urllib.parse.unquote(path).lstrip("/")
        if not rel or rel.startswith(".") or ".." in rel.split("/") or rel in STATIC_BLOCK:
            return False
        ext = os.path.splitext(rel)[1].lower()
        if ext not in STATIC_EXT:
            return False
        fp = os.path.join(ROOT, *rel.split("/"))
        if not os.path.isfile(fp):
            return False
        try:
            with open(fp, "rb") as f:
                blob = f.read()
        except Exception:
            return False
        self._send(200, blob, MIME.get(ext, "application/octet-stream"), "public, max-age=86400", gzip_ok=False)
        return True

    def _status_payload(self):
        data = load_data()
        counts = {}
        for key in ("works", "reviews", "services", "process", "guarantees", "cities"):
            items = (data.get(key) or {}).get("items")
            counts[key] = len(items) if isinstance(items, list) else 0
        sm = build_sitemap(data)
        meta = _meta_of(data)
        try:
            backups = len(_storage_list_bucket(BACKUP_BUCKET, 200))
        except Exception:
            backups = 0
        return {
            "rev": meta["rev"], "at": meta["at"], "backups": backups,
            "db_read": bool(_db_state.get("read")),
            "db_write": _db_state.get("write"),
            "storage": _bucket_ensure(),
            "bucket": BUCKET,
            "ai": {"yandex": bool(YANDEX_API_KEY and FOLDER_ID), "gigachat": bool(GIGACHAT_AUTH_KEY)},
            "counts": counts,
            "size": len(json.dumps(data, ensure_ascii=False).encode("utf-8")),
            "domain": _domain(data),
            "sitemap_urls": sm.count("<url>"),
            "sitemap_images": sm.count("<image:image>"),
        }

    def log_message(self, fmt, *args):
        if os.environ.get("VERBOSE"):
            print("[http] " + (fmt % args), flush=True)


# ============================================================
#  ЗАПУСК
# ============================================================
def main():
    print("BOOT: Кухни Островский CMS", flush=True)
    print("BOOT: PORT = {}".format(PORT), flush=True)
    print("BOOT: DOMAIN = {} ({})".format(_domain(), _host()), flush=True)
    print("BOOT: Supabase = {} / таблица {}".format(SUPABASE_URL or "НЕ ЗАДАН", DATA_TABLE), flush=True)
    print("BOOT: Storage bucket = {}".format(BUCKET), flush=True)
    print("BOOT: AI = yandex:{} gigachat:{}".format(bool(YANDEX_API_KEY and FOLDER_ID), bool(GIGACHAT_AUTH_KEY)), flush=True)
    if not os.environ.get("SUPABASE_SERVICE_KEY"):
        print("BOOT: ВНИМАНИЕ! SUPABASE_SERVICE_KEY взята из кода — задайте её в переменных хостинга!", flush=True)
    p = os.path.join(ROOT, "page.html")
    if os.path.exists(p):
        print("BOOT: page.html найден ({} байт)".format(os.path.getsize(p)), flush=True)
    else:
        print("BOOT: ВНИМАНИЕ! page.html НЕ НАЙДЕН в {}".format(ROOT), flush=True)
    try:
        load_fresh()
    except Exception as e:
        print("BOOT: первичная загрузка не удалась: {}".format(e), flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
