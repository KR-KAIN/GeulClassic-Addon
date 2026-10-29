# DB 조사 및 적용 기준 — 2026-10-24

## 1. Planet Helper (GMS Classic World)
https://planet-helper.com/gmsclassic/ko/db/
한국어 페이지에서 아이템 2,211개, 몬스터 193개 등 표시. 아이템 한글명과 영문 검색 기능은 대조 자료로 유용함. 다만 https://planet-helper.com/gmsclassic/ko/terms/ 에서는 데이터 자동 수집과 DB 재가공, 데이터셋 제작 등을 허락 없이 진행하지 말라고 명시함. 현재 앱에 사이트 자료/번역문을 추출하거나 내장하지 않음. 허락받은 데이터 파일이 있다면 offline CSV/JSON importer로 연결 가능.

## 2. 메이플노트 빅뱅
https://xn--o80b01o9mlw3kdzc.com/bigbang
과거 메이플 콘텐츠를 비교할 수 있음. 사이트 FAQ는 과거 클라이언트 데이터에서 수집한 드랍테이블이 재구성된 현행 클래식 서버와 일치하지 않을 수 있다고 밝힘. 최신 클래식 아이템명 확정 근거로 단독 사용 불가. 일괄 복제 허용 범위 미확인 → 크롤링/배포하지 않음.

## 3. GMS v83 영문 ID + 허용된 한국어 원본
영문 영구 색인은 GMS v83 WZ XML 공개 자료를 이용하여 로컬 빌드함. 앞선 별도 비교에서 제3자 한국어 항목 4,406개 중 4,324개 ID가 이 색인과 일치했으나, 개별 공식명 및 이차 이용 권리는 미검증. 현재 ZIP에는 한글명 4,324개를 실어 배포하지 않음.

## 4. Classic Maple Wiki
https://classicmaple.wiki/  https://github.com/classicmaple-wiki/classicmaple-wiki
영어 중심 공개 JSON은 CC BY-NC-SA 4.0으로 제공. 출처 표시와 비상업적 조건을 충족한다는 전제하에 기존 오프라인 다운로더를 유지함.

## 안전한 대조 워크플로
권리가 확인된 한국어 CSV/JSON -> 동일 숫자 item_id로 영문 v83 색인과 조인 -> 빈 이름/ID 충돌 제거 -> 영문명 중복이 상충하는 항목 제외 -> 사람 검토 -> 앱의 기존 승인된 용어집 가져오기. 사이트를 자동 수집하지 않음.
