import torch
import torchvision
from torchvision import models

def main():
    torch.cuda.set_device(0)
    model = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
    model.eval()
    model.cuda()
    input_shape = (1, 3, 224, 224)
    x = torch.randn(input_shape)
    x = x.cuda()
    with torch.no_grad():
        y = model(x)
    print(y.shape)

if __name__ == "__main__":
    main()
