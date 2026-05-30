"""
StyleMLP — import this in both your training script and score_with_mlp.py.

Input:  1792-dim vector  (alpha * FashionCLIP_768  ++  (1-alpha) * DINOv2_1024)
Output: scalar logit     (sigmoid gives 0-1 score)

Save:   torch.save(model, 'style_mlp.pt')
Load:   model = torch.load('style_mlp.pt', weights_only=False)
"""
import torch.nn as nn


class StyleMLP(nn.Module):
    def __init__(self, input_dim=1792, hidden_dims=(512, 128), dropout=0.3):
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
