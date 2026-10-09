Claude 루틴이 평일 21:55 KST에 이 폴더의 `request.txt`를 main에 커밋하면
`.github/workflows/live-prices.yml`이 시작되어 22:00~02:00 KST 동안 10분마다 실시간 시세로 사이트를 다시 배포한다.
(`trigger/`와 분리: 그 폴더는 아침 데일리 발송을 깨운다.)
