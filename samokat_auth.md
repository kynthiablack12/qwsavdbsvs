# Самокат — данные авторизации (пойманы через Frida OkHttp logger 2026-08-09)
# Приложение: ru.sbcs.store v4.10.0 (build 92544), Android 9, device SM-S906N

## Bearer JWT (рабочий на момент 11:30-11:35 МСК, живёт ~5 мин)
authorization: Bearer eyJraWQiOiI2MTg2OTEiLCJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJhdWQiOiJodHRwczovL3NhbW9rYXQucnUiLCJzdWIiOiIxMzcxMDUwMjAyIiwiZGV2aWNlX2lkIjoiZTE2ODg4YTAxNDYyOTBiOCIsInNjb3BlIjpbIkNBUlRfTUFOQUdFTUVOVCIsIlBST0ZJTEVfTUFOQUdFTUVOVCIsIk9SREVSX01BTkFHRU1FTlQiXSwiZXhwIjoxNzg2MjUzNzE4LCJpYXQiOjE3ODYyNTM0MTgsInVzZXIiOnsidXNlcklkIjoiMTM3MTA1MDIwMiIsInVzZXJVdWlkIjoiMWY4YzI4NGUtMWIxZC00YTg3LTg4YmMtOTlkNDcyMzYyYzI2IiwidXNlclR5cGUiOiJTQU1PS0FUIn0sImp0aSI6IjEzNzA0Mjk3MjAzIiwiY2xpZW50X2lkIjoic2Ftb2thdCJ9.Cnwb58msYfzJ_rWGvwAlouFDqXuzXdg7TmjBNZQdcDKwA-dbIGGwPbJOs7lR3KQwMFrPzdfMW3deDFP_b1AXkPnNV5JXwdEeHpSctlN4OU5KtZ6K8Hv0Ps-cqWlB6fw_4OITXUAyEgeWCzaljdUMktifvBr9IGnb9H2In831oh0

## JWT payload
aud: https://samokat.ru
sub: 1371050202
device_id: e16888a0146290b8
scope: [CART_MANAGEMENT, PROFILE_MANAGEMENT, ORDER_MANAGEMENT]
user.userId: 1371050202
user.userUuid: 1f8c284e-1b1d-4a87-88bc-99d472362c26
user.userType: SAMOKAT
client_id: samokat
exp: 1786253718 (11:35:18 2026-08-09 МСК)
iat: 1786253418 (11:30:18)

## Заголовки аутентифицированных запросов к api.samokat.ru
authorization: Bearer <JWT>
deviceid: e16888a0146290b8
systemversion: 9
x-user-id: 1371050202
x-user-type: user
x-application-platform: android
x-application-version: 4.10.0
x-creeper: 99kiQACN25iAI2UUjKsoI69KqF9lj0bOa6PGrsPUGNGvHjog7GCno_FlhKXkPfQh8TY8lxGFWOkqhM_2x_iYgEKtvw8SsKb7DVk26cG96_1agdoXqgEuLZfAiyY5rrUWvEDvG8sJ2RQ_4KfMy062NIrJ1wluO9QZAffijXERxNoykieCmZvmgH0EktPKoeNXy1_O81qk0jTpfoM3Xo6EuYLGHS35oI_x0CqpCi4ywNtHGulVcp90A90ZaozsoxWh_arDQ6rjd0uSLfxuhtngChG1CYGbBine
x-trace-flags: 0
x-application-store: Undetermined
User-Agent: smartspacestoreapp/4.10.0 (build: 92544; device: SM-S906N; OS: Android 9)
Cookie: spid=1786250798350_6d0a2b94665fc367c521c620b122231f_cio6aonsl8hb1c5m; spsc=1786250798350_904cf6efac55ba446d053c8815716813_-5NTZKWQ97TALSB.ugyoys3Igm1Azdr677ENFoURCbAZ

## Профиль (GET /showcase/users/profile)
mobile: +79372537435
sberUuid: 933ae5d2f1546dafe6ee451d090ed2f42b0568dbb94b92c9715f3454528587f85916154b62e843db
isClient: true
sberOfferStatus: ACCEPTED
emailValidationStatus: NOT_VALID
selectedAddressId: 192485375 (Омск, пр-кт К. Маркса 36/2 кв 57)

## Вход — через СберID (oauth/configuration/sber, v2/users/profile/sber)
## Сам флоу входа (номер->SMS->код) шёл через WebView СберID и не перехвачен OkHttp-хуком

## Наблюдаемые эндпоинты api.samokat.ru
GET  /showcase/config/mobile                     (конфиг, 200)
GET  /showcase/users/profile                     (профиль, 200)
GET  /showcase/v2/users/profile/sber             (Сбер-профиль)
GET  /showcase/oauth/configuration/sber          (конфиг OAuth Сбера)
PUT  /showcase/v2/users/profile/timezone
GET  /showcase/showcases/list?lat=..&lon=..
POST /showcase/pickup-locations/by-radius
