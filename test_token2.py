import requests, sys
sys.stdout.reconfigure(encoding='utf-8')

h = {
    'x-device-id': 'fe53fb8c-79eb-3f35-876b-5beadded889b',
    'x-device-tag': '8AA04F8C-3C01-4F11-A0E5-35221DD407CF_L!3E5CB4F7-61A8-4628-8A63-F8CE3E6A7222',
    'x-app-version': '8.114.0',
    'x-platform-version': '28',
    'x-device-platform': 'Android',
    'Content-Type': 'application/json; charset=UTF-8',
    'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 9; SM-S906N Build/PQ3A.190605.09261140)',
    'X-Analytics-Session-Id': '759a32eb-845d-446d-a1f7-9c6b6b12f7bd',
    'X-Apps-Flyer-Id': '1785996392858-4192453017068239882',
    'X-Telemetry': 'aBK_1BS3Mk60I3iaCg5qAZ_4RmtdNx2NVR8rhtwQRRE8oHvCDYMCJmCYBMzioCjILdXPWYtpAgUP5aFbX8DQpleVyiOnl85rgaKS6ZcQsfF2P0omJuscJfRWbFZ6iLj1Wq1cvJvl18Il1L8ti9vctPz7JAYfznZtv5DR5VmPu58cJ31KBUSXpTcTVJw34oUXR_xLcYlqymSa-QwMf8OtzgaSRyC8khFg9CWNG2JU8L_3pBTOeV6WkHc4VDg0aP8I8mPxm7k5YCvgyZVTJhCoGY2fmNm4spcPmKZt',
    'X-Telemetry-Version': '1',
    'sentry-trace': '5055f0e542f54d1ca16c991644d36718-4236a4d6ff5f43db',
    'baggage': 'sentry-environment=production,sentry-public_key=6d4cfb7c8887ad7d38f6d3182a75acda,sentry-release=ru.tander.magnit%408.114.0%2B1436169,sentry-sample_rand=0.6914726812662438,sentry-trace_id=5055f0e542f54d1ca16c991644d36718',
    'Accept-Encoding': 'gzip',
}
body = '{"aud":"loyalty-mobile","magnitIdCode":"2781757c-628a-4732-b063-028921ec2be6"}'
r = requests.post('https://id.magnit.ru/v1/auth/token', headers=h, data=body, timeout=15)
print('status', r.status_code)
print(r.text[:800])
