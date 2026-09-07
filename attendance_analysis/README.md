# 출근부 분석 모델

## 데이터 구성

이미지와 정답 엑셀 파일의 확장자를 제외한 이름을 동일하게 맞춥니다.

```text
dataset/
  files/
    attendance_001.jpg
  labels/
    attendance_001.xlsx
```

엑셀 첫 행에는 열 이름을 입력하고, 둘째 행부터 출근부의 각 기록을 입력합니다. 기본 열은 `지점`, `직원명`, `직종`, `생년월일`, `날짜`, `출근시간`, `퇴근시간`, `휴게시간`, `근무유형`입니다. 모든 정답 파일에서 같은 열 이름과 자료형을 사용해야 합니다. 기존 JSON 정답도 계속 지원합니다.

엑셀 내용은 학습할 때 프로그램 내부에서 표 구조로 자동 변환됩니다. 이미지 분석 결과는 앱에서 저장 위치를 선택하면 같은 표 구조의 XLSX 파일로 저장됩니다.

## 실행

```powershell
python -m attendance_analysis.train --epochs 30
python -m attendance_analysis.predict dataset/files/attendance_001.jpg --checkpoint attendance_analysis/outputs/best.pt --output attendance_001_분석결과.xlsx
```

앱의 `문서 분석 > 출근부 분석`에서도 같은 작업을 실행할 수 있습니다.

## 모델 교체

새 `torch.nn.Module`을 `model.py`에서 `@register_model("모델명")`으로 등록하고 `config.py`의 `model_name`을 변경합니다. 모델은 `forward(images, tokens)`와 `generate(images, bos_id, eos_id, max_length)` 인터페이스를 구현해야 합니다.
