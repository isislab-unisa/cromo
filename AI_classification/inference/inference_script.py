import os
import cv2
import torch
import torchvision.models as models
import torchvision.transforms as transforms
from PIL import Image
import numpy as np
import torch.nn.functional as F
import argparse

# --- Configurazione e Iperparametri ---
SIMILARITY_THRESHOLD = 0.65
INLIER_THRESHOLD = 10
K_CANDIDATES = 3  # Numero di candidati da verificare geometricamente

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


def verify_match_geometric(query_path, candidate_item):
    """Utilizza ORB e RANSAC per verificare se due immagini corrispondono geometricamente."""
    try:
        img1 = cv2.imread(query_path, cv2.IMREAD_GRAYSCALE)
        if img1 is None or candidate_item["descriptors"] is None:
            return False, 0

        # Ricostruisce i keypoints dal formato serializzato
        kp2 = [
            cv2.KeyPoint(
                x=p[0][0],
                y=p[0][1],
                size=p[1],
                angle=p[2],
                response=p[3],
                octave=p[4],
                class_id=p[5],
            )
            for p in candidate_item["keypoints"]
        ]
        des2 = candidate_item["descriptors"]

        orb = cv2.ORB_create(nfeatures=5000)
        kp1, des1 = orb.detectAndCompute(img1, None)

        if des1 is None or len(des1) < 2 or len(des2) < 2:
            return False, 0

        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = bf.match(des1, des2)
        matches = sorted(matches, key=lambda x: x.distance)
        good_matches = matches

        if len(good_matches) > INLIER_THRESHOLD:
            src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(
                -1, 1, 2
            )
            dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(
                -1, 1, 2
            )

            M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
            if M is None:
                return False, 0

            inlier_count = np.sum(mask)
            return inlier_count >= INLIER_THRESHOLD, inlier_count
        else:
            return False, len(good_matches)
    except Exception as e:
        print(f"Errore durante la verifica geometrica: {e}")
        return False, 0


def find_best_candidate_class(query_embedding, index):
    """Trova la classe del waypoint con la migliore corrispondenza media."""
    best_match_score = -1.0
    best_match_info = None

    for item in index:
        similarity = F.cosine_similarity(
            query_embedding, item["embedding"].to(device), dim=0
        )
        if similarity > best_match_score:
            best_match_score = similarity
            best_match_info = item

    return best_match_info, best_match_score.item()


def main():
    parser = argparse.ArgumentParser(description="Classifica un'immagine di query.")
    parser.add_argument(
        "--image-path", required=True, help="Percorso dell'immagine di query."
    )
    parser.add_argument(
        "--checkpoint",
        required=True,
        help="Percorso del file di cache (l'indice) da caricare.",
    )
    args = parser.parse_args()

    if not os.path.exists(args.checkpoint):
        print(
            f"File di cache non trovato: {args.checkpoint}. Esegui prima create_embedding_db.py.", flush=True
        )
        exit(1)

    # --- Setup ---
    extractor = get_embedding_extractor().to(device)
    transform = get_image_transform()
    waypoint_index = torch.load(args.checkpoint, weights_only=False)

    print(f"\n📸 Inizio query con: {os.path.basename(args.image_path)}")

    # --- Fase 1: Recupero tramite Deep Learning ---
    query_embedding = extract_embedding(args.image_path, extractor, transform)
    if query_embedding is None:
        print("   [Fase 1] Immagine di query non riconosciuta.", flush=True)
        exit(1)

    candidate, score = find_best_candidate_class(query_embedding, waypoint_index)
    print(
        f"   [Fase 1] Miglior candidato: classe '{candidate['waypoint_name']}' (Similarità: {score:.4f})", flush=True
    )

    if score < SIMILARITY_THRESHOLD:
        print(
            f"   [RISULTATO] RIFIUTATO ❌ (Motivo: Bassa similarità, sotto la soglia di {SIMILARITY_THRESHOLD})", flush=True
        )
        return None

    # --- Fase 2: Verifica Geometrica Robusta ---
    candidate_waypoint_name = candidate["waypoint_name"]
    # print(
    #     f"   [Fase 2] Verifica geometrica sui migliori {K_CANDIDATES} candidati della classe '{candidate_waypoint_name}'..."
    # )

    all_images_in_class = [
        item
        for item in waypoint_index
        if item["waypoint_name"] == candidate_waypoint_name
    ]
    all_images_in_class.sort(
        key=lambda x: F.cosine_similarity(
            query_embedding, x["embedding"].to(device), dim=0
        ),
        reverse=True,
    )
    top_k_to_verify = all_images_in_class[:K_CANDIDATES]

    overall_match_found = False
    max_inliers = 0
    for item_to_verify in top_k_to_verify:
        is_match, inliers = verify_match_geometric(args.image_path, item_to_verify)
        if inliers > max_inliers:
            max_inliers = inliers
        if is_match:
            overall_match_found = True
            break

    # --- Decisione Finale ---
    if overall_match_found:
        print(
            f"   [RISULTATO] CORRISPONDENZA TROVATA: {candidate_waypoint_name} ✅ (Max Inliers: {max_inliers})"
        )
        print(f"Recognized waypoint: {candidate_waypoint_name}")
        return candidate_waypoint_name
    else:
        print(
            f"   [RISULTATO] RIFIUTATO ❌ (Motivo: Verifica geometrica fallita. Max Inliers: {max_inliers}, Necessari: {INLIER_THRESHOLD})"
        )
        print("No matching waypoint found.")
        return None


if __name__ == "__main__":
    main()