# ============================================================
#  Яндекс Маркет: авто-написание отзыва о товаре (UGC)
#
#  Реальные запросы из браузера (DevTools). Захват 2026-08-19.
#
#  Флоу (порядок вызовов при оставлении отзыва из раздела
#  «Мои задания» / my/tasks):
#
#  1) apiUgcReviewFormOpen  — открыть форму отзыва (получить context)
#  2) apiUgcReviewFormSave  — сохранить отзыв (отправить текст/оценку)
#  3) apiUgcThankPage       — показать "спасибо" (requestType=THANKS)
#
#  Общий формат (все три — POST application/json на
#  https://market.yandex.ru/api/web/market.front.marketFront.MarketFront/<METHOD>):
#
#  Тело:
#  {
#    "path": "/my/tasks",
#    "params": {
#      "requestType": "SAVE_REVIEW" | "THANKS",
#      "context": "<base64 JSON>",
#      "body": {   // только для SAVE_REVIEW
#        "averageGrade": 5,
#        "pro": "текст отзыва",
#        "anonymity": 0,
#        "selectedFactors": {},
#        "media": []
#      }
#    }
#  }
#
#  context (base64-декод):
#  {
#    "modelId": 6118573678,
#    "agitationId": "0-6118573679",
#    "surface": "lk",
#    "source": "cabinet-tasks",
#    "sku": 6118573679,
#    "osku": 6118573679,
#    "omodel": 6118573678,
#    "businessId": 216972682,
#    "orderId": 60351256195,
#    "hideEntity": "OSKU"
#  }
#
#  Заголовки (обязательные):
#    Content-Type: application/json
#    sk: <CSRF-токен из страницы>   (u35f74daa948471bd3f53f2d0209e3822)
#    x-market-app-version: 2026.08.16.0-desktop.t4520775952
#    x-market-apphost-target: market-pers-master-apphost
#    x-market-core-service: <UNKNOWN>
#    x-market-front-glue: 1787131749000
#    x-market-page-id: market:my-tasks
#    x-requested-with: XMLHttpRequest
#    x-retpath-y: https://market.yandex.ru/my/tasks
#    Origin: https://market.yandex.ru
#    Referer: https://market.yandex.ru/my/tasks
#    Cookie: Session_id=... (полный набор)
#    UA: стандартный Chrome 151
# ============================================================