import math

import torch
from torch import nn


MODEL_REGISTRY = {}


def register_model(name):
    def decorator(model_class):
        MODEL_REGISTRY[name] = model_class
        return model_class
    return decorator


def create_model(name, **kwargs):
    if name not in MODEL_REGISTRY:
        available = ", ".join(sorted(MODEL_REGISTRY))
        raise ValueError(f"알 수 없는 모델: {name}. 사용 가능: {available}")
    return MODEL_REGISTRY[name](**kwargs)


@register_model("cnn_transformer")
class CnnTransformer(nn.Module):
    def __init__(self, vocab_size, embedding_dim=256, transformer_layers=4,
                 attention_heads=8, dropout=0.1, max_sequence_length=2048):
        super().__init__()
        channels = (32, 64, 128, embedding_dim)
        layers = []
        input_channels = 3
        for output_channels in channels:
            layers.extend((
                nn.Conv2d(input_channels, output_channels, 3, stride=2, padding=1),
                nn.BatchNorm2d(output_channels),
                nn.GELU(),
            ))
            input_channels = output_channels
        self.encoder = nn.Sequential(*layers)
        self.memory_pool = nn.AdaptiveAvgPool2d((16, 12))
        self.token_embedding = nn.Embedding(vocab_size, embedding_dim)
        self.position_embedding = nn.Embedding(max_sequence_length, embedding_dim)
        decoder_layer = nn.TransformerDecoderLayer(
            embedding_dim, attention_heads, embedding_dim * 4,
            dropout=dropout, batch_first=True, activation="gelu",
        )
        self.decoder = nn.TransformerDecoder(decoder_layer, transformer_layers)
        self.output = nn.Linear(embedding_dim, vocab_size)
        self.scale = math.sqrt(embedding_dim)

    def encode_image(self, images):
        features = self.memory_pool(self.encoder(images))
        return features.flatten(2).transpose(1, 2)

    def forward(self, images, tokens):
        positions = torch.arange(tokens.size(1), device=tokens.device).unsqueeze(0)
        target = self.token_embedding(tokens) * self.scale + self.position_embedding(positions)
        causal_mask = nn.Transformer.generate_square_subsequent_mask(tokens.size(1), device=tokens.device)
        return self.output(self.decoder(target, self.encode_image(images), tgt_mask=causal_mask))

    @torch.no_grad()
    def generate(self, images, bos_id, eos_id, max_length):
        memory = self.encode_image(images)
        tokens = torch.full((images.size(0), 1), bos_id, dtype=torch.long, device=images.device)
        finished = torch.zeros(images.size(0), dtype=torch.bool, device=images.device)
        for _ in range(max_length - 1):
            positions = torch.arange(tokens.size(1), device=tokens.device).unsqueeze(0)
            target = self.token_embedding(tokens) * self.scale + self.position_embedding(positions)
            mask = nn.Transformer.generate_square_subsequent_mask(tokens.size(1), device=tokens.device)
            logits = self.output(self.decoder(target, memory, tgt_mask=mask))[:, -1]
            next_token = logits.argmax(dim=-1)
            tokens = torch.cat((tokens, next_token.unsqueeze(1)), dim=1)
            finished |= next_token.eq(eos_id)
            if finished.all():
                break
        return tokens

