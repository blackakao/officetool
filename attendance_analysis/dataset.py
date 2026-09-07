import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps
from torch.utils.data import Dataset

from attendance_analysis.label_io import LABEL_EXTENSIONS, read_label


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
SPECIAL_TOKENS = ("<pad>", "<bos>", "<eos>", "<unk>")


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class JsonCharTokenizer:
    def __init__(self, characters=()):
        self.tokens = list(SPECIAL_TOKENS) + sorted(set(characters) - set(SPECIAL_TOKENS))
        self.token_to_id = {token: index for index, token in enumerate(self.tokens)}

    @classmethod
    def from_label_files(cls, label_files):
        characters = set()
        for path in label_files:
            characters.update(canonical_json(read_label(path)))
        return cls(characters)

    @classmethod
    def from_dict(cls, data):
        tokenizer = cls()
        tokenizer.tokens = list(data["tokens"])
        tokenizer.token_to_id = {token: index for index, token in enumerate(tokenizer.tokens)}
        return tokenizer

    def to_dict(self):
        return {"tokens": self.tokens}

    def encode(self, text, max_length):
        ids = [self.bos_id]
        ids.extend(self.token_to_id.get(char, self.unk_id) for char in text)
        ids.append(self.eos_id)
        ids = ids[:max_length]
        if ids[-1] != self.eos_id:
            ids[-1] = self.eos_id
        ids.extend([self.pad_id] * (max_length - len(ids)))
        return torch.tensor(ids, dtype=torch.long)

    def decode(self, ids):
        result = []
        for token_id in ids:
            token = self.tokens[int(token_id)]
            if token == "<eos>":
                break
            if token not in SPECIAL_TOKENS:
                result.append(token)
        return "".join(result)

    @property
    def pad_id(self):
        return self.token_to_id["<pad>"]

    @property
    def bos_id(self):
        return self.token_to_id["<bos>"]

    @property
    def eos_id(self):
        return self.token_to_id["<eos>"]

    @property
    def unk_id(self):
        return self.token_to_id["<unk>"]

    def __len__(self):
        return len(self.tokens)


def image_to_tensor(path, size):
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail(size, Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", size, "white")
        left = (size[0] - image.width) // 2
        top = (size[1] - image.height) // 2
        canvas.paste(image, (left, top))
        array = np.asarray(canvas, dtype=np.float32) / 255.0
    return torch.from_numpy(array).permute(2, 0, 1).contiguous()


class AttendanceDataset(Dataset):
    def __init__(self, dataset_dir, tokenizer=None, image_size=(768, 1024), max_length=2048):
        self.dataset_dir = Path(dataset_dir)
        self.files_dir = self.dataset_dir / "files"
        self.labels_dir = self.dataset_dir / "labels"
        images = {
            path.stem: path for path in self.files_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        } if self.files_dir.exists() else {}
        labels = {}
        for path in self.labels_dir.iterdir() if self.labels_dir.exists() else ():
            if path.is_file() and path.suffix.lower() in LABEL_EXTENSIONS:
                if path.stem in labels:
                    raise ValueError(f"같은 이름의 정답 파일이 여러 개입니다: {path.stem}")
                labels[path.stem] = path
        self.samples = [(images[stem], labels[stem]) for stem in sorted(images.keys() & labels.keys())]
        if not self.samples:
            raise ValueError("dataset/files 이미지와 이름이 같은 dataset/labels XLSX 또는 JSON 쌍이 없습니다.")
        self.tokenizer = tokenizer or JsonCharTokenizer.from_label_files(label for _, label in self.samples)
        self.image_size = image_size
        self.max_length = max_length

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, index):
        image_path, label_path = self.samples[index]
        target = canonical_json(read_label(label_path))
        return {
            "image": image_to_tensor(image_path, self.image_size),
            "tokens": self.tokenizer.encode(target, self.max_length),
            "name": image_path.stem,
        }
