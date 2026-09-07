import argparse
import json
import random
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader, Subset

from attendance_analysis.config import Config
from attendance_analysis.dataset import AttendanceDataset
from attendance_analysis.model import create_model


def split_indices(length, validation_ratio, seed):
    indices = list(range(length))
    random.Random(seed).shuffle(indices)
    validation_count = int(length * validation_ratio) if length > 1 else 0
    validation_count = min(max(validation_count, 1 if length >= 5 else 0), max(length - 1, 0))
    return indices[validation_count:], indices[:validation_count]


def run_epoch(model, loader, optimizer, criterion, device, pad_id):
    training = optimizer is not None
    model.train(training)
    total_loss = 0.0
    for batch in loader:
        images = batch["image"].to(device)
        tokens = batch["tokens"].to(device)
        inputs, targets = tokens[:, :-1], tokens[:, 1:]
        with torch.set_grad_enabled(training):
            logits = model(images, inputs)
            loss = criterion(logits.reshape(-1, logits.size(-1)), targets.reshape(-1))
            if training:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
        total_loss += loss.item()
    return total_loss / max(len(loader), 1)


def train(config):
    torch.manual_seed(config.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dataset = AttendanceDataset(
        config.dataset_dir,
        image_size=(config.image_width, config.image_height),
        max_length=config.max_sequence_length,
    )
    train_indices, validation_indices = split_indices(len(dataset), config.validation_ratio, config.seed)
    train_loader = DataLoader(
        Subset(dataset, train_indices), batch_size=config.batch_size,
        shuffle=True, num_workers=config.num_workers,
    )
    validation_loader = DataLoader(
        Subset(dataset, validation_indices), batch_size=config.batch_size,
        num_workers=config.num_workers,
    ) if validation_indices else None

    model = create_model(config.model_name, **config.model_kwargs(len(dataset.tokenizer))).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate)
    criterion = nn.CrossEntropyLoss(ignore_index=dataset.tokenizer.pad_id)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    best_loss = float("inf")
    checkpoint_path = config.output_dir / "best.pt"

    for epoch in range(1, config.epochs + 1):
        train_loss = run_epoch(model, train_loader, optimizer, criterion, device, dataset.tokenizer.pad_id)
        validation_loss = (
            run_epoch(model, validation_loader, None, criterion, device, dataset.tokenizer.pad_id)
            if validation_loader else train_loss
        )
        print(f"epoch {epoch:03d} train={train_loss:.4f} validation={validation_loss:.4f}", flush=True)
        if validation_loss < best_loss:
            best_loss = validation_loss
            torch.save({
                "model_name": config.model_name,
                "model_state": model.state_dict(),
                "model_kwargs": config.model_kwargs(len(dataset.tokenizer)),
                "tokenizer": dataset.tokenizer.to_dict(),
                "config": config.to_dict(),
                "epoch": epoch,
                "validation_loss": validation_loss,
            }, checkpoint_path)
    print(f"완료: {checkpoint_path}", flush=True)
    return checkpoint_path


def main():
    defaults = Config()
    parser = argparse.ArgumentParser(description="출근부 이미지 JSON 학습")
    parser.add_argument("--dataset", type=Path, default=defaults.dataset_dir)
    parser.add_argument("--output", type=Path, default=defaults.output_dir)
    parser.add_argument("--model", default=defaults.model_name)
    parser.add_argument("--epochs", type=int, default=defaults.epochs)
    parser.add_argument("--batch-size", type=int, default=defaults.batch_size)
    args = parser.parse_args()
    config = Config(
        dataset_dir=args.dataset, output_dir=args.output, model_name=args.model,
        epochs=args.epochs, batch_size=args.batch_size,
    )
    train(config)


if __name__ == "__main__":
    main()

