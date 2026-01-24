import torch
from torch.utils.data import Dataset
import numpy as np

class ModelDataset(Dataset):
    """
    Custom dataset class for the model.
    Wraps data from data_loader.py and prepares it for the model.
    """

    def __init__(self, X, y):
        self.X = torch.FloatTensor(X)
        self.y = torch.FloatTensor(y)

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]


