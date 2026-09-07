from dataclasses import asdict, dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    dataset_dir: Path = PROJECT_ROOT / "dataset"
    output_dir: Path = PROJECT_ROOT / "attendance_analysis" / "outputs"
    model_name: str = "cnn_transformer"
    image_width: int = 768
    image_height: int = 1024
    max_sequence_length: int = 2048
    embedding_dim: int = 256
    transformer_layers: int = 4
    attention_heads: int = 8
    dropout: float = 0.1
    batch_size: int = 2
    epochs: int = 30
    learning_rate: float = 0.0001
    validation_ratio: float = 0.1
    num_workers: int = 0
    seed: int = 42

    @property
    def files_dir(self) -> Path:
        return self.dataset_dir / "files"

    @property
    def labels_dir(self) -> Path:
        return self.dataset_dir / "labels"

    def model_kwargs(self, vocab_size: int) -> dict:
        return {
            "vocab_size": vocab_size,
            "embedding_dim": self.embedding_dim,
            "transformer_layers": self.transformer_layers,
            "attention_heads": self.attention_heads,
            "dropout": self.dropout,
            "max_sequence_length": self.max_sequence_length,
        }

    def to_dict(self) -> dict:
        result = asdict(self)
        result["dataset_dir"] = str(self.dataset_dir)
        result["output_dir"] = str(self.output_dir)
        return result

