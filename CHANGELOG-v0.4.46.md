# 글클메 애드온 v0.4.46

- 원본 v0.4.45 기반. WGC는 MapleStory 게임 HWND를 직접 지정해 창 내용만 수집. Win32 프로세스 메모리/패킷 접근 없음.
- OCR worker가 채팅 영역의 화면 x/y가 변경될 때 채팅 이력을 초기화하던 문제 수정. 같은 게임 HWND/ROI 크기의 WGC→MSS 전환에도 이력 보존.
- WGC callback에서 window geometry client/window/ROI를 한 번에 읽고, 위치 변경 시 오래된 좌표 프레임 제거.
- 변경 프레임 수집 큐 한도 48프레임·64MB (여전히 부하 시 유실 가능, 진단 알림 유지).
- v0.4.45 BUILD 오류: EXP-only fixture에서 단축키 키보드가 감지되길 요구하던 잘못된 단위 테스트를 keyboard-reference fixture로 교체.

## 검증 한계
Windows WGC 실제 게임 캡처 / 전체 PowerShell EXE 빌드 / 실게임에서 누락률 0%를 보장하지 않습니다.
