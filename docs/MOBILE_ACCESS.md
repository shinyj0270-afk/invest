# 휴대폰 대시보드

회사 PC를 LTE/5G에서 보는 경우와 집 PC를 같은 Wi-Fi에서 보는 경우를 지원한다. 기존 PC 대시보드(127.0.0.1:8767)는 유지하고 별도 로그인 게이트웨이가 기존 화면/API를 연결한다. 보유내역·DB를 복사하거나 새 수집 프로그램을 만들지 않는다. 휴대폰은 읽기 전용이며 입력·수동 갱신은 PC에서 한다. NordVPN은 접속 경로에서 제외한다.

## 회사 PC: LTE/5G 외부 접속

1. 평소처럼 `scripts/open-investment.cmd`로 PC 대시보드를 실행한다.
2. `scripts/open-mobile-internet.cmd`를 더블클릭한다.
3. 첫 실행에 접속 비밀번호(12자 이상)를 두 번 입력한다. 화면·로그에는 표시하지 않고 PBKDF2 해시만 보존한다.
4. 표시된 `https://…trycloudflare.com` 주소를 휴대폰에서 연다. 사용자 이름은 `investment`, 비밀번호는 직접 설정한 값이다.

공식 cloudflared Windows 2026.10.0을 PC별 `.local`에 다운로드하고 고정 SHA256을 확인한다. 전역 설치·방화벽 인바운드 개방·예약 등록은 하지 않는다. 게이트웨이는 127.0.0.1:8771에서만 수신하며 외부 TLS는 Cloudflare가 처리한다. PC에서 Cloudflare로 나가는 연결이 가능해야 한다. 모든 페이지/API에 로그인이 필요하므로 주소만 알아서는 자료를 볼 수 없다.

계정·도메인이 필요 없는 **임시 주소**다. 재실행하면 주소가 바뀌며 서비스 가동 보장은 없다. 장기 고정 주소는 아래 고정 HTTPS 연결을 사용한다. [Quick Tunnels 공식 안내](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)

PC와 실행 창을 켜 두어야 한다. Ctrl+C로 종료하면 이 실행이 만든 외부 연결 프로세스도 종료한다. 기존 PC 대시보드는 계속 실행된다.

## 집 PC: 같은 Wi-Fi 접속

1. PC 대시보드를 실행하고 `scripts/open-mobile-dashboard.cmd`를 더블클릭한다.
2. 첫 실행에 접속 비밀번호를 설정한다. Git for Windows의 OpenSSL로 이 PC 주소에 대한 HTTPS 인증서를 생성한다.
3. 표시된 `https://PC내부IP:8770`을 같은 Wi-Fi 휴대폰에서 연다. 사용자 이름은 `investment`다. 홈 화면에 추가하면 편리하다.

자동 주소 탐지는 Windows 물리 네트워크 카드를 사용하며 VPN 카드를 제외한다. 사설 주소가 없거나 여러 주소가 있으면 임의 선택하지 않는다. 첫 실행에 실제 내부 주소를 지정할 수 있다.

```powershell
.\.venv\Scripts\python.exe -B scripts/mobile_dashboard.py --address 192.168.0.10
```

주소는 예시다. Windows 방화벽의 접속 허용 창이 나오면 사용할 개인 네트워크에 한해 허용한다. 창이 없고 차단되면 8770/TCP의 원격 범위를 로컬 서브넷으로 제한한 인바운드 규칙을 별도로 등록한다. 스크립트는 방화벽을 변경하지 않는다. Wi-Fi의 기기 간 통신 차단 여부도 확인한다.

처음에는 자체 서명 인증서 때문에 브라우저가 인증서 확인을 요구할 수 있다. PC 화면의 주소와 인증서 SHA256을 확인한다. 경고 없이 사용하려면 해당 주소에 대한 신뢰할 수 있는 인증서를 구성한다. 공유기 DHCP 예약으로 PC 주소를 유지할 수 있다.

## 고정 외부 HTTPS 주소

도메인/HTTPS 연결이 이미 구성돼 있다면 다음을 사용한다.

```powershell
.\.venv\Scripts\python.exe -B scripts/mobile_dashboard.py --public-origin https://invest.example.com
```

도메인은 예시다. 실제 HTTPS 연결에서 `http://127.0.0.1:8771`로 연결하고 원래 도메인의 Host 헤더를 유지한다. 로컬 HTTP는 loopback에서만 수신한다. 외부 TLS 인증서와 접근 제한은 실제 확인해야 한다. 임시 주소에서 고정 주소로 자동 전환하지 않는다.

## 설정과 검증

- LAN과 외부 설정은 `.local/mobile-access/lan/`, `.local/mobile-access/internet/`에 각각 보존한다. 인증서·개인키·비밀번호 해시·외부 연결 도구는 공유/Git 대상이 아니다. 회사/집에서 각각 설정한다.
- 주소 변경·비밀번호 재설정 때는 접속 서버를 종료하고 해당 설정 폴더를 다른 로컬 이름으로 보존 이동한 후 다시 실행한다. 기존 인증서/설정을 자동 덮어쓰지 않는다.
- HTTPS, 모든 페이지/API 인증, 등록 Host/Origin만 허용, 실패 횟수 제한, 원격 POST 거부 및 기존 X-Dashboard-Token 검사를 적용한다. 임의 대상 프록시·파일 열람·인증정보/쿠키/Forwarded 헤더 전달은 지원하지 않는다.
- 기존 PC 자동 수집은 유지된다. 화면 열람에 따른 기존 GET 상태 점검은 동작할 수 있다. 읽기 전용은 원격 수동 변경 요청을 거부한다는 의미다.
- 합성 인증/프록시/TLS·모바일 검사와 합성 자료의 실제 임시 외부 연결 검사는 본인의 실제 휴대폰·집 Wi-Fi·인증서 신뢰 확인과 구분한다.

개발 검증: `.venv/Scripts/python.exe -B -m unittest tests.test_mobile_dashboard`. 기존 격리 검증: `tools/validate_share_candidates.py --ui`.
