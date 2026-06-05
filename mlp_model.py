"""
StyleMLP — import this in both your training script and score_with_mlp.py.

Input:  feature vector, concatenated:
          alpha     * FashionCLIP image  (768)
          (1-alpha) * DINOv2             (1024)
          text_w    * FashionCLIP text   (768)   ← optional, if embeddings.npz has it
          category one-hot               (10)
        = 2570 dims with text, 1802 without.
Output: scalar logit     (sigmoid gives 0-1 score)

input_dim is set at construction time from the actual feature width, so the
default below is only documentation — train_mlp.py passes X.shape[1].

Save:   torch.save(model, 'style_mlp.pt')
Load:   model = torch.load('style_mlp.pt', weights_only=False)
"""
import torch.nn as nn


class StyleMLP(nn.Module):
    def __init__(self, input_dim=2570, hidden_dims=(256, 64), dropout=0.3):
        super().__init__()
        layers = []
        prev = input_dim
        for h in hidden_dims:
            layers += [nn.Linear(prev, h), nn.GELU(), nn.Dropout(dropout)]
            prev = h
        layers.append(nn.Linear(prev, 1))
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)
