# Copyright (c) OpenMMLab. All rights reserved.
from typing import Tuple

import torch
import torch.nn as nn
from mmengine.dist import get_world_size
from mmengine.model import BaseModule

from mmselfsup.registry import MODELS


@MODELS.register_module()
class LatentPredictHead(BaseModule):
    """Head for latent feature prediction.

    This head builds a predictor, which can be any registered neck component.
    For example, BYOL and SimSiam call this head and build NonLinearNeck.
    It also implements similarity loss between two forward features.

    Args:
        loss (dict): Config dict for the loss.
        predictor (dict): Config dict for the predictor.
    """

    def __init__(self, loss: dict, predictor: dict) -> None:
        super().__init__()
        self.loss = MODELS.build(loss)
        self.predictor = MODELS.build(predictor)

    def forward(self, input: torch.Tensor,
                target: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Forward head.

        Args:
            input (torch.Tensor): NxC input features.
            target (torch.Tensor): NxC target features.

        Returns:
            torch.Tensor: The latent predict loss.
        """
        pred = self.predictor([input])[0]
        target = target.detach()

        loss = self.loss(pred, target)

        return loss


@MODELS.register_module()
class LatentCrossCorrelationHead(BaseModule):
    """Head for latent feature cross correlation. Part of the code is borrowed
    from:
    `https://github.com/facebookresearch/barlowtwins/blob/main/main.py>`_.

    Args:
        in_channels (int): Number of input channels.
        loss (dict): Config dict for module of loss functions.
    """

    def __init__(self, in_channels: int, loss: dict) -> None:
        super().__init__()
        self.world_size = get_world_size()
        self.bn = nn.BatchNorm1d(in_channels, affine=False)
        self.loss = MODELS.build(loss)

    def forward(self, input: torch.Tensor,
                target: torch.Tensor) -> torch.Tensor:
        """Forward head.

        Args:
            input (torch.Tensor): NxC input features.
            target (torch.Tensor): NxC target features.

        Returns:
            torch.Tensor: The cross correlation matrix.
        """
        # cross-correlation matrix
        cross_correlation_matrix = self.bn(input).T @ self.bn(target)
        cross_correlation_matrix.div_(input.size(0) * self.world_size)

        if torch.distributed.is_initialized():
            torch.distributed.all_reduce(cross_correlation_matrix)

        loss = self.loss(cross_correlation_matrix)
        return loss