from sklearn.metrics import f1_score, accuracy_score
import torch
import torch.nn as nn
import torch
from dataset import get_dataset
from model import MultiLabelImageClassifier
import os
from torch.utils.data import DataLoader
from utils import *

@torch.no_grad()
def evaluate_model_val(model, dataloader, device):
    model.eval()
    criterion = nn.CrossEntropyLoss()

    total_loss = 0
    all_preds_action, all_labels_action = [], []
    all_preds_emotion, all_labels_emotion = [], []
    all_preds_situation, all_labels_situation = [], []

    for images, y_action, y_emotion, y_situation in dataloader:
        images = images.to(device)
        y_action = y_action.to(device)
        y_emotion = y_emotion.to(device)
        y_situation = y_situation.to(device)

        a_logits, e_logits, s_logits = model(images)

        loss_a = criterion(a_logits, y_action)
        loss_e = criterion(e_logits, y_emotion)
        loss_s = criterion(s_logits, y_situation)
        loss = loss_a + loss_e + loss_s
        total_loss += loss.item()

        # 예측값 및 정답 저장
        all_preds_action.extend(torch.argmax(a_logits, dim=1).cpu().numpy())
        all_preds_emotion.extend(torch.argmax(e_logits, dim=1).cpu().numpy())
        all_preds_situation.extend(torch.argmax(s_logits, dim=1).cpu().numpy())

        all_labels_action.extend(y_action.cpu().numpy())
        all_labels_emotion.extend(y_emotion.cpu().numpy())
        all_labels_situation.extend(y_situation.cpu().numpy())

    # F1 계산
    macro_f1 = f1_score(
        all_labels_action + all_labels_emotion + all_labels_situation,
        all_preds_action + all_preds_emotion + all_preds_situation,
        average='macro'
    )
    micro_f1 = f1_score(
        all_labels_action + all_labels_emotion + all_labels_situation,
        all_preds_action + all_preds_emotion + all_preds_situation,
        average='micro'
    )

    # Partial Match Score: 각 항목이 맞으면 1/3씩 점수 부여
    partial_correct = sum([
        (p1 == l1) + (p2 == l2) + (p3 == l3)
        for p1, l1, p2, l2, p3, l3 in zip(
            all_preds_action, all_labels_action,
            all_preds_emotion, all_labels_emotion,
            all_preds_situation, all_labels_situation
        )
    ])
    partial_score = partial_correct / (len(all_labels_action) * 3)

    # Exact Match: 3개 다 맞는 경우만 1점
    exact_match_acc = sum([
        (p1 == l1 and p2 == l2 and p3 == l3)
        for p1, l1, p2, l2, p3, l3 in zip(
            all_preds_action, all_labels_action,
            all_preds_emotion, all_labels_emotion,
            all_preds_situation, all_labels_situation
        )
    ]) / len(all_labels_action)

    # Label-wise Accuracy
    label_wise_acc = {
        'action': accuracy_score(all_labels_action, all_preds_action),
        'emotion': accuracy_score(all_labels_emotion, all_preds_emotion),
        'situation': accuracy_score(all_labels_situation, all_preds_situation),
    }

    avg_loss = total_loss / len(dataloader)

    return avg_loss, macro_f1, micro_f1, partial_score, exact_match_acc, label_wise_acc

@torch.no_grad()
def evaluate_model(config, split='test'):
    device = config['device']
    config['label_maps'] = get_label_maps_from_config(config)
    batch_size = config['batch_size']

    # 데이터셋 로딩
    dataset = get_dataset(config, split=split)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=4, pin_memory=True)
    
    # 모델 초기화 및 불러오기
    model_wrapper = MultiLabelImageClassifier(
        num_actions=len(config['label_maps']['action']),
        num_emotions=len(config['label_maps']['emotion']),
        num_situations=len(config['label_maps']['situation']),
        backbone_name=config['model_name'],
        pretrained=False  # 평가 시엔 fine-tuned 가중치를 로딩하므로 pretrained=False
    )
    model = model_wrapper.get_model()

    # 저장된 best 모델 불러오기
    model_path = os.path.join(config['save_path'], config['model_name'], config['best_model_path']) 
    assert os.path.exists(model_path), f"모델 경로 {model_path}가 존재하지 않습니다."

    model.load_state_dict(torch.load(model_path, map_location=device), strict=True)                    #  strict=False이거 좀 위험할 것 같음
    model.to(device)

    val_loss, macro_f1, micro_f1, partial_score, exact_match_acc, label_wise = evaluate_model_val(model, loader, device)

    print(f"\n✅🔍 Evaluation ({split.upper()} Set):")
    print(f"Loss: {val_loss:.4f}")
    print(f"Macro F1: {macro_f1:.4f}")
    print(f"Micro F1: {micro_f1:.4f}")
    print(f"Partial Match Score: {partial_score:.4f}")
    print(f"Exact Match Accuracy: {exact_match_acc:.4f}")
    print(f"Label-wise Accuracy:\n  - Action: {label_wise['action']:.4f}  | Emotion: {label_wise['emotion']:.4f}  | Situation: {label_wise['situation']:.4f}")