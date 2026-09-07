import argparse
import json
from pathlib import Path

import torch

from attendance_analysis.dataset import JsonCharTokenizer, image_to_tensor
from attendance_analysis.model import create_model
from attendance_analysis.label_io import write_excel_result


def predict(image_path, checkpoint_path, device=None):
    device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    tokenizer = JsonCharTokenizer.from_dict(checkpoint["tokenizer"])
    model = create_model(checkpoint["model_name"], **checkpoint["model_kwargs"])
    model.load_state_dict(checkpoint["model_state"])
    model.to(device).eval()
    config = checkpoint.get("config", {})
    width = int(config.get("image_width", 768))
    height = int(config.get("image_height", 1024))
    max_length = int(config.get("max_sequence_length", 2048))
    image = image_to_tensor(image_path, (width, height)).unsqueeze(0).to(device)
    tokens = model.generate(image, tokenizer.bos_id, tokenizer.eos_id, max_length)[0]
    raw_text = tokenizer.decode(tokens.tolist())
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return {"_error": "모델 출력이 올바른 JSON이 아닙니다.", "_raw": raw_text}


def main():
    parser = argparse.ArgumentParser(description="출근부 이미지 분석")
    parser.add_argument("image", type=Path)
    parser.add_argument("--checkpoint", type=Path, default=Path(__file__).parent / "outputs" / "best.pt")
    parser.add_argument("--output", type=Path, help="결과 파일(.xlsx 또는 .json)")
    args = parser.parse_args()
    result = predict(args.image, args.checkpoint)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.suffix.lower() == ".xlsx":
            write_excel_result(result, args.output)
        elif args.output.suffix.lower() == ".json":
            with args.output.open("w", encoding="utf-8") as file:
                file.write(output)
        else:
            parser.error("--output은 .xlsx 또는 .json 파일이어야 합니다.")
        print(f"결과 저장: {args.output}")
    print(output)


if __name__ == "__main__":
    main()
