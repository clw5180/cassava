# @Author: yican, yelanlan
# @Date: 2020-06-16 20:43:36
# @Last Modified by:   yican
# @Last Modified time: 2020-06-14 16:21:14
# Third party libraries
import math
import torch.nn as nn
import torch
import torch.nn.functional as F
from torch.autograd import Variable


class CrossEntropyLossOneHot(nn.Module):
    def __init__(self):
        super(CrossEntropyLossOneHot, self).__init__()
        self.log_softmax = nn.LogSoftmax(dim=-1)

    def forward(self, preds, labels, snapmix=False, ohem=False):
        if not snapmix:
            if not ohem:
                ce_loss = torch.mean(torch.sum(-labels * self.log_softmax(preds), -1))
            else:
                ce_loss = torch.sum(-labels * self.log_softmax(preds), -1)
                ce_loss, idx = torch.sort(ce_loss, descending=True)
                bs = preds.shape[0]
                ce_loss = torch.mean(ce_loss[int(bs/4):int(bs/4*3)])
        else:
            ce_loss = torch.sum(-labels * self.log_softmax(preds), -1)
        # if reduction == 'sum':
        # w = [4, 2, 2, 0.4, 1.65]
        # ws = [w for _ in range(preds.shape[0])]
        # ce_loss = torch.mean(torch.sum(-labels * self.log_softmax(preds)*torch.as_tensor(ws).to(preds.device), -1)) # weight loss
        loss = ce_loss

        # # from https://www.kaggle.com/c/cassava-leaf-disease-classification/discussion/203271
        # cosine_loss = F.cosine_embedding_loss(preds, labels, torch.Tensor([1]).to(preds.device))
        # focal_loss = 1 * (1-torch.exp(-ce_loss))**2 * ce_loss
        # loss = focal_loss

        return loss

def ohem_loss( rate, cls_pred, cls_target ):
    batch_size = cls_pred.size(0) 
    ohem_cls_loss = F.cross_entropy(cls_pred, cls_target, reduction='none', ignore_index=-1)

    sorted_ohem_loss, idx = torch.sort(ohem_cls_loss, descending=True)
    keep_num = min(sorted_ohem_loss.size()[0], int(batch_size*rate) )
    if keep_num < sorted_ohem_loss.size()[0]:
        keep_idx_cuda = idx[:keep_num]
        ohem_cls_loss = ohem_cls_loss[keep_idx_cuda]
    cls_loss = ohem_cls_loss.sum() / keep_num
    return cls_loss

class FocalCosineLoss(nn.Module):
    def __init__(self, alpha=1, gamma=2, xent=.1):
        super(FocalCosineLoss, self).__init__()
        self.alpha = alpha
        self.gamma = gamma

        self.xent = xent

        self.y = torch.Tensor([1]).cuda()

    def forward(self, input, target, reduction="mean"):
        cosine_loss = F.cosine_embedding_loss(input, F.one_hot(target, num_classes=input.size(-1)), self.y, reduction=reduction)

        cent_loss = F.cross_entropy(F.normalize(input), target, reduce=False)
        pt = torch.exp(-cent_loss)
        focal_loss = self.alpha * (1-pt)**self.gamma * cent_loss

        if reduction == "mean":
            focal_loss = torch.mean(focal_loss)

        return cosine_loss + self.xent * focal_loss

class FocalLoss(nn.Module):
    def __init__(self, gamma=0, alpha=None, size_average=True):
        super(FocalLoss, self).__init__()
        self.gamma = gamma
        self.alpha = alpha
        if isinstance(alpha,(float,int,long)): self.alpha = torch.Tensor([alpha,1-alpha])
        if isinstance(alpha,list): self.alpha = torch.Tensor(alpha)
        self.size_average = size_average

    def forward(self, input, target):
        if input.dim()>2:
            input = input.view(input.size(0),input.size(1),-1)  # N,C,H,W => N,C,H*W
            input = input.transpose(1,2)    # N,C,H*W => N,H*W,C
            input = input.contiguous().view(-1,input.size(2))   # N,H*W,C => N*H*W,C
        target = target.view(-1,1)

        logpt = F.log_softmax(input)
        logpt = logpt.gather(1,target)
        logpt = logpt.view(-1)
        pt = Variable(logpt.data.exp())

        if self.alpha is not None:
            if self.alpha.type()!=input.data.type():
                self.alpha = self.alpha.type_as(input.data)
            at = self.alpha.gather(0,target.data.view(-1))
            logpt = logpt * Variable(at)

        loss = -1 * (1-pt)**self.gamma * logpt
        if self.size_average: return loss.mean()
        else: return loss.sum()