import os
import torch
import torchvision.models as models
import torchvision.transforms as transforms
from PIL import Image
import cv2
import numpy as np
from tqdm import tqdm
import argparse

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def get_embedding_extractor():
    """Carica un modello ResNet pre-addestrato per l'estrazione di feature."""
    model = models.resnet50(weights=models.ResNet50_Weights.DEFAULT)
    feature_extractor = torch.nn.Sequential(*list(model.children())[:-1])
    feature_extractor.eval()
    return feature_extractor


def get_image_transform():
    """Restituisce la pipeline di trasformazione standard per i modelli ImageNet."""
    return transforms.Compose(
        [
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ]
    )


def extract_embedding(image_path, model, transform):
    """Elabora una singola immagine ed estrae il suo embedding."""
    try:
        image = Image.open(image_path).convert("RGB")
        image_t = transform(image).unsqueeze(0).to(device)
        with torch.no_grad():
            embedding = model(image_t)
            embedding = embedding.flatten()
        return embedding
    except Exception as e:
        print(f"Errore durante l'elaborazione di {image_path}: {e}")
        return None


def compute_orb_features(image_path):
    """Calcola le feature ORB (keypoints e descrittori) per una singola immagine."""
    try:
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None, None
        orb = cv2.ORB_create(nfeatures=5000)
        kp, des = orb.detectAndCompute(img, None)
        return kp, des
    except Exception as e:
        print(f"Errore durante il calcolo delle feature ORB per {image_path}: {e}")
        return None, None


def index_waypoints(waypoints_dir, model, transform, cache_path):
    """
    Scorre tutte le immagini dei waypoint, estrae i loro embedding e le feature geometriche,
    e li memorizza in un indice.
    """
    print("Indicizzazione delle immagini dei waypoint...")
    index = []
    waypoint_folders = [
        d
        for d in os.listdir(waypoints_dir)
        if os.path.isdir(os.path.join(waypoints_dir, d))
    ]

    for waypoint_name in tqdm(waypoint_folders, desc="Waypoints"):
        folder_path = os.path.join(waypoints_dir, waypoint_name)
        for image_name in os.listdir(folder_path):
            if image_name.lower().endswith((".png", ".jpg", ".jpeg")):
                image_path = os.path.join(folder_path, image_name)
                embedding = extract_embedding(image_path, model, transform)
                kp, des = compute_orb_features(image_path)

                if embedding is not None and des is not None:
                    # Converte i keypoints in un formato serializzabile
                    kp_serializable = [
                        (p.pt, p.size, p.angle, p.response, p.octave, p.class_id)
                        for p in kp
                    ]
                    index.append(
                        {
                            "waypoint_name": waypoint_name,
                            "image_path": image_path,
                            "embedding": embedding.cpu(),
                            "keypoints": kp_serializable,
                            "descriptors": des,
                        }
                    )
    print(f"Indicizzazione completata. Trovate {len(index)} immagini.")
    # Salva l'indice su disco
    torch.save(index, cache_path)
    print(f"Indice salvato in: {cache_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Estrae embedding e feature geometriche dalle immagini di training."
    )
    parser.add_argument(
        "--input-dir", required=True, help="Percorso della cartella di training."
    )
    parser.add_argument(
        "--output-dir",
        default="waypoints_cache.pt",
        help="Percorso per salvare il file di cache (l'indice).",
    )
    args = parser.parse_args()

    extractor = get_embedding_extractor().to(device)
    transform = get_image_transform()

    train_dir = args.input_dir + "/train"
    output_dir = args.output_dir + "/model.pt"

    index_waypoints(train_dir, extractor, transform, output_dir)