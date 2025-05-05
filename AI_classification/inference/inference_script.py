import torch
import torch.nn as nn
from torchvision import transforms, models
from PIL import Image
import argparse


def load_checkpoint(checkpoint_path: str, device: torch.device):
    """
    Load a checkpoint dict containing:
      - 'state_dict': model weights
      - 'class_names': list of class labels
    """
    checkpoint = torch.load(checkpoint_path, map_location=device)
    class_names = checkpoint["class_names"]
    state_dict = checkpoint["model_state_dict"]
    return state_dict, class_names


def build_model(num_classes: int, state_dict: dict, device: torch.device) -> nn.Module:
    """
    Initialize Swin V2 model, replace head, load weights, and return in eval mode.
    """
    model = models.swin_v2_b(weights=None)
    in_features = model.head.in_features
    model.head = nn.Linear(in_features, num_classes)
    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()
    return model


def preprocess_image(image_path: str) -> torch.Tensor:
    """
    Load an image and apply training transforms.
    Returns a tensor batch (1, C, H, W).
    """
    transform = transforms.Compose(
        [
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )
    img = Image.open(image_path).convert("RGB")
    return transform(img).unsqueeze(0)


def predict(
    model: nn.Module,
    image_tensor: torch.Tensor,
    class_names: list,
    device: torch.device,
    topk: int = 1,
):
    """
    Return top-k predictions for the input image tensor.
    """
    image_tensor = image_tensor.to(device)
    with torch.no_grad():
        outputs = model(image_tensor)
        probs = torch.softmax(outputs, dim=1)[0]
        top_probs, top_idxs = probs.topk(topk)
    predictions = [
        (class_names[idx], prob.item()) for idx, prob in zip(top_idxs, top_probs)
    ]
    return predictions


def main():
    parser = argparse.ArgumentParser(
        description="Single-image inference using a saved checkpoint with class names"
    )
    parser.add_argument(
        "--image-path", type=str, required=True, help="Path to the image file"
    )
    parser.add_argument(
        "--checkpoint",
        type=str,
        required=True,
        help="Path to the .pth checkpoint saved during training",
    )
    parser.add_argument(
        "--device", type=str, default=None, help='"cpu" or "cuda" (auto if omitted)'
    )
    parser.add_argument(
        "--top-k", type=int, default=1, help="Number of top predictions to display"
    )
    args = parser.parse_args()

    # Device selection
    if args.device:
        device = torch.device(args.device)
    else:
        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    # Load checkpoint and model
    state_dict, class_names = load_checkpoint(args.checkpoint, device)
    model = build_model(len(class_names), state_dict, device)

    # Preprocess and predict
    img_t = preprocess_image(args.image_path)
    preds = predict(model, img_t, class_names, device, topk=args.top_k)

    # Display results
    for cls, prob in preds:
        print(f"{cls}: {prob * 100:.2f}%")
        
    top_pred = preds[0]
    return top_pred[0]


if __name__ == "__main__":
    main()
